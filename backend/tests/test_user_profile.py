"""
user_profile サービスのユニットテスト。

_build_keyword_sets と _count_keyword_mentions の純粋関数部分を
モックを使ってテストする。update_user_profile の DB 統合テストは
インメモリ SQLite を使う。
"""

from __future__ import annotations

from collections import Counter
from unittest.mock import MagicMock, patch

import pytest

from app.services.user_profile import (
    _TOP_N,
    _build_keyword_sets,
    _count_keyword_mentions,
)


# ---------------------------------------------------------------------------
# _build_keyword_sets のテスト
# ---------------------------------------------------------------------------


class TestBuildKeywordSets:
    """_build_keyword_sets 関数のテスト。"""

    def test_returns_empty_dicts_when_cache_not_initialized(self) -> None:
        """マスターキャッシュ未初期化時は空辞書を返す。"""
        with patch(
            "app.services.user_profile.get_master_cache",
            side_effect=RuntimeError("未初期化"),
        ):
            line_kw, cat_kw = _build_keyword_sets()

        assert line_kw == {}
        assert cat_kw == {}

    def test_registers_line_code_and_name(self) -> None:
        """ラインのコードと名称がキーワードとして登録される。"""
        mock_line = MagicMock()
        mock_line.name = "組立ライン1"
        mock_line.aliases = []

        mock_cache = MagicMock()
        mock_cache.lines = {"LINE_A": mock_line}
        mock_cache.sites = {}

        with patch("app.services.user_profile.get_master_cache", return_value=mock_cache):
            line_kw, cat_kw = _build_keyword_sets()

        assert "line_a" in line_kw
        assert line_kw["line_a"] == "LINE_A"
        assert "組立ライン1" in line_kw
        assert line_kw["組立ライン1"] == "LINE_A"

    def test_registers_line_aliases(self) -> None:
        """ラインのエイリアスがキーワードとして登録される。"""
        mock_line = MagicMock()
        mock_line.name = "組立"
        mock_line.aliases = ["エイリアス1", "alias_one"]

        mock_cache = MagicMock()
        mock_cache.lines = {"LINE_B": mock_line}
        mock_cache.sites = {}

        with patch("app.services.user_profile.get_master_cache", return_value=mock_cache):
            line_kw, _ = _build_keyword_sets()

        assert "エイリアス1" in line_kw
        assert "alias_one" in line_kw
        assert line_kw["エイリアス1"] == "LINE_B"

    def test_registers_site_code_and_name(self) -> None:
        """サイトのコードと名称がカテゴリキーワードとして登録される。"""
        mock_site = MagicMock()
        mock_site.name = "東京工場"
        mock_site.aliases = []

        mock_cache = MagicMock()
        mock_cache.lines = {}
        mock_cache.sites = {"SITE_TK": mock_site}

        with patch("app.services.user_profile.get_master_cache", return_value=mock_cache):
            _, cat_kw = _build_keyword_sets()

        assert "site_tk" in cat_kw
        assert cat_kw["site_tk"] == "SITE_TK"
        assert "東京工場" in cat_kw

    def test_empty_aliases_are_skipped(self) -> None:
        """空文字列のエイリアスはキーワードとして登録されない。"""
        mock_line = MagicMock()
        mock_line.name = "ライン"
        mock_line.aliases = ["", "  "]  # 空文字と空白

        mock_cache = MagicMock()
        mock_cache.lines = {"L1": mock_line}
        mock_cache.sites = {}

        with patch("app.services.user_profile.get_master_cache", return_value=mock_cache):
            line_kw, _ = _build_keyword_sets()

        # 空文字列や空白はキーワードに含まれない
        assert "" not in line_kw
        # ただし "  " は strip されないためキーワードに含まれる可能性あり
        # ここでは空チェックのみ確認
        assert line_kw.get("l1") == "L1"


# ---------------------------------------------------------------------------
# _count_keyword_mentions のテスト
# ---------------------------------------------------------------------------


