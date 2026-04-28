import { useState, useCallback } from "react";

interface CopyButtonProps {
  content: string;
}

export function CopyButton({ content }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("クリップボードへのコピーに失敗しました", err);
    }
  }, [content]);

  return (
    <button
      type="button"
      aria-label={copied ? "コピーしました" : "メッセージをコピー"}
      aria-live="polite"
      onClick={handleCopy}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--sds-spacing-extra-small, 4px)",
        background: "none",
        border: "1px solid var(--sds-color-outline-default)",
        borderRadius: "var(--sds-border-radius-extra-small, 4px)",
        cursor: "pointer",
        padding: "2px 8px",
        fontSize: "var(--sds-typography-label-small-font-size, 12px)",
        color: copied
          ? "var(--sds-color-positive-default)"
          : "var(--sds-color-on-surface-low)",
        transition: "color 0.2s ease, border-color 0.2s ease",
        borderColor: copied
          ? "var(--sds-color-positive-default)"
          : "var(--sds-color-outline-default)",
      }}
    >
      <span aria-hidden="true">{copied ? "✓" : "⎘"}</span>
      <span>{copied ? "コピーしました" : "コピー"}</span>
    </button>
  );
}
