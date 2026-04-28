"""
ユーザープロファイルサービスモジュール。
チャット履歴を分析してユーザーの行動プロファイルを更新する。

キーワード頻度分析によりユーザーがよく参照するラインやカテゴリを抽出し、
user_behaviors テーブルに保存する。LLM は使用しない。
"""

from __future__ import annotations

import json
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.master_cache import get_master_cache
from app.models.database import Message, Session, UserBehavior

logger = logging.getLogger(__name__)

# プロファイルに保存するトップN件数
_TOP_N = 5
# 分析対象の直近メッセージ数
_RECENT_MESSAGE_LIMIT = 50
# recent_context に保存する最大文字数
_RECENT_CONTEXT_MAX_CHARS = 100


def _build_keyword_sets() -> tuple[dict[str, str], dict[str, str]]:
    """
    マスターキャッシュからライン名・コード・エイリアスの検索用辞書を構築する。

    Returns:
        (line_keywords, category_keywords) のタプル。
        各辞書はキーワード文字列 -> 正規コードのマッピング。
    """
    try:
        cache = get_master_cache()
    except RuntimeError:
        logger.warning(
            "マスターキャッシュが未初期化のため、キーワード辞書を構築できません"
        )
        return {}, {}

    line_keywords: dict[str, str] = {}
    for code, line_data in cache.lines.items():
        # コード自体をキーワードとして登録
        line_keywords[code.lower()] = code
        # 正式名称をキーワードとして登録
        line_keywords[line_data.name.lower()] = code
        # エイリアスをキーワードとして登録
        for alias in line_data.aliases:
            if alias:
                line_keywords[alias.lower()] = code

    # カテゴリはサイトコードをカテゴリとして使用する
    category_keywords: dict[str, str] = {}
    for code, site_data in cache.sites.items():
        category_keywords[code.lower()] = code
        category_keywords[site_data.name.lower()] = code
        for alias in site_data.aliases:
            if alias:
                category_keywords[alias.lower()] = code

    return line_keywords, category_keywords


def _count_keyword_mentions(
    messages: list[Message],
    line_keywords: dict[str, str],
    category_keywords: dict[str, str],
) -> tuple[Counter[str], Counter[str]]:
    """
    メッセージリスト中のキーワード出現回数をカウントする。

    テキストを小文字に変換した上で部分文字列マッチングを行う。
    長いキーワードを優先するため、キーワードを長さの降順でチェックする。

    Args:
        messages: 分析対象の Message ORM インスタンスリスト。
        line_keywords: キーワード -> ラインコードのマッピング辞書。
        category_keywords: キーワード -> サイトコードのマッピング辞書。

    Returns:
        (line_counter, category_counter) のタプル。
        各 Counter はコード -> 出現回数のマッピング。
    """
    line_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()

    # 長いキーワードを優先するためソート（最長一致）
    sorted_line_kw = sorted(line_keywords.keys(), key=len, reverse=True)
    sorted_cat_kw = sorted(category_keywords.keys(), key=len, reverse=True)

    for msg in messages:
        # ユーザーメッセージのみを対象とする（アシスタントの回答は除外）
        if msg.role != "user":
            continue

        content_lower = msg.content.lower()

        # ラインキーワードをカウント
        counted_line_codes: set[str] = set()
        for kw in sorted_line_kw:
            if kw in content_lower:
                code = line_keywords[kw]
                if code not in counted_line_codes:
                    line_counter[code] += 1
                    counted_line_codes.add(code)

        # カテゴリ（サイト）キーワードをカウント
        counted_cat_codes: set[str] = set()
        for kw in sorted_cat_kw:
            if kw in content_lower:
                code = category_keywords[kw]
                if code not in counted_cat_codes:
                    category_counter[code] += 1
                    counted_cat_codes.add(code)

    return line_counter, category_counter


async def update_user_profile(user_id: str, db: AsyncSession) -> None:
    """
    ユーザーの直近チャット履歴を分析して user_behaviors レコードを更新する。

    処理ステップ:
      1. ユーザーの直近 50 件のメッセージを取得する
      2. マスターキャッシュのキーワードと照合して出現頻度をカウントする
      3. 頻出ライン上位 5 件を frequent_lines に保存する
      4. 頻出カテゴリ上位 5 件を frequent_categories に保存する
      5. 最新ユーザーメッセージの先頭 100 文字を recent_context に保存する

    エラーが発生した場合はログに記録して静かに終了する（チャットフローをブロックしない）。

    Args:
        user_id: 対象ユーザーの ID。
        db: 非同期データベースセッション。
    """
    try:
        # Step 1: ユーザーの直近メッセージを取得する
        # Session -> Message の JOIN でユーザーに紐づくメッセージを取得
        messages_result = await db.execute(
            select(Message)
            .join(Session, Message.session_id == Session.id)
            .where(Session.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(_RECENT_MESSAGE_LIMIT)
        )
        messages: list[Message] = list(messages_result.scalars().all())

        if not messages:
            logger.debug(
                "プロファイル更新: ユーザー %s のメッセージが存在しません", user_id
            )
            return

        # Step 2: マスターキャッシュからキーワード辞書を構築する
        line_keywords, category_keywords = _build_keyword_sets()

        # Step 3 & 4: キーワード出現頻度をカウントする
        line_counter, category_counter = _count_keyword_mentions(
            messages, line_keywords, category_keywords
        )

        # 頻出上位 N 件を抽出する（出現回数 0 のものは除外）
        top_lines: list[str] = [code for code, _ in line_counter.most_common(_TOP_N)]
        top_categories: list[str] = [
            code for code, _ in category_counter.most_common(_TOP_N)
        ]

        # Step 5: 最新ユーザーメッセージを recent_context として取得する
        # messages は降順なので先頭がもっとも新しい。ユーザーメッセージを探す
        recent_context: str | None = None
        for msg in messages:
            if msg.role == "user":
                recent_context = msg.content[:_RECENT_CONTEXT_MAX_CHARS]
                break

        # UserBehavior レコードを UPSERT する
        behavior_result = await db.execute(
            select(UserBehavior).where(UserBehavior.user_id == user_id)
        )
        behavior = behavior_result.scalar_one_or_none()

        if behavior is None:
            behavior = UserBehavior(user_id=user_id)
            db.add(behavior)

        behavior.frequent_lines = json.dumps(top_lines, ensure_ascii=False)
        behavior.frequent_categories = json.dumps(top_categories, ensure_ascii=False)
        behavior.recent_context = recent_context

        await db.commit()

        logger.info(
            "プロファイル更新完了: user_id=%s, lines=%s, categories=%s",
            user_id,
            top_lines,
            top_categories,
        )

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "プロファイル更新中にエラーが発生しました: user_id=%s, error=%s",
            user_id,
            exc,
        )
