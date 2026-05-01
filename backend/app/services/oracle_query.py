"""
Oracle データベースクエリサービスモジュール。
LLM が生成した SQL を検証・実行し、安全に結果を返す。

接続プールはアプリケーション起動時に init_oracle_pool() で初期化し、
終了時に close_oracle_pool() で解放する。

セキュリティ運用ガイド:
  - 本番環境の Oracle 接続ユーザーは GRANT SELECT ANY TABLE と CREATE SESSION
    のみを保有する読み取り専用ロールに限定すること。
  - DML/DDL/PL-SQL 実行権限 (CREATE/ALTER/DROP/INSERT/UPDATE/DELETE/EXECUTE
    ANY PROCEDURE 等) は付与しない。
  - DBMS_*/UTL_* 等の特権パッケージへの EXECUTE 権限を付与しない。
  - 万一 LLM が悪意ある SQL を生成した場合でも、本モジュールの validate_sql()
    で構文チェック、かつ DB 側の権限制限で多層防御を実現する。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import sqlparse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.bedrock_client import generate_text
from app.infrastructure.config import config
from app.models.database import OracleQueryTemplate
from app.services.text_normalizer import normalize_query

logger = logging.getLogger(__name__)

# モジュールレベルの接続プール（遅延初期化）
_oracle_pool: Any | None = None

# ---------------------------------------------------------------------------
# カスタム例外
# ---------------------------------------------------------------------------


class OracleUnavailableError(Exception):
    """Oracle DB に接続できない場合に送出される例外。"""


class OracleQueryValidationError(Exception):
    """SQL バリデーション失敗時に送出される例外。"""


# ---------------------------------------------------------------------------
# 結果データクラス
# ---------------------------------------------------------------------------


@dataclass
class OracleQueryResult:
    """Oracle クエリ実行結果を表すデータクラス。"""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    sql_executed: str = ""


# ---------------------------------------------------------------------------
# スキーマ定義とシステムプロンプト
# ---------------------------------------------------------------------------

_SCHEMA_DEFINITION = """
## 利用可能なテーブル

### HF1R6M01 — 生産トレーサビリティ（製造実績）
| カラム        | 型      | 説明                                     |
|---------------|---------|------------------------------------------|
| MK_DATE       | VARCHAR | 製造日時 (YYYYMMDDHHmmss)               |
| STA_NO1       | VARCHAR | ステーション番号1                         |
| STA_NO2       | VARCHAR | ステーション番号2                         |
| STA_NO3       | VARCHAR | ステーション番号3                         |
| M_SERIAL      | VARCHAR | 製品シリアル番号                          |
| INSP_ITEMNAME | VARCHAR | 検査項目名                               |
| MEASURE       | NUMBER  | 計測値                                   |

### HF1REM01 — 品質検査結果
| カラム         | 型      | 説明                                               |
|----------------|---------|-----------------------------------------------------|
| MK_DATE        | VARCHAR | 検査日時 (YYYYMMDDHHmmss)                          |
| STA_NO1        | VARCHAR | ステーション番号1                                   |
| STA_NO2        | VARCHAR | ステーション番号2                                   |
| STA_NO3        | VARCHAR | ステーション番号3                                   |
| OPEFIN_RESULT  | NUMBER  | 検査結果 (1=良品, 2=不良品)                        |
| NG_CODE        | VARCHAR | 不良コード（OPEFIN_RESULT=2 でも NULL の場合あり） |
| EXCEPT_FLAG    | NUMBER  | 除外フラグ (0=通常, 1=除外対象)                   |
| PARTS_NO       | VARCHAR | 部品番号                                           |

### HF1SGM01 — トラブルマスタ
| カラム          | 型      | 説明             |
|-----------------|---------|------------------|
| CODE_NO         | VARCHAR | トラブルコード   |
| TROUBLE_NG_INFO | VARCHAR | トラブル内容説明 |

### HF1RFM01 — トラブル実績データ
| カラム             | 型      | 説明                                                      |
|--------------------|---------|-----------------------------------------------------------|
| MK_DATE            | VARCHAR | 発生日時 (YYYYMMDDHHmmss)                                |
| STA_NO1            | VARCHAR | ステーション番号1                                         |
| STA_NO2            | VARCHAR | ステーション番号2                                         |
| STA_NO3            | VARCHAR | ステーション番号3                                         |
| CODE_NO            | VARCHAR | トラブルコード (HF1SGM01.CODE_NO と結合可)               |
| T4_UPDATE_CHECK    | NUMBER  | 更新区分 (4=アラーム, 5=停止)                            |
| EXCEPT_FLAG        | NUMBER  | 除外フラグ (0=通常, 1=除外対象)                          |

