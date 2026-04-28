"""
ユーザーメモリ自動抽出サービス。

チャット会話からユーザーに関する情報を自動的に抽出し、
UserMemory(source="auto") として保存する。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import bedrock_client
from app.models.database import UserMemory

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM_PROMPT = """\
以下の会話から、ユーザー自身に関する情報（所属、役割、担当ライン、好み、専門分野など）を抽出してください。
一般的な質問や技術的な問い合わせからは何も抽出しないでください。

重要: 各項目は短い日本語の文として出力してください。JSONオブジェクトや構造化データではなく、人が読める自然な文にしてください。
例: ["所属はソ企", "担当ラインはモータ組立43号（KJMA43）", "田業（SAND）拠点で勤務"]

既存のユーザー情報:
{existing_memories}

会話:
ユーザー: {user_query}
アシスタント: {assistant_answer}

新しく判明したユーザー情報をJSON文字列配列で返してください。何もなければ空配列[]を返してください。
出力はJSON配列のみ。説明不要。"""


async def extract_and_save_memories(
    user_id: str,
    user_query: str,
    assistant_answer: str,
    db: AsyncSession,
) -> None:
    """
    会話からユーザーに関する新情報を抽出し、自動メモリとして保存する。

    LLM にユーザー発言とAI回答を渡し、ユーザーに関する事実を抽出する。
    既存メモリと重複しない情報のみ保存する。
    失敗してもチャット応答には影響しない（呼び出し元で try-except する）。

    Args:
        user_id: ユーザー ID。
        user_query: ユーザーの発言テキスト。
        assistant_answer: アシスタントの回答テキスト。
        db: 非同期データベースセッション。
    """
    # 既存メモリを取得（重複チェック用）
    result = await db.execute(
        select(UserMemory.content)
        .where(UserMemory.user_id == user_id)
        .order_by(UserMemory.created_at)
    )
    existing_contents = [row[0] for row in result.all()]
    existing_text = (
        "\n".join(f"- {c}" for c in existing_contents)
        if existing_contents
        else "（なし）"
    )

    # LLM に抽出を依頼
    prompt = _EXTRACTION_SYSTEM_PROMPT.format(
        existing_memories=existing_text,
        user_query=user_query,
        assistant_answer=assistant_answer[:1000],  # 回答は長すぎる場合があるので制限
    )

    response = await bedrock_client.generate_text(
        prompt=prompt,
        system_prompt="",
        max_tokens=512,
        temperature=0.1,
    )

    # JSON 配列をパース
    extracted = _parse_extraction_response(response)
    if not extracted:
        return

    # 重複チェック: 既存メモリと完全一致 or 部分包含のものは除外
    new_items = _filter_duplicates(extracted, existing_contents)
    if not new_items:
        logger.debug("自動メモリ: 新規項目なし（全て既存と重複）")
        return

    # 保存
    now = datetime.now(timezone.utc).isoformat()
    for content in new_items:
        memory = UserMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            content=content,
            source="auto",
            created_at=now,
            updated_at=now,
        )
        db.add(memory)

    await db.commit()
    logger.info("自動メモリ: %d 件を保存しました (user_id=%s)", len(new_items), user_id)


def _parse_extraction_response(response: str) -> list[str]:
    """LLM レスポンスから JSON 配列をパースする。"""
    text = response.strip()

    # ```json ... ``` で囲まれている場合の対応
    if text.startswith("```"):
        lines = text.splitlines()
        json_lines = [line for line in lines if not line.startswith("```")]
        text = "\n".join(json_lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # JSON 配列部分だけ抽出を試みる
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.debug("自動メモリ: LLM 応答のパースに失敗（JSON配列なし）")
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.debug("自動メモリ: LLM 応答のパースに失敗")
            return []

    if not isinstance(parsed, list):
        return []

    # 文字列のみ取り出し、空文字は除外
    return [str(item).strip() for item in parsed if str(item).strip()]


def _filter_duplicates(
    new_items: list[str],
    existing: list[str],
) -> list[str]:
    """既存メモリと重複する項目を除外する。"""
    filtered: list[str] = []
    for item in new_items:
        is_duplicate = False
        for ex in existing:
            # 完全一致 or 一方が他方を含む場合は重複とみなす
            if item == ex or item in ex or ex in item:
                is_duplicate = True
                break
        if not is_duplicate:
            filtered.append(item)
    return filtered
