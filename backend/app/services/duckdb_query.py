"""
DuckDB を使った CSV データクエリサービス。

フォルダソース（source_type="data"）内の CSV ファイルを DuckDB で読み込み、
SQL クエリを実行する。セキュリティ上、SELECT/WITH のみ許可し、
毎回 :memory: で起動するため永続化リスクはない。

CsvDataSession を使うと、同一セッション内で DuckDB 接続と UTF-8 変換済み
ファイルを再利用でき、大量ファイル時のパフォーマンスが大幅に向上する。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field

import duckdb
import sqlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class CsvColumnInfo:
    """CSV カラム情報。"""

    name: str
    dtype: str


@dataclass
class CsvTableInfo:
    """CSV テーブル情報（1 ファイル＝1 テーブル）。"""

    table_name: str
    file_path: str
    columns: list[CsvColumnInfo] = field(default_factory=list)
    row_count: int = 0
    sample_rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class QueryResult:
    """SQL クエリ実行結果。"""

    columns: list[str]
    rows: list[list[str]]
    row_count: int
    truncated: bool = False
    sql_executed: str = ""


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------

_MAX_RESULT_ROWS = 100
_MAX_RESULT_CHARS = 50_000
_SAMPLE_ROWS = 3

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|"
    r"GRANT|REVOKE|EXEC|EXECUTE|PREPARE|DEALLOCATE|CALL|COPY|EXPORT|IMPORT|"
    r"ATTACH|DETACH|LOAD|INSTALL|PRAGMA|SET|RESET|USE|CHECKPOINT|VACUUM)\b",
    re.IGNORECASE,
)

# DuckDB のファイル読み出し系テーブル関数（任意ファイル読み取りの防止）
_FORBIDDEN_TABLE_FUNCS = re.compile(
    r"\b(read_csv|read_csv_auto|sniff_csv|read_parquet|parquet_scan|read_json|"
    r"read_json_auto|read_json_objects|read_ndjson|read_ndjson_auto|read_text|"
    r"read_blob|read_xlsx|st_read|glob|iceberg_scan|delta_scan)\s*\(",
    re.IGNORECASE,
)

_ALLOWED_STARTERS = re.compile(
    r"^\s*(SELECT|WITH)\b",
    re.IGNORECASE,
)

_CSV_EXTENSIONS = {".csv", ".tsv"}

# エンコーディングフォールバック順序
_ENCODINGS = ["utf-8", "cp932", "shift_jis", "euc_jp"]

# DuckDB がネイティブ対応するエンコーディング
_DUCKDB_NATIVE_ENCODINGS = {"utf-8", "utf-16", "latin-1"}


# Parquet キャッシュ設定
_PARQUET_CACHE_DIR = "/app/data/parquet_cache"
_PARQUET_BATCH_SIZE = 50  # 1バッチあたりの最大 CSV 数
_MANIFEST_VERSION = 1


# ---------------------------------------------------------------------------
# Parquet キャッシュデータクラス
# ---------------------------------------------------------------------------


@dataclass
class ParquetBatchInfo:
    """Parquet バッチ情報。"""

    parquet_file: str
    csv_files: list[str]
    row_count: int


@dataclass
class ParquetCacheResult:
    """Parquet キャッシュの結果情報。"""

    cache_dir: str
    columns: list[CsvColumnInfo]
    total_rows: int
    parquet_files: list[str]
    hit: bool  # キャッシュヒットかどうか


# ---------------------------------------------------------------------------
# Parquet キャッシュ管理
# ---------------------------------------------------------------------------


def _read_manifest(cache_dir: str) -> dict[str, object] | None:
    """manifest.json を読み込む。破損時は None を返す。"""
    manifest_path = os.path.join(cache_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != _MANIFEST_VERSION:
            return None
        return data
    except (json.JSONDecodeError, KeyError, OSError):
        logger.warning("manifest.json 破損、キャッシュを再構築します: %s", cache_dir)
        return None


def _write_manifest(cache_dir: str, manifest: dict[str, object]) -> None:
    """manifest.json をアトミックに書き込む。"""
    manifest_path = os.path.join(cache_dir, "manifest.json")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, manifest_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _convert_csv_batch_to_parquet(
    csv_files: list[tuple[str, str]],
    parquet_path: str,
) -> tuple[list[CsvColumnInfo], int]:
    """CSV ファイル群を1つの Parquet ファイルに変換する。

    Args:
        csv_files: list of (abs_path, filename)
        parquet_path: 出力 Parquet ファイルパス

    Returns:
        (columns, row_count)
    """
    con = duckdb.connect(":memory:")
    tmp_files: list[str] = []
    columns: list[CsvColumnInfo] = []
    total_rows = 0

    try:
        union_parts: list[str] = []
        for abs_path, fname in csv_files:
            enc = _detect_encoding(abs_path)
            delimiter = "\t" if abs_path.lower().endswith(".tsv") else ","
            skip_rows = _detect_skip_rows(abs_path, enc)

            read_path = _ensure_utf8(abs_path, enc)
            if read_path != abs_path:
                tmp_files.append(read_path)
            read_enc = "utf-8" if read_path != abs_path else enc

            escaped_path = read_path.replace("\\", "\\\\").replace("'", "''")
            escaped_fname = fname.replace("'", "''")
            skip_clause = f", skip={skip_rows}" if skip_rows > 0 else ""

            select_sql = (
                f"SELECT *, '{escaped_fname}' AS _source_file "
                f"FROM read_csv('{escaped_path}', "
                f"header=true, auto_detect=true, delim='{delimiter}', "
                f"encoding='{read_enc}', ignore_errors=true{skip_clause})"
            )
            union_parts.append(select_sql)

        if not union_parts:
            return columns, 0

        union_sql = " UNION ALL ".join(union_parts)

        # カラム情報を取得（最初のファイルから）
        try:
            sample = con.execute(f"SELECT * FROM ({union_parts[0]}) LIMIT 0")
            columns = [
                CsvColumnInfo(name=desc[0], dtype=str(desc[1]))
                for desc in sample.description
            ]
        except Exception:
            pass

        # Parquet に書き出し
        escaped_parquet = parquet_path.replace("\\", "\\\\").replace("'", "''")
        con.execute(
            f"COPY ({union_sql}) TO '{escaped_parquet}' "
            f"(FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        # 行数カウント
        count_result = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{escaped_parquet}')"
        ).fetchone()
        total_rows = count_result[0] if count_result else 0

    finally:
        con.close()
        for tf in tmp_files:
            try:
                os.unlink(tf)
            except OSError:
                pass

    return columns, total_rows


def ensure_parquet_cache(source_id: str, container_path: str) -> ParquetCacheResult:
    """Parquet キャッシュを確認し、必要に応じて変換を実行する。

    初回は全 CSV → Parquet 変換。2回目以降は差分のみ変換。
    """
    cache_dir = os.path.join(_PARQUET_CACHE_DIR, source_id)
    os.makedirs(cache_dir, exist_ok=True)

    # 現在の CSV ファイル一覧
    csv_files = _find_csv_files(container_path)
    current_filenames = {os.path.basename(abs_path) for abs_path, _ in csv_files}
    filename_to_path = {
        os.path.basename(abs_path): abs_path for abs_path, _ in csv_files
    }

    # マニフェスト読み込み
    manifest = _read_manifest(cache_dir)
    if manifest is None:
        # 破損 or 初回 → 全削除して再構築
        for f in os.listdir(cache_dir):
            fpath = os.path.join(cache_dir, f)
            try:
                os.unlink(fpath)
            except OSError:
                pass
        manifest = {
            "version": _MANIFEST_VERSION,
            "source_id": source_id,
            "container_path": container_path,
            "columns": [],
            "total_rows": 0,
            "batches": [],
            "converted_files": [],
        }

    converted_set = set(manifest.get("converted_files", []))
    new_filenames = current_filenames - converted_set

    if not new_filenames:
        # キャッシュヒット
        parquet_files = [
            os.path.join(cache_dir, b["parquet_file"])
            for b in manifest.get("batches", [])
        ]
        columns = [
            CsvColumnInfo(name=c["name"], dtype=c["dtype"])
            for c in manifest.get("columns", [])
        ]
        return ParquetCacheResult(
            cache_dir=cache_dir,
            columns=columns,
            total_rows=manifest.get("total_rows", 0),
            parquet_files=parquet_files,
            hit=True,
        )

    # 新規 CSV をバッチ変換
    new_files_list = sorted(new_filenames)
    existing_batch_count = len(manifest.get("batches", []))
    batches = list(manifest.get("batches", []))
    all_columns: list[CsvColumnInfo] = []
    added_rows = 0

    for i in range(0, len(new_files_list), _PARQUET_BATCH_SIZE):
        batch_chunk = new_files_list[i : i + _PARQUET_BATCH_SIZE]
        batch_num = existing_batch_count + (i // _PARQUET_BATCH_SIZE) + 1
        parquet_filename = f"batch_{batch_num:03d}.parquet"
        parquet_path = os.path.join(cache_dir, parquet_filename)

        batch_csv_files = [
            (filename_to_path[fname], fname)
            for fname in batch_chunk
            if fname in filename_to_path
        ]

        try:
            columns, row_count = _convert_csv_batch_to_parquet(
                batch_csv_files, parquet_path
            )
            if not all_columns and columns:
                all_columns = columns
            added_rows += row_count

            batches.append(
                ParquetBatchInfo(
                    parquet_file=parquet_filename,
                    csv_files=batch_chunk,
                    row_count=row_count,
                )
            )
            converted_set.update(batch_chunk)
        except Exception as exc:
            logger.error("Parquet バッチ変換失敗 (batch_%03d): %s", batch_num, exc)
            # 書き途中のファイルを削除
            try:
                os.unlink(parquet_path)
            except OSError:
                pass
            # manifest 未更新で次回再試行
            break

    # columns 情報の更新（初回 or 既存が空の場合）
    if all_columns:
        manifest_columns = [{"name": c.name, "dtype": c.dtype} for c in all_columns]
    else:
        manifest_columns = manifest.get("columns", [])
        all_columns = [
            CsvColumnInfo(name=c["name"], dtype=c["dtype"]) for c in manifest_columns
        ]

    total_rows = manifest.get("total_rows", 0) + added_rows

    # マニフェスト更新
    manifest = {
        "version": _MANIFEST_VERSION,
        "source_id": source_id,
        "container_path": container_path,
        "columns": manifest_columns
        if all_columns
        else [{"name": c.name, "dtype": c.dtype} for c in all_columns],
        "total_rows": total_rows,
        "batches": [
            {
                "parquet_file": b.parquet_file,
                "csv_files": b.csv_files,
                "row_count": b.row_count,
            }
            if isinstance(b, ParquetBatchInfo)
            else b
            for b in batches
        ],
        "converted_files": sorted(converted_set),
    }
    _write_manifest(cache_dir, manifest)

    parquet_files = [
        os.path.join(
            cache_dir, b["parquet_file"] if isinstance(b, dict) else b.parquet_file
        )
        for b in batches
    ]

    return ParquetCacheResult(
        cache_dir=cache_dir,
        columns=all_columns,
        total_rows=total_rows,
        parquet_files=parquet_files,
        hit=False,
    )


def invalidate_parquet_cache(source_id: str) -> None:
    """Parquet キャッシュを削除する。"""
    cache_dir = os.path.join(_PARQUET_CACHE_DIR, source_id)
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
        logger.info("Parquet キャッシュ削除: %s", cache_dir)


# ---------------------------------------------------------------------------
# セキュリティ
# ---------------------------------------------------------------------------


def validate_sql(sql: str) -> str | None:
    """SQL が単一の SELECT/WITH クエリのみか検証する。

    SELECT/WITH 以外で始まるクエリ、データ変更・設定変更・ファイル読み出し系の
    キーワード/関数を含むクエリ、複数ステートメントを拒否する。

    Returns:
        None: 安全
        str: エラーメッセージ
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "SQL が空です。"

    if not _ALLOWED_STARTERS.match(stripped):
        return "SELECT または WITH で始まるクエリのみ実行できます。"

    if _FORBIDDEN_KEYWORDS.search(stripped):
        return (
            "禁止されたキーワードが含まれています。SELECT クエリのみ使用してください。"
        )

    if _FORBIDDEN_TABLE_FUNCS.search(stripped):
        return "ファイル読み出し系の関数（read_csv 等）は使用できません。"

    # 複数ステートメントを拒否する（; 区切りで 2 つ以上のクエリを送れないようにする）
    try:
        statements = [s for s in sqlparse.parse(stripped) if str(s).strip()]
    except Exception:
        return "SQL の解析に失敗しました。"
    if len(statements) > 1:
        return "複数の SQL ステートメントは実行できません。"

    return None


