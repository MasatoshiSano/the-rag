---
title: "EventSourceではカスタムヘッダーを送れない — fetch + ReadableStreamでSSEクライアントを自作する"
emoji: "📨"
type: "tech"
topics: ["SSE", "TypeScript", "React", "Fetch API", "Streaming"]
published: true
category: "HowTo"
date: "2026-04-28"
description: "ブラウザ標準のEventSourceがカスタムヘッダー（認証トークン等）を送れない制約を、fetch + ReadableStreamによるSSEクライアント自作で解決する実装パターンを解説"
---

## やりたかったこと

RAGチャットアプリケーションのSSE（Server-Sent Events）ストリーミングで、ユーザーIDを特定するための **カスタムヘッダー `X-User-Id`** を送信したかった。

しかし、ブラウザ標準の `EventSource` API には致命的な制約がある。

## ❌ EventSourceの制約

```typescript
// これはできない
const eventSource = new EventSource(url, {
    headers: { "X-User-Id": getUserId() }  // ❌ 無視される
});

// GETメソッドのみ、POSTできない
// カスタムヘッダーは一切送れない
```

`EventSource` の仕様上の問題：

| 項目 | EventSource | 必要なもの |
|------|------------|----------|
| HTTPメソッド | GET のみ | POST対応 |
| カスタムヘッダー | 不可 | `X-User-Id` を送りたい |
| 認証トークン | Bearer token不可 | Authorization: Bearer ... |
| CORS認証情報 | 制限あり | credentials含めたい |

## ✅ fetch + ReadableStreamで自作する

標準の `Fetch API` と `ReadableStream` を使えば、完全にコントロール可能なSSEクライアントが実装できる。

### 基本的な実装パターン

```typescript
async function streamChat(
    payload: ChatRequestPayload,
    onEvent: (event: SseEvent) => void,
    onError?: (error: Error) => void
) {
    const abortController = new AbortController();

    try {
        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-User-Id": getUserId(),  // ✅ カスタムヘッダー送信可能
            },
            body: JSON.stringify(payload),
            signal: abortController.signal,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        // ✅ ReadableStreamで一行ずつ処理
        const reader = response.body!.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // UTF-8デコード（マルチバイト文字対応）
            buffer += decoder.decode(value, { stream: true });

            // 改行でスプリット、不完全行はバッファに残す
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
                // SSE形式: "data: {...}"
                if (!line.trim().startsWith("data:")) continue;

                const jsonStr = line.trim().slice("data:".length).trim();
                try {
                    const raw = JSON.parse(jsonStr);
                    const event = convertBackendEvent(raw);
                    if (event) onEvent(event);
                } catch (parseError) {
                    console.error("Failed to parse SSE data:", jsonStr, parseError);
                }
            }
        }

        // 最後のバッファ行を処理
        if (buffer.trim()) {
            if (buffer.trim().startsWith("data:")) {
                const jsonStr = buffer.trim().slice("data:".length).trim();
                try {
                    const raw = JSON.parse(jsonStr);
                    const event = convertBackendEvent(raw);
                    if (event) onEvent(event);
                } catch (parseError) {
                    console.error("Failed to parse final SSE data:", jsonStr, parseError);
                }
            }
        }
    } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
            console.log("Chat stream cancelled");
        } else {
            onError?.(error as Error);
        }
    } finally {
        // クリーンアップ
        abortController.abort();
    }
}

// ユーザーIDを取得（localStorageから）
function getUserId(): string {
    return localStorage.getItem("rag-phantom-user-id") ?? "unknown";
}
```

### ポイント1: バッファハンドリング

SSEデータは改行で区切られていますが、ネットワークから到着するデータはチャンクごとに分割されています。そのため、不完全な行を次のreadサイクルまでバッファリングする必要があります。

```typescript
const lines = buffer.split("\n");
buffer = lines.pop() ?? "";  // 最後の不完全行をバッファに残す

for (const line of lines) {
    // 完全な行のみ処理
    if (!line.trim().startsWith("data:")) continue;
    // ...
}
```

### ポイント2: UTF-8デコードのstream オプション

マルチバイト文字（日本語など）がチャンク境界で分割された場合、`stream: true` により `TextDecoder` が不完全なシーケンスを次のreadまで待ってくれます。

```typescript
decoder.decode(value, { stream: true });
```

## Backend イベント型の変換

FastAPI の `/api/chat/stream` が返すイベントは snake_case ですが、React フロントエンドは camelCase の型安全な構造にしたいはずです。

### Backend型（snake_case）

```typescript
// Backend が送信するSSE data（例）
type BackendSseEvent = {
    event: "token" | "agentic_step" | "session_created" | "error";
    data: Record<string, unknown>;
};

// token イベント
{ "event": "token", "data": { "text": "こんにちは" } }

// agentic_step イベント
{ "event": "agentic_step", "data": { "iteration": 1, "tool_name": "read_document", "tool_input": {...} } }
```

### Frontend型（camelCase + discriminated union）

```typescript
type SseEvent =
    | SseTokenEvent
    | SseAgenticStepEvent
    | SseSessionCreatedEvent
    | SseErrorEvent;

type SseTokenEvent = {
    type: "token";
    token: string;
};

type SseAgenticStepEvent = {
    type: "agentic_step";
    iteration: number;
    toolName: string;
    toolInput: Record<string, unknown>;
};

type SseSessionCreatedEvent = {
    type: "session_created";
    sessionId: string;
};

type SseErrorEvent = {
    type: "error";
    message: string;
};
```

