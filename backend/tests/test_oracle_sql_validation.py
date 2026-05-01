"""
oracle_query.validate_sql のユニットテスト。

文字列リテラル内の禁止キーワード誤検知対策（_strip_string_literals 経由）と、
正規ケース・攻撃ケースの境界を確認する。
"""

from __future__ import annotations

import pytest

from app.services.oracle_query import _strip_string_literals, validate_sql


# ---------------------------------------------------------------------------
# _strip_string_literals: 文字列リテラル除去ロジック単体
# ---------------------------------------------------------------------------


class TestStripStringLiterals:
    def test_simple_literal_replaced(self) -> None:
        """単純なシングルクォート文字列が '' に置換される。"""
        result = _strip_string_literals("SELECT * FROM t WHERE name = 'BEGIN_DATE'")
        assert result == "SELECT * FROM t WHERE name = ''"

    def test_escaped_quote_handled(self) -> None:
        """Oracle のエスケープクォート '' を含む文字列も1リテラルとして扱う。"""
        result = _strip_string_literals("SELECT 'O''Brien' FROM dual")
        assert result == "SELECT '' FROM dual"

    def test_double_quoted_identifier_untouched(self) -> None:
        """ダブルクォートの識別子はそのまま残る。"""
        sql = 'SELECT "BEGIN_DATE" FROM t'
        assert _strip_string_literals(sql) == sql

    def test_no_literal(self) -> None:
        """リテラルが無い SQL はそのまま返る。"""
        sql = "SELECT col FROM t WHERE id = 1"
        assert _strip_string_literals(sql) == sql


# ---------------------------------------------------------------------------
# validate_sql: 正常系（誤検知が起きないこと）
# ---------------------------------------------------------------------------


class TestValidateSqlAllowsLiterals:
    def test_allows_string_literal_with_keyword(self) -> None:
        """文字列リテラル内の BEGIN は禁止キーワードとして弾かれない。"""
        valid, msg = validate_sql(
            "SELECT * FROM HF1REM01 WHERE INSP_ITEMNAME = 'BEGIN_DATE' "
            "AND EXCEPT_FLAG IN (0, 1)"
        )
        assert valid is True, msg

    def test_allows_string_literal_with_dbms_word(self) -> None:
        """文字列リテラル内の DBMS_OUTPUT も誤検知されない。"""
        valid, msg = validate_sql(
            "SELECT * FROM HF1REM01 WHERE PARTS_NO = 'DBMS_OUTPUT_PART' "
            "AND EXCEPT_FLAG IN (0, 1)"
        )
        assert valid is True, msg

    def test_allows_escaped_quote_in_literal(self) -> None:
        """エスケープクォートを含むリテラルでも誤検知しない。"""
        valid, msg = validate_sql(
            "SELECT 'O''Brien BEGIN section' FROM dual"
        )
        assert valid is True, msg

    def test_allows_simple_select(self) -> None:
        """単純な SELECT は通る。"""
        valid, msg = validate_sql("SELECT 1 FROM dual")
        assert valid is True, msg

    def test_allows_with_cte(self) -> None:
        """WITH 句 (CTE) も通る。"""
        valid, msg = validate_sql(
            "WITH a AS (SELECT 1 AS x FROM dual) SELECT x FROM a"
        )
        assert valid is True, msg


# ---------------------------------------------------------------------------
# validate_sql: 攻撃系（リテラル除去後も拒否されること）
# ---------------------------------------------------------------------------


class TestValidateSqlRejectsAttacks:
    def test_rejects_actual_begin_block(self) -> None:
        """実際の BEGIN ブロックは拒否される（先頭が SELECT/WITH でないため）。"""
        valid, msg = validate_sql(
            "BEGIN UTL_HTTP.REQUEST('http://evil') END"
        )
        assert valid is False
        assert msg

    def test_rejects_dbms_call_outside_literal(self) -> None:
        """文字列リテラル外の DBMS_* 呼び出しは拒否される。"""
        valid, msg = validate_sql(
            "SELECT DBMS_LOB.SUBSTR(col) FROM t"
        )
        assert valid is False
        assert "DBMS_*" in msg or "禁止" in msg

    def test_rejects_utl_call_outside_literal(self) -> None:
        """文字列リテラル外の UTL_* 呼び出しは拒否される。"""
        valid, msg = validate_sql(
            "SELECT UTL_HTTP.REQUEST('x') FROM dual"
        )
        assert valid is False

    def test_rejects_sys_reference_outside_literal(self) -> None:
        """SYS.* スキーマ参照は拒否される。"""
        valid, msg = validate_sql("SELECT SYS.USER_TABLES FROM dual")
        assert valid is False

    def test_rejects_multiple_statements(self) -> None:
        """複数ステートメントは拒否される。"""
        valid, msg = validate_sql("SELECT 1 FROM dual; DROP TABLE t")
        assert valid is False

    def test_rejects_update_statement(self) -> None:
        """UPDATE 文は先頭 allowlist で拒否される。"""
        valid, msg = validate_sql("UPDATE t SET col=1")
        assert valid is False

    def test_rejects_empty_sql(self) -> None:
        """空 SQL は拒否される。"""
        valid, msg = validate_sql("")
        assert valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
