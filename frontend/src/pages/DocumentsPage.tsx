// DocumentsPage: document list with tabs for active docs and trash
import { useState, useCallback, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabItem } from "@serendie/ui";
import {
  SerendieSymbolFile,
  SerendieSymbolDataFilled,
} from "@serendie/symbols";
import { useKbStore } from "../stores/kbStore";
import { getKnowledgeBases } from "../api/knowledge-bases";
import {
  getDocuments,
  getDocument,
  cancelDocument,
  reindexDocument,
  softDeleteDocument,
  restoreDocument,
  permanentDeleteDocument,
} from "../api/documents";
import { DocumentTable } from "../components/documents/DocumentTable";
import { DocumentDetail } from "../components/documents/DocumentDetail";
import { TrashList } from "../components/documents/TrashList";
import type { Document } from "../types/document";

type TabValue = "documents" | "trash";

const ALL_STATUSES: Array<{ value: string; label: string }> = [
  { value: "", label: "すべて" },
  { value: "processing", label: "処理中" },
  { value: "indexed", label: "完了" },
  { value: "convert_failed", label: "変換失敗" },
  { value: "tag_failed", label: "タグ失敗" },
  { value: "index_failed", label: "インデックス失敗" },
  { value: "permanent_failed", label: "処理失敗" },
  { value: "cancelled", label: "キャンセル" },
  { value: "tagged", label: "タグ付け完了" },
];

const LIMIT = 20;

