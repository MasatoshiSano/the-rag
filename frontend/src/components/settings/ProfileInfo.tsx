// ProfileInfo: user memory management (Gemini-like "about me")
// Users can add, edit, and delete free-text memories that are injected into RAG prompts.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createMemory, deleteMemory, getMemories, updateMemory } from "../../api/users";
import type { UserMemoryItem } from "../../types/user";

const sectionStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container-low)",
  borderRadius: "var(--sds-border-radius-medium, 12px)",
  padding: "24px",
  display: "flex",
  flexDirection: "column",
  gap: "16px",
};

const memoryItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: "8px",
  padding: "10px 12px",
  backgroundColor: "var(--sds-color-surface-container)",
  borderRadius: "var(--sds-border-radius-small, 8px)",
  fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
  lineHeight: 1.5,
};

const buttonBase: React.CSSProperties = {
  border: "none",
  cursor: "pointer",
  borderRadius: "var(--sds-border-radius-extra-small, 4px)",
  fontSize: "var(--sds-typography-label-small-font-size, 12px)",
  padding: "4px 8px",
  flexShrink: 0,
};

const addButtonStyle: React.CSSProperties = {
  ...buttonBase,
  backgroundColor: "var(--sds-color-impression-primary)",
  color: "var(--sds-color-on-primary-default)",
  padding: "8px 16px",
  fontSize: "var(--sds-typography-label-medium-font-size, 13px)",
  fontWeight: 600,
  alignSelf: "flex-start",
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  minHeight: "60px",
  padding: "8px 12px",
  border: "1px solid var(--sds-color-outline-default)",
  borderRadius: "var(--sds-border-radius-small, 8px)",
  fontFamily: "inherit",
  fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
  lineHeight: 1.5,
  resize: "vertical",
  backgroundColor: "var(--sds-color-surface-default)",
  color: "var(--sds-color-on-surface-default)",
};

function MemoryItem({
  memory,
  onDelete,
  onUpdate,
}: {
  memory: UserMemoryItem;
  onDelete: (id: string) => void;
  onUpdate: (id: string, content: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(memory.content);

  const handleSave = () => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== memory.content) {
      onUpdate(memory.id, trimmed);
    }
    setEditing(false);
  };

  const handleCancel = () => {
    setEditValue(memory.content);
    setEditing(false);
  };

  if (editing) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <textarea
          style={textareaStyle}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          aria-label="メモリを編集"
        />
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            style={{ ...buttonBase, backgroundColor: "var(--sds-color-impression-primary)", color: "var(--sds-color-on-primary-default)" }}
            onClick={handleSave}
          >
            保存
          </button>
          <button
            type="button"
            style={{ ...buttonBase, backgroundColor: "var(--sds-color-surface-container-high)", color: "var(--sds-color-on-surface-default)" }}
            onClick={handleCancel}
          >
            キャンセル
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={memoryItemStyle}>
      <span style={{ flex: 1, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {memory.source === "auto" && (
          <span
            style={{
              display: "inline-block",
              fontSize: "var(--sds-typography-label-small-font-size, 11px)",
              backgroundColor: "var(--sds-color-impression-tertiary, #e0e7ff)",
              color: "var(--sds-color-on-tertiary-container, #3730a3)",
              borderRadius: "var(--sds-border-radius-extra-small, 4px)",
              padding: "1px 6px",
              marginRight: "6px",
              fontWeight: 600,
              verticalAlign: "middle",
            }}
          >
            自動
          </span>
        )}
        {memory.content}
      </span>
      <button
        type="button"
        style={{ ...buttonBase, backgroundColor: "transparent", color: "var(--sds-color-on-surface-low)" }}
        onClick={() => setEditing(true)}
        aria-label={`「${memory.content.slice(0, 20)}」を編集`}
        title="編集"
      >
        ✏️
      </button>
      <button
        type="button"
        style={{ ...buttonBase, backgroundColor: "transparent", color: "var(--sds-color-error-default)" }}
        onClick={() => onDelete(memory.id)}
        aria-label={`「${memory.content.slice(0, 20)}」を削除`}
        title="削除"
      >
        ✕
      </button>
    </div>
  );
}

export function ProfileInfo() {
  const queryClient = useQueryClient();
  const [newContent, setNewContent] = useState("");

  const { data: memories, isLoading, isError } = useQuery({
    queryKey: ["memories"],
    queryFn: getMemories,
  });

  const createMutation = useMutation({
    mutationFn: (content: string) => createMemory(content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memories"] });
      setNewContent("");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => updateMemory(id, content),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memories"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteMemory(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memories"] }),
  });

  const handleAdd = () => {
    const trimmed = newContent.trim();
    if (trimmed) {
      createMutation.mutate(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <section aria-labelledby="profile-info-heading" style={sectionStyle}>
      <div>
        <h2
          id="profile-info-heading"
          style={{
            margin: 0,
            fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
            fontWeight: 700,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          自分について
        </h2>
        <p
          style={{
            margin: "4px 0 0",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-on-surface-low)",
          }}
        >
          ここに登録した情報はAIが回答時に参考にします
        </p>
      </div>

      {isLoading ? (
        <p aria-live="polite" aria-busy="true" style={{ color: "var(--sds-color-on-surface-low)", margin: 0 }}>
          読み込み中...
        </p>
      ) : isError ? (
        <p role="alert" style={{ color: "var(--sds-color-error-default)", margin: 0 }}>
          読み込みに失敗しました。
        </p>
      ) : (
        <>
          {/* Existing memories */}
          {memories && memories.length > 0 && (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "8px" }} aria-label="登録済みメモリ一覧">
              {memories.map((m) => (
                <li key={m.id}>
                  <MemoryItem
                    memory={m}
                    onDelete={(id) => deleteMutation.mutate(id)}
                    onUpdate={(id, content) => updateMutation.mutate({ id, content })}
                  />
                </li>
              ))}
            </ul>
          )}

          {memories && memories.length === 0 && (
            <p style={{ color: "var(--sds-color-on-surface-low)", fontSize: "var(--sds-typography-body-small-font-size, 13px)", margin: 0, fontStyle: "italic" }}>
              まだ登録がありません。あなたについて教えてください。
            </p>
          )}

          {/* Add new memory */}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label
              htmlFor="new-memory-input"
              style={{
                fontSize: "var(--sds-typography-label-medium-font-size, 13px)",
                fontWeight: 600,
                color: "var(--sds-color-on-surface-low)",
              }}
            >
              新しいメモリを追加
            </label>
            <textarea
              id="new-memory-input"
              style={textareaStyle}
              value={newContent}
              onChange={(e) => setNewContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="例: 生技14グループに所属しています / よく使うラインはEPS成型#5です"
              rows={2}
            />
            <button
              type="button"
              style={{
                ...addButtonStyle,
                opacity: !newContent.trim() || createMutation.isPending ? 0.5 : 1,
              }}
              onClick={handleAdd}
              disabled={!newContent.trim() || createMutation.isPending}
            >
              {createMutation.isPending ? "追加中..." : "追加"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
