import { useEffect, useRef, type CSSProperties } from "react";
import { useChatStore } from "../../stores/chatStore";
import type { AgenticStep } from "../../stores/chatStore";
import { MessageBubble, renderMarkdown } from "./MessageBubble";

const STATUS_LABELS: Record<string, string> = {
  query_analysis: "クエリを分析中...",
  vector_search: "ベクトル検索中...",
  oracle_query: "データベースを検索中...",
  structuring_output: "回答を整形中...",
  generating: "回答生成中...",
  idle: "",
};

function formatAgenticStep(step: AgenticStep): string {
  const progress = `(${step.iteration}/${step.maxIterations})`;
  switch (step.status) {
    case "thinking":
      return `検索戦略を検討中... ${progress}`;
    case "searching":
      return `「${step.searchQuery ?? ""}」で検索中... ${progress}`;
    case "found":
      return `${step.resultCount ?? 0}件の結果を取得 ${progress}`;
  }
}

export function MessageList() {
  const messages = useChatStore((s) => s.messages);
  const streamingText = useChatStore((s) => s.streamingText);
  const streamingStatus = useChatStore((s) => s.streamingStatus);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const sources = useChatStore((s) => s.sources);
  const agenticSteps = useChatStore((s) => s.agenticSteps);

  const bottomRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or streaming text change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, agenticSteps]);

  const statusLabel = STATUS_LABELS[streamingStatus] ?? "";

  return (
    <div
      ref={listRef}
      role="log"
      aria-label="チャットメッセージ"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      style={{
        flex: 1,
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "var(--sds-spacing-large, 16px)",
        padding: "var(--sds-spacing-large, 16px) 0",
      }}
    >
      {messages.length === 0 && !isStreaming && (
        <div
          aria-label="メッセージがありません"
          className="empty-state"
          style={{ flex: 1 }}
        >
          <p className="empty-state-title">質問を入力してください</p>
          <p className="empty-state-description">
            ナレッジベースに関する質問を入力すると、AIが回答します。
          </p>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {/* Streaming assistant bubble */}
      {isStreaming && (
        <article
          aria-label="アシスタントが回答中"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            padding: "0 var(--sds-spacing-large, 16px)",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              fontSize: "var(--sds-typography-label-small-font-size, 11px)",
              color: "var(--sds-color-on-surface-low)",
              marginBottom: "var(--sds-spacing-extra-small, 4px)",
              fontWeight: 600,
            }}
          >
            アシスタント
          </span>

          <div
            style={{
              maxWidth: "min(640px, 80%)",
              padding: "var(--sds-spacing-medium, 12px) var(--sds-spacing-large, 16px)",
              borderRadius:
                "var(--sds-border-radius-large, 16px) var(--sds-border-radius-large, 16px) var(--sds-border-radius-large, 16px) var(--sds-border-radius-extra-small, 4px)",
              backgroundColor: "var(--sds-color-surface-container)",
              color: "var(--sds-color-on-surface-default)",
              fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
              lineHeight: 1.6,
              wordBreak: "break-word",
              whiteSpace: "normal",
            }}
          >
            {streamingText ? renderMarkdown(streamingText) : (
              <span
                aria-hidden="true"
                style={{
                  display: "inline-flex",
                  gap: 3,
                  alignItems: "center",
                }}
              >
                <span style={dotStyle(0)} />
                <span style={dotStyle(1)} />
                <span style={dotStyle(2)} />
              </span>
            )}
          </div>

          {/* Agentic search steps */}
          {agenticSteps.length > 0 && (
            <div
              style={{
                marginTop: "var(--sds-spacing-small, 8px)",
                display: "flex",
                flexDirection: "column",
                gap: "4px",
                maxWidth: "min(640px, 80%)",
              }}
            >
              {agenticSteps.map((step, idx) => (
                <div
                  key={idx}
                  role="status"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "var(--sds-typography-label-small-font-size, 11px)",
                    color: step.status === "found"
                      ? "var(--sds-color-success-default, #16a34a)"
                      : "var(--sds-color-on-surface-low)",
                    lineHeight: 1.5,
                  }}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor: step.status === "found"
                        ? "var(--sds-color-success-default, #16a34a)"
                        : "var(--sds-color-primary-default)",
                      ...(step.status !== "found"
                        ? { animation: "pulse 1.4s ease-in-out infinite" }
                        : {}),
                    }}
                  />
                  {formatAgenticStep(step)}
                </div>
              ))}
            </div>
          )}

          {/* Status indicator */}
          {statusLabel && (
            <div
              role="status"
              aria-live="polite"
              aria-label={statusLabel}
              style={{
                marginTop: "var(--sds-spacing-small, 8px)",
                display: "flex",
                alignItems: "center",
                gap: "var(--sds-spacing-small, 8px)",
                fontSize: "var(--sds-typography-label-small-font-size, 12px)",
                color: "var(--sds-color-on-surface-low)",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  backgroundColor: "var(--sds-color-primary-default)",
                  animation: "pulse 1.4s ease-in-out infinite",
                }}
              />
              {statusLabel}
            </div>
          )}

          {/* Partial sources during streaming */}
          {sources.length > 0 && (
            <div style={{ maxWidth: "min(640px, 80%)", width: "100%", marginTop: "var(--sds-spacing-small, 8px)" }}>
              <p
                style={{
                  margin: "0 0 4px 0",
                  fontSize: "var(--sds-typography-label-small-font-size, 12px)",
                  color: "var(--sds-color-on-surface-low)",
                  fontWeight: 600,
                }}
              >
                検索結果 ({sources.length})
              </p>
            </div>
          )}
        </article>
      )}

      <div ref={bottomRef} aria-hidden="true" />

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes blink {
          0%, 80%, 100% { opacity: 0; }
          40% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function dotStyle(index: number): CSSProperties {
  return {
    display: "inline-block",
    width: 6,
    height: 6,
    borderRadius: "50%",
    backgroundColor: "var(--sds-color-on-surface-low)",
    animation: `blink 1.4s ease-in-out ${index * 0.2}s infinite`,
  };
}