export function DocumentsPage() {
  const { id: urlDocumentId } = useParams<{ id?: string }>();
  const queryClient = useQueryClient();
  const { selectedKbId, setSelectedKbId } = useKbStore();

  const [activeTab, setActiveTab] = useState<TabValue>("documents");
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [detailDoc, setDetailDoc] = useState<Document | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [detailInitialTab, setDetailInitialTab] = useState<"tags" | "preview" | "versions">("tags");

  // Open document detail when navigating via /documents/:id
  useEffect(() => {
    if (!urlDocumentId) return;
    let cancelled = false;
    getDocument(urlDocumentId).then((doc) => {
      if (cancelled) return;
      if (doc.knowledge_base_id && doc.knowledge_base_id !== selectedKbId) {
        setSelectedKbId(doc.knowledge_base_id);
      }
      setDetailDoc(doc);
      setDetailInitialTab("preview");
      setIsDetailOpen(true);
    }).catch(() => { /* ignore fetch errors */ });
    return () => { cancelled = true; };
  }, [urlDocumentId, selectedKbId, setSelectedKbId]);

  // Knowledge bases for selector
  const { data: knowledgeBases = [] } = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: getKnowledgeBases,
  });

  // Active documents
  const { data: activeDocuments = [], isLoading: isLoadingDocs } = useQuery({
    queryKey: ["documents", selectedKbId, offset, statusFilter],
    queryFn: () =>
      getDocuments({
        knowledge_base_id: selectedKbId!,
        limit: LIMIT,
        offset,
        status: statusFilter || undefined,
      }),
    enabled: !!selectedKbId && activeTab === "documents",
    refetchInterval: 5000,
  });

  // Trash documents (deletedAt != null)
  const { data: allForTrash = [], isLoading: isLoadingTrash } = useQuery({
    queryKey: ["documents-trash", selectedKbId],
    queryFn: () =>
      getDocuments({
        knowledge_base_id: selectedKbId!,
        limit: 100,
        offset: 0,
      }),
    enabled: !!selectedKbId && activeTab === "trash",
    refetchInterval: 10000,
    select: (docs) => docs.filter((d) => d.deleted_at !== null),
  });

  const cancelMutation = useMutation({
    mutationFn: (doc: Document) => cancelDocument(doc.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (doc: Document) => reindexDocument(doc.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (doc: Document) => softDeleteDocument(doc.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (doc: Document) => restoreDocument(doc.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["documents-trash"] });
    },
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: (doc: Document) => permanentDeleteDocument(doc.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["documents-trash"] });
    },
  });

  const handleDocumentClick = useCallback((doc: Document) => {
    setDetailDoc(doc);
    setDetailInitialTab("tags");
    setIsDetailOpen(true);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setIsDetailOpen(false);
  }, []);

  const handleTabChange = useCallback((tab: TabValue) => {
    setActiveTab(tab);
    setOffset(0);
    setSelectedDocumentIds([]);
  }, []);

  const handleStatusFilterChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      setStatusFilter(e.target.value);
      setOffset(0);
    },
    []
  );

  const trashCount = allForTrash.length;

  return (
    <section aria-label="ドキュメント管理">
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "16px", boxSizing: "border-box" }}>
        {/* Page heading */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "20px",
          }}
        >
          <SerendieSymbolFile
            style={{
              width: 28,
              height: 28,
              color: "var(--sds-color-impression-primary)",
            }}
            aria-hidden="true"
          />
          <h1
            style={{
              margin: 0,
              fontSize: "var(--sds-typography-headline-small-font-size, 20px)",
              fontWeight: 700,
              color: "var(--sds-color-on-surface-default)",
            }}
          >
            ドキュメント管理
          </h1>
        </div>

        {/* KB selector */}
        <div style={{ marginBottom: "20px" }}>
          <label
            htmlFor="docs-kb-select"
            style={{
              display: "block",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              fontWeight: 600,
              color: "var(--sds-color-on-surface-default)",
              marginBottom: "6px",
            }}
          >
            <SerendieSymbolDataFilled
              style={{
                width: 14,
                height: 14,
                verticalAlign: "middle",
                marginRight: "4px",
              }}
              aria-hidden="true"
            />
            ナレッジベース
          </label>
          <select
            id="docs-kb-select"
            value={selectedKbId ?? ""}
            onChange={(e) => {
              setSelectedKbId(e.target.value || null);
              setOffset(0);
            }}
            style={{
              maxWidth: "400px",
              width: "100%",
              padding: "8px 12px",
              fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
              border: "1px solid var(--sds-color-outline-default)",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              backgroundColor: "var(--sds-color-surface-default)",
              color: "var(--sds-color-on-surface-default)",
              cursor: "pointer",
              outline: "none",
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow =
                "0 0 0 2px var(--sds-color-impression-primary)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = "none";
            }}
          >
            <option value="">-- ナレッジベースを選択 --</option>
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </div>

        {!selectedKbId ? (
          <div className="empty-state">
            <SerendieSymbolDataFilled
              style={{
                width: 48,
                height: 48,
                color: "var(--sds-color-on-surface-variant)",
              }}
              aria-hidden="true"
            />
            <p className="empty-state-title">ナレッジベースを選択してください</p>
            <p className="empty-state-description">
              上のドロップダウンからナレッジベースを選択すると、ドキュメント一覧が表示されます。
            </p>
          </div>
        ) : (
          <>
            {/* Tabs */}
            <Tabs
              value={activeTab}
              onValueChange={(e) => handleTabChange(e.value as TabValue)}
            >
              <TabItem
                title="ドキュメント"
                value="documents"
              />
              <TabItem
                title="ゴミ箱"
                value="trash"
                badge={trashCount > 0 ? trashCount : undefined}
              />
            </Tabs>

            {/* Documents tab content */}
            {activeTab === "documents" && (
              <div style={{ marginTop: "16px" }}>
                {/* Filters */}
                <div
                  style={{
                    display: "flex",
                    gap: "12px",
                    flexWrap: "wrap",
                    marginBottom: "12px",
                    alignItems: "center",
                  }}
                >
                  <label
                    htmlFor="status-filter"
                    style={{
                      fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                      color: "var(--sds-color-on-surface-default)",
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}
                  >
                    ステータス:
                  </label>
                  <select
                    id="status-filter"
                    value={statusFilter}
                    onChange={handleStatusFilterChange}
                    style={{
                      padding: "6px 10px",
                      fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                      border: "1px solid var(--sds-color-outline-default)",
                      borderRadius: "var(--sds-border-radius-small, 8px)",
                      backgroundColor: "var(--sds-color-surface-default)",
                      color: "var(--sds-color-on-surface-default)",
                      cursor: "pointer",
                      outline: "none",
                    }}
                    onFocus={(e) => {
                      e.currentTarget.style.boxShadow =
                        "0 0 0 2px var(--sds-color-impression-primary)";
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.boxShadow = "none";
                    }}
                  >
                    {ALL_STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>

                  {selectedDocumentIds.length > 0 && (
                    <span
                      aria-live="polite"
                      style={{
                        fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                        color: "var(--sds-color-impression-primary)",
                      }}
                    >
                      {selectedDocumentIds.length} 件選択中
                    </span>
                  )}
                </div>

                {isLoadingDocs ? (
                  <div
                    role="status"
                    aria-label="ドキュメントを読み込み中"
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      padding: "48px",
                      color: "var(--sds-color-on-surface-variant)",
                    }}
                  >
                    読み込み中...
                  </div>
                ) : (
                  <DocumentTable
                    documents={activeDocuments.filter((d) => d.deleted_at === null)}
                    total={activeDocuments.filter((d) => d.deleted_at === null).length}
                    limit={LIMIT}
                    offset={offset}
                    onPageChange={setOffset}
                    onDocumentClick={handleDocumentClick}
                    onCancel={(doc) => cancelMutation.mutate(doc)}
                    onRetry={(doc) => retryMutation.mutate(doc)}
                    onDelete={(doc) => deleteMutation.mutate(doc)}
                    selectedIds={selectedDocumentIds}
                    onSelectionChange={setSelectedDocumentIds}
                  />
                )}
              </div>
            )}

            {/* Trash tab content */}
            {activeTab === "trash" && (
              <div style={{ marginTop: "16px" }}>
                {isLoadingTrash ? (
                  <div
                    role="status"
                    aria-label="ゴミ箱を読み込み中"
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      padding: "48px",
                      color: "var(--sds-color-on-surface-variant)",
                    }}
                  >
                    読み込み中...
                  </div>
                ) : (
                  <TrashList
                    documents={allForTrash}
                    onRestore={(doc) => restoreMutation.mutate(doc)}
                    onPermanentDelete={(doc) => permanentDeleteMutation.mutate(doc)}
                  />
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Document detail drawer */}
      <DocumentDetail
        document={detailDoc}
        isOpen={isDetailOpen}
        onClose={handleCloseDetail}
        initialTab={detailInitialTab}
      />
    </section>
  );
}
