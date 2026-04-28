// TextInput: direct text input for uploading as .md file
import { useState, useCallback } from "react";
import { Button } from "@serendie/ui";
import { SerendieSymbolEdit } from "@serendie/symbols";

interface TextInputProps {
  onSubmit: (file: File) => void;
  disabled: boolean;
}

function generateDefaultFilename(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const date = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
  const time = `${pad(now.getHours())}${pad(now.getMinutes())}`;
  return `text-${date}-${time}.md`;
}

function ensureMdExtension(title: string): string {
  return title.endsWith(".md") ? title : `${title}.md`;
}

export function TextInput({ onSubmit, disabled }: TextInputProps) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  const canSubmit = text.trim().length > 0 && !disabled;

  const handleSubmit = useCallback(() => {
    if (!canSubmit) return;
    const filename = title.trim()
      ? ensureMdExtension(title.trim())
      : generateDefaultFilename();
    const file = new File([text], filename, { type: "text/markdown" });
    onSubmit(file);
    setTitle("");
    setText("");
  }, [canSubmit, title, text, onSubmit]);

  return (
    <div
      style={{
        border: "1px solid var(--sds-color-outline-default)",
        borderRadius: "var(--sds-border-radius-medium, 12px)",
        padding: "24px",
        backgroundColor: "var(--sds-color-surface-container)",
        display: "flex",
        flexDirection: "column",
        gap: "16px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          color: "var(--sds-color-on-surface-variant)",
        }}
      >
        <SerendieSymbolEdit
          style={{ width: 24, height: 24 }}
          aria-hidden="true"
        />
        <span
          style={{
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            fontWeight: 700,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          テキストを直接入力してアップロード
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        <label
          htmlFor="text-input-title"
          style={{
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            fontWeight: 600,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          タイトル
        </label>
        <input
          id="text-input-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="タイトル（任意）"
          disabled={disabled}
          style={{
            width: "100%",
            maxWidth: "480px",
            padding: "8px 12px",
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: "var(--sds-border-radius-small, 8px)",
            backgroundColor: "var(--sds-color-surface-default)",
            color: "var(--sds-color-on-surface-default)",
            outline: "none",
            boxSizing: "border-box",
          }}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow =
              "0 0 0 2px var(--sds-color-impression-primary)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        <span
          style={{
            fontSize: "var(--sds-typography-body-small-font-size, 11px)",
            color: "var(--sds-color-on-surface-variant)",
          }}
        >
          未入力の場合は自動生成されます（例: text-20260406-1430.md）
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
        <label
          htmlFor="text-input-content"
          style={{
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            fontWeight: 600,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          テキスト内容
        </label>
        <textarea
          id="text-input-content"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="テキストを入力..."
          disabled={disabled}
          rows={10}
          aria-required="true"
          style={{
            width: "100%",
            padding: "12px",
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: "var(--sds-border-radius-small, 8px)",
            backgroundColor: "var(--sds-color-surface-default)",
            color: "var(--sds-color-on-surface-default)",
            resize: "vertical",
            outline: "none",
            boxSizing: "border-box",
            fontFamily: "inherit",
            lineHeight: 1.6,
          }}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow =
              "0 0 0 2px var(--sds-color-impression-primary)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = "none";
          }}
        />
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          styleType="filled"
          size="medium"
          disabled={!canSubmit}
          onClick={handleSubmit}
        >
          アップロード
        </Button>
      </div>
    </div>
  );
}
