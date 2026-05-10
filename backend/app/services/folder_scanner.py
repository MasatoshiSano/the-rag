"""
ローカルフォルダスキャンサービス。
Windows パスをコンテナ内パスに変換し、対応ファイルを再帰的にスキャンする。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset(
    {".md", ".txt", ".csv", ".json", ".pdf", ".pptx", ".xlsx", ".docx", ".html"}
)

# ホストドライブのマウントルート（docker-compose で /mnt:/host_drives:ro）
_HOST_DRIVES_ROOT = "/host_drives"


def _ensure_within_host_drives(path: str) -> str:
    """path が /host_drives 配下に収まることを realpath ベースで検証する。

    `..` セグメントやシンボリックリンクによるマウント領域外への脱出を防ぐ。

    Args:
        path: 検証対象のコンテナ内パス。

    Returns:
        正規化済みの絶対パス。

    Raises:
        ValueError: path が /host_drives の外を指す場合。
    """
    root_real = os.path.realpath(_HOST_DRIVES_ROOT)
    path_real = os.path.realpath(path)
    if (
        os.path.commonpath([root_real, path_real]) != root_real
        or path_real == root_real
    ):
        raise ValueError(
            f"パスがマウント領域 ({_HOST_DRIVES_ROOT}) の外を指しています: {path}"
        )
    return path_real


def windows_path_to_container_path(win_path: str) -> str:
    """
    Windows パスをコンテナ内パスに変換する。

    ドライブレターパス:
        C:\\Users\\docs → /host_drives/c/Users/docs
        E:/Data/files  → /host_drives/e/Data/files

    UNC パス:
        \\\\server\\share\\path → /host_drives/unc/server/share/path

    Raises:
        ValueError: 認識できないパス形式、または変換結果が /host_drives の外を指す場合。
    """
    normalized = win_path.replace("\\", "/").rstrip("/")

    # UNC パス: //server/share/...
    unc_match = re.match(r"^//([^/]+)/(.+)", normalized)
    if unc_match:
        server = unc_match.group(1)
        rest = unc_match.group(2)
        return _ensure_within_host_drives(f"/host_drives/unc/{server}/{rest}")

    # ドライブレターパス: C:/...
    drive_match = re.match(r"^([A-Za-z]):/?(.*)", normalized)
    if drive_match:
        drive_letter = drive_match.group(1).lower()
        rest = drive_match.group(2)
        candidate = (
            f"/host_drives/{drive_letter}/{rest}"
            if rest
            else f"/host_drives/{drive_letter}"
        )
        return _ensure_within_host_drives(candidate)

    raise ValueError(f"Windowsパスとして認識できません: {win_path}")


@dataclass(frozen=True)
class ScannedFile:
    """スキャン結果の1ファイルを表すデータクラス。"""

    relative_path: str
    absolute_path: str
    filename: str
    size_bytes: int


def scan_folder(
    container_path: str,
    extensions: frozenset[str] | None = None,
    max_files: int = 500,
) -> list[ScannedFile]:
    """
    コンテナ内パスを再帰スキャンし、対応拡張子のファイル一覧を返す。

    Args:
        container_path: スキャン対象のコンテナ内絶対パス。
        extensions: 対象拡張子のセット。None の場合は SUPPORTED_EXTENSIONS を使用。
        max_files: 返却ファイル数の上限。

    Returns:
        ScannedFile のリスト（最大 max_files 件）。
    """
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS

    if not os.path.isdir(container_path):
        logger.warning("フォルダが存在しません: %s", container_path)
        return []

    container_real = os.path.realpath(container_path)
    files: list[ScannedFile] = []

    # シンボリックリンク経由の脱出を防ぐ（os.walk は既定でディレクトリリンクを辿らない）
    for dirpath, _dirnames, filenames in os.walk(container_path):
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            if ext.lower() not in extensions:
                continue

            abs_path = os.path.join(dirpath, fname)
            # ファイルがシンボリックリンク等でスキャン対象フォルダの外を指す場合はスキップ
            abs_real = os.path.realpath(abs_path)
            if os.path.commonpath([container_real, abs_real]) != container_real:
                logger.warning(
                    "スキャン対象外のパスを指すファイルをスキップ: %s", abs_path
                )
                continue

            rel_path = os.path.relpath(abs_path, container_path)
            # バックスラッシュをスラッシュに統一
            rel_path = rel_path.replace("\\", "/")

            try:
                size = os.path.getsize(abs_path)
            except OSError:
                size = 0

            files.append(
                ScannedFile(
                    relative_path=rel_path,
                    absolute_path=abs_path,
                    filename=fname,
                    size_bytes=size,
                )
            )

            if len(files) >= max_files:
                logger.warning(
                    "ファイル数上限 (%d) に達しました: %s", max_files, container_path
                )
                return files

    return files