### HF1SKM01 — 部品マスタ
| カラム     | 型      | 説明     |
|------------|---------|----------|
| PARTS_NO   | VARCHAR | 部品番号 |
| PARTS_NAME | VARCHAR | 部品名   |
"""

_BUSINESS_RULES = """
## ビジネスルール（必ず厳守すること）

1. **EXCEPT_FLAG フィルタ**
   - HF1REM01 または HF1RFM01 を参照する SELECT 文・サブクエリすべてに
     `EXCEPT_FLAG IN (0, 1)` を必ず付加すること。
   - サブクエリ・CTE 内も例外なく適用する。

2. **不良コードの NULL 対応**
   - NG_CODE は OPEFIN_RESULT=2 でも NULL になる場合がある。
   - HF1SGM01 との結合は常に `LEFT JOIN` を使用すること。
   - 不良内容表示には `NVL(s.TROUBLE_NG_INFO, '未分類')` を使用すること。

3. **トラブル件数**
   - トラブル件数の集計には `T4_UPDATE_CHECK = 4`（アラーム）のレコードのみを使用する。

4. **トラブル継続時間**
   - HF1RFM01 の T4_UPDATE_CHECK=4 の MK_DATE から、
     同一 STA_NO1/STA_NO2/STA_NO3 の次の HF1REM01.MK_DATE を差し引いて算出する。
   - MK_DATE は VARCHAR (YYYYMMDDHHmmss) のため、
     `TO_DATE(MK_DATE, 'YYYYMMDDHH24MISS')` で変換してから差分計算する。

5. **不良率**
   - 計算式: `SUM(CASE WHEN OPEFIN_RESULT=2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)`
   - ゼロ除算を避けるため、COUNT(*) > 0 の条件を考慮すること。

6. **日時フォーマット**
   - MK_DATE は VARCHAR 型 (YYYYMMDDHHmmss) のため、
     日時比較には `TO_DATE()` 変換または文字列比較 (`LIKE '20240101%'`) を使用する。

7. **出力形式**
   - SQL 文のみを返すこと。説明文・コードブロック記法（```）は一切含めないこと。
   - セミコロン (;) は末尾に付けないこと。
"""

_SYSTEM_PROMPT_TEMPLATE = """\
あなたは Oracle Database SQL 生成の専門家です。
ユーザーの自然言語による質問を、以下のスキーマ定義とビジネスルールに厳密に従った \
Oracle SQL SELECT 文に変換してください。

{schema}

{rules}

## 参考クエリテンプレート（参考用、そのまま使用しないこと）

{templates}

上記のルールとスキーマを厳守した Oracle SQL を生成してください。
"""


# ---------------------------------------------------------------------------
# SQL 生成
# ---------------------------------------------------------------------------


async def _load_query_templates(db: AsyncSession) -> str:
    """
    DB から oracle_query_templates を取得し、プロンプト用文字列に変換する。

    Args:
        db: 非同期 SQLAlchemy セッション。

    Returns:
        テンプレート情報の整形済み文字列。テンプレートがない場合は空文字列。
    """
    result = await db.execute(select(OracleQueryTemplate))
    templates: list[OracleQueryTemplate] = list(result.scalars().all())

    if not templates:
        return "（テンプレートなし）"

    lines: list[str] = []
    for tmpl in templates:
        lines.append(f"### {tmpl.name}")
        lines.append(f"説明: {tmpl.description}")
        lines.append(f"SQL:\n{tmpl.sql_template}")
        try:
            params = json.loads(tmpl.parameters)
            if params:
                lines.append(f"パラメータ: {json.dumps(params, ensure_ascii=False)}")
        except (json.JSONDecodeError, TypeError):
            pass
        lines.append("")

    return "\n".join(lines)


def _extract_sql_from_response(response: str) -> str:
    """
    LLM レスポンスから SQL 文を抽出する。
    コードブロック（```sql ... ``` または ``` ... ```）を除去し、
    先頭・末尾の空白とセミコロンを取り除く。

    Args:
        response: LLM が生成したテキスト。

    Returns:
        クリーニングされた SQL 文字列。
    """
    # コードブロック記法を除去する
    cleaned = re.sub(r"```(?:sql)?\s*", "", response, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "")
    # 末尾のセミコロンと空白を除去する
    cleaned = cleaned.strip().rstrip(";").strip()
    return cleaned


