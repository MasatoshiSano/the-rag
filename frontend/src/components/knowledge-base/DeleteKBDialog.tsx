// DeleteKBDialog: KB削除確認ダイアログ（破壊的操作の確認）
// WCAG 2.1.1: キーボード操作、focus management

import { useEffect, useRef, useId } from "react";
import type { KnowledgeBase } from "../../types/knowledge-base";

interface DeleteKBDialogProps {
  kb: KnowledgeBase | null;
  onClose: () => void;
  onConfirm: (id: string) => Promise<void>;
  isDeleting: boolean;
}

export function DeleteKBDialog({
  kb,
  onClose,
  onConfirm,
  isDeleting,
}: DeleteKBDialogProps) {
  const titleId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (kb) {
      const timer = setTimeout(() => cancelRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [kb]);

  useEffect(() => {
    if (!kb) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [kb, onClose]);

  if (!kb) return null;

  return (
    <div
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.5)",
        zIndex: 500,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          backgroundColor: "var(--sds-color-surface-default)",
          borderRadius: 8,
          padding: 24,
          width: "100%",
          maxWidth: 400,
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
      >
        <h2
          id={titleId}
          style={{
            margin: "0 0 12px",
            fontSize: 18,
            fontWeight: 600,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          ナレッジベースを削除
        </h2>
        <p
          style={{
            margin: "0 0 24px",
            fontSize: 14,
            color: "var(--sds-color-on-surface-default)",
            lineHeight: 1.6,
          }}
        >
          <strong>{kb.name}</strong> を削除しますか？
          <br />
          関連するすべてのドキュメントとセッションも削除されます。この操作は取り消せません。
        </p>
        <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
          <button
            ref={cancelRef}
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            style={{
              padding: "8px 20px",
              border: "1px solid var(--sds-color-outline-default)",
              borderRadius: 6,
              backgroundColor: "transparent",
              color: "var(--sds-color-on-surface-default)",
              fontSize: 14,
              cursor: isDeleting ? "not-allowed" : "pointer",
              fontWeight: 500,
            }}
          >
            キャンセル
          </button>
          <button
            type="button"
            aria-busy={isDeleting}
            onClick={() => onConfirm(kb.id)}
            disabled={isDeleting}
            style={{
              padding: "8px 20px",
              border: "none",
              borderRadius: 6,
              backgroundColor: "var(--sds-color-error-default, #B00020)",
              color: "#fff",
              fontSize: 14,
              cursor: isDeleting ? "not-allowed" : "pointer",
              fontWeight: 500,
              opacity: isDeleting ? 0.7 : 1,
            }}
          >
            {isDeleting ? "削除中..." : "削除する"}
          </button>
        </div>
      </div>
    </div>
  );
}
