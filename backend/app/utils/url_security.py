"""
外部 URL アクセスのセキュリティユーティリティ。

GitHub/Gitea 同期等の外部 HTTP 呼び出しで以下を強制する:
  - スキームは http/https のみ
  - ホスト名は完全一致 (allowlist)
  - DNS 解決後の IP がプライベート/ループバック/リンクローカルでない
    (DNS リバインディング対策、SSRF 対策)

## DNS リバインディング対策について

本モジュールの ``validate_and_resolve`` は事前に DNS 解決して IP を検査するが、
後続の httpx リクエストでは DNS が再解決されるため、TTL=0 のドメインに対する
DNS リバインディング攻撃（事前検証時は安全な IP、リクエスト時は内部 IP）に
対する根本的な防御にはならない（TOCTOU 問題）。

## 運用ノート

- allowlist には信頼できるドメイン（公式 GitHub/Gitea 等）のみを追加すること。
- 攻撃者が制御するドメインを allowlist に入れると、DNS リバインディングで
  内部ネットワークへの SSRF が成立する可能性がある。
- 根本対策が必要な場合は、httpx の transport で IP-pinning を実装するか、
  プロキシ経由で外部到達のみを許可するネットワーク設計を採用すること。
- 現状の RAG Phantom では allowlist が GitHub 公式 / 自社運用 Gitea のみに
  限定されているため、実害は無視できるレベルとして許容している。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# 許可するスキーム
_ALLOWED_SCHEMES = {"http", "https"}


def validate_external_url(url: str, allowed_hosts: set[str]) -> str:
    """
    外部 URL のホスト名を厳密に検証する。

    Args:
        url: 検証対象 URL。
        allowed_hosts: 許可するホスト名のセット (小文字、equality 比較)。

    Returns:
        小文字化された hostname。

    Raises:
        HTTPException(400): スキーム・ホスト名が不正な場合。
    """
    if not url:
        raise HTTPException(status_code=400, detail="Invalid URL host")

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid URL host") from exc

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme must be http or https: {parsed.scheme}",
        )

    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL host")

    host = parsed.hostname.lower()
    allowed_lower = {h.lower() for h in allowed_hosts}

    if host not in allowed_lower:
        logger.warning(
            "URL host not in allowlist: host=%s, allowed=%s", host, allowed_lower
        )
        raise HTTPException(status_code=400, detail="Invalid URL host")

    return host


def _resolve_and_validate_ip(hostname: str) -> None:
    """
    ホスト名を DNS 解決し、得られた全 IP がプライベート/ループバック/
    リンクローカル/マルチキャストでないことを確認する。

    Args:
        hostname: 解決対象のホスト名。

    Raises:
        HTTPException(400): 危険な IP に解決された場合 (SSRF 対策)。
    """
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid hostname")

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=400,
            detail=f"DNS resolution failed: {hostname}",
        ) from exc

    seen: set[str] = set()
    for entry in addrinfo:
        # entry は (family, type, proto, canonname, sockaddr) のタプル
        sockaddr = entry[4]
        if not sockaddr:
            continue
        addr = sockaddr[0]
        if addr in seen:
            continue
        seen.add(addr)

        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            # IP として解釈できない場合は念のため拒否
            logger.warning("Cannot parse resolved address: %s", addr)
            raise HTTPException(
                status_code=400, detail="Invalid resolved IP"
            ) from None

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            logger.warning(
                "Blocked SSRF attempt: hostname=%s resolved to forbidden IP %s",
                hostname,
                addr,
            )
            raise HTTPException(
                status_code=400,
                detail="Resolved IP is not allowed (private/loopback/link-local).",
            )


def validate_and_resolve(url: str, allowed_hosts: set[str]) -> str:
    """
    URL のホスト名 allowlist 検証と DNS 解決後 IP の検証を一括で行う。

    Args:
        url: 検証対象 URL。
        allowed_hosts: 許可するホスト名セット。

    Returns:
        検証済み hostname。

    Raises:
        HTTPException(400): 検証失敗時。
    """
    host = validate_external_url(url, allowed_hosts)
    _resolve_and_validate_ip(host)
    return host