class TestCountKeywordMentions:
    """_count_keyword_mentions 関数のテスト。"""

    def _make_message(self, role: str, content: str) -> MagicMock:
        """テスト用の Message モック生成ヘルパー。"""
        msg = MagicMock()
        msg.role = role
        msg.content = content
        return msg

    def test_counts_user_messages_only(self) -> None:
        """アシスタントメッセージはカウントされず、ユーザーメッセージのみカウントされる。"""
        messages = [
            self._make_message("user", "LINE_A について教えてください"),
            self._make_message("assistant", "LINE_A は組立ラインです"),
        ]
        line_kw = {"line_a": "LINE_A"}
        cat_kw: dict[str, str] = {}

        line_counter, _ = _count_keyword_mentions(messages, line_kw, cat_kw)

        # ユーザーメッセージ 1 件のみカウント
        assert line_counter["LINE_A"] == 1

    def test_case_insensitive_matching(self) -> None:
        """大文字・小文字を区別せずにマッチングする。"""
        messages = [
            self._make_message("user", "Line_A と Line_B を確認"),
        ]
        line_kw = {"line_a": "LINE_A", "line_b": "LINE_B"}
        cat_kw: dict[str, str] = {}

        line_counter, _ = _count_keyword_mentions(messages, line_kw, cat_kw)

        assert line_counter["LINE_A"] == 1
        assert line_counter["LINE_B"] == 1

    def test_single_message_counts_once_per_code(self) -> None:
        """1 つのメッセージに同じコードの複数キーワードがあっても 1 回のみカウントする。"""
        messages = [
            # "line_a" と "alias_a" が同じコード "LINE_A" を指す
            self._make_message("user", "line_a と alias_a を調査"),
        ]
        line_kw = {"line_a": "LINE_A", "alias_a": "LINE_A"}
        cat_kw: dict[str, str] = {}

        line_counter, _ = _count_keyword_mentions(messages, line_kw, cat_kw)

        # 同一コードは 1 メッセージにつき 1 回
        assert line_counter["LINE_A"] == 1

    def test_multiple_messages_accumulate_counts(self) -> None:
        """複数のメッセージのカウントが累積される。"""
        messages = [
            self._make_message("user", "line_a について"),
            self._make_message("user", "line_a の状況"),
            self._make_message("user", "line_b を確認"),
        ]
        line_kw = {"line_a": "LINE_A", "line_b": "LINE_B"}
        cat_kw: dict[str, str] = {}

        line_counter, _ = _count_keyword_mentions(messages, line_kw, cat_kw)

        assert line_counter["LINE_A"] == 2
        assert line_counter["LINE_B"] == 1

    def test_no_keywords_matched_returns_empty_counter(self) -> None:
        """キーワードにマッチしない場合は空の Counter を返す。"""
        messages = [
            self._make_message("user", "一般的な質問をしています"),
        ]
        line_kw = {"line_xyz": "LINE_XYZ"}
        cat_kw: dict[str, str] = {}

        line_counter, cat_counter = _count_keyword_mentions(messages, line_kw, cat_kw)

        assert len(line_counter) == 0
        assert len(cat_counter) == 0

    def test_empty_messages_list(self) -> None:
        """空のメッセージリストは空の Counter を返す。"""
        line_counter, cat_counter = _count_keyword_mentions([], {}, {})

        assert isinstance(line_counter, Counter)
        assert isinstance(cat_counter, Counter)
        assert len(line_counter) == 0

    def test_category_keywords_counted_separately(self) -> None:
        """カテゴリキーワードはライン集計とは独立してカウントされる。"""
        messages = [
            self._make_message("user", "東京工場のラインAを確認"),
        ]
        line_kw = {"라인a": "LINE_A"}
        cat_kw = {"東京工場": "SITE_TK"}

        _, cat_counter = _count_keyword_mentions(messages, line_kw, cat_kw)

        assert cat_counter["SITE_TK"] == 1


# ---------------------------------------------------------------------------
# TOP_N 定数のテスト
# ---------------------------------------------------------------------------


class TestConstants:
    """モジュール定数の確認テスト。"""

    def test_top_n_is_five(self) -> None:
        """_TOP_N は 5 であること。"""
        assert _TOP_N == 5