### 変換関数

```typescript
function convertBackendEvent(raw: BackendSseEvent): SseEvent | null {
    switch (raw.event) {
        case "token":
            return {
                type: "token",
                token: (raw.data.text as string) ?? "",
            };

        case "agentic_step":
            return {
                type: "agentic_step",
                iteration: (raw.data.iteration as number) ?? 0,
                toolName: ((raw.data.tool_name as string) ?? "").replace(/_/g, ""),
                toolInput: (raw.data.tool_input as Record<string, unknown>) ?? {},
            };

        case "session_created":
            return {
                type: "session_created",
                sessionId: (raw.data.session_id as string) ?? "",
            };

        case "error":
            return {
                type: "error",
                message: (raw.data.message as string) ?? "Unknown error",
            };

        default:
            console.warn("Unknown SSE event type:", raw.event);
            return null;
    }
}
```

## Reactでの使用例

カスタムフック `useChatStream` を作成して、コンポーネントから簡単に利用できるようにします。

```typescript
import { useRef, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function useChatStream() {
    const [isStreaming, setIsStreaming] = useState(false);
    const [streamError, setStreamError] = useState<Error | null>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

    const startStream = useCallback(
        async (
            payload: ChatRequestPayload,
            onEvent: (event: SseEvent) => void,
            knowledgeBaseId: string
        ) => {
            setIsStreaming(true);
            setStreamError(null);
            abortControllerRef.current = new AbortController();

            try {
                await streamChat(
                    payload,
                    onEvent,
                    (error) => setStreamError(error)
                );
            } catch (error) {
                setStreamError(error as Error);
            } finally {
                setIsStreaming(false);
            }
        },
        []
    );

    const cancelStream = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
    }, []);

    return {
        isStreaming,
        streamError,
        startStream,
        cancelStream,
    };
}

// コンポーネントでの使用
function ChatComponent() {
    const { isStreaming, streamError, startStream, cancelStream } = useChatStream();
    const [messages, setMessages] = useState<SseEvent[]>([]);

    const handleSendMessage = async (text: string) => {
        await startStream(
            { message: text, kb_id: "kb-123" },
            (event) => {
                setMessages((prev) => [...prev, event]);
            }
        );
    };

    return (
        <>
            <button onClick={() => handleSendMessage("こんにちは")}>
                Send
            </button>
            {isStreaming && <button onClick={cancelStream}>Cancel</button>}
            {streamError && <p style={{ color: "red" }}>{streamError.message}</p>}
            <div>
                {messages.map((msg, i) => (
                    <div key={i}>
                        {msg.type === "token" && <span>{msg.token}</span>}
                        {msg.type === "agentic_step" && (
                            <pre>{JSON.stringify(msg, null, 2)}</pre>
                        )}
                    </div>
                ))}
            </div>
        </>
    );
}
```

## キャンセル処理

SSEストリームをキャンセルする必要がある場合、`AbortController` を使用します。

```typescript
// キャンセルボタンクリック時
const handleCancel = () => {
    abortController.abort();  // ✅ 即座に接続を切断
};

// streamChat 内での処理
try {
    const response = await fetch("/api/chat/stream", {
        signal: abortController.signal,
        // ...
    });
} catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
        console.log("User cancelled the stream");
    }
}
```

## エラーハンドリング

ネットワークエラーやパースエラーに対応します。

```typescript
async function streamChat(
    payload: ChatRequestPayload,
    onEvent: (event: SseEvent) => void,
    onError?: (error: Error) => void
) {
    try {
        const response = await fetch("/api/chat/stream", {
            // ...
        });

        // HTTPエラーチェック
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }

        const reader = response.body!.getReader();
        // ...
    } catch (error) {
        if (error instanceof Error && error.name === "AbortError") {
            // ユーザーキャンセルの場合はonErrorを呼ばない
            return;
        }

        const err = error instanceof Error ? error : new Error(String(error));
        onError?.(err);
    }
}
```

## EventSourceではなくfetch + ReadableStreamを選ぶべき理由

| 要件 | EventSource | fetch+ReadableStream |
|------|-------------|---------------------|
| カスタムヘッダー | ❌ | ✅ |
| 認証トークン | ❌ | ✅ |
| POSTリクエスト | ❌ | ✅ |
| キャンセル制御 | 限定的 | ✅ AbortController |
| エラーハンドリング | 基本的 | ✅ 詳細 |
| ストリーミング型式 | SSE固定 | ✅ 柔軟 |

**RAGチャットのような認証が必要なアプリケーションでは、カスタムヘッダー対応が必須となるため、fetch + ReadableStream の実装が現実的です。**

## まとめ

- **EventSource**: 単純なSSEには便利だが、認証やカスタムヘッダーが必要なら使えない
- **fetch + ReadableStream**: 少し複雑だが、完全にコントロール可能で本番アプリに向いている
- **バッファハンドリング**: 不完全な行をバッファリングし、次のreadサイクルで結合する
- **型安全**: Backend snake_case → Frontend camelCase の型変換で、TypeScriptの恩恵を最大限受ける
- **AbortController**: キャンセル処理を簡潔に実装できる

この実装パターンは、RAGチャットだけでなく、AI APIのストリーミング応答やリアルタイム通知など、認証付きのSSEが必要なあらゆるユースケースに応用できます。
