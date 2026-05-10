"""
AWS Bedrock クライアントモジュール。
Claude Sonnet 4.5、Cohere Embed、Cohere Rerank の呼び出しラッパーを提供する。
"""

import asyncio
import base64
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.infrastructure.config import config

logger = logging.getLogger(__name__)

# Module-level client (lazy init)
_bedrock_runtime: "boto3.client | None" = None

# リトライ対象とする AWS API エラーコード（スロットリング・一時的なサービス不能）
_RETRYABLE_AWS_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "ServiceUnavailable",
        "ModelTimeoutException",
        "InternalServerException",
        "ModelNotReadyException",
    }
)


def _is_retryable_bedrock_error(exc: BaseException) -> bool:
    """Bedrock 呼び出しでリトライする価値のあるエラーかを判定する。

    スロットリング・一時的なサービス不能・接続/タイムアウト系のみリトライ対象とし、
    不正リクエスト（ValidationException 等）やレスポンスのパースエラーはリトライしない。

    Args:
        exc: 発生した例外。

    Returns:
        リトライすべきなら True。
    """
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in _RETRYABLE_AWS_ERROR_CODES
    # ConnectTimeoutError / ReadTimeoutError / EndpointConnectionError などは BotoCoreError 派生
    return isinstance(exc, BotoCoreError)


def get_bedrock_runtime() -> "boto3.client":
    """
    AWS Bedrock Runtime クライアントを返す。
    初回呼び出し時にインスタンスを生成し、以降はキャッシュを返す。

    Returns:
        boto3 Bedrock Runtime クライアント。
    """
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=config.BEDROCK_REGION,
        )
    return _bedrock_runtime


@dataclass
class RerankResult:
    """リランク結果を表すデータクラス。"""

    index: int
    relevance_score: float
    document: str


@retry(
    stop=stop_after_attempt(config.MAX_RETRY_COUNT),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_bedrock_error),
    reraise=True,
)
async def generate_text(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """
    Claude Sonnet 4.5 でテキスト生成（非ストリーミング）。

    Args:
        prompt: ユーザーへのプロンプト文字列。
        system_prompt: システムプロンプト文字列。
        max_tokens: 生成する最大トークン数。
        temperature: 生成の多様性を制御するパラメータ（0.0〜1.0）。

    Returns:
        生成されたテキスト文字列。
    """
    client = get_bedrock_runtime()

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system_prompt:
        body["system"] = [{"type": "text", "text": system_prompt}]

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


async def generate_text_stream(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """
    Claude Sonnet 4.5 でテキスト生成（ストリーミング）。
    トークンを逐次 yield する。

    Args:
        prompt: ユーザーへのプロンプト文字列。
        system_prompt: システムプロンプト文字列。
        max_tokens: 生成する最大トークン数。
        temperature: 生成の多様性を制御するパラメータ（0.0〜1.0）。

    Yields:
        生成されたテキストのチャンク文字列。
    """
    client = get_bedrock_runtime()

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system_prompt:
        body["system"] = [{"type": "text", "text": system_prompt}]

    response = await asyncio.to_thread(
        client.invoke_model_with_response_stream,
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    stream = response["body"]
    for event in stream:
        chunk = event.get("chunk")
        if chunk:
            data = json.loads(chunk["bytes"])
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield delta["text"]


@retry(
    stop=stop_after_attempt(config.MAX_RETRY_COUNT),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_bedrock_error),
    reraise=True,
)
async def generate_vision(
    image_data: bytes,
    prompt: str,
    mime_type: str = "image/png",
    max_tokens: int = 2048,
) -> str:
    """
    Claude Vision で画像解析。Base64 エンコード画像を送信してテキスト説明を取得する。

    Args:
        image_data: 画像のバイナリデータ。
        prompt: 画像に関するプロンプト文字列。
        mime_type: 画像の MIME タイプ（デフォルト: "image/png"）。
        max_tokens: 生成する最大トークン数。

    Returns:
        画像解析結果のテキスト文字列。
    """
    client = get_bedrock_runtime()

    encoded_image = base64.b64encode(image_data).decode("utf-8")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": encoded_image,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
    }

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


@dataclass
class ToolUseBlock:
    """tool_use レスポンスブロックを表すデータクラス。"""

    id: str
    name: str
    input: dict[str, str | int | list[str] | None]


@dataclass
class TextBlock:
    """text レスポンスブロックを表すデータクラス。"""

    text: str


@dataclass
class ModelResponse:
    """tool_use 対応 LLM レスポンスを表すデータクラス。"""

    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens"
    content: list[ToolUseBlock | TextBlock]
    content_raw: list[
        dict[str, object]
    ]  # Bedrock API 形式そのまま（messages 再構築用）


@retry(
    stop=stop_after_attempt(config.MAX_RETRY_COUNT),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_bedrock_error),
    reraise=True,
)
async def generate_with_tools(
    messages: list[dict[str, object]],
    system_prompt: str,
    tools: list[dict[str, object]],
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> ModelResponse:
    """
    Claude でツール付きテキスト生成（非ストリーミング）。

    Args:
        messages: Messages API 形式のメッセージリスト。
        system_prompt: システムプロンプト文字列。
        tools: ツール定義リスト。
        max_tokens: 生成する最大トークン数。
        temperature: 生成の多様性を制御するパラメータ。

    Returns:
        ModelResponse（stop_reason, content ブロックリスト, content_raw）。
    """
    client = get_bedrock_runtime()

    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
        "tools": tools,
    }
    if system_prompt:
        body["system"] = [{"type": "text", "text": system_prompt}]

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    result = json.loads(response["body"].read())
    stop_reason = result.get("stop_reason", "end_turn")
    raw_content: list[dict[str, object]] = result.get("content", [])

    parsed_content: list[ToolUseBlock | TextBlock] = []
    for block in raw_content:
        if block.get("type") == "tool_use":
            parsed_content.append(
                ToolUseBlock(
                    id=block["id"],
                    name=block["name"],
                    input=block.get("input", {}),
                )
            )
        elif block.get("type") == "text":
            parsed_content.append(TextBlock(text=block.get("text", "")))

    return ModelResponse(
        stop_reason=stop_reason,
        content=parsed_content,
        content_raw=raw_content,
    )


