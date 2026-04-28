// UploadProgress: per-file status indicator with polling every 2 seconds
import { useEffect, useRef } from "react";
import { IconButton } from "@serendie/ui";
import {
  SerendieSymbolFile,
  SerendieSymbolClose,
  SerendieSymbolCheckCircleFilled,
  SerendieSymbolAlertCircleFilled,
  SerendieSymbolRefresh,
} from "@serendie/symbols";
import type { DocumentStatus } from "../../types/document";
import { getDocument } from "../../api/documents";

export interface UploadedFile {
  documentId: string;
  fileName: string;
  fileSize: number;
  status: DocumentStatus;
}

interface UploadProgressProps {
  files: UploadedFile[];
  onStatusUpdate: (documentId: string, status: DocumentStatus) => void;
  onRemove: (documentId: string) => void;
}

const STATUS_LABELS: Record<DocumentStatus, string> = {
  processing: "処理中",
  converting: "変換中",
  converted: "変換完了",
  tagging: "タグ付け中",
  tagged: "タグ付け完了",
  confirmed: "確認済み",
  chunking: "チャンク化中",
  chunked: "チャンク化完了",
  indexing: "インデックス構築中",
  indexed: "インデックス完了",
  convert_failed: "変換失敗",
  tag_failed: "タグ付け失敗",
  index_failed: "インデックス失敗",
  permanent_failed: "処理失敗",
  cancelled: "キャンセル済み",
};

const POLLING_STATUSES: DocumentStatus[] = [
  "processing",
  "converting",
  "tagging",
  "confirmed",
  "chunking",
  "indexing",
];