# ---------------------------------------------------------------------------
# CSV 検出・読み込み
# ---------------------------------------------------------------------------


def _detect_encoding(file_path: str) -> str:
    """ファイルのエンコーディングを自動検出する。"""
    for enc in _ENCODINGS:
        try:
            with open(file_path, encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def _detect_skip_rows(file_path: str, encoding: str) -> int:
    """CSV の先頭メタデータ行数を検出する。

    PLC ロギング CSV 等は先頭に `[SECTION]` マーカー行やデータ型定義行があり、
    実際のカラムヘッダーは数行下になる。この関数はスキップすべき行数を返す。
    """
    try:
        with open(file_path, encoding=encoding) as f:
            first_line = f.readline().strip()
    except Exception:
        return 0

    # 先頭が `[` で始まる場合はセクションマーカー行
    if first_line.startswith("["):
        # 行2 もメタデータ（データ型定義など）であることが多い
        # 行3 が実カラムヘッダーとなるので skip=2
        return 2
    return 0


def _ensure_utf8(file_path: str, encoding: str) -> str:
    """DuckDB 非対応エンコーディングの場合、UTF-8 一時ファイルに変換して返す。

    DuckDB 対応エンコーディングならそのままパスを返す。
    """
    if encoding in _DUCKDB_NATIVE_ENCODINGS:
        return file_path

    suffix = os.path.splitext(file_path)[1]
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        encoding="utf-8",
        delete=False,
    )
    try:
        with open(file_path, encoding=encoding) as src:
            for chunk in iter(lambda: src.read(65536), ""):
                tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise


