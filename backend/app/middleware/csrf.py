"""
CSRF 防御ミドルウェア。

状態変更系メソッド (POST/PUT/PATCH/DELETE) に対して Origin/Referer ヘッダを
allowlist で検証する。CORS とは独立の二重防御として動作する。
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# 状態変更系メソッド
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def is_origin_allowed(origin: str, allowed: list[str]) -> bool:
    """
    Origin (または Referer から抽出した origin) が allowed リストに含まれるか判定する。

    Args:
        origin: 検証対象 Origin (例: "https://example.com:443")。
        allowed: 許可済み Origin リスト。

    Returns:
        True if 許可、False otherwise。
    """
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False

    normalized = f"{parsed.scheme}://{parsed.netloc}"

    for entry in allowed:
        try:
            ep = urlparse(entry)
        except Exception:
            continue
        if not ep.scheme or not ep.netloc:
            continue
        if f"{ep.scheme}://{ep.netloc}" == normalized:
            return True
    return False


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    """
    POST/PUT/PATCH/DELETE リクエストに対し Origin/Referer ヘッダを
    検証する CSRF 防御ミドルウェア。

    - GET/HEAD/OPTIONS はスルー
    - Origin ヘッダがある場合: allowed_origins と完全一致を要求
    - Origin が無く Referer がある場合: Referer の origin 部分を検証
    - 両方無い場合: 安全側に倒して 403

    例外パス (CSRF 検証スキップ):
      - ``/health``: ヘルスチェック (Origin ヘッダを持たないクライアントが多い)
      - ``/api/ext/*``: API キー認証 (Depends(verify_api_key)) で別途防御されており、
        サーバー間連携クライアント (curl, requests 等) は通常 Origin ヘッダを送らない
        ため CSRF 検証は不要。API キー認証は CSRF と同等以上の防御力を持つ。
    """

    # CSRF 検証をスキップするパスプレフィックスの allowlist。
    # 完全一致 (path == prefix) または前方一致 (path.startswith(prefix)) で判定する。
    EXEMPT_PATH_PREFIXES: tuple[str, ...] = ("/health", "/api/ext/")

    def __init__(self, app, allowed_origins: list[str]) -> None:
        super().__init__(app)
        self._allowed_origins = list(allowed_origins)

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if method not in _MUTATING_METHODS:
            return await call_next(request)

        # 例外パス (ヘルスチェック / API キー認証ルーター) は CSRF 検証をスキップ。
        # /api/ext/* は API キー認証 (Depends(verify_api_key)) で別途防御されており、
        # サーバー間連携クライアントは通常 Origin ヘッダを送らないため CSRF 検証は不要。
        path = request.url.path
        for exempt in self.EXEMPT_PATH_PREFIXES:
            if path == exempt or path.startswith(exempt):
                return await call_next(request)

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        candidate = origin
        if not candidate and referer:
            # Referer から origin を抽出
            try:
                parsed = urlparse(referer)
                if parsed.scheme and parsed.netloc:
                    candidate = f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                candidate = None

        if not candidate or not is_origin_allowed(candidate, self._allowed_origins):
            logger.warning(
                "CSRF check failed: method=%s path=%s origin=%r referer=%r",
                method,
                path,
                origin,
                referer,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF check failed: invalid Origin/Referer"},
            )

        return await call_next(request)
