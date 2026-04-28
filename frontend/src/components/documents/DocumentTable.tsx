// DocumentTable: filterable, paginated document list with status badges and actions
import { useCallback, useId } from "react";
import { Button, IconButton } from "@serendie/ui";
import {
  SerendieSymbolDelete,
  SerendieSymbolRefresh,
  SerendieSymbolClose,
  SerendieSymbolChevronLeft,
  SerendieSymbolChevronRight,
  SerendieSymbolDownload,
} from "@serendie/symbols";
import { downloadDocument } from "../../api/documents";
import type { Document, DocumentStatus } from "../../types/document";

const STATUS_LABELS: Record<DocumentStatus, string> = {
  processing: "処理中",
  converting: "変換中",
  converted: "変換完了",
  tagging: "タグ付け中",
  tagged: "タグ付け完了",
  confirmed: "確認済み",
  chunking: "チャンク化中",
  chunked: "チャンク化完了",
  indexing: "インデックス中",
  indexed: "完了",
  convert_failed: "変換失敗",
  tag_failed: "タグ失敗",
  index_failed: "インデックス失敗",
  permanent_failed: "処理失敗",
  cancelled: "キャンセル",
};

type StatusColor = {
  bg: string;
  text: string;
  border: string;
};

const STATUS_COLORS: Record<string, StatusColor> = {
  indexed: {
    bg: "var(--sds-color-positive-container, #e8f5e9)",
    text: "var(--sds-color-positive-default, #2e7d32)",
    border: "var(--sds-color-positive-default, #2e7d32)",
  },
  processing: {
    bg: "#e3f0fc",
    text: "#0353AA",
    border: "#0353AA",
  },
  converting: {
    bg: "#e3f0fc",
    text: "#0353AA",
    border: "#0353AA",
  },
  tagging: {
    bg: "#e3f0fc",
    text: "#0353AA",
    border: "#0353AA",
  },
  chunking: {
    bg: "#e3f0fc",
    text: "#0353AA",
    border: "#0353AA",
  },
  indexing: {
    bg: "#e3f0fc",
    text: "#0353AA",
    border: "#0353AA",
  },
  convert_failed: {
    bg: "var(--sds-color-negative-container, #fdecea)",
    text: "var(--sds-color-negative-default, #d32f2f)",
    border: "var(--sds-color-negative-default, #d32f2f)",
  },
  tag_failed: {
    bg: "var(--sds-color-negative-container, #fdecea)",
    text: "var(--sds-color-negative-default, #d32f2f)",
    border: "var(--sds-color-negative-default, #d32f2f)",
  },
  index_failed: {
    bg: "var(--sds-color-negative-container, #fdecea)",
    text: "var(--sds-color-negative-default, #d32f2f)",
    border: "var(--sds-color-negative-default, #d32f2f)",
  },
  permanent_failed: {
    bg: "var(--sds-color-negative-container, #fdecea)",
    text: "var(--sds-color-negative-default, #d32f2f)",
    border: "var(--sds-color-negative-default, #d32f2f)",
  },
  cancelled: {
    bg: "var(--sds-color-surface-variant)",
    text: "var(--sds-color-on-surface-variant)",
    border: "var(--sds-color-outline-default)",
  },
  tagged: {
    bg: "var(--sds-color-warning-container, #fff3e0)",
    text: "var(--sds-color-warning-default, #f57c00)",
    border: "var(--sds-color-warning-default, #f57c00)",
  },
};

function getStatusColor(status: DocumentStatus): StatusColor {
  return (
    STATUS_COLORS[status] ?? {
      bg: "var(--sds-color-surface-container)",
      text: "var(--sds-color-on-surface-variant)",
      border: "var(--sds-color-outline-default)",
    }
  );
}

const FAILED_STATUSES: DocumentStatus[] = [
  "convert_failed",
  "tag_failed",
  "index_failed",
  "permanent_failed",
];

const PROCESSING_STATUSES: DocumentStatus[] = [
  "processing",
  "converting",
  "tagging",
  "confirmed",
  "chunking",
  "indexing",
];

