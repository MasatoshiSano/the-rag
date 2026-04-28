---
title: "RAGチャットからユーザーの関心を自動抽出する — LLMメモリ抽出 + キーワード頻度プロファイル"
emoji: "🧠"
type: "tech"
topics: ["LLM", "RAG", "Python", "Personalization", "AI"]
published: true
category: "Architecture"
date: "2026-04-28"
description: "チャット完了後にLLMでユーザー情報を自動抽出するメモリ機能と、LLMを使わずキーワード頻度カウントで行動プロファイルを構築する2つのアプローチを解説"
---

## はじめに

RAGチャットシステムで「ユーザーが何に関心があるのか」を理解することは、パーソナライズされた回答提供とコンテキスト最適化に不可欠です。本記事では、RAG Phantomで実装した2つのユーザー理解アプローチを解説します。

- **LLMメモリ抽出**: 高精度だがAPI呼び出しコスト発生
- **キーワード頻度プロファイル**: LLM不使用で無料、ドメイン辞書ベース

どちらも独立して動作し、失敗時もチャットフロー全体をブロックしません。

## 1. LLMメモリ抽出 — 事実を精密に記憶させる

### 何をするのか

チャット応答が完了した直後、会話内容を分析して「ユーザー自身に関する新しい情報」をJSON形式で抽出します。既存メモリと統合し、重複を除去します。

```
会話例）
ユーザー: 「弊社ソ企のモータ43号の調査をしています」
アシスタント: 「モータ43号は...」

抽出結果:
[
  "所属: ソ企",
  "担当: モータ43号"
]
```

### システムプロンプト設計

既存メモリを前提条件として与え、「新しく判明した情報のみ」を抽出させます。

```python
_EXTRACTION_SYSTEM_PROMPT = """
以下の会話から、ユーザー自身に関する情報を抽出してください。

既存のユーザー情報:
{existing_memories}

ユーザーの質問: {user_query}
アシスタントの回答: {assistant_answer}

指示:
- 抽出した情報は「キー: 値」形式で記述してください
- 既存情報と重複する内容は含めないでください
- 会話から直接読み取れる情報のみを抽出してください
- JSON形式の文字列配列で返してください

例:
["所属: ソ企", "担当: モータ43号", "よく使うツール: DuckDB"]
"""
```

### 実装のポイント

#### 1）重複排除ロジック

単純な等値比較では不足。包含関係をチェックして冗長性を排除します。

```python
def _is_duplicate_memory(item: str, existing: list[str]) -> bool:
    """包含関係による重複チェック"""
    for ex in existing:
        # "所属: ソ企" と "ソ企" の関係を検出
        if item in ex or ex in item:
            return True
    return False
```

#### 2）LLMレスポンスパース — 堅牢性を重視

Claudeは時に意図しないフォーマットで返す可能性があります。複数のパース戦略を用意します。

```python
def _parse_memory_json(response_text: str) -> list[str]:
    """複数のパース戦略で堅牢性を確保"""
    text = response_text.strip()

    # 戦略1: JSONコードブロックの抽出
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()

    # 戦略2: 最初の [ と最後の ] を検出
    start_idx = text.find("[")
    end_idx = text.rfind("]")
    if start_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]

    # JSONをパース
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(item).strip() for item in data]
        return []
    except json.JSONDecodeError:
        logging.warning(f"Failed to parse memory JSON: {response_text}")
        return []
```

#### 3）実行フロー

```python
async def extract_user_memory(
    user_id: str,
    user_query: str,
    assistant_answer: str,
    existing_memories: list[str] = None,
) -> list[str]:
    """チャット後のメモリ自動抽出"""
    if existing_memories is None:
        existing_memories = []

    try:
        # LLMに抽出させる
        prompt = _EXTRACTION_SYSTEM_PROMPT.format(
            existing_memories="\n".join(existing_memories) or "なし",
            user_query=user_query,
            assistant_answer=assistant_answer,
        )

        response = await bedrock_client.invoke_model(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            messages=[{"role": "user", "content": prompt}],
        )

        new_memories = _parse_memory_json(response.get("content", [{}])[0].get("text", ""))

        # 既存メモリと統合
        for mem in new_memories:
            if not _is_duplicate_memory(mem, existing_memories):
                existing_memories.append(mem)

        return existing_memories

    except Exception as e:
        logging.warning(f"Memory extraction failed for user {user_id}: {e}")
        return existing_memories  # フローをブロックしない
```

## 2. キーワード頻度プロファイル — LLM不使用で関心を推測

### 何をするのか

ドメイン辞書（ライン名、コード、エイリアス）を活用し、直近50メッセージ内でキーワード出現頻度をカウント。LLM呼び出しなしで、ユーザーが「最近どのラインに関心があるのか」を特定します。

