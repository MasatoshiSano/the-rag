// TagEditor: display and edit AI-suggested tags with confidence badges
import { useState, useRef, useCallback } from "react";
import { Button, IconButton } from "@serendie/ui";
import {
  SerendieSymbolPlus,
  SerendieSymbolClose,
  SerendieSymbolCheckCircle,
} from "@serendie/symbols";

const TAG_KEYS = [
  "site",
  "line",
  "process",
  "category",
  "date",
  "equipment",
  "parts",
  "persons",
  "keywords",
] as const;

type TagKey = (typeof TAG_KEYS)[number];

export interface EditableTag {
  id: string;
  tagKey: string;
  tagValue: string;
  confidence: number;
  confirmed: boolean;
  isNew?: boolean;
}

interface TagEditorProps {
  documentId: string;
  fileName: string;
  tags: EditableTag[];
  onChange: (documentId: string, tags: EditableTag[]) => void;
}

const TAG_KEY_LABELS: Record<TagKey, string> = {
  site: "現場",
  line: "ライン",
  process: "工程",
  category: "カテゴリ",
  date: "日付",
  equipment: "設備",
  parts: "部品",
  persons: "担当者",
  keywords: "キーワード",
};

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "var(--sds-color-positive-default, #2e7d32)";
  if (confidence >= 0.5) return "var(--sds-color-warning-default, #f57c00)";
  return "var(--sds-color-negative-default, #d32f2f)";
}

let nextId = 1;
function generateId(): string {
  return `new-tag-${nextId++}`;
}