async def generate_text_stream_with_messages(
    messages: list[dict[str, object]],
    system_prompt: str = "",
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    """
    マルチターンメッセージでのストリーミングテキスト生成。

    Args:
        messages: Messages API 形式のメッセージリスト。
        system_prompt: システムプロンプト文字列。
        max_tokens: 生成する最大トークン数。
        temperature: 生成の多様性を制御するパラメータ。

    Yields:
        生成されたテキストのチャンク文字列。
    """
    client = get_bedrock_runtime()

    body: dict = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system_prompt:
        body["system"] = [{"type": "text", "text": system_prompt}]

    response = await asyncio.to_thread(
        client.invoke_model_with_response_stream,
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    stream = response["body"]
    for event in stream:
        chunk = event.get("chunk")
        if chunk:
            data = json.loads(chunk["bytes"])
            if data.get("type") == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield delta["text"]


@retry(
    stop=stop_after_attempt(config.MAX_RETRY_COUNT),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_bedrock_error),
    reraise=True,
)
async def embed_texts(
    texts: list[str], input_type: str = "search_document"
) -> list[list[float]]:
    """
    Cohere Embed でテキストをベクトル化（バッチ処理対応、最大96テキスト/コール）。

    Args:
        texts: 埋め込み対象のテキストリスト。
        input_type: Cohere の input_type。ドキュメント側は "search_document"、
            検索クエリ側は "search_query" を指定する（既定はドキュメント側）。

    Returns:
        各テキストに対応する埋め込みベクトルのリスト。
    """
    client = get_bedrock_runtime()

    all_embeddings: list[list[float]] = []
    batch_size = 96

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        body: dict = {
            "texts": batch,
            "input_type": input_type,
            "truncate": "END",
        }

        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=config.BEDROCK_EMBED_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
        )

        result = json.loads(response["body"].read())
        all_embeddings.extend(result["embeddings"])

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """
    Cohere Embed で検索クエリをベクトル化。
    input_type="search_query" を使用する。

    Args:
        text: ベクトル化する検索クエリ文字列。

    Returns:
        クエリの埋め込みベクトル。
    """
    client = get_bedrock_runtime()

    body: dict = {
        "texts": [text],
        "input_type": "search_query",
        "truncate": "END",
    }

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=config.BEDROCK_EMBED_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    result = json.loads(response["body"].read())
    return result["embeddings"][0]


@retry(
    stop=stop_after_attempt(config.MAX_RETRY_COUNT),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_retryable_bedrock_error),
    reraise=True,
)
async def rerank(
    query: str,
    documents: list[str],
    top_n: int = 10,
) -> list[RerankResult]:
    """
    Cohere Rerank で検索結果をリランキングする。

    Args:
        query: 検索クエリ文字列。
        documents: 再ランク付け対象のドキュメントリスト。
        top_n: 返却する上位ドキュメント数。

    Returns:
        再ランク付けされた RerankResult のリスト。
    """
    client = get_bedrock_runtime()

    body: dict = {
        "api_version": 2,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }

    response = await asyncio.to_thread(
        client.invoke_model,
        modelId=config.BEDROCK_RERANK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )

    result = json.loads(response["body"].read())
    return [
        RerankResult(
            index=r["index"],
            relevance_score=r["relevance_score"],
            document=documents[r["index"]],
        )
        for r in result["results"]
    ]