```
直近メッセージ内容分析:
- "モータ43号" → 4回出現 → frequent_lines: "モータ43号"
- "品質" → 3回出現 → frequent_categories: "品質管理"
- recent_context: "モータ43号の...について最近よく質問している"
```

### マスターデータ準備

ドメイン辞書を構築します。ここでは「製造ラインマスタ」を想定。

```python
LINES_MASTER = {
    "ソ企": {
        "モータ43号": ["モータ43号", "M43", "43号"],
        "アクチュエータLV": ["アクチュエータLV", "LV", "LV型"],
    },
    "セ企": {
        "コンプレッサ200": ["コンプレッサ200", "CP200", "200番"],
    }
}

CATEGORIES_MASTER = {
    "品質管理": ["不良", "品質", "QC", "検査"],
    "生産計画": ["スケジュール", "納期", "計画", "工程"],
    "保全": ["故障", "メンテナンス", "保守"],
}
```

### 最長一致アルゴリズム

複数のキーワードが重複する場合、より具体的なキーワードをマッチさせます。

```python
def _build_search_dict(master: dict) -> list[tuple[str, str]]:
    """マスターから (キーワード, コード) のペアを構築
    最長一致のため長さ降順でソート
    """
    pairs = []
    for section, items in master.items():
        for code, aliases in items.items():
            for alias in aliases:
                pairs.append((alias.lower(), code))

    # 長さ降順でソート（最長一致を優先）
    return sorted(pairs, key=lambda x: len(x[0]), reverse=True)

def _count_keywords(
    messages: list[dict],
    lines_pairs: list[tuple[str, str]],
    categories_pairs: list[tuple[str, str]],
) -> tuple[dict, dict]:
    """直近メッセージからキーワード出現頻度をカウント"""
    line_counts = {}
    category_counts = {}

    for msg in messages:
        text = msg.get("content", "").lower()
        counted_codes = set()  # 1メッセージ内での重複カウント防止

        # ラインのマッチング
        for keyword, code in lines_pairs:
            if keyword in text and code not in counted_codes:
                line_counts[code] = line_counts.get(code, 0) + 1
                counted_codes.add(code)

        counted_categories = set()

        # カテゴリのマッチング
        for keyword, category in categories_pairs:
            if keyword in text and category not in counted_categories:
                category_counts[category] = category_counts.get(category, 0) + 1
                counted_categories.add(category)

    return line_counts, category_counts
```

### プロファイル生成

頻度カウント結果から上位5件を抽出し、最新コンテキストを付加します。

```python
async def build_user_profile(
    user_id: str,
    message_limit: int = 50,
) -> dict:
    """ユーザーの行動プロファイルを構築（LLM不使用）"""
    try:
        # 直近N件のメッセージを取得
        recent_messages = await get_recent_messages(
            user_id=user_id,
            limit=message_limit,
        )

        if not recent_messages:
            return {
                "frequent_lines": [],
                "frequent_categories": [],
                "recent_context": "",
            }

        # キーワード検索辞書を構築
        lines_pairs = _build_search_dict(LINES_MASTER)
        categories_pairs = _build_search_dict(CATEGORIES_MASTER)

        # カウント実行
        line_counts, category_counts = _count_keywords(
            recent_messages,
            lines_pairs,
            categories_pairs,
        )

        # 上位5件を抽出
        frequent_lines = sorted(
            line_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        frequent_categories = sorted(
            category_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        # 最新コンテキスト（先頭100文字）
        recent_context = recent_messages[-1].get("content", "")[:100]

        return {
            "frequent_lines": [line for line, count in frequent_lines],
            "frequent_categories": [cat for cat, count in frequent_categories],
            "recent_context": recent_context,
        }

    except Exception as e:
        logging.warning(f"Profile building failed for user {user_id}: {e}")
        return {
            "frequent_lines": [],
            "frequent_categories": [],
            "recent_context": "",
        }
```

## 3. 2つのアプローチを統合する

### コンテキスト注入の設計

クエリ分析時に、メモリとプロファイルの両方をシステムプロンプトに注入します。

```python
async def analyze_query_with_context(
    user_id: str,
    query: str,
) -> str:
    """ユーザーコンテキストを含めた高度なクエリ分析"""

    # メモリとプロファイルを並行取得
    memories, profile = await asyncio.gather(
        get_user_memories(user_id),
        build_user_profile(user_id),
    )

    context_text = f"""
ユーザー情報:
- 既知の背景: {'; '.join(memories) if memories else 'なし'}
- 最近の関心: ライン={', '.join(profile['frequent_lines']) if profile['frequent_lines'] else 'なし'}
- 最近の質問: {profile['recent_context']}
    """

    system_prompt = f"""
あなたはRAG検索アシスタントです。
以下のユーザー情報を踏まえて、より適切な検索クエリに変換してください。

{context_text}

ユーザーの質問: {query}

改善版クエリを出力してください。
    """

    response = await bedrock_client.invoke_model(...)
    return response
```

