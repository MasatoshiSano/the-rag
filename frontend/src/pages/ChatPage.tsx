import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useChatStore } from "../stores/chatStore";
import { useKbStore } from "../stores/kbStore";
import { getSession } from "../api/sessions";
import type { SessionMessage } from "../api/sessions";
import type { Message, Source } from "../types/message";
import { MessageList } from "../components/chat/MessageList";
import { ChatInput } from "../components/chat/ChatInput";
import { useStreamChat } from "../hooks/useStreamChat";

function mapSessionSources(sources: SessionMessage["sources"]): Source[] {
  if (!sources) return [];
  return sources.map((s) => ({
    documentId: s.document_id ?? "",
    documentName: s.document_name ?? "",
    sectionTitle: s.section_title ?? "",
    score: s.score ?? 0,
    snippet: s.snippet ?? "",
  }));
}

function mapSessionMessage(msg: SessionMessage, sessionId: string): Message {
  return {
    id: msg.id,
    sessionId,
    role: msg.role,
    content: msg.content,
    sources: mapSessionSources(msg.sources),
    rating: msg.rating,
    inputType: (msg.input_type as "text" | "voice") ?? "text",
    isCancelled: msg.is_cancelled,
    createdAt: msg.created_at,
  };
}

export function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>();
  const selectedKbId = useKbStore((s) => s.selectedKbId);
  const setMessages = useChatStore((s) => s.setMessages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const { sendMessage } = useStreamChat();

  // Load session messages when sessionId param is present
  const { data: sessionData, isLoading: isLoadingMessages } = useQuery({
    queryKey: ["session-detail", sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: !!sessionId && !isStreaming,
    staleTime: 0,
  });

  // Sync loaded messages into the chat store (skip while streaming to avoid overwriting)
  useEffect(() => {
    if (sessionData && !isStreaming) {
      const mapped = sessionData.messages.map((m) =>
        mapSessionMessage(m, sessionData.id)
      );
      setMessages(mapped);
    }
  }, [sessionData, isStreaming, setMessages]);

  // Clear messages when navigating to a new (sessionless) chat
  useEffect(() => {
    if (!sessionId) {
      clearMessages();
    }
  }, [sessionId, clearMessages]);

  const handleSend = (content: string) => {
    sendMessage(content, sessionId);
  };

  // Guard: knowledge base not selected
  if (!selectedKbId) {
    return (
      <div
        aria-label="ナレッジベース未選択"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          flex: 1,
          gap: "var(--sds-spacing-large, 16px)",
          padding: "var(--sds-spacing-extra-large, 24px)",
          textAlign: "center",
        }}
      >
        <div
          aria-live="polite"
          role="status"
          className="empty-state"
        >
          <span
            aria-hidden="true"
            style={{ fontSize: 48, display: "block", marginBottom: 16 }}
          >
            📚
          </span>
          <h1 className="empty-state-title">
            ナレッジベースを選択してください
          </h1>
          <p className="empty-state-description">
            チャットを開始するには、サイドバーからナレッジベースを選択してください。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      aria-label="チャット"
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        overflow: "hidden",
        minHeight: 0,
      }}
    >
      {/* Page heading for screen readers */}
      <h1
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0,0,0,0)",
          whiteSpace: "nowrap",
          border: 0,
        }}
      >
        チャット{sessionId ? ` - セッション ${sessionId}` : ""}
      </h1>

      {/* Loading state for session messages */}
      {isLoadingMessages && (
        <div
          role="status"
          aria-live="polite"
          aria-label="メッセージを読み込み中"
          style={{
            padding: "var(--sds-spacing-medium, 12px) var(--sds-spacing-large, 16px)",
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            color: "var(--sds-color-on-surface-low)",
            textAlign: "center",
          }}
        >
          メッセージを読み込み中...
        </div>
      )}

      {/* Message list */}
      <MessageList />

      {/* Chat input */}
      <ChatInput onSend={handleSend} />
    </div>
  );
}