async def generate_sql(
    natural_language_query: str,
    db: AsyncSession,
) -> str:
    """
    自然言語クエリから Oracle SQL を生成する。

    Bedrock Claude を使用して、スキーマ定義・ビジネスルール・DB 保存テンプレートを
    コンテキストとして渡し、SQL SELECT 文を生成させる。

    Args:
        natural_language_query: ユーザーの自然言語クエリ（NFKC 正規化済みを推奨）。
        db: 非同期 SQLAlchemy セッション（テンプレート取得に使用）。

    Returns:
        生成された Oracle SQL 文字列。
    """
    templates_text = await _load_query_templates(db)

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=_SCHEMA_DEFINITION,
        rules=_BUSINESS_RULES,
        templates=templates_text,
    )

    prompt = (
        f"以下の質問に対応する Oracle SQL SELECT 文を生成してください。\n\n"
        f"質問: {natural_language_query}"
    )

    logger.debug("SQL 生成開始: query=%r", natural_language_query)
    response = await generate_text(
        prompt=prompt,
        system_prompt=system_prompt,
        max_tokens=2048,
        temperature=0.0,
    )

    sql = _extract_sql_from_response(response)
    logger.debug("SQL 生成完了: sql=%r", sql[:200])
    return sql


# ---------------------------------------------------------------------------
# SQL バリデーション
# ---------------------------------------------------------------------------

# 許可するステートメントタイプ
_ALLOWED_STMT_TYPES = frozenset({"SELECT", "UNKNOWN"})

# 明示的に拒否するキーワード集合 (Oracle/PL-SQL 拡張対応)
_FORBIDDEN_KEYWORDS = {
    "UPDATE", "DELETE", "DROP", "INSERT", "ALTER", "CREATE",
    "TRUNCATE", "MERGE", "EXEC", "EXECUTE", "CALL",
    "BEGIN", "DECLARE", "GRANT", "REVOKE",
    "COMMIT", "ROLLBACK", "SAVEPOINT",
    "LOCK", "COMMENT", "ANALYZE", "FLASHBACK",
    "PRAGMA", "ATTACH", "DETACH",
}

