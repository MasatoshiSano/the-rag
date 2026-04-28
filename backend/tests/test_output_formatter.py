"""
output_formatter サービスのユニットテスト。

format_table_data と suggest_chart_config の純粋関数をテストする。
DB アクセスは不要なため、モックや非同期フィクスチャなしで実行できる。
"""

from __future__ import annotations

import pytest

from app.services.output_formatter import format_table_data, suggest_chart_config


# ---------------------------------------------------------------------------
# format_table_data のテスト
# ---------------------------------------------------------------------------


class TestFormatTableData:
    """format_table_data 関数のテスト。"""

    def test_format_table_data_basic(self) -> None:
        """基本的なカラム・行データが正しく変換される。"""
        columns = ["DATE", "LINE_CODE", "COUNT"]
        rows = [
            ["2024-01-01", "LINE_A", 10],
            ["2024-01-02", "LINE_A", 20],
        ]

        result = format_table_data(columns, rows)

        # カラム定義の検証
        assert len(result["columns"]) == 3
        col_keys = [c["key"] for c in result["columns"]]
        assert col_keys == ["DATE", "LINE_CODE", "COUNT"]

        # 型推定の検証
        col_types = {c["key"]: c["type"] for c in result["columns"]}
        assert col_types["DATE"] == "date"
        assert col_types["COUNT"] == "number"

        # 行データの検証
        assert len(result["rows"]) == 2
        assert result["rows"][0]["DATE"] == "2024-01-01"
        assert result["rows"][0]["LINE_CODE"] == "LINE_A"
        assert result["rows"][0]["COUNT"] == 10
        assert result["rows"][1]["COUNT"] == 20

    def test_format_table_data_empty(self) -> None:
        """空の結果セットは columns と rows が空リストになる。"""
        result = format_table_data([], [])

        assert result["columns"] == []
        assert result["rows"] == []

    def test_format_table_data_columns_without_rows(self) -> None:
        """カラムはあるが行が空の場合、型はサンプル値 None で推定する。"""
        columns = ["ITEM_NAME", "TOTAL"]
        rows: list[list] = []

        result = format_table_data(columns, rows)

        assert len(result["columns"]) == 2
        assert result["rows"] == []
        col_types = {c["key"]: c["type"] for c in result["columns"]}
        # サンプル値が None かつパターンなしの場合は text または number/category
        assert col_types["TOTAL"] == "number"  # _NUMERIC_COLUMN_PATTERN にマッチ

    def test_format_table_data_label_equals_key(self) -> None:
        """各カラムの label は key と同じ値になる。"""
        columns = ["SITE_CODE"]
        rows = [["SITE_A"]]

        result = format_table_data(columns, rows)

        col = result["columns"][0]
        assert col["key"] == col["label"] == "SITE_CODE"

    def test_format_table_data_numeric_value_infers_number_type(self) -> None:
        """サンプル値が数値型の場合、カラム型を number と推定する。"""
        columns = ["MEASUREMENT"]
        rows = [[3.14]]

        result = format_table_data(columns, rows)

        assert result["columns"][0]["type"] == "number"

    def test_format_table_data_category_column(self) -> None:
        """category パターンにマッチするカラム名は category 型になる。"""
        columns = ["CATEGORY"]
        rows = [["TypeA"]]

        result = format_table_data(columns, rows)

        assert result["columns"][0]["type"] == "category"

    def test_format_table_data_datetime_value_serialized(self) -> None:
        """datetime オブジェクトは isoformat 文字列にシリアライズされる。"""
        from datetime import datetime, timezone

        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        columns = ["TS"]
        rows = [[dt]]

        result = format_table_data(columns, rows)

        assert result["rows"][0]["TS"] == dt.isoformat()

    def test_format_table_data_none_value(self) -> None:
        """行内の None 値はそのまま None として格納される。"""
        columns = ["VAL"]
        rows = [[None]]

        result = format_table_data(columns, rows)

        assert result["rows"][0]["VAL"] is None


# ---------------------------------------------------------------------------
# suggest_chart_config のテスト
# ---------------------------------------------------------------------------