def _sanitize_table_name(filename: str) -> str:
    """ファイル名からテーブル名を生成する。"""
    name = os.path.splitext(filename)[0]
    # 英数字・アンダースコア以外をアンダースコアに置換
    name = re.sub(r"[^a-zA-Z0-9_\u3000-\u9fff\uff00-\uffef]", "_", name)
    # 先頭が数字の場合は t_ を付与
    if name and name[0].isdigit():
        name = f"t_{name}"
    return name or "table"


def _find_csv_files(container_path: str) -> list[tuple[str, str]]:
    """フォルダ内の CSV/TSV ファイルを検出する。

    Returns:
        list of (absolute_path, table_name)
    """
    results: list[tuple[str, str]] = []
    if not os.path.isdir(container_path):
        return results

    seen_names: dict[str, int] = {}
    for root, _dirs, files in os.walk(container_path):
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _CSV_EXTENSIONS:
                continue
            abs_path = os.path.join(root, fname)
            table_name = _sanitize_table_name(fname)

            # 重複テーブル名の回避
            if table_name in seen_names:
                seen_names[table_name] += 1
                table_name = f"{table_name}_{seen_names[table_name]}"
            else:
                seen_names[table_name] = 0

            results.append((abs_path, table_name))
    return results


# ---------------------------------------------------------------------------
# メイン API
# ---------------------------------------------------------------------------