# 禁止キーワードを単語境界で検出する正規表現
_FORBIDDEN_KEYWORDS_RE = re.compile(
    r"\b(" + "|".join(sorted(_FORBIDDEN_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Oracle 特権パッケージ呼び出しを拒否するパターン
_ORACLE_PRIVILEGED_PATTERNS = [
    (re.compile(r"\bDBMS_\w+", re.IGNORECASE), "DBMS_*"),
    (re.compile(r"\bUTL_\w+", re.IGNORECASE), "UTL_*"),
    (re.compile(r"\bSYS\.\w+", re.IGNORECASE), "SYS.*"),
]


def _strip_comments(sql: str) -> str:
    """
    sqlparse を使って SQL からコメントを除去する。

    Args:
        sql: 元 SQL。

    Returns:
        コメント除去済み SQL (失敗時は元 SQL)。
    """
    try:
        return sqlparse.format(sql, strip_comments=True)
    except Exception:  # noqa: BLE001
        return sql


# シングルクォート文字列リテラルを検出する正規表現。
# Oracle のエスケープされたクォート '' (例: 'O''Brien') にも対応。
# Oracle の識別子クォートは "..." (ダブルクォート) なので本パターンの影響外。
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _strip_string_literals(sql: str) -> str:
    """
    シングルクォート文字列リテラルを空文字列リテラル ('') に置換する。

    禁止キーワードや特権パッケージ名を文字列リテラル内で誤検知することを防ぐ
    （例: ``WHERE col = 'BEGIN_DATE'`` の 'BEGIN' が BEGIN ブロックとして
    誤検知されるのを回避）。

    Args:
        sql: 元 SQL（コメント除去済み推奨）。

    Returns:
        文字列リテラルを '' に潰した SQL。
    """
    return _STRING_LITERAL_RE.sub("''", sql)


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    生成された SQL の安全性を検証する。

    SELECT および WITH（CTE）ステートメントのみを許可する。
    UPDATE、DELETE、DROP、INSERT、ALTER、CREATE、TRUNCATE、MERGE、
    BEGIN/DECLARE (PL/SQL ブロック)、GRANT/REVOKE、COMMIT/ROLLBACK、
    LOCK/COMMENT/ANALYZE/FLASHBACK、DBMS_*/UTL_*/SYS.* 等は拒否する。

    実装方針:
      1. コメントを剥がす (コメント内に BEGIN を仕込む難読化対策)
      2. sqlparse でステートメント分解、複数文を厳格拒否
      3. 先頭トークンが SELECT または WITH のみ allowlist
      4. 文字列リテラル除去後の SQL に対して禁止キーワード正規表現検査
         (例: ``WHERE col = 'BEGIN_DATE'`` の誤検知を回避)
      5. 文字列リテラル除去後の SQL に対して Oracle 特権パッケージ
         (DBMS_*/UTL_*/SYS.*) を正規表現検査

    Args:
        sql: 検証対象の SQL 文字列。

    Returns:
        (is_valid, error_message) のタプル。
        is_valid が True の場合 error_message は空文字列。
    """
    if not sql or not sql.strip():
        logger.warning("SQL validation failed: empty SQL")
        return False, "SQL が空です。"

    # Step 1: コメントを剥がす (BEGIN/DBMS_ 等のコメント埋込み難読化対策)
    stripped_sql = _strip_comments(sql).strip()
    if not stripped_sql:
        logger.warning("SQL validation failed: empty after strip_comments")
        return False, "SQL が空です。"

    # Step 2: sqlparse でパースしてステートメント分解
    try:
        statements = sqlparse.parse(stripped_sql)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQL validation failed: parse error: %s | sql=%r", exc, sql[:200])
        return False, f"SQL のパースに失敗しました: {exc}"

    if not statements:
        logger.warning("SQL validation failed: no statements | sql=%r", sql[:200])
        return False, "有効な SQL ステートメントが見つかりません。"

    # 複数ステートメントを厳格拒否 (空白のみの末尾要素はスキップ)
    non_empty_statements = [s for s in statements if str(s).strip()]
    if len(non_empty_statements) > 1:
        logger.warning(
            "SQL validation failed: multiple statements (%d) | sql=%r",
            len(non_empty_statements),
            sql[:200],
        )
        return False, "複数の SQL ステートメントは許可されていません。"

    stmt = non_empty_statements[0]

    # Step 3: 先頭の意味ありトークンが SELECT/WITH であることを allowlist で確認
    first_keyword = None
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        ttype_str = str(token.ttype) if token.ttype else ""
        # コメントは strip 済みだが念のためスキップ
        if "Comment" in ttype_str:
            continue
        # 先頭の単語を取得
        first_keyword = token.normalized.upper().strip()
        break

    if first_keyword not in {"SELECT", "WITH"}:
        logger.warning(
            "SQL validation failed: first keyword=%r not SELECT/WITH | sql=%r",
            first_keyword,
            sql[:200],
        )
        return (
            False,
            f"SELECT または WITH（CTE）文のみ許可されています (先頭: {first_keyword})。",
        )

    # 文字列リテラルを除去した版を検査用に用意する。
    # 'BEGIN_DATE' のような正常な文字列リテラル内の単語が禁止キーワードとして
    # 誤検知されるのを防ぐ。識別子は "..." (ダブルクォート) を使うため影響なし。
    literals_stripped_sql = _strip_string_literals(stripped_sql)

    # Step 4: 禁止キーワードを正規表現で検査 (文字列リテラル除去後の SQL)
    forbidden_match = _FORBIDDEN_KEYWORDS_RE.search(literals_stripped_sql)
    if forbidden_match:
        keyword = forbidden_match.group(0).upper()
        logger.warning(
            "SQL validation failed: forbidden keyword=%s | sql=%r",
            keyword,
            sql[:200],
        )
        return False, f"禁止されたキーワードが含まれています: {keyword}"

    # Step 5: Oracle 特権パッケージ検出 (文字列リテラル除去後の SQL)
    for pattern, label in _ORACLE_PRIVILEGED_PATTERNS:
        if pattern.search(literals_stripped_sql):
            logger.warning(
                "SQL validation failed: privileged package %s | sql=%r",
                label,
                sql[:200],
            )
            return False, f"Oracle 特権パッケージは使用できません: {label}"

    # 追加: sqlparse の get_type が SELECT 以外を返す場合も拒否
    stmt_type = stmt.get_type()
    if stmt_type is not None and stmt_type not in _ALLOWED_STMT_TYPES:
        logger.warning(
            "SQL validation failed: stmt_type=%s | sql=%r", stmt_type, sql[:200]
        )
        return (
            False,
            f"SELECT または WITH（CTE）文のみ許可されています（取得型: {stmt_type}）。",
        )

    # 最終: トークンレベルで DML/DDL を確認 (sqlparse のトークン分類)
    flat_tokens = list(stmt.flatten())
    for token in flat_tokens:
        ttype_str = str(token.ttype)
        if "DML" in ttype_str or "DDL" in ttype_str:
            if token.normalized.upper() not in {"SELECT", "WITH"}:
                logger.warning(
                    "SQL validation failed: token DML/DDL=%s | sql=%r",
                    token.normalized.upper(),
                    sql[:200],
                )
                return (
                    False,
                    f"禁止された操作が含まれています: {token.normalized.upper()}",
                )

    return True, ""


# ---------------------------------------------------------------------------
# 接続プール管理
# ---------------------------------------------------------------------------


async def init_oracle_pool() -> None:
    """
    Oracle 接続プールを初期化する。アプリケーション起動時に呼び出す。

    config.ORACLE_ENABLED が False の場合は何もしない。
    接続に失敗した場合は OracleUnavailableError を送出する。

    Raises:
        OracleUnavailableError: Oracle に接続できない場合。
    """
    global _oracle_pool

    if not config.ORACLE_ENABLED:
        logger.info("ORACLE_ENABLED=False のため、Oracle 接続プールをスキップします。")
        return

    if _oracle_pool is not None:
        logger.debug("Oracle 接続プールは既に初期化済みです。")
        return

    try:
        import oracledb  # type: ignore[import-untyped]

        _oracle_pool = await oracledb.create_pool_async(
            user=config.ORACLE_USER,
            password=config.ORACLE_PASSWORD,
            dsn=config.ORACLE_DSN,
            min=config.ORACLE_POOL_MIN,
            max=config.ORACLE_POOL_MAX,
            increment=1,
        )
        logger.debug(
            "Oracle 接続プールを初期化しました (min=%d, max=%d)。",
            config.ORACLE_POOL_MIN,
            config.ORACLE_POOL_MAX,
        )
    except ImportError as exc:
        raise OracleUnavailableError(
            "oracledb パッケージがインストールされていません。"
        ) from exc
    except Exception as exc:
        raise OracleUnavailableError(
            f"Oracle 接続プールの初期化に失敗しました: {exc}"
        ) from exc


async def close_oracle_pool() -> None:
    """
    Oracle 接続プールを閉じる。アプリケーション終了時に呼び出す。

    プールが初期化されていない場合は何もしない。
    """
    global _oracle_pool

    if _oracle_pool is None:
        return

    try:
        await _oracle_pool.close()
        logger.info("Oracle 接続プールを閉じました。")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Oracle 接続プールのクローズ中にエラーが発生しました: %s", exc)
    finally:
        _oracle_pool = None


# ---------------------------------------------------------------------------
# クエリ実行
# ---------------------------------------------------------------------------


def _run_oracle_query_sync(
    pool: Any,
    sql: str,
    row_limit: int,
    timeout_seconds: int,
) -> OracleQueryResult:
    """
    Oracle クエリを同期的に実行する内部関数。
    asyncio.to_thread() から呼び出す想定。

    Args:
        pool: oracledb 接続プール（同期用）。
        sql: 実行する SELECT SQL 文字列。
        row_limit: 取得する最大行数。
        timeout_seconds: クエリタイムアウト秒数。

    Returns:
        OracleQueryResult オブジェクト。
    """

    with pool.acquire() as connection:
        # callTimeout はミリ秒単位で指定する
        connection.callTimeout = timeout_seconds * 1000

        with connection.cursor() as cursor:
            cursor.execute(sql)

            # カラム名を description から取得する
            columns: list[str] = (
                [col[0] for col in cursor.description] if cursor.description else []
            )

            # row_limit + 1 行取得して truncated 判定を行う
            raw_rows = cursor.fetchmany(row_limit + 1)

    truncated = len(raw_rows) > row_limit
    result_rows = raw_rows[:row_limit]

    # oracledb の行は tuple のため list に変換する
    serialized_rows: list[list[Any]] = []
    for row in result_rows:
        serialized_row: list[Any] = []
        for value in row:
            # LOB などのオブジェクトを文字列化する
            if hasattr(value, "read"):
                serialized_row.append(value.read())
            else:
                serialized_row.append(value)
        serialized_rows.append(serialized_row)

    return OracleQueryResult(
        columns=columns,
        rows=serialized_rows,
        row_count=len(serialized_rows),
        truncated=truncated,
    )


async def execute_query(
    sql: str,
    timeout: int | None = None,
) -> OracleQueryResult:
    """
    Oracle データベースに対して SQL クエリを実行する。
    設定された行数制限とタイムアウトを適用する。

    asyncio.to_thread() を使用してブロッキング操作をオフロードする。

    Args:
        sql: 実行する SQL 文字列（事前に validate_sql() で検証済みであること）。
        timeout: クエリタイムアウト秒数（None の場合は config.ORACLE_QUERY_TIMEOUT を使用）。

    Returns:
        OracleQueryResult オブジェクト。

    Raises:
        OracleUnavailableError: 接続プールが未初期化の場合。
        asyncio.TimeoutError: タイムアウトが発生した場合。
    """
    if _oracle_pool is None:
        raise OracleUnavailableError(
            "Oracle 接続プールが初期化されていません。init_oracle_pool() を呼び出してください。"
        )

    effective_timeout = timeout if timeout is not None else config.ORACLE_QUERY_TIMEOUT
    row_limit = config.ORACLE_ROW_LIMIT

    logger.debug(
        "Oracle クエリ実行開始 (timeout=%ds, row_limit=%d)",
        effective_timeout,
        row_limit,
    )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_oracle_query_sync,
                _oracle_pool,
                sql,
                row_limit,
                effective_timeout,
            ),
            timeout=effective_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Oracle クエリがタイムアウトしました (timeout=%ds)。", effective_timeout
        )
        raise

    if result.truncated:
        logger.debug(
            "クエリ結果が %d 行に切り詰められました。",
            row_limit,
        )

    logger.debug(
        "Oracle クエリ実行完了: row_count=%d, truncated=%s",
        result.row_count,
        result.truncated,
    )
    return result


# ---------------------------------------------------------------------------
# メインオーケストレーション
# ---------------------------------------------------------------------------


async def process_oracle_query(
    query: str,
    db: AsyncSession,
) -> OracleQueryResult:
    """
    自然言語クエリから Oracle SQL を生成・検証・実行する一連の処理を行う。

    処理ステップ:
      1. クエリを NFKC 正規化する
      2. Bedrock Claude で Oracle SQL を生成する
      3. 生成された SQL を検証する
      4. Oracle DB に対してクエリを実行する
      5. OracleQueryResult を返す

    Args:
        query: ユーザーの自然言語クエリ文字列。
        db: 非同期 SQLAlchemy セッション（テンプレート取得に使用）。

    Returns:
        OracleQueryResult オブジェクト。

    Raises:
        OracleUnavailableError: Oracle が利用不可能な場合。
        OracleQueryValidationError: 生成された SQL が安全でない場合。
        asyncio.TimeoutError: クエリ実行がタイムアウトした場合。
    """
    if not config.ORACLE_ENABLED:
        raise OracleUnavailableError(
            "Oracle 機能は無効化されています（ORACLE_ENABLED=False）。"
        )

    # Step 1: クエリを正規化する
    normalized_query = normalize_query(query)
    # 個人情報・機密情報がクエリに含まれる可能性があるため debug レベル
    logger.debug("Oracle クエリ処理開始: normalized_query=%r", normalized_query)
    logger.info("Oracle クエリ処理開始 (length=%d)", len(normalized_query))

    # Step 2: SQL を生成する
    sql = await generate_sql(natural_language_query=normalized_query, db=db)
    # 生 SQL ログは debug レベルへ (本番 INFO では出さない)
    logger.debug("生成された SQL: %r", sql[:500])

    # Step 3: SQL を検証する
    is_valid, error_message = validate_sql(sql)
    if not is_valid:
        logger.warning("SQL バリデーション失敗: %s | SQL: %r", error_message, sql[:200])
        raise OracleQueryValidationError(
            f"生成された SQL が安全性チェックを通過しませんでした: {error_message}\n\nSQL: {sql}"
        )

    # Step 4: クエリを実行する
    result = await execute_query(sql=sql)

    # 実行した SQL を結果に付加する
    result.sql_executed = sql

    return result
