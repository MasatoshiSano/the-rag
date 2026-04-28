"""folder_scanner モジュールのユニットテスト。"""

import os
import tempfile

import pytest

from app.services.folder_scanner import (
    ScannedFile,
    scan_folder,
    windows_path_to_container_path,
)
from app.services.rag import _keyword_search_in_text


# ---------------------------------------------------------------------------
# windows_path_to_container_path テスト
# ---------------------------------------------------------------------------


class TestWindowsPathToContainerPath:
    def test_c_drive_backslash(self) -> None:
        result = windows_path_to_container_path(r"C:\Users\docs")
        assert result == "/host_drives/c/Users/docs"

    def test_e_drive_forward_slash(self) -> None:
        result = windows_path_to_container_path("E:/Data/files")
        assert result == "/host_drives/e/Data/files"

    def test_drive_root(self) -> None:
        result = windows_path_to_container_path("D:\\")
        assert result == "/host_drives/d"

    def test_drive_root_no_slash(self) -> None:
        result = windows_path_to_container_path("D:")
        assert result == "/host_drives/d"

    def test_lowercase_drive(self) -> None:
        result = windows_path_to_container_path("c:/temp")
        assert result == "/host_drives/c/temp"

    def test_trailing_slash_stripped(self) -> None:
        result = windows_path_to_container_path("C:\\Users\\docs\\")
        assert result == "/host_drives/c/Users/docs"

    def test_invalid_path_raises(self) -> None:
        with pytest.raises(ValueError, match="認識できません"):
            windows_path_to_container_path("/unix/path")

    def test_relative_path_raises(self) -> None:
        with pytest.raises(ValueError, match="認識できません"):
            windows_path_to_container_path("relative/path")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="認識できません"):
            windows_path_to_container_path("")

    def test_unc_path_backslash(self) -> None:
        result = windows_path_to_container_path(r"\\10.168.22.161\data\Taden\Assy")
        assert result == "/host_drives/unc/10.168.22.161/data/Taden/Assy"

    def test_unc_path_forward_slash(self) -> None:
        result = windows_path_to_container_path("//server/share/path/to/folder")
        assert result == "/host_drives/unc/server/share/path/to/folder"

    def test_unc_path_trailing_slash(self) -> None:
        result = windows_path_to_container_path(r"\\server\share\docs\\")
        assert result == "/host_drives/unc/server/share/docs"

    def test_unc_path_share_only(self) -> None:
        result = windows_path_to_container_path(r"\\server\share")
        assert result == "/host_drives/unc/server/share"


# ---------------------------------------------------------------------------
# scan_folder テスト
# ---------------------------------------------------------------------------


class TestScanFolder:
    def test_scan_supported_files(self, tmp_path: str) -> None:
        """対応拡張子のファイルのみがスキャンされる。"""
        base = tempfile.mkdtemp()
        # 対応ファイル
        for name in ["readme.md", "data.csv", "report.pdf"]:
            with open(os.path.join(base, name), "w") as f:
                f.write("test content")
        # 非対応ファイル
        with open(os.path.join(base, "image.png"), "w") as f:
            f.write("binary")
        with open(os.path.join(base, "code.py"), "w") as f:
            f.write("print('hello')")

        result = scan_folder(base)
        filenames = {f.filename for f in result}
        assert "readme.md" in filenames
        assert "data.csv" in filenames
        assert "report.pdf" in filenames
        assert "image.png" not in filenames
        assert "code.py" not in filenames

    def test_scan_recursive(self) -> None:
        """サブディレクトリも再帰的にスキャンする。"""
        base = tempfile.mkdtemp()
        sub = os.path.join(base, "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "nested.txt"), "w") as f:
            f.write("nested")

        result = scan_folder(base)
        assert len(result) == 1
        assert result[0].relative_path == "sub/nested.txt" or result[0].relative_path == "sub\\nested.txt"

    def test_scan_max_files(self) -> None:
        """max_files で結果が制限される。"""
        base = tempfile.mkdtemp()
        for i in range(10):
            with open(os.path.join(base, f"file{i}.txt"), "w") as f:
                f.write(f"content {i}")

        result = scan_folder(base, max_files=3)
        assert len(result) == 3

    def test_scan_nonexistent_dir(self) -> None:
        """存在しないディレクトリでは空リストを返す。"""
        result = scan_folder("/nonexistent/path/12345")
        assert result == []

    def test_scanned_file_fields(self) -> None:
        """ScannedFile の全フィールドが正しく設定される。"""
        base = tempfile.mkdtemp()
        filepath = os.path.join(base, "test.md")
        with open(filepath, "w") as f:
            f.write("# Hello")

        result = scan_folder(base)
        assert len(result) == 1
        sf = result[0]
        assert isinstance(sf, ScannedFile)
        assert sf.filename == "test.md"
        assert sf.relative_path == "test.md"
        assert sf.absolute_path == filepath
        assert sf.size_bytes > 0


# ---------------------------------------------------------------------------
# _keyword_search_in_text テスト
# ---------------------------------------------------------------------------


class TestKeywordSearchInText:
    def test_single_keyword(self) -> None:
        content = "line1 apple\nline2 banana\nline3 apple again"
        matches = _keyword_search_in_text(content, "apple")
        assert len(matches) == 2
        assert matches[0]["line_number"] == 1
        assert matches[1]["line_number"] == 3

    def test_and_same_line(self) -> None:
        """両方のキーワードが同一行にある場合はヒットする。"""
        content = "row1 foo bar\nrow2 baz\nrow3 foo"
        matches = _keyword_search_in_text(content, "foo bar")
        assert len(matches) == 1
        assert matches[0]["line_number"] == 1

    def test_and_window_nearby(self) -> None:
        """キーワードが異なる行でもウィンドウ内にあればヒットする。"""
        lines = ["header K298C03573"] + ["filler"] * 8 + ["spec 圧力計 0.45"]
        content = "\n".join(lines)
        matches = _keyword_search_in_text(content, "K298C03573 圧力計", window_size=20)
        assert len(matches) >= 1

    def test_and_window_too_far(self) -> None:
        """キーワードがウィンドウ外にある場合はANDヒットせずORフォールバック。"""
        lines = ["header K298C03573"] + ["filler"] * 25 + ["spec 圧力計 0.45"]
        content = "\n".join(lines)
        matches = _keyword_search_in_text(content, "K298C03573 圧力計", window_size=20)
        # OR フォールバック — partial match
        assert len(matches) >= 1
        assert matches[0].get("match_type") == "partial"

    def test_or_fallback_sorted_by_count(self) -> None:
        """OR フォールバック時、マッチキーワード数の多い行が先頭に来る。"""
        content = "line1 alpha\nline2 alpha beta\nline3 beta gamma"
        matches = _keyword_search_in_text(
            content, "alpha beta gamma", window_size=1
        )
        # AND は 0件 → OR フォールバック
        assert len(matches) >= 2
        # line2 has 2 keywords (alpha, beta), line3 has 2 (beta, gamma), line1 has 1
        assert matches[0].get("match_type") == "partial"
        assert len(matches[0]["matched_keywords"]) >= 2

    def test_no_match_returns_empty(self) -> None:
        content = "nothing relevant here"
        matches = _keyword_search_in_text(content, "zzz999")
        assert matches == []

    def test_max_results_respected(self) -> None:
        content = "\n".join(f"line{i} keyword" for i in range(50))
        matches = _keyword_search_in_text(content, "keyword", max_results=5)
        assert len(matches) == 5
