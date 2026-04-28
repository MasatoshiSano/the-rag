// TrashList: soft-deleted documents with restore and permanent delete
import { useState, useCallback } from "react";
import { Button } from "@serendie/ui";
import {
  SerendieSymbolRefresh,
  SerendieSymbolTrash,
} from "@serendie/symbols";
import type { Document } from "../../types/document";

interface TrashListProps {
  documents: Document[];
  onRestore: (doc: Document) => void;
  onPermanentDelete: (doc: Document) => void;
}

const RETENTION_DAYS = 30;

function daysUntilExpiry(deleted_at: string): number {
  const deleted = new Date(deleted_at).getTime();
  const expiry = deleted + RETENTION_DAYS * 24 * 60 * 60 * 1000;
  const now = Date.now();
  return Math.max(0, Math.ceil((expiry - now) / (24 * 60 * 60 * 1000)));
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface ConfirmDialogProps {
  doc: Document;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDialog({ doc, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-desc"
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 300,
      }}
    >
      {/* Backdrop */}
      <div
        aria-hidden="true"
        onClick={onCancel}
        style={{
          position: "absolute",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.5)",
        }}
      />
      <div
        style={{
          position: "relative",
          backgroundColor: "var(--sds-color-surface-default)",
          borderRadius: "var(--sds-border-radius-medium, 12px)",
          padding: "24px",
          maxWidth: "440px",
          width: "90%",
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
      >
        <h2
          id="confirm-dialog-title"
          style={{
            margin: "0 0 12px 0",
            fontSize: "var(--sds-typography-body-medium-font-size, 16px)",
            fontWeight: 700,
            color: "var(--sds-color-negative-default, #d32f2f)",
          }}
        >
          完全削除の確認
        </h2>
        <p
          id="confirm-dialog-desc"
          style={{
            margin: "0 0 20px 0",
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            color: "var(--sds-color-on-surface-default)",
            lineHeight: 1.6,
          }}
        >
          <strong>{doc.filename}</strong> を完全に削除します。
          この操作は取り消せません。本当に削除しますか？
        </p>
        <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
          <Button styleType="outlined" size="small" onClick={onCancel}>
            キャンセル
          </Button>
          <Button
            styleType="filled"
            size="small"
            onClick={onConfirm}
            style={{ backgroundColor: "var(--sds-color-negative-default, #d32f2f)" }}
          >
            完全削除
          </Button>
        </div>
      </div>
    </div>
  );
}

export function TrashList({ documents, onRestore, onPermanentDelete }: TrashListProps) {
  const [confirmTarget, setConfirmTarget] = useState<Document | null>(null);

  const handleConfirmDelete = useCallback(() => {
    if (confirmTarget) {
      onPermanentDelete(confirmTarget);
      setConfirmTarget(null);
    }
  }, [confirmTarget, onPermanentDelete]);

  if (documents.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-state-title">ゴミ箱は空です</p>
        <p className="empty-state-description">
          削除されたドキュメントは {RETENTION_DAYS} 日間ここに保管されます。
        </p>
      </div>
    );
  }

  return (
    <>
      <ul
        aria-label="削除済みドキュメント一覧"
        style={{ listStyle: "none", margin: 0, padding: 0 }}
      >
        {documents.map((doc) => {
          const remainingDays = doc.deleted_at ? daysUntilExpiry(doc.deleted_at) : RETENTION_DAYS;
          const isExpiringSoon = remainingDays <= 7;

          return (
            <li
              key={doc.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "12px 16px",
                borderRadius: "var(--sds-border-radius-small, 8px)",
                border: `1px solid ${
                  isExpiringSoon
                    ? "var(--sds-color-negative-default, #d32f2f)"
                    : "var(--sds-color-outline-default)"
                }`,
                backgroundColor: isExpiringSoon
                  ? "var(--sds-color-negative-container, #fdecea)"
                  : "var(--sds-color-surface-container)",
                marginBottom: "8px",
                flexWrap: "wrap",
              }}
            >
              {/* File info */}
              <div style={{ flex: 1, minWidth: "160px" }}>
                <p
                  style={{
                    margin: "0 0 2px 0",
                    fontWeight: 600,
                    fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                    color: "var(--sds-color-on-surface-default)",
                    wordBreak: "break-all",
                  }}
                >
                  {doc.filename}
                </p>
                <p
                  style={{
                    margin: 0,
                    fontSize: "11px",
                    color: "var(--sds-color-on-surface-variant)",
                  }}
                >
                  {doc.file_type.toUpperCase()}
                </p>
              </div>

              {/* Delete date */}
              <div style={{ textAlign: "center", minWidth: "120px" }}>
                <p
                  style={{
                    margin: "0 0 2px 0",
                    fontSize: "11px",
                    color: "var(--sds-color-on-surface-variant)",
                  }}
                >
                  削除日時
                </p>
                <p
                  style={{
                    margin: 0,
                    fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                    color: "var(--sds-color-on-surface-default)",
                  }}
                >
                  {doc.deleted_at ? formatDate(doc.deleted_at) : "—"}
                </p>
              </div>

              {/* Retention countdown */}
              <div style={{ textAlign: "center", minWidth: "80px" }}>
                <p
                  style={{
                    margin: "0 0 2px 0",
                    fontSize: "11px",
                    color: "var(--sds-color-on-surface-variant)",
                  }}
                >
                  残り
                </p>
                <p
                  style={{
                    margin: 0,
                    fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                    fontWeight: 700,
                    color: isExpiringSoon
                      ? "var(--sds-color-negative-default, #d32f2f)"
                      : "var(--sds-color-on-surface-default)",
                  }}
                >
                  {remainingDays} 日
                </p>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <Button
                  styleType="outlined"
                  size="small"
                  leftIcon={
                    <SerendieSymbolRefresh style={{ width: 14, height: 14 }} />
                  }
                  onClick={() => onRestore(doc)}
                  aria-label={`${doc.filename} を復元`}
                >
                  復元
                </Button>
                <Button
                  styleType="ghost"
                  size="small"
                  leftIcon={
                    <SerendieSymbolTrash style={{ width: 14, height: 14 }} />
                  }
                  onClick={() => setConfirmTarget(doc)}
                  aria-label={`${doc.filename} を完全削除`}
                  style={{ color: "var(--sds-color-negative-default, #d32f2f)" }}
                >
                  完全削除
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      {confirmTarget && (
        <ConfirmDialog
          doc={confirmTarget}
          onConfirm={handleConfirmDelete}
          onCancel={() => setConfirmTarget(null)}
        />
      )}
    </>
  );
}
