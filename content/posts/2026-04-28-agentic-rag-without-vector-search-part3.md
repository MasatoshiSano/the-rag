---
title: "ベクトル検索を使わないRAG（第3回：リアルタイム進捗配信編）— SSEでエージェントの思考過程を可視化する"
emoji: "📡"
type: "tech"
topics: ["RAG", "SSE", "FastAPI", "React", "AI Agent"]
published: true
category: "Architecture"
date: "2026-04-28"
description: "エージェンティック検索の各ステップ（思考中→検索中→N件発見）をSSEでフロントエンドにリアルタイム配信し、擬似ストリーミングでUXを向上させる実装を解説"
series: "ベクトル検索を使わないRAG"
seriesOrder: 3
---

> **このシリーズ: 全3回**
> 1. [第1回: エージェントループ設計編](/posts/agentic-rag-without-vector-search-part1)
> 2. [第2回: 検索エンジン編](/posts/agentic-rag-without-vector-search-part2)
> 3. [第3回: リアルタイム進捗配信編](/posts/agentic-rag-without-vector-search-part3) ← 今ここ

前2回では、エージェントが文書を検索し、その結果を判断してアクションを決定するループを実装しました。しかし、ユーザー視点では、回答が完成するまで画面が何もしない状態になってしまいます。

この記事では、**Server-Sent Events（SSE）** を使ってエージェントの思考過程をリアルタイムで可視化し、さらに完成済みのテキストを疑似ストリーミングで配信する実装パターンを解説します。

## SSEイベント設計：エージェントステップの可視化

### イベントシーケンス

RAG検索のライフサイクルを、バックエンドが以下のシーケンスでイベントを発行します：

```
session           ← セッション情報（KB ID等）
status(analyzing) ← 分析中
  ↓
[agentic_step × N（ループの各イテレーション）]
  agentic_step(thinking)  ← エージェントが思考中
  agentic_step(searching) ← 検索実行中
  agentic_step(found)     ← N件の文書発見
  ↓
status(generating) ← 回答生成中
token × N          ← トークン逐次配信（本物またはチャンク）
sources            ← 参考文書リスト
complete           ← イベントストリーム終了
done               ← クライアント側で画面更新を完了
```

### バックエンド側の実装

#### SSEヘルパー関数

FastAPIでSSEを送信するための基本的なヘルパー関数です：

```python
def _sse(event: str, data: dict) -> str:
    """SSEメッセージをフォーマット"""
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"
```

このヘルパーは、イベントタイプと任意のデータ辞書を受け取り、JSON形式でカプセル化して返します。`ensure_ascii=False` により、日本語を含むテキストもそのまま送信できます。

#### エージェントステップイベント

エージェントのループ内で、各ステップごとにイベントを発行します：

```python
async def _search_and_analyze_with_agent(
    session: Session,
    kb_id: str,
    max_iterations: int = 5
) -> AsyncGenerator[str, None]:
    """エージェントループの実装"""

    iteration = 0
    while iteration < max_iterations:
        iteration += 1

        # 1. 思考ステップ
        yield _sse("agentic_step", {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "status": "thinking",
        })

        # エージェントが次のアクション（検索クエリ）を決定
        action = await agent_decide_next_action(...)

        # 2. 検索ステップ
        yield _sse("agentic_step", {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "status": "searching",
            "search_query": f"文書内検索: 「{action.query}」",
        })

        # 検索を実行
        results = await full_text_search(action.query, kb_id)

        # 3. 発見ステップ
        yield _sse("agentic_step", {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "status": "found",
            "result_count": len(results),
            "documents": [
                {"id": r.id, "title": r.title, "snippet": r.snippet[:100]}
                for r in results
            ]
        })

        # エージェントが結果を処理し、終了判定
        if action.end_turn or iteration >= max_iterations:
            break

    # 回答生成へ
    yield _sse("status", {"status": "generating"})
```

### StreamingResponseの設定

FastAPIでSSEを配信するエンドポイントの実装：

