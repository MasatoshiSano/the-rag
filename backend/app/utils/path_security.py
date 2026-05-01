"""
ローカルファイルシステム操作のセキュリティユーティリティ。

ファイル削除・スキャン操作で以下を強制する:
  - realpath 解決後のパスが指定 root 配下に留まっていることを確認
  - パストラバーサル (../) の検出
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def is_within_root(path: str, allowed_root: str) -> bool:
    """
    指定パスがシンボリックリンク解決後も allowed_root の配下にあるか判定する。

    Args:
        path: 検査対象パス。
        allowed_root: 許可するルートディレクトリ。

    Returns:
        True if path が allowed_root の配下、False otherwise。
    """
    if not path or not allowed_root:
        return False

    try:
        resolved = os.path.realpath(path)
        root_resolved = os.path.realpath(allowed_root)
    except OSError:
        return False

    try:
        common = os.path.commonpath([resolved, root_resolved])
    except ValueError:
        # 異なるドライブ等で commonpath が計算できない場合
        return False

    return common == root_resolved


def safe_remove_within(path: str, allowed_root: str) -> bool:
    """
    パスが allowed_root の配下にある場合のみファイルを削除する。

    Args:
        path: 削除対象ファイルパス。
        allowed_root: 許可するルートディレクトリ。

    Returns:
        True if 削除成功、False if root 外で削除をスキップした、
        または削除に失敗した場合。
    """
    if not path:
        return False

    if not is_within_root(path, allowed_root):
        logger.warning(
            "Refusing to delete file outside allowed_root: path=%s root=%s",
            path,
            allowed_root,
        )
        return False

    if not os.path.exists(path):
        return False

    try:
        os.remove(path)
        return True
    except OSError:
        logger.exception("Failed to delete file: %s", path)
        return False