_MAX_DESCRIBE_TABLES = 20


def describe_csv_tables(
    container_path: str,
    max_tables: int = _MAX_DESCRIBE_TABLES,
) -> list[CsvTableInfo]:
    """フォルダ内の CSV をスキャンし、テーブル情報を返す。

    Args:
        container_path: フォルダパス。
        max_tables: 詳細取得するテーブル数の上限。
    """
    csv_files = _find_csv_files(container_path)
    if not csv_files:
        return []

    tables: list[CsvTableInfo] = []
    tmp_files: list[str] = []
    con = duckdb.connect(":memory:")
    try:
        for abs_path, table_name in csv_files[:max_tables]:
            try:
                info, tmp = _describe_single_csv(con, abs_path, table_name)
                tables.append(info)
                if tmp:
                    tmp_files.append(tmp)
            except Exception as exc:
                logger.warning("CSV 読み込み失敗 (%s): %s", abs_path, exc)
    finally:
        con.close()
        for tf in tmp_files:
            try:
                os.unlink(tf)
            except OSError:
                pass

    return tables


def _describe_single_csv(
    con: duckdb.DuckDBPyConnection, abs_path: str, table_name: str
) -> tuple[CsvTableInfo, str | None]:
    """1つの CSV をスキャンして CsvTableInfo を返す。

    Returns:
        (CsvTableInfo, 一時ファイルパス or None)
    """
    enc = _detect_encoding(abs_path)
    delimiter = "\t" if abs_path.lower().endswith(".tsv") else ","
    skip_rows = _detect_skip_rows(abs_path, enc)

    # DuckDB 非対応エンコーディングの場合は UTF-8 に変換
    read_path = _ensure_utf8(abs_path, enc)
    tmp_path = read_path if read_path != abs_path else None
    read_enc = "utf-8" if tmp_path else enc

    # VIEW 作成
    # パス内のバックスラッシュをエスケープ
    escaped_path = read_path.replace("\\", "\\\\").replace("'", "''")
    skip_clause = f", skip={skip_rows}" if skip_rows > 0 else ""
    con.execute(
        f'CREATE OR REPLACE VIEW "{table_name}" AS '
        f"SELECT * FROM read_csv('{escaped_path}', "
        f"header=true, auto_detect=true, delim='{delimiter}', "
        f"encoding='{read_enc}', ignore_errors=true{skip_clause})"
    )

    # カラム情報取得
    cols_result = con.execute(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table_name}'"
    ).fetchall()

    columns = [CsvColumnInfo(name=row[0], dtype=row[1]) for row in cols_result]

    # 行数
    row_count = con.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]

    # サンプル行
    sample_result = con.execute(f'SELECT * FROM "{table_name}" LIMIT {_SAMPLE_ROWS}')
    col_names = [desc[0] for desc in sample_result.description]
    sample_rows = [
        {col_names[i]: str(val) for i, val in enumerate(row)}
        for row in sample_result.fetchall()
    ]

    return CsvTableInfo(
        table_name=table_name,
        file_path=abs_path,
        columns=columns,
        row_count=row_count,
        sample_rows=sample_rows,
    ), tmp_path