```python
from fastapi.responses import StreamingResponse

@app.post("/api/chat")
async def chat_agentic(
    req: ChatRequest,
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> StreamingResponse:
    """SSEでエージェント思考プロセスを配信"""

    async def event_generator():
        session = db.get_or_create_session(kb_id=req.kb_id, user_id=x_user_id)

        # セッション情報を初期化
        yield _sse("session", {
            "session_id": session.id,
            "kb_id": session.kb_id,
        })
        yield _sse("status", {"status": "analyzing"})

        # エージェントループを実行
        async for event in _search_and_analyze_with_agent(
            session, req.kb_id, max_iterations=5
        ):
            yield event

        # 回答生成のストリーミング
        async for token in bedrock_client.generate_text_stream_with_messages(...):
            yield _sse("token", {"text": token})

        # 参考文書を送信
        yield _sse("sources", {"documents": [...]})

        # イベントストリーム完了
        yield _sse("complete", {"message": "検索と生成が完了しました"})

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### Nginxの設定

バックエンドがSSEを正しく配信するには、Nginxで `X-Accel-Buffering` をディスエーブルする必要があります：

```nginx
location /api/chat {
    proxy_pass http://backend:8000;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;

    # SSEバッファリングを無効化
    proxy_buffering off;
    proxy_cache off;
    proxy_http_version 1.1;
    proxy_set_header Connection '';

    # ロングポーリング対応
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;

    # SSE用ヘッダーを追加
    add_header X-Accel-Buffering no;
}
```

## 疑似ストリーミング：完成済みテキストの逐次配信

### 問題：エージェントが途中で終了する場合

エージェントループ内で最終回答が決定した場合、LLMはそのテキスト全体を一度に返します。しかし、ユーザーにはやはり「リアルタイム生成」のように見せたいです。

```python
# エージェントが終了判定
if agent_decision.end_turn:
    # ここで最終テキストが得られている（完成済み）
    final_text = agent_decision.response_text
    # 例: "検索の結果、モータは43番目に配置されています..."
```

このような場合に、完成済みのテキストを20文字ずつのチャンクに分割してストリーミング風に配信するテクニックが「疑似ストリーミング」です。

### 実装パターン

```python
async def _generate_response_with_streaming(
    final_text: str | None,
    bedrock_client: BedrockClient,
    max_iterations: int,
    iteration: int,
) -> AsyncGenerator[str, None]:
    """
    - final_text がある場合：チャンク分割して疑似ストリーミング
    - ない場合：実際のLLMストリーミングを使用
    """

    if final_text:
        # 擬似ストリーミング：既にある回答を小分けにして配信
        chunk_size = 20
        for i in range(0, len(final_text), chunk_size):
            chunk = final_text[i : i + chunk_size]
            yield _sse("token", {"text": chunk})
    else:
        # 実ストリーミング：最大イテレーションに達した場合、ここで実際にLLM呼び出し
        async for token in bedrock_client.generate_text_stream_with_messages(
            messages=context_messages,
            model="claude-3-5-sonnet-20241022",
            system=system_prompt,
            temperature=0.5,
        ):
            yield _sse("token", {"text": token})
```

### ユースケースの解説

1. **エージェントが途中で確信を持って終了** → `final_text` が得られる → 疑似ストリーミング
   - 例：文書から直接抽出した答え「モータ番号は43です」
   - ユーザーは画面に逐次テキストが表示されるように見える
   - 実際には既に完成済みだが、UXは良好

2. **エージェントが最大イテレーション（5回）に達した** → `final_text` は `None` → 実ストリーミング
   - LLMの完全な生成プロセスをリアルタイム配信
   - ファクト生成や複数情報の統合が必要な場合

## フロントエンド側のSSEクライアント実装

### EventSourceではなくfetch + ReadableStreamを使う理由

標準の `EventSource` APIは、カスタムHTTPヘッダーを送信できません。RAGシステムではユーザーIDを `X-User-Id` ヘッダーで送信する必要があるため、`fetch` + `ReadableStream` の組み合わせを使用します。

### フロントエンド実装

```typescript
// types/sse.ts
export type SseEvent =
  | { type: "session"; sessionId: string; kbId: string }
  | { type: "status"; status: "analyzing" | "generating" }
  | { type: "agenticStep"; iteration: number; maxIterations: number; substatus: "thinking" | "searching" | "found"; searchQuery?: string; resultCount?: number }
  | { type: "token"; text: string }
  | { type: "sources"; documents: Array<{ id: string; title: string }> }
  | { type: "complete"; message: string };