export function TagEditor({ documentId, fileName, tags, onChange }: TagEditorProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  const updateTag = useCallback(
    (id: string, updates: Partial<EditableTag>) => {
      onChange(
        documentId,
        tags.map((t) => (t.id === id ? { ...t, ...updates } : t))
      );
    },
    [documentId, tags, onChange]
  );

  const removeTag = useCallback(
    (id: string) => {
      onChange(
        documentId,
        tags.filter((t) => t.id !== id)
      );
    },
    [documentId, tags, onChange]
  );

  const addNewTag = useCallback(() => {
    const newTag: EditableTag = {
      id: generateId(),
      tagKey: TAG_KEYS[0],
      tagValue: "",
      confidence: 1,
      confirmed: true,
      isNew: true,
    };
    onChange(documentId, [...tags, newTag]);
    // Focus the new tag's value input after render
    setTimeout(() => {
      setEditingId(newTag.id);
    }, 50);
  }, [documentId, tags, onChange]);

  const startEditing = useCallback((id: string) => {
    setEditingId(id);
    setTimeout(() => editInputRef.current?.focus(), 50);
  }, []);

  const stopEditing = useCallback(() => {
    setEditingId(null);
  }, []);

  return (
    <div
      style={{
        border: "1px solid var(--sds-color-outline-default)",
        borderRadius: "var(--sds-border-radius-medium, 12px)",
        padding: "16px",
        backgroundColor: "var(--sds-color-surface-default)",
      }}
    >
      <h3
        style={{
          margin: "0 0 12px 0",
          fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
          fontWeight: 700,
          color: "var(--sds-color-on-surface-default)",
          wordBreak: "break-all",
        }}
      >
        {fileName}
      </h3>

      {tags.length === 0 ? (
        <p
          style={{
            margin: "0 0 12px 0",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-on-surface-variant)",
          }}
        >
          タグがありません。手動で追加できます。
        </p>
      ) : (
        <ul
          aria-label={`${fileName} のタグ一覧`}
          style={{
            listStyle: "none",
            margin: "0 0 12px 0",
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          {tags.map((tag) => (
            <li
              key={tag.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
                padding: "8px",
                borderRadius: "var(--sds-border-radius-small, 8px)",
                backgroundColor: tag.confirmed
                  ? "var(--sds-color-surface-container)"
                  : "var(--sds-color-surface-variant)",
              }}
            >
              {/* Tag key selector */}
              <select
                aria-label="タグキー"
                value={tag.tagKey}
                onChange={(e) => updateTag(tag.id, { tagKey: e.target.value })}
                style={{
                  fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                  border: "1px solid var(--sds-color-outline-default)",
                  borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
                  padding: "2px 6px",
                  backgroundColor: "var(--sds-color-surface-default)",
                  color: "var(--sds-color-on-surface-default)",
                  cursor: "pointer",
                }}
              >
                {TAG_KEYS.map((key) => (
                  <option key={key} value={key}>
                    {TAG_KEY_LABELS[key]}
                  </option>
                ))}
                {/* Allow custom key if not in preset */}
                {!TAG_KEYS.includes(tag.tagKey as TagKey) && (
                  <option value={tag.tagKey}>{tag.tagKey}</option>
                )}
              </select>

              {/* Tag value - inline editing */}
              {editingId === tag.id ? (
                <input
                  ref={editInputRef}
                  type="text"
                  aria-label="タグ値"
                  value={tag.tagValue}
                  onChange={(e) => updateTag(tag.id, { tagValue: e.target.value })}
                  onBlur={stopEditing}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === "Escape") stopEditing();
                  }}
                  style={{
                    flex: 1,
                    minWidth: "80px",
                    fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                    border: "1px solid var(--sds-color-impression-primary)",
                    borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
                    padding: "2px 6px",
                    backgroundColor: "var(--sds-color-surface-default)",
                    color: "var(--sds-color-on-surface-default)",
                    outline: "none",
                  }}
                />
              ) : (
                <button
                  aria-label={`タグ値 ${tag.tagValue || "(空)"} を編集`}
                  onClick={() => startEditing(tag.id)}
                  style={{
                    flex: 1,
                    textAlign: "left",
                    background: "none",
                    border: "1px solid transparent",
                    borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
                    padding: "2px 6px",
                    cursor: "text",
                    fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                    color: tag.tagValue
                      ? "var(--sds-color-on-surface-default)"
                      : "var(--sds-color-on-surface-variant)",
                    minWidth: "80px",
                  }}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor =
                      "var(--sds-color-outline-default)";
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor = "transparent";
                  }}
                >
                  {tag.tagValue || "値を入力..."}
                </button>
              )}

              {/* Confidence badge (AI suggested only) */}
              {!tag.isNew && (
                <span
                  aria-label={`確信度 ${Math.round(tag.confidence * 100)}%`}
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    color: confidenceColor(tag.confidence),
                    whiteSpace: "nowrap",
                    border: `1px solid ${confidenceColor(tag.confidence)}`,
                    borderRadius: "var(--sds-border-radius-full, 9999px)",
                    padding: "1px 6px",
                  }}
                >
                  {Math.round(tag.confidence * 100)}%
                </span>
              )}

              {/* Confirm checkbox */}
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  cursor: "pointer",
                  fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                  color: tag.confirmed
                    ? "var(--sds-color-positive-default, #2e7d32)"
                    : "var(--sds-color-on-surface-variant)",
                  whiteSpace: "nowrap",
                }}
              >
                <input
                  type="checkbox"
                  checked={tag.confirmed}
                  onChange={(e) => updateTag(tag.id, { confirmed: e.target.checked })}
                  aria-label={`${tag.tagKey}: ${tag.tagValue} を確認済みにする`}
                  style={{ width: "14px", height: "14px", cursor: "pointer" }}
                />
                <SerendieSymbolCheckCircle
                  style={{ width: 14, height: 14 }}
                  aria-hidden="true"
                />
                確認
              </label>

              {/* Delete button */}
              <IconButton
                icon={
                  <SerendieSymbolClose style={{ width: 16, height: 16 }} />
                }
                aria-label={`タグ "${tag.tagKey}: ${tag.tagValue}" を削除`}
                shape="circle"
                styleType="ghost"
                size="small"
                onClick={() => removeTag(tag.id)}
              />
            </li>
          ))}
        </ul>
      )}

      <Button
        styleType="outlined"
        size="small"
        leftIcon={<SerendieSymbolPlus style={{ width: 16, height: 16 }} />}
        onClick={addNewTag}
      >
        タグを追加
      </Button>
    </div>
  );
}
