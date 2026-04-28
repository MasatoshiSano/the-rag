import { useState, useCallback, useRef, useEffect, type KeyboardEvent } from "react";
import { useChatStore } from "../../stores/chatStore";
import { useUserStore } from "../../stores/userStore";
import { updateSettings } from "../../api/users";
import { VoiceButton } from "./VoiceButton";

interface ChatInputProps {
  onSend: (content: string) => void;
}

export function ChatInput({ onSend }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const cancelStreaming = useChatStore((s) => s.cancelStreaming);

  // ローカルstate でトグルを即座に反映（user が null でも動作する）
  const storeMode = useUserStore((s) => s.user?.response_mode);
  const [localMode, setLocalMode] = useState<"simple" | "detailed">(storeMode ?? "detailed");
  useEffect(() => {
    if (storeMode) setLocalMode(storeMode);
  }, [storeMode]);

  const toggleResponseMode = useCallback(() => {
    const newMode = localMode === "simple" ? "detailed" : "simple";
    setLocalMode(newMode);
    useUserStore.getState().updateUserSettings({ response_mode: newMode });
    updateSettings({ response_mode: newMode })
      .then((updated) => useUserStore.getState().setUser(updated))
      .catch(() => {});
  }, [localMode]);

  // 検索モードトグル
  const storeSearchMode = useUserStore((s) => s.user?.search_mode);
  const [localSearchMode, setLocalSearchMode] = useState<"normal" | "agentic">(storeSearchMode ?? "agentic");
  useEffect(() => {
    if (storeSearchMode) setLocalSearchMode(storeSearchMode);
  }, [storeSearchMode]);

  const toggleSearchMode = useCallback(() => {
    const newMode = localSearchMode === "normal" ? "agentic" : "normal";
    setLocalSearchMode(newMode);
    localStorage.setItem("the-rag-search-mode", newMode);
    useUserStore.getState().updateUserSettings({ search_mode: newMode });
    updateSettings({ search_mode: newMode })
      .then((updated) => useUserStore.getState().setUser(updated))
      .catch(() => {});
  }, [localSearchMode]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setText("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, isStreaming, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, []);

  const canSend = text.trim().length > 0 && !isStreaming;

  return (
    <div
      role="region"
      aria-label="メッセージ入力エリア"
      style={{
        borderTop: "1px solid var(--sds-color-outline-default)",
        backgroundColor: "var(--sds-color-surface-default)",
        padding: "var(--sds-spacing-medium, 12px) var(--sds-spacing-large, 16px)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--sds-spacing-small, 8px)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: "var(--sds-spacing-small, 8px)",
          backgroundColor: "var(--sds-color-surface-container)",
          borderRadius: "var(--sds-border-radius-medium, 12px)",
          border: "1px solid var(--sds-color-outline-default)",
          padding: "var(--sds-spacing-small, 8px) var(--sds-spacing-medium, 12px)",
          transition: "border-color 0.15s ease",
        }}
        onFocusCapture={(e) => {
          (e.currentTarget as HTMLDivElement).style.borderColor =
            "var(--sds-color-primary-default)";
        }}
        onBlurCapture={(e) => {
          (e.currentTarget as HTMLDivElement).style.borderColor =
            "var(--sds-color-outline-default)";
        }}
      >
        <textarea
          ref={textareaRef}
          id="chat-input"
          aria-label={isStreaming ? "回答中です。入力できません。" : "メッセージを入力 (Shift+Enterで改行)"}
          disabled={isStreaming}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          placeholder={isStreaming ? "回答中..." : "メッセージを入力... (Shift+Enterで改行)"}
          rows={1}
          style={{
            flex: 1,
            resize: "none",
            border: "none",
            outline: "none",
            backgroundColor: "transparent",
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            color: isStreaming
              ? "var(--sds-color-on-surface-low)"
              : "var(--sds-color-on-surface-default)",
            lineHeight: 1.5,
            minHeight: 24,
            maxHeight: 180,
            overflowY: "auto",
            fontFamily: "inherit",
            cursor: isStreaming ? "not-allowed" : "text",
          }}
        />

        {/* Voice input button - visible when not streaming */}
        {!isStreaming && (
          <VoiceButton
            onTranscript={(transcript) =>
              setText((prev) => (prev ? prev + transcript : transcript))
            }
            disabled={isStreaming}
          />
        )}

        {/* Stop button during streaming */}
        {isStreaming ? (
          <button
            type="button"
            aria-label="回答を中断する"
            onClick={cancelStreaming}
            style={{
              flexShrink: 0,
              width: 36,
              height: 36,
              borderRadius: "50%",
              border: "2px solid var(--sds-color-caution-default)",
              backgroundColor: "transparent",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--sds-color-caution-default)",
              transition: "background-color 0.15s ease",
              fontSize: 14,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "var(--sds-color-caution-container)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "transparent";
            }}
          >
            <span aria-hidden="true">■</span>
          </button>
        ) : (
          /* Send button */
          <button
            type="button"
            aria-label="メッセージを送信"
            disabled={!canSend}
            onClick={handleSend}
            style={{
              flexShrink: 0,
              width: 36,
              height: 36,
              borderRadius: "50%",
              border: "none",
              backgroundColor: canSend
                ? "var(--sds-color-primary-default)"
                : "var(--sds-color-on-surface-disabled)",
              cursor: canSend ? "pointer" : "not-allowed",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: canSend
                ? "var(--sds-color-on-primary-default)"
                : "var(--sds-color-on-surface-low)",
              transition: "background-color 0.15s ease",
            }}
          >
            <span aria-hidden="true" style={{ fontSize: 16, lineHeight: 1 }}>
              ↑
            </span>
          </button>
        )}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            type="button"
            role="switch"
            aria-checked={localSearchMode === "agentic"}
            aria-label="検索モード切替"
            onClick={toggleSearchMode}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "2px 8px",
              border: "1px solid var(--sds-color-outline-default)",
              borderRadius: "var(--sds-border-radius-small, 6px)",
              backgroundColor: "transparent",
              cursor: "pointer",
              fontSize: "var(--sds-typography-label-small-font-size, 11px)",
              color: "var(--sds-color-on-surface-low)",
              lineHeight: 1.5,
              transition: "border-color 0.15s ease",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 28,
                height: 14,
                borderRadius: 7,
                backgroundColor: localSearchMode === "agentic"
                  ? "var(--sds-color-primary-default)"
                  : "var(--sds-color-on-surface-disabled)",
                position: "relative",
                transition: "background-color 0.15s ease",
              }}
            >
              <span
                style={{
                  display: "block",
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  backgroundColor: "#fff",
                  position: "absolute",
                  top: 2,
                  left: localSearchMode === "agentic" ? 16 : 2,
                  transition: "left 0.15s ease",
                }}
              />
            </span>
            {localSearchMode === "agentic" ? "深掘り" : "通常"}
          </button>
        <button
          type="button"
          role="switch"
          aria-checked={localMode === "detailed"}
          aria-label="回答モード切替"
          onClick={toggleResponseMode}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "2px 8px",
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: "var(--sds-border-radius-small, 6px)",
            backgroundColor: "transparent",
            cursor: "pointer",
            fontSize: "var(--sds-typography-label-small-font-size, 11px)",
            color: "var(--sds-color-on-surface-low)",
            lineHeight: 1.5,
            transition: "border-color 0.15s ease",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 28,
              height: 14,
              borderRadius: 7,
              backgroundColor: localMode === "detailed"
                ? "var(--sds-color-primary-default)"
                : "var(--sds-color-on-surface-disabled)",
              position: "relative",
              transition: "background-color 0.15s ease",
            }}
          >
            <span
              style={{
                display: "block",
                width: 10,
                height: 10,
                borderRadius: "50%",
                backgroundColor: "#fff",
                position: "absolute",
                top: 2,
                left: localMode === "detailed" ? 16 : 2,
                transition: "left 0.15s ease",
              }}
            />
          </span>
          {localMode === "detailed" ? "詳細" : "コンパクト"}
        </button>
        </div>
        <p
          aria-hidden="true"
          style={{
            margin: 0,
            fontSize: "var(--sds-typography-label-small-font-size, 11px)",
            color: "var(--sds-color-on-surface-low)",
          }}
        >
          Enterで送信・Shift+Enterで改行
        </p>
      </div>
    </div>
  );
}