// hooks/useChatSSE.ts
export const useChatSSE = () => {
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const chat = async (kbId: string, query: string) => {
    setIsLoading(true);
    setEvents([]);
    abortControllerRef.current = new AbortController();

    try {
      const userId = localStorage.getItem("rag-phantom-user-id") || "";
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
        body: JSON.stringify({ kb_id: kbId, query }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.body) throw new Error("Response body not available");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.trim().startsWith("data:")) continue;

          try {
            const jsonStr = line.slice(5).trim(); // "data: " を削除
            const raw = JSON.parse(jsonStr);
            const event = convertBackendEvent(raw);
            setEvents((prev) => [...prev, event]);
          } catch (err) {
            console.error("Failed to parse SSE event:", err);
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // キャンセルされた場合、最後のテキストに「中断」表記を追加
        setEvents((prev) => [
          ...prev,
          { type: "token", text: "（回答が中断されました）" },
        ]);
      } else {
        console.error("Chat SSE error:", err);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const cancel = () => {
    abortControllerRef.current?.abort();
  };

  return { events, isLoading, chat, cancel };
};
```

### イベント変換関数

バックエンドの `snake_case` をフロントエンドの `camelCase` に統一：

```typescript
// utils/convertBackendEvent.ts
function convertBackendEvent(raw: any): SseEvent {
  switch (raw.event) {
    case "session":
      return {
        type: "session",
        sessionId: raw.data.session_id,
        kbId: raw.data.kb_id,
      };
    case "status":
      return {
        type: "status",
        status: raw.data.status,
      };
    case "agentic_step":
      return {
        type: "agenticStep",
        iteration: raw.data.iteration,
        maxIterations: raw.data.max_iterations,
        substatus: raw.data.status,
        searchQuery: raw.data.search_query,
        resultCount: raw.data.result_count,
      };
    case "token":
      return {
        type: "token",
        text: raw.data.text,
      };
    case "sources":
      return {
        type: "sources",
        documents: raw.data.documents,
      };
    case "complete":
      return {
        type: "complete",
        message: raw.data.message,
      };
    default:
      throw new Error(`Unknown event: ${raw.event}`);
  }
}
```

### チャット画面でのイベント処理

```typescript
// pages/ChatPage.tsx
export const ChatPage: React.FC = () => {
  const { events, isLoading, chat, cancel } = useChatSSE();
  const [displayText, setDisplayText] = useState("");
  const [agenticSteps, setAgenticSteps] = useState<AgenticStep[]>([]);

  useEffect(() => {
    for (const event of events) {
      switch (event.type) {
        case "agenticStep":
          setAgenticSteps((prev) => [
            ...prev,
            {
              iteration: event.iteration,
              maxIterations: event.maxIterations,
              substatus: event.substatus,
              searchQuery: event.searchQuery,
            },
          ]);
          break;

        case "token":
          setDisplayText((prev) => prev + event.text);
          break;

        case "status":
          // ローディング状態を更新（例：「分析中」→「生成中」）
          break;

        case "sources":
          // 参考文書をサイドバーに表示
          break;

        case "complete":
          // SSEストリーム完了
          break;
      }
    }
  }, [events]);

  const handleSend = (query: string) => {
    setDisplayText("");
    setAgenticSteps([]);
    chat("kb-123", query);
  };

  return (
    <div>
      {/* エージェントステップのリアルタイム表示 */}
      <div className="agent-progress">
        {agenticSteps.map((step, idx) => (
          <div key={idx} className="step">
            <div>イテレーション {step.iteration}/{step.maxIterations}</div>
            <div className="substatus">
              {step.substatus === "thinking" && "思考中..."}
              {step.substatus === "searching" && (
                <>
                  検索中: <code>{step.searchQuery}</code>
                </>
              )}
              {step.substatus === "found" && `${step.found}件発見`}
            </div>
          </div>
        ))}
      </div>

      {/* 生成中のテキスト */}
      <div className="response">
        {displayText}
        {isLoading && <span className="cursor">▌</span>}
      </div>

      {/* 送信・キャンセルボタン */}
      <button onClick={() => handleSend(query)} disabled={isLoading}>
        送信
      </button>
      {isLoading && <button onClick={cancel}>キャンセル</button>}
    </div>
  );
};
```

## キャンセル処理の実装

ユーザーが「キャンセル」ボタンをクリックしたとき、`AbortController` でfetchをキャンセルします。

```typescript
const cancel = () => {
  abortControllerRef.current?.abort();
};

// useChatSSEの try-catch で処理
catch (err) {
  if (err instanceof DOMException && err.name === "AbortError") {
    // キャンセルされた場合、ユーザーに通知
    setEvents((prev) => [
      ...prev,
      {
        type: "token",
        text: "（回答が中断されました）",
      },
    ]);
  } else {
    console.error("Chat SSE error:", err);
  }
}
```

バックエンド側でも、ストリーミング中にクライアントが切断された場合は自動的にジェネレータが終了するため、追加の処理は不要です。

## SSE設計のベストプラクティス

### 1. イベント粒度の最適化

細かすぎるイベント（1文字ごとなど）はオーバーヘッドが大きいため、適切なサイズを選びます。

```python
# 推奨：20-100文字のチャンク
chunk_size = 20

# 避けるべき：1文字ごと（オーバーヘッドが大きい）
chunk_size = 1

# 避けるべき：全文を1イベント（インタラクティブ性が失われる）
chunk_size = len(final_text)
```

### 2. エラーハンドリング

```python
yield _sse("error", {
    "code": "SEARCH_FAILED",
    "message": "文書検索に失敗しました。しばらく後に再度試してください。",
    "retriable": True,
})
```

### 3. ログとモニタリング

```python
import logging

logger = logging.getLogger(__name__)

async def _search_and_analyze_with_agent(...):
    logger.info(f"Agent loop started: kb_id={kb_id}, max_iterations={max_iterations}")

    for iteration in range(max_iterations):
        logger.debug(f"Iteration {iteration}: status=thinking")
        # ...
        logger.debug(f"Iteration {iteration}: found {len(results)} documents")
```

## パフォーマンス考慮事項

### メモリ使用量

```python
# OK：イベントを逐次yield（ストリーミング）
async for token in bedrock_client.stream(...):
    yield _sse("token", {"text": token})

# NG：全イベントをメモリに蓄積
events = []
async for token in bedrock_client.stream(...):
    events.append(_sse("token", {"text": token}))
return events  # メモリ爆発
```

### ネットワークバッファリング

Nginxでバッファリングを無効化する際、フロントエンドが読み込み可能な状態でなければ、バックエンド側のメモリが増加します。フロントエンドがイベントを適切に処理しているか監視しましょう。

```typescript
// イベント処理の遅延を監視
const startTime = Date.now();
for (const event of largeEventBatch) {
  // イベント処理
}
const duration = Date.now() - startTime;
if (duration > 100) {
  console.warn(`Slow event processing: ${duration}ms`);
}
```

## デバッグのコツ

### バックエンド側

```bash
# SSEが正しく送信されているか確認
curl -H "X-User-Id: test-user" \
     -H "Content-Type: application/json" \
     -d '{"kb_id": "kb-123", "query": "モータ"}' \
     http://localhost:8010/api/chat

# 出力例：
# data: {"event": "session", "data": {"session_id": "...", "kb_id": "kb-123"}}
# data: {"event": "status", "data": {"status": "analyzing"}}
# ...
```

### フロントエンド側

```typescript
// コンソールでSSEイベントをログ
const reader = response.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = new TextDecoder().decode(value);
  console.log("SSE payload:", text); // 生のペイロードを確認

  // JSON パースのテスト
  try {
    JSON.parse(text.slice(5));
  } catch (err) {
    console.error("Invalid JSON:", text);
  }
}
```

### ブラウザの開発者ツール

Chrome DevTools の Network タブで、SSE接続を確認できます：

1. ChatページのリクエストURLをクリック
2. Message タブを開く
3. `data:` で始まるメッセージを確認

## まとめ：SSEでエージェント過程を可視化

このパートで実装したSSE戦略により：

- **リアルタイム進捗表示**：エージェントが「思考中」「検索中」「N件発見」というステップを逐次表示
- **擬似ストリーミング**：完成済みのテキストも逐次配信されているように見える
- **キャンセル対応**：ユーザーは中断できる
- **バックエンド効率性**：完成済みテキストはすぐにユーザーに返す

これらの技術により、ベクトル検索を使わないRAGでも、ユーザー体験は十分にインタラクティブになります。

---

これで「ベクトル検索を使わないRAG」シリーズは完結です。第1回から順に読むことで、エージェントループ設計→検索エンジン→リアルタイム配信まで一貫した理解が得られます。
