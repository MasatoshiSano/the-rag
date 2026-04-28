"""
外部 API エンドポイント用の API キー認証依存関数。
X-API-Key ヘッダーを検証し、config.API_KEYS に含まれるキーのみ許可する。
"""

from fastapi import Header, HTTPException

from app.infrastructure.config import config


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    X-API-Key ヘッダーを検証する FastAPI 依存関数。

    Args:
        x_api_key: リクエストヘッダーの X-API-Key 値。

    Returns:
        検証済みの API キー文字列。

    Raises:
        HTTPException: キーが無効または未指定の場合（403）。
    """
    if x_api_key not in config.API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return x_api_key
