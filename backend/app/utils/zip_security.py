"""
ZIP 解凍のセキュリティユーティリティ。

以下を強制する:
  - 合計展開サイズの上限 (Zip Bomb 緩和)
  - 1 ファイルあたりの展開サイズ上限
  - 圧縮率の上限 (Zip Bomb 緩和)
  - パストラバーサル防止 (basename 抽出済み前提)
"""

from __future__ import annotations

import logging
from typing import Iterator
from zipfile import ZipFile, ZipInfo

logger = logging.getLogger(__name__)

# 圧縮率上限 (展開サイズ / 圧縮サイズ)。これを超える場合は Zip Bomb 疑い。
_COMPRESSION_RATIO_LIMIT = 100

# 1チャンクの読み込みサイズ
_READ_CHUNK = 64 * 1024


class ZipSecurityError(Exception):
    """ZIP セキュリティ違反 (上限超過 / 圧縮率異常 / etc.)。"""


def check_zip_info(
    zip_info: ZipInfo,
    max_per_file: int,
    cumulative_size: int,
    max_total: int,
) -> None:
    """
    ZipInfo の展開前事前チェック。

    Args:
        zip_info: ZipFile.infolist() の要素。
        max_per_file: 1ファイルあたりの上限バイト数。
        cumulative_size: これまでに展開した合計バイト数。
        max_total: 合計上限バイト数。

    Raises:
        ZipSecurityError: 制限違反の場合。
    """
    file_size = zip_info.file_size
    compress_size = max(zip_info.compress_size, 1)

    if file_size > max_per_file:
        raise ZipSecurityError(
            f"ZIP entry '{zip_info.filename}' exceeds per-file limit "
            f"({file_size} > {max_per_file})"
        )

    if cumulative_size + file_size > max_total:
        raise ZipSecurityError(
            f"ZIP total contents exceed limit "
            f"({cumulative_size + file_size} > {max_total})"
        )

    # 圧縮率チェック (Zip Bomb 緩和)
    if file_size / compress_size > _COMPRESSION_RATIO_LIMIT:
        raise ZipSecurityError(
            f"ZIP entry '{zip_info.filename}' has suspicious compression ratio "
            f"({file_size}/{compress_size}={file_size / compress_size:.1f})"
        )


def safe_read_entry(
    zf: ZipFile,
    zip_info: ZipInfo,
    max_per_file: int,
) -> bytes:
    """
    ZIP エントリをストリーミングで読み込み、展開サイズが max_per_file を
    超えた時点で打ち切る。

    Args:
        zf: 開いた ZipFile。
        zip_info: 対象エントリ。
        max_per_file: 1ファイルあたりの上限バイト数。

    Returns:
        展開済みバイト列。

    Raises:
        ZipSecurityError: 上限超過時。
    """
    extracted = bytearray()
    with zf.open(zip_info) as src:
        for chunk in iter(lambda: src.read(_READ_CHUNK), b""):
            extracted.extend(chunk)
            if len(extracted) > max_per_file:
                raise ZipSecurityError(
                    f"ZIP entry '{zip_info.filename}' exceeds per-file limit "
                    f"during streaming read ({len(extracted)} > {max_per_file})"
                )
    return bytes(extracted)


def iter_safe_entries(
    zf: ZipFile,
    max_total: int,
    max_per_file: int,
) -> Iterator[tuple[ZipInfo, bytes]]:
    """
    ZipFile を反復し、安全に解凍した (ZipInfo, content) を yield する。

    Args:
        zf: 開いた ZipFile。
        max_total: 全体の展開上限バイト数。
        max_per_file: 1ファイルあたりの上限バイト数。

    Yields:
        (ZipInfo, bytes) のタプル。

    Raises:
        ZipSecurityError: 制限違反時。
    """
    cumulative = 0
    for zip_info in zf.infolist():
        if zip_info.is_dir():
            continue
        check_zip_info(zip_info, max_per_file, cumulative, max_total)
        content = safe_read_entry(zf, zip_info, max_per_file)
        cumulative += len(content)
        if cumulative > max_total:
            raise ZipSecurityError(
                f"ZIP total contents exceed limit during streaming "
                f"({cumulative} > {max_total})"
            )
        yield zip_info, content
