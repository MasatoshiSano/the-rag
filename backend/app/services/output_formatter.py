"""
出力データ整形サービスモジュール。
Oracle クエリ結果をフロントエンド表示用の構造化データに変換し、
チャートタイプをヒューリスティクスで推定する。
DB への保存も担う。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ChatOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 型エイリアス
# ---------------------------------------------------------------------------

ColumnDef = dict[str, str]  # {key, label, type}
TableData = dict[str, Any]  # {columns: [ColumnDef], rows: [list[Any]]}
ChartConfig = dict[str, Any]  # {type, x_key, y_keys, title}

# ---------------------------------------------------------------------------
# カラム型推定
# ---------------------------------------------------------------------------

# 日付・時刻カラム名のパターン（大文字・小文字不問）
_DATE_COLUMN_PATTERN = re.compile(
    r"(date|time|datetime|timestamp|mk_date|year|month|day|dt|tm)",
    re.IGNORECASE,
)

# 数値カラム名のパターン（大文字・小文字不問）
_NUMERIC_COLUMN_PATTERN = re.compile(
    r"(count|sum|avg|total|rate|ratio|amount|value|measure|num|qty|quantity|"
    r"件数|合計|平均|割合|数量|計測)",
    re.IGNORECASE,
)

# カテゴリカラム名のパターン（大文字・小文字不問）
_CATEGORY_COLUMN_PATTERN = re.compile(
    r"(code|name|type|category|class|status|flag|label|group|kind|"
    r"コード|名称|種別|分類|区分|ステータス)",
    re.IGNORECASE,
)


def _infer_column_type(column_name: str, sample_value: Any) -> str:
    """
    カラム名とサンプル値からカラムの表示型を推定する。

    Args:
        column_name: カラム名文字列。
        sample_value: 代表値（None の場合もある）。

    Returns:
        'date' | 'number' | 'category' | 'text' のいずれか。
    """
    col = column_name.upper()

    if _DATE_COLUMN_PATTERN.search(col):
        return "date"

    # サンプル値が数値型かチェックする
    if sample_value is not None and isinstance(sample_value, (int, float)):
        return "number"

    if _NUMERIC_COLUMN_PATTERN.search(col):
        return "number"

    if _CATEGORY_COLUMN_PATTERN.search(col):
        return "category"

    return "text"


# ---------------------------------------------------------------------------
# テーブルデータ整形
# ---------------------------------------------------------------------------


def format_table_data(
    columns: list[str],
    rows: list[list[Any]],
) -> TableData:
    """
    Oracle クエリ結果のカラムリストと行リストを構造化テーブルデータに変換する。

    各カラムに key（元カラム名）、label（表示用ラベル）、type（表示型）を付与する。
    行は dict 形式に変換する。

    Args:
        columns: カラム名の文字列リスト。
        rows: 行データのリスト（各行は値のリスト）。

    Returns:
        {
            "columns": [{"key": str, "label": str, "type": str}, ...],
            "rows": [{"column_key": value, ...}, ...],
        }
    """
    if not columns:
        return {"columns": [], "rows": []}

    # サンプル行（最初の行）からカラム型を推定する
    sample_row: list[Any] = rows[0] if rows else [None] * len(columns)

    column_defs: list[ColumnDef] = []
    for idx, col_name in enumerate(columns):
        sample_val = sample_row[idx] if idx < len(sample_row) else None
        col_type = _infer_column_type(col_name, sample_val)
        column_defs.append(
            {
                "key": col_name,
                "label": col_name,
                "type": col_type,
            }
        )

    # 各行を dict 形式に変換する
    dict_rows: list[dict[str, Any]] = []
    for row in rows:
        row_dict: dict[str, Any] = {}
        for idx, col_name in enumerate(columns):
            value = row[idx] if idx < len(row) else None
            # JSON シリアライズ可能な型に変換する
            if hasattr(value, "isoformat"):
                row_dict[col_name] = value.isoformat()
            elif value is not None:
                row_dict[col_name] = value
            else:
                row_dict[col_name] = None
        dict_rows.append(row_dict)

    logger.debug(
        "テーブルデータ整形完了: columns=%d, rows=%d",
        len(column_defs),
        len(dict_rows),
    )

    return {"columns": column_defs, "rows": dict_rows}


# ---------------------------------------------------------------------------
# チャート設定推定
# ---------------------------------------------------------------------------


def suggest_chart_config(
    table_data: TableData,
    query_text: str,
) -> ChartConfig | None:
    """
    テーブルデータの構造とクエリテキストからチャートタイプをヒューリスティクスで推定する。

    推定ルール（優先順位順）:
      1. 日付型カラムが存在する → 折れ線グラフ（line）
      2. カテゴリ型カラムが存在し数値カラムが複数 → 棒グラフ（bar）
      3. クエリに「割合」「比率」「比較」「構成」「内訳」を含む → 円グラフ（pie）
      4. カテゴリ型カラムが存在し数値カラムが1つ → 棒グラフ（bar）
      5. それ以外 → None（テーブル表示のみ）

    Args:
        table_data: format_table_data の返り値。
        query_text: ユーザーのクエリ文字列（ヒューリスティクス判定に使用）。

    Returns:
        チャート設定 dict または None（チャートなし）。
        チャート設定は {type, x_key, y_keys, title} を含む。
    """
    col_defs: list[ColumnDef] = table_data.get("columns", [])
    rows: list[dict] = table_data.get("rows", [])

    if not col_defs or not rows:
        return None

    date_cols = [c for c in col_defs if c["type"] == "date"]
    numeric_cols = [c for c in col_defs if c["type"] == "number"]
    category_cols = [c for c in col_defs if c["type"] == "category"]

    # 数値カラムが存在しない場合はチャート生成不可
    if not numeric_cols:
        return None

    # ルール 1: 日付カラムが存在する → 折れ線グラフ
    if date_cols:
        x_key = date_cols[0]["key"]
        y_keys = [c["key"] for c in numeric_cols[:3]]  # 最大3系列
        return {
            "type": "line",
            "x_key": x_key,
            "y_keys": y_keys,
            "title": _extract_chart_title(query_text),
        }

    # ルール 3: クエリが割合・比率に関係する → 円グラフ（数値が1つ、カテゴリが1つ）
    proportion_keywords = re.compile(
        r"(割合|比率|比較|構成|内訳|proportion|ratio|share|distribution)",
        re.IGNORECASE,
    )
    if (
        proportion_keywords.search(query_text)
        and category_cols
        and len(numeric_cols) == 1
    ):
        return {
            "type": "pie",
            "x_key": category_cols[0]["key"],
            "y_keys": [numeric_cols[0]["key"]],
            "title": _extract_chart_title(query_text),
        }

    # ルール 2 & 4: カテゴリカラムが存在する → 棒グラフ
    if category_cols:
        x_key = category_cols[0]["key"]
        y_keys = [c["key"] for c in numeric_cols[:3]]  # 最大3系列
        return {
            "type": "bar",
            "x_key": x_key,
            "y_keys": y_keys,
            "title": _extract_chart_title(query_text),
        }

    return None


def _extract_chart_title(query_text: str, max_length: int = 30) -> str:
    """
    クエリテキストからチャートタイトルを生成する。

    Args:
        query_text: ユーザーのクエリ文字列。
        max_length: タイトルの最大文字数。

    Returns:
        チャートタイトル文字列。
    """
    title = query_text.strip()
    if len(title) > max_length:
        title = title[:max_length] + "..."
    return title


# ---------------------------------------------------------------------------
# DB 保存
# ---------------------------------------------------------------------------


async def save_output(
    db: AsyncSession,
    message_id: str,
    output_type: str,
    table_data: TableData | None,
    chart_config: ChartConfig | None,
    sql_executed: str | None,
    row_count: int,
) -> ChatOutput:
    """
    構造化出力データを chat_outputs テーブルに保存する。

    output_type は 'table' | 'chart' | 'both' | 'none' のいずれかを指定する。
    既存レコードは保存せず新規作成する（1メッセージに1出力）。

    Args:
        db: 非同期データベースセッション。
        message_id: 紐付けるメッセージ ID。
        output_type: 出力種別 ('table' | 'chart' | 'both' | 'none')。
        table_data: format_table_data の返り値（None の場合は保存しない）。
        chart_config: suggest_chart_config の返り値（None の場合は保存しない）。
        sql_executed: 実行された SQL 文字列（None の場合はスキップ）。
        row_count: 結果行数。

    Returns:
        保存した ChatOutput ORM インスタンス。
    """
    now = datetime.now(timezone.utc).isoformat()

    table_data_json: str | None = None
    if table_data is not None:
        try:
            table_data_json = json.dumps(table_data, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("table_data の JSON シリアライズに失敗しました: %s", exc)

    chart_config_json: str | None = None
    if chart_config is not None:
        try:
            chart_config_json = json.dumps(chart_config, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning("chart_config の JSON シリアライズに失敗しました: %s", exc)

    chat_output = ChatOutput(
        id=str(uuid.uuid4()),
        message_id=message_id,
        output_type=output_type,
        table_data=table_data_json,
        chart_config=chart_config_json,
        sql_executed=sql_executed,
        row_count=row_count,
        created_at=now,
    )
    db.add(chat_output)

    try:
        await db.flush()
    except Exception as exc:
        logger.error("ChatOutput の DB 保存に失敗しました: %s", exc)
        raise

    logger.info(
        "ChatOutput を保存しました: id=%s, message_id=%s, output_type=%s, row_count=%d",
        chat_output.id,
        message_id,
        output_type,
        row_count,
    )
    return chat_output