interface DocumentTableProps {
  documents: Document[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  onDocumentClick: (doc: Document) => void;
  onCancel: (doc: Document) => void;
  onRetry: (doc: Document) => void;
  onDelete: (doc: Document) => void;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function DocumentTable({
  documents,
  total,
  limit,
  offset,
  onPageChange,
  onDocumentClick,
  onCancel,
  onRetry,
  onDelete,
  selectedIds,
  onSelectionChange,
}: DocumentTableProps) {
  const selectAllId = useId();
  const totalPages = Math.ceil(total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  const allSelected =
    documents.length > 0 &&
    documents.every((d) => selectedIds.includes(d.id));

  const handleSelectAll = useCallback(
    (checked: boolean) => {
      if (checked) {
        onSelectionChange([
          ...new Set([...selectedIds, ...documents.map((d) => d.id)]),
        ]);
      } else {
        const docIds = new Set(documents.map((d) => d.id));
        onSelectionChange(selectedIds.filter((id) => !docIds.has(id)));
      }
    },
    [documents, selectedIds, onSelectionChange]
  );

  const handleSelectOne = useCallback(
    (id: string, checked: boolean) => {
      if (checked) {
        onSelectionChange([...selectedIds, id]);
      } else {
        onSelectionChange(selectedIds.filter((sid) => sid !== id));
      }
    },
    [selectedIds, onSelectionChange]
  );

  if (documents.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-state-title">ドキュメントがありません</p>
        <p className="empty-state-description">
          フィルターを変更するか、ドキュメントをアップロードしてください。
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ overflowX: "auto" }}>
        <table
          aria-label="ドキュメント一覧"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "2px solid var(--sds-color-outline-default)",
                backgroundColor: "var(--sds-color-surface-container)",
              }}
            >
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "center",
                  width: "40px",
                }}
              >
                <input
                  id={selectAllId}
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                  aria-label="すべて選択"
                  style={{ width: "16px", height: "16px", cursor: "pointer" }}
                />
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "left",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                }}
              >
                ファイル名
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "left",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                  minWidth: "100px",
                }}
              >
                ステータス
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "left",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                }}
              >
                タグ
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "center",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                  width: "60px",
                }}
              >
                Ver.
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "left",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                  whiteSpace: "nowrap",
                }}
              >
                アップロード日
              </th>
              <th
                scope="col"
                style={{
                  padding: "10px 12px",
                  textAlign: "right",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-default)",
                  minWidth: "120px",
                }}
              >
                操作
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc, idx) => {
              const color = getStatusColor(doc.status);
              const isSelected = selectedIds.includes(doc.id);
              const isFailed = FAILED_STATUSES.includes(doc.status);
              const isProcessing = PROCESSING_STATUSES.includes(doc.status);

              return (
                <tr
                  key={doc.id}
                  style={{
                    borderBottom: "1px solid var(--sds-color-surface-variant)",
                    backgroundColor: isSelected
                      ? "var(--sds-color-impression-primaryContainer)"
                      : idx % 2 === 0
                      ? "var(--sds-color-surface-default)"
                      : "var(--sds-color-surface-container)",
                    cursor: "pointer",
                  }}
                  onClick={() => onDocumentClick(doc)}
                >
                  {/* Checkbox cell */}
                  <td
                    style={{ padding: "10px 12px", textAlign: "center" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(e) => handleSelectOne(doc.id, e.target.checked)}
                      aria-label={`${doc.filename} を選択`}
                      style={{ width: "16px", height: "16px", cursor: "pointer" }}
                    />
                  </td>

                  {/* Filename */}
                  <td style={{ padding: "10px 12px" }}>
                    <div>
                      <span
                        style={{
                          display: "block",
                          fontWeight: 500,
                          color: "var(--sds-color-on-surface-default)",
                          maxWidth: "240px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={doc.filename}
                      >
                        {doc.filename}
                      </span>
                      <span
                        style={{
                          fontSize: "11px",
                          color: "var(--sds-color-on-surface-variant)",
                        }}
                      >
                        {doc.file_type.toUpperCase()}
                      </span>
                    </div>
                  </td>

                  {/* Status badge */}
                  <td style={{ padding: "10px 12px" }}>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: "var(--sds-border-radius-full, 9999px)",
                        fontSize: "11px",
                        fontWeight: 600,
                        backgroundColor: color.bg,
                        color: color.text,
                        border: `1px solid ${color.border}`,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {STATUS_LABELS[doc.status]}
                    </span>
                  </td>

                  {/* Tags */}
                  <td style={{ padding: "10px 12px" }}>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "4px",
                        maxWidth: "200px",
                      }}
                    >
                      {doc.tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag.id}
                          style={{
                            display: "inline-block",
                            padding: "1px 6px",
                            borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
                            fontSize: "11px",
                            backgroundColor: "var(--sds-color-surface-variant)",
                            color: "var(--sds-color-on-surface-variant)",
                            border: "1px solid var(--sds-color-outline-default)",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {tag.tag_key}: {tag.tag_value}
                        </span>
                      ))}
                      {doc.tags.length > 3 && (
                        <span
                          style={{
                            fontSize: "11px",
                            color: "var(--sds-color-on-surface-variant)",
                          }}
                        >
                          +{doc.tags.length - 3}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Version */}
                  <td
                    style={{
                      padding: "10px 12px",
                      textAlign: "center",
                      color: "var(--sds-color-on-surface-variant)",
                    }}
                  >
                    v{doc.version}
                  </td>

                  {/* Date */}
                  <td
                    style={{
                      padding: "10px 12px",
                      color: "var(--sds-color-on-surface-variant)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {formatDate(doc.uploaded_at)}
                  </td>

                  {/* Actions */}
                  <td
                    style={{
                      padding: "10px 12px",
                      textAlign: "right",
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: "4px",
                        justifyContent: "flex-end",
                        alignItems: "center",
                      }}
                    >
                      {doc.status === "indexed" && (
                        <IconButton
                          icon={
                            <SerendieSymbolDownload style={{ width: 16, height: 16 }} />
                          }
                          aria-label={`${doc.filename} をダウンロード`}
                          title="ダウンロード"
                          shape="circle"
                          styleType="ghost"
                          size="small"
                          onClick={() => downloadDocument(doc.id, doc.filename)}
                        />
                      )}

                      {isProcessing && (
                        <Button
                          styleType="outlined"
                          size="small"
                          leftIcon={
                            <SerendieSymbolClose style={{ width: 14, height: 14 }} />
                          }
                          onClick={() => onCancel(doc)}
                          aria-label={`${doc.filename} を中止`}
                        >
                          中止
                        </Button>
                      )}

                      {isFailed && doc.status !== "permanent_failed" && (
                        <Button
                          styleType="outlined"
                          size="small"
                          leftIcon={
                            <SerendieSymbolRefresh style={{ width: 14, height: 14 }} />
                          }
                          onClick={() => onRetry(doc)}
                          aria-label={`${doc.filename} を再試行 (${doc.retry_count}/3)`}
                        >
                          再試行 ({doc.retry_count}/3)
                        </Button>
                      )}

                      {doc.status === "tagged" && (
                        <Button
                          styleType="filled"
                          size="small"
                          leftIcon={
                            <SerendieSymbolRefresh style={{ width: 14, height: 14 }} />
                          }
                          onClick={() => onRetry(doc)}
                          aria-label={`${doc.filename} のインデックスを構築`}
                        >
                          インデックス構築
                        </Button>
                      )}

                      {doc.status === "cancelled" && (
                        <Button
                          styleType="outlined"
                          size="small"
                          leftIcon={
                            <SerendieSymbolRefresh style={{ width: 14, height: 14 }} />
                          }
                          onClick={() => onRetry(doc)}
                          aria-label={`${doc.filename} を再試行`}
                        >
                          再試行
                        </Button>
                      )}

                      {!isProcessing && (
                        <IconButton
                          icon={
                            <SerendieSymbolDelete style={{ width: 16, height: 16 }} />
                          }
                          aria-label={`${doc.filename} を削除`}
                          title="削除"
                          shape="circle"
                          styleType="ghost"
                          size="small"
                          onClick={() => onDelete(doc)}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <nav
          aria-label="ページネーション"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: "8px",
            marginTop: "16px",
          }}
        >
          <span
            style={{
              fontSize: "var(--sds-typography-body-small-font-size, 12px)",
              color: "var(--sds-color-on-surface-variant)",
            }}
          >
            {offset + 1}–{Math.min(offset + limit, total)} / {total} 件
          </span>
          <IconButton
            icon={<SerendieSymbolChevronLeft style={{ width: 18, height: 18 }} />}
            aria-label="前のページ"
            shape="circle"
            styleType="outlined"
            size="small"
            disabled={offset === 0}
            onClick={() => onPageChange(Math.max(0, offset - limit))}
          />
          <span
            aria-current="page"
            style={{
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              color: "var(--sds-color-on-surface-default)",
            }}
          >
            {currentPage} / {totalPages}
          </span>
          <IconButton
            icon={<SerendieSymbolChevronRight style={{ width: 18, height: 18 }} />}
            aria-label="次のページ"
            shape="circle"
            styleType="outlined"
            size="small"
            disabled={offset + limit >= total}
            onClick={() => onPageChange(offset + limit)}
          />
        </nav>
      )}
    </div>
  );
}