### エラーハンドリング戦略

両アプローチとも失敗時、チャットフロー全体をブロックしません。gracefulに機能を低下させます。

```python
async def get_user_context(user_id: str) -> dict:
    """ユーザーコンテキスト取得（部分失敗対応）"""
    result = {
        "memories": [],
        "profile": {
            "frequent_lines": [],
            "frequent_categories": [],
            "recent_context": "",
        },
        "errors": [],
    }

    # メモリ抽出の試行
    try:
        result["memories"] = await get_user_memories(user_id)
    except Exception as e:
        logging.warning(f"Memory fetch failed: {e}")
        result["errors"].append("memory_fetch")

    # プロファイル構築の試行
    try:
        result["profile"] = await build_user_profile(user_id)
    except Exception as e:
        logging.warning(f"Profile build failed: {e}")
        result["errors"].append("profile_build")

    # エラーが発生していても、利用可能なデータで続行
    return result
```

## 4. パフォーマンス最適化

### キャッシング戦略

プロファイルは計算コストがかかるため、直近1分間のキャッシュを導入します。

```python
_profile_cache: dict[str, tuple[float, dict]] = {}
_PROFILE_CACHE_TTL = 60  # 秒

async def build_user_profile(user_id: str) -> dict:
    """キャッシュ付きプロファイル構築"""
    now = time.time()

    if user_id in _profile_cache:
        cached_time, cached_profile = _profile_cache[user_id]
        if now - cached_time < _PROFILE_CACHE_TTL:
            return cached_profile

    # 計算処理...
    profile = {...}

    _profile_cache[user_id] = (now, profile)
    return profile
```

### 並行処理

メモリ抽出とプロファイル構築は独立しているため、`asyncio.gather`で並行実行します。

```python
# 直列実行（遅い）
memories = await get_user_memories(user_id)
profile = await build_user_profile(user_id)

# 並行実行（高速）
memories, profile = await asyncio.gather(
    get_user_memories(user_id),
    build_user_profile(user_id),
)
```

## 5. 使い分けの指針

| 特性 | LLMメモリ抽出 | キーワード頻度プロファイル |
|------|-----------|-------------------------|
| **精度** | 高（自然言語理解） | 中（パターンマッチ） |
| **コスト** | API呼び出し発生 | 無料 |
| **対象情報** | 所属、役職、タスク、目標 | 関心ラインの傾向 |
| **実装難度** | 低（プロンプト設計） | 中（辞書整備） |
| **失敗時の影響** | 軽微（新情報逃す） | 軽微（傾向が使えない） |

### 推奨ユースケース

**LLMメモリ抽出が活躍:**
- 「このユーザーはどこに所属?」→ メモリから取得
- 「前回の話題は?」→ メモリで追跡
- 個別ユーザーの背景を正確に把握

**キーワード頻度プロファイルが活躍:**
- 「今月は何の質問が多い?」→ プロファイルから判定
- RAG検索時の暗黙的リランキング
- コスト削減（LLM呼び出し0）

## 6. 実装例：統合エンドポイント

チャット完了時に両機能を実行するエンドポイント例です。

```python
@router.post("/chat/complete")
async def complete_chat(
    user_id: str,
    session_id: str,
    user_query: str,
    assistant_answer: str,
):
    """チャット完了時のメモリ + プロファイル更新"""

    try:
        # メモリ抽出とプロファイル構築を並行実行
        existing_memories = await get_user_memories(user_id)

        updated_memories, profile = await asyncio.gather(
            extract_user_memory(
                user_id=user_id,
                user_query=user_query,
                assistant_answer=assistant_answer,
                existing_memories=existing_memories,
            ),
            build_user_profile(user_id),
        )

        # データベースに保存
        await save_user_memories(user_id, updated_memories)
        await save_user_profile(user_id, profile)

        return {
            "status": "success",
            "memories_count": len(updated_memories),
            "frequent_lines": profile["frequent_lines"],
        }

    except Exception as e:
        logging.error(f"Chat completion handler error: {e}")
        return {"status": "partial_failure", "error": str(e)}
```

## まとめ

RAGチャットシステムでユーザーを理解する2つの手法：

1. **LLMメモリ抽出**: 高精度の事実抽出、コスト発生、設計シンプル
2. **キーワード頻度プロファイル**: 無料で行動傾向把握、辞書整備が鍵

両方を組み合わせることで、「誰か」「何に関心があるか」を包括的に把握でき、パーソナライズされたRAG体験を実現できます。

エラーハンドリングを適切に設計すれば、どちらかが失敗してもチャットフローに影響なし。本番環境で安心して運用できます。

---

## 参考リンク

- [RAG Phantom リポジトリ](https://github.com/your-repo)
- [Claude API Documentation](https://docs.anthropic.com/ja/api)
- [SQLAlchemy 2.0 非同期ガイド](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