def execute_csv_query(sql: str, container_path: str) -> QueryResult:
    """CSV を VIEW として登録し、SQL を実行して結果を返す。

    単発クエリ用。複数クエリを実行する場合は CsvDataSession を使うこと。
    """
    session = CsvDataSession(container_path)
    try:
        session.prepare()
        return session.execute(sql)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# セッションベースの DuckDB 接続管理
# ---------------------------------------------------------------------------


class CsvDataSession:
    """DuckDB 接続と UTF-8 変換ファイルをセッション内で再利用するクラス。

    source_id を指定すると Parquet キャッシュモードになり、初回のみ
    CSV→Parquet 変換を行い、以降はキャッシュを再利用する。
    全 CSV は統合テーブル ``data`` として1つで提供される。

    source_id 未指定の場合は従来の CSV VIEW 方式にフォールバックする。

    使い方:
        session = CsvDataSession(container_path, source_id="xxx")
        try:
            session.prepare()          # Parquet キャッシュ or CSV VIEW 登録
            tables = session.describe() # テーブル一覧
            result = session.execute(sql)  # SQL 実行
        finally:
            session.close()            # 接続クリーンアップ
    """

    def __init__(self, container_path: str, source_id: str = "") -> None:
        self.container_path = container_path
        self.source_id = source_id
        self._con: duckdb.DuckDBPyConnection | None = None
        self._tmp_files: list[str] = []
        self._prepared = False
        self._csv_files: list[tuple[str, str]] = []
        self._lock = threading.Lock()
        self._use_parquet = False
        self._cache_result: ParquetCacheResult | None = None

    @property
    def total_table_count(self) -> int:
        if self._use_parquet:
            return 1  # 統合テーブル "data" 1つ
        return len(self._csv_files)

    @property
    def csv_files(self) -> list[tuple[str, str]]:
        return self._csv_files

    def prepare(self) -> None:
        """CSV データを準備する。

        source_id あり → Parquet キャッシュ → 統合 VIEW "data" 登録。
        source_id なし → 従来の CSV VIEW 方式。
        2回目以降の呼び出しは何もしない。
        """
        with self._lock:
            if self._prepared:
                return

            if self.source_id:
                self._prepare_parquet()
            else:
                self._prepare_csv_views()
            self._prepared = True

    def _prepare_parquet(self) -> None:
        """Parquet キャッシュモードで準備する。"""
        self._csv_files = _find_csv_files(self.container_path)
        if not self._csv_files:
            return

        cache_result = ensure_parquet_cache(self.source_id, self.container_path)
        self._cache_result = cache_result

        if not cache_result.parquet_files:
            # キャッシュ変換失敗、CSV VIEW にフォールバック
            logger.warning("Parquet キャッシュ空、CSV VIEW にフォールバック")
            self._prepare_csv_views()
            return

        self._use_parquet = True
        self._con = duckdb.connect(":memory:")

        # 全 Parquet ファイルを統合 VIEW "data" として登録
        parquet_glob = os.path.join(cache_result.cache_dir, "*.parquet")
        escaped_glob = parquet_glob.replace("\\", "\\\\").replace("'", "''")
        self._con.execute(
            f'CREATE OR REPLACE VIEW "data" AS '
            f"SELECT * FROM read_parquet('{escaped_glob}')"
        )

    def _prepare_csv_views(self) -> None:
        """従来の CSV VIEW 方式で準備する（フォールバック）。"""
        self._csv_files = _find_csv_files(self.container_path)
        if not self._csv_files:
            return

        self._con = duckdb.connect(":memory:")
        for abs_path, table_name in self._csv_files:
            enc = _detect_encoding(abs_path)
            delimiter = "\t" if abs_path.lower().endswith(".tsv") else ","
            skip_rows = _detect_skip_rows(abs_path, enc)
            try:
                read_path = _ensure_utf8(abs_path, enc)
                if read_path != abs_path:
                    self._tmp_files.append(read_path)
                read_enc = "utf-8" if read_path != abs_path else enc
                escaped_path = read_path.replace("\\", "\\\\").replace("'", "''")
                skip_clause = f", skip={skip_rows}" if skip_rows > 0 else ""
                self._con.execute(
                    f'CREATE OR REPLACE VIEW "{table_name}" AS '
                    f"SELECT * FROM read_csv('{escaped_path}', "
                    f"header=true, auto_detect=true, delim='{delimiter}', "
                    f"encoding='{read_enc}', ignore_errors=true{skip_clause})"
                )
            except Exception as exc:
                logger.warning("CSV VIEW 作成失敗 (%s): %s", abs_path, exc)

    def describe(self, max_tables: int = _MAX_DESCRIBE_TABLES) -> list[CsvTableInfo]:
        """テーブル情報を返す（prepare 済みの接続を再利用）。"""
        if not self._prepared:
            self.prepare()
        if not self._con:
            return []

        if self._use_parquet:
            return self._describe_parquet()
        return self._describe_csv_views(max_tables)

    def _describe_parquet(self) -> list[CsvTableInfo]:
        """Parquet モードのテーブル情報（統合テーブル "data" 1つ）。"""
        cache = self._cache_result
        if not cache or not self._con:
            return []

        # サンプル行を取得
        try:
            sample_result = self._con.execute(
                f'SELECT * FROM "data" LIMIT {_SAMPLE_ROWS}'
            )
            col_names = [desc[0] for desc in sample_result.description]
            sample_rows = [
                {col_names[i]: str(val) for i, val in enumerate(row)}
                for row in sample_result.fetchall()
            ]

            # columns はキャッシュ結果から取得。ただし実際の DuckDB 型と合わせる
            columns = (
                [
                    CsvColumnInfo(name=name, dtype=str(desc[1]))
                    for name, desc in zip(col_names, sample_result.description)
                ]
                if sample_result.description
                else cache.columns
            )

        except Exception as exc:
            logger.warning("Parquet describe 失敗: %s", exc)
            columns = cache.columns
            sample_rows = []

        return [
            CsvTableInfo(
                table_name="data",
                file_path=cache.cache_dir,
                columns=columns,
                row_count=cache.total_rows,
                sample_rows=sample_rows,
            )
        ]

    def _describe_csv_views(self, max_tables: int) -> list[CsvTableInfo]:
        """従来の CSV VIEW 方式のテーブル情報。"""
        tables: list[CsvTableInfo] = []
        for abs_path, table_name in self._csv_files[:max_tables]:
            try:
                cols_result = self._con.execute(
                    f"SELECT column_name, data_type FROM information_schema.columns "
                    f"WHERE table_name = '{table_name}'"
                ).fetchall()
                columns = [
                    CsvColumnInfo(name=row[0], dtype=row[1]) for row in cols_result
                ]

                row_count = self._con.execute(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).fetchone()[0]

                sample_result = self._con.execute(
                    f'SELECT * FROM "{table_name}" LIMIT {_SAMPLE_ROWS}'
                )
                col_names = [desc[0] for desc in sample_result.description]
                sample_rows = [
                    {col_names[i]: str(val) for i, val in enumerate(row)}
                    for row in sample_result.fetchall()
                ]

                tables.append(
                    CsvTableInfo(
                        table_name=table_name,
                        file_path=abs_path,
                        columns=columns,
                        row_count=row_count,
                        sample_rows=sample_rows,
                    )
                )
            except Exception as exc:
                logger.warning("CSV describe 失敗 (%s): %s", abs_path, exc)
        return tables

    def execute(self, sql: str) -> QueryResult:
        """SQL クエリを実行して結果を返す（prepare 済みの接続を再利用）。"""
        if not self._prepared:
            self.prepare()
        if not self._con:
            return QueryResult(columns=[], rows=[], row_count=0, sql_executed=sql)

        result = self._con.execute(sql)
        col_names = [desc[0] for desc in result.description]
        all_rows = result.fetchmany(_MAX_RESULT_ROWS + 1)

        truncated = len(all_rows) > _MAX_RESULT_ROWS
        rows_to_return = all_rows[:_MAX_RESULT_ROWS]

        str_rows: list[list[str]] = []
        total_chars = 0
        char_truncated = False
        for row in rows_to_return:
            str_row = [str(v) for v in row]
            row_chars = sum(len(s) for s in str_row)
            if total_chars + row_chars > _MAX_RESULT_CHARS:
                char_truncated = True
                break
            str_rows.append(str_row)
            total_chars += row_chars

        return QueryResult(
            columns=col_names,
            rows=str_rows,
            row_count=len(str_rows),
            truncated=truncated or char_truncated,
            sql_executed=sql,
        )

    def close(self) -> None:
        """DuckDB 接続を閉じ、一時ファイルを削除する。

        Parquet キャッシュは永続なので削除しない。
        """
        with self._lock:
            if self._con:
                try:
                    self._con.close()
                except Exception:
                    pass
                self._con = None
            for tf in self._tmp_files:
                try:
                    os.unlink(tf)
                except OSError:
                    pass
            self._tmp_files.clear()
            self._prepared = False