class TestSuggestChartConfig:
    """suggest_chart_config 関数のテスト。"""

    def _make_table_data(
        self,
        col_specs: list[tuple[str, str]],
        rows: list[dict],
    ) -> dict:
        """テスト用のテーブルデータを生成するヘルパー。

        Args:
            col_specs: [(key, type), ...] 形式のカラム仕様リスト。
            rows: 行データのリスト。
        """
        columns = [{"key": k, "label": k, "type": t} for k, t in col_specs]
        return {"columns": columns, "rows": rows}

    def test_suggest_chart_config_date_column(self) -> None:
        """日付型カラムが存在する場合は折れ線グラフが推定される。"""
        table_data = self._make_table_data(
            col_specs=[("MK_DATE", "date"), ("COUNT", "number")],
            rows=[{"MK_DATE": "2024-01-01", "COUNT": 5}],
        )

        result = suggest_chart_config(table_data, "日次件数を見せて")

        assert result is not None
        assert result["type"] == "line"
        assert result["x_key"] == "MK_DATE"
        assert "COUNT" in result["y_keys"]

    def test_suggest_chart_config_category(self) -> None:
        """カテゴリ型カラムと数値カラムが存在する場合は棒グラフが推定される。"""
        table_data = self._make_table_data(
            col_specs=[("LINE_CODE", "category"), ("TOTAL", "number")],
            rows=[{"LINE_CODE": "LINE_A", "TOTAL": 100}],
        )

        result = suggest_chart_config(table_data, "ライン別の合計")

        assert result is not None
        assert result["type"] == "bar"
        assert result["x_key"] == "LINE_CODE"
        assert "TOTAL" in result["y_keys"]

    def test_suggest_chart_config_proportion_query(self) -> None:
        """クエリに「割合」が含まれ、カテゴリ1列・数値1列の場合は円グラフが推定される。"""
        table_data = self._make_table_data(
            col_specs=[("STATUS", "category"), ("CNT", "number")],
            rows=[{"STATUS": "OK", "CNT": 80}, {"STATUS": "NG", "CNT": 20}],
        )

        result = suggest_chart_config(table_data, "ステータス別の割合を確認")

        assert result is not None
        assert result["type"] == "pie"
        assert result["x_key"] == "STATUS"
        assert "CNT" in result["y_keys"]

    def test_suggest_chart_config_proportion_query_english(self) -> None:
        """クエリに 'proportion' が含まれる場合も円グラフが推定される。"""
        table_data = self._make_table_data(
            col_specs=[("TYPE", "category"), ("AMOUNT", "number")],
            rows=[{"TYPE": "A", "AMOUNT": 50}],
        )

        result = suggest_chart_config(table_data, "show proportion by type")

        assert result is not None
        assert result["type"] == "pie"

    def test_suggest_chart_config_no_suggestion(self) -> None:
        """数値カラムが存在しない場合は None が返る。"""
        table_data = self._make_table_data(
            col_specs=[("NAME", "text"), ("STATUS", "text")],
            rows=[{"NAME": "doc1", "STATUS": "OK"}],
        )

        result = suggest_chart_config(table_data, "ドキュメント一覧")

        assert result is None

    def test_suggest_chart_config_empty_rows(self) -> None:
        """行が空の場合は None が返る。"""
        table_data = self._make_table_data(
            col_specs=[("DATE", "date"), ("COUNT", "number")],
            rows=[],
        )

        result = suggest_chart_config(table_data, "件数推移")

        assert result is None

    def test_suggest_chart_config_empty_columns(self) -> None:
        """カラムが空の場合は None が返る。"""
        table_data: dict = {"columns": [], "rows": []}

        result = suggest_chart_config(table_data, "なんか")

        assert result is None

    def test_suggest_chart_config_title_truncated(self) -> None:
        """30文字を超えるクエリはタイトルが省略される。"""
        long_query = "あ" * 40
        table_data = self._make_table_data(
            col_specs=[("MK_DATE", "date"), ("CNT", "number")],
            rows=[{"MK_DATE": "2024-01-01", "CNT": 1}],
        )

        result = suggest_chart_config(table_data, long_query)

        assert result is not None
        assert result["title"].endswith("...")
        assert len(result["title"]) <= 33  # 30 文字 + "..."

    def test_suggest_chart_config_multiple_numeric_columns(self) -> None:
        """数値カラムが複数ある場合、y_keys は最大3つまで含む。"""
        table_data = self._make_table_data(
            col_specs=[
                ("DATE", "date"),
                ("CNT1", "number"),
                ("CNT2", "number"),
                ("CNT3", "number"),
                ("CNT4", "number"),
            ],
            rows=[{"DATE": "2024-01-01", "CNT1": 1, "CNT2": 2, "CNT3": 3, "CNT4": 4}],
        )

        result = suggest_chart_config(table_data, "推移")

        assert result is not None
        assert result["type"] == "line"
        assert len(result["y_keys"]) == 3

    def test_suggest_chart_config_category_with_multiple_numerics_is_bar(self) -> None:
        """カテゴリと複数数値カラムの組み合わせは棒グラフになる（割合クエリなし）。"""
        table_data = self._make_table_data(
            col_specs=[
                ("LINE_CODE", "category"),
                ("OK_CNT", "number"),
                ("NG_CNT", "number"),
            ],
            rows=[{"LINE_CODE": "LINE_A", "OK_CNT": 90, "NG_CNT": 10}],
        )

        result = suggest_chart_config(table_data, "ライン別OK/NG比較")

        assert result is not None
        assert result["type"] == "bar"