const FAILED_STATUSES: DocumentStatus[] = [
  "convert_failed",
  "tag_failed",
  "index_failed",
  "permanent_failed",
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const DONE_STATUSES: DocumentStatus[] = ["indexed", "tagged", "converted", "chunked"];

function StatusIcon({ status }: { status: DocumentStatus }) {
  if (DONE_STATUSES.includes(status)) {
    return (
      <SerendieSymbolCheckCircleFilled
        style={{ width: 20, height: 20, color: "var(--sds-color-positive-default, #2e7d32)" }}
        aria-hidden="true"
      />
    );
  }
  if (FAILED_STATUSES.includes(status) || status === "cancelled") {
    return (
      <SerendieSymbolAlertCircleFilled
        style={{ width: 20, height: 20, color: "var(--sds-color-negative-default, #d32f2f)" }}
        aria-hidden="true"
      />
    );
  }
  if (POLLING_STATUSES.includes(status)) {
    return (
      <SerendieSymbolRefresh
        style={{
          width: 20,
          height: 20,
          color: "var(--sds-color-impression-primary)",
          animation: "spin 1.5s linear infinite",
        }}
        aria-hidden="true"
      />
    );
  }
  return (
    <SerendieSymbolFile
      style={{ width: 20, height: 20, color: "var(--sds-color-on-surface-variant)" }}
      aria-hidden="true"
    />
  );
}

function ProgressBar({ status }: { status: DocumentStatus }) {
  const isActive = POLLING_STATUSES.includes(status);
  const isDone = DONE_STATUSES.includes(status);
  const isFailed = FAILED_STATUSES.includes(status);

  if (!isActive && !isDone && !isFailed) return null;

  return (
    <div
      role="progressbar"
      aria-label={`処理状況: ${STATUS_LABELS[status]}`}
      aria-valuenow={isDone ? 100 : undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      style={{
        height: "4px",
        borderRadius: "2px",
        backgroundColor: "var(--sds-color-surface-variant)",
        overflow: "hidden",
        marginTop: "4px",
      }}
    >
      <div
        style={{
          height: "100%",
          borderRadius: "2px",
          backgroundColor: isFailed
            ? "var(--sds-color-negative-default, #d32f2f)"
            : isDone
            ? "var(--sds-color-positive-default, #2e7d32)"
            : "var(--sds-color-impression-primary)",
          width: isDone ? "100%" : "60%",
          transition: "width 0.3s ease",
          ...(isActive
            ? {
                animation: "indeterminate 1.5s infinite ease-in-out",
                transformOrigin: "left center",
              }
            : {}),
        }}
      />
    </div>
  );
}

export function UploadProgress({ files, onStatusUpdate, onRemove }: UploadProgressProps) {
  const intervalsRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  useEffect(() => {
    // Add CSS animation keyframes once
    if (!document.getElementById("upload-progress-styles")) {
      const style = document.createElement("style");
      style.id = "upload-progress-styles";
      style.textContent = `
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes indeterminate {
          0% { transform: translateX(-100%) scaleX(0.5); }
          50% { transform: translateX(50%) scaleX(0.8); }
          100% { transform: translateX(200%) scaleX(0.5); }
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  useEffect(() => {
    const currentIntervals = intervalsRef.current;

    for (const file of files) {
      const shouldPoll = POLLING_STATUSES.includes(file.status);
      const isPolling = currentIntervals.has(file.documentId);

      if (shouldPoll && !isPolling) {
        const interval = setInterval(async () => {
          try {
            const doc = await getDocument(file.documentId);
            onStatusUpdate(file.documentId, doc.status);
            if (!POLLING_STATUSES.includes(doc.status)) {
              clearInterval(currentIntervals.get(file.documentId));
              currentIntervals.delete(file.documentId);
            }
          } catch {
            // Silently ignore polling errors
          }
        }, 2000);
        currentIntervals.set(file.documentId, interval);
      } else if (!shouldPoll && isPolling) {
        clearInterval(currentIntervals.get(file.documentId));
        currentIntervals.delete(file.documentId);
      }
    }

    // Clean up intervals for removed files
    for (const [id, interval] of currentIntervals) {
      if (!files.find((f) => f.documentId === id)) {
        clearInterval(interval);
        currentIntervals.delete(id);
      }
    }

    return () => {
      // Cleanup on unmount
      for (const interval of currentIntervals.values()) {
        clearInterval(interval);
      }
      currentIntervals.clear();
    };
  }, [files, onStatusUpdate]);

  if (files.length === 0) return null;

  return (
    <section aria-label="アップロードファイル一覧">
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        {files.map((file) => {
          const isFailed = FAILED_STATUSES.includes(file.status);
          return (
            <li
              key={file.documentId}
              aria-label={`${file.fileName}: ${STATUS_LABELS[file.status]}`}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "10px",
                padding: "10px 12px",
                borderRadius: "var(--sds-border-radius-small, 8px)",
                backgroundColor: "var(--sds-color-surface-container)",
                border: `1px solid ${
                  isFailed
                    ? "var(--sds-color-negative-default, #d32f2f)"
                    : "var(--sds-color-surface-variant)"
                }`,
              }}
            >
              <StatusIcon status={file.status} />

              <div style={{ flex: 1, minWidth: 0 }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                    fontWeight: 600,
                    color: "var(--sds-color-on-surface-default)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={file.fileName}
                >
                  {file.fileName}
                </p>
                <p
                  style={{
                    margin: "2px 0 0 0",
                    fontSize: "var(--sds-typography-body-small-font-size, 11px)",
                    color: isFailed
                      ? "var(--sds-color-negative-default, #d32f2f)"
                      : "var(--sds-color-on-surface-variant)",
                  }}
                >
                  {STATUS_LABELS[file.status]} &middot; {formatFileSize(file.fileSize)}
                </p>
                <ProgressBar status={file.status} />
              </div>

              <IconButton
                icon={<SerendieSymbolClose style={{ width: 16, height: 16 }} />}
                aria-label={`${file.fileName} をリストから削除`}
                shape="circle"
                styleType="ghost"
                size="small"
                onClick={() => onRemove(file.documentId)}
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}
