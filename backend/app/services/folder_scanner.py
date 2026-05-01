"""
ローカルフォルダスキャンサービス。
Windows パスをコンテナ内パスに変換し、対応ファイルを再帰的にスキャンする。

パストラバーサル防止:
  - 入力 Windows パスに `..` セグメントが含まれる場合は ValueError。
  - 変換後のコンテナパスを realpath 解決し、`/host_drives/` 配下に
    留まっていることを検証する (シンボリックリンク経由の脱出防止)。
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

# host_drives マウントのルート (docker-compose.yml で /mnt:/host_drives:ro)
_HOST_DRIVES_ROOT = "/host_drives"


def _ensure_within_host_drives(path: str) -> None:
    """
    realpath 解決後のパスが /host_drives/ 配下に留まっているか確認する。

    Raises:
        ValueError: ルート外に脱出している場合 (シンボリックリンク等)。
    """
    try:
        resolved = os.path.realpath(path)
    except OSError as exc:
        raise ValueError(f"パス解決に失敗しました: {path}") from exc

    # /host_drives 自体は許容、それ以外は配下にあること
    try:
        common = os.path.commonpath([resolved, _HOST_DRIVES_ROOT])
    except ValueError as exc:
        raise ValueError(
            f"path traversal detected: {path} -> {resolved}"
        ) from exc

    if common != _HOST_DRIVES_ROOT:
        raise ValueError(
            f"path traversal detected: {path} -> {resolved}"
        )


def windows_path_to_container_path(win_path: str) -> str:
    """
    Windows パスをコンテナ内パスに変換する。

    ドライブレターパス:
        C:\\Users\\docs → /host_drives/c/Users/docs
        E:/Data/files  → /host_drives/e/Data/files

    UNC パス:
        \\\\server\\share\\path → /host_drives/unc/server/share/path

    パストラバーサル防止:
        `..` セグメントを含む入力は拒否する。
        変換後パスを realpath 解決し /host_drives/ 配下から脱出していないことを確認する。

    Raises:
        ValueError: 認識できないパス形式、またはパストラバーサル検知時。
    """
    normalized = win_path.replace("\\", "/").rstrip("/")

    # `..` セグメント検出 (任意の場所に含まれていれば拒否)
    segments = normalized.split("/")
    for seg in segments:
        if seg == "..":
            raise ValueError(
                f"path traversal detected: '..' segment in path: {win_path}"
            )

    # UNC パス: //server/share/...
    unc_match = re.match(r"^//([^/]+)/(.+)", normalized)
    if unc_match:
        server = unc_match.group(1)
        rest = unc_match.group(2)
        # rest 側の `..` は上で除去済みだが念のため
        result = f"/host_drives/unc/{server}/{rest}"
        _ensure_within_host_drives(result)
        return result

    # ドライブレターパス: C:/...
    drive_match = re.match(r"^([A-Za-z]):/?(.*)", normalized)
    if drive_match:
        drive_letter = drive_match.group(1).lower()
        rest = drive_match.group(2)
        result = (
            f"/host_drives/{drive_letter}/{rest}"
            if rest
            else f"/host_drives/{drive_letter}"
        )
        _ensure_within_host_drives(result)
        return result

    raise ValueError(
        f"Windowsパスとして認識できません: {win_path}"
    )


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

    # 入口でも root チェック (DB 改ざん経由の不正パス対策)
    try:
        _ensure_within_host_drives(container_path)
    except ValueError:
        logger.warning(
            "scan_folder: container_path が /host_drives 外: %s", container_path
        )
        return []

    files: list[ScannedFile] = []

    # followlinks=False を明示 (シンボリックリンク経由のディレクトリ参照を抑止)
    for dirpath, _dirnames, filenames in os.walk(container_path, followlinks=False):
        # 各 dirpath が /host_drives/ 配下に留まっていることを確認
        try:
            _ensure_within_host_drives(dirpath)
        except ValueError:
            logger.warning(
                "scan_folder: skip dirpath outside host_drives: %s", dirpath
            )
            continue

        for fname in filenames:
            _, ext = os.path.splitext(fname)
            if ext.lower() not in extensions:
                continue

            abs_path = os.path.join(dirpath, fname)

            # シンボリックリンクのターゲットが root を超える場合の防御
            try:
                _ensure_within_host_drives(abs_path)
            except ValueError:
                logger.warning(
                    "scan_folder: skip symlink target outside host_drives: %s",
                    abs_path,
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
