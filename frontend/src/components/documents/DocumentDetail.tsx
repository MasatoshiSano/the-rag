// DocumentDetail: slide-in drawer with tag editing, markdown preview, version history
import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, IconButton } from "@serendie/ui";
import {
  SerendieSymbolClose,
  SerendieSymbolSave,
  SerendieSymbolDownload,
} from "@serendie/symbols";
import type { Document } from "../../types/document";
import type { EditableTag } from "../upload/TagEditor";
import {
  getDocument,
  getDocumentVersions,
  patchDocumentTags,
  downloadDocument,
} from "../../api/documents";
import { TagEditor } from "../upload/TagEditor";

type DrawerTab = "tags" | "preview" | "versions";

interface DocumentDetailProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
  initialTab?: DrawerTab;
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUS_LABELS: Record<string, string> = {
  processing: "処理中",
  converting: "変換中",
  converted: "変換完了",
  tagging: "タグ付け中",
  tagged: "未確認",
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

export function DocumentDetail({ document, isOpen, onClose, initialTab = "tags" }: DocumentDetailProps) {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<DrawerTab>(initialTab);
  const [editableTags, setEditableTags] = useState<EditableTag[]>([]);
  const [tagsDirty, setTagsDirty] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  // Fetch detail (markdown content)
  const { data: detail } = useQuery({
    queryKey: ["document-detail", document?.id],
    queryFn: () => getDocument(document!.id),
    enabled: isOpen && !!document?.id,
  });

  // Fetch versions
  const { data: versions = [] } = useQuery({
    queryKey: ["document-versions", document?.id],
    queryFn: () => getDocumentVersions(document!.id),
    enabled: isOpen && !!document?.id && activeTab === "versions",
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!document) return;
      await patchDocumentTags(
        document.id,
        editableTags.map((t) => ({
          tag_key: t.tagKey,
          tag_value: t.tagValue,
          confirmed: t.confirmed,
        }))
      );
    },
    onSuccess: () => {
      setTagsDirty(false);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["document-detail", document?.id] });
    },
  });

  // Reset tab when initialTab changes (e.g. navigating from source panel)
  useEffect(() => {
    if (isOpen) setActiveTab(initialTab);
  }, [isOpen, initialTab]);

  // Sync tags from document when it changes
  useEffect(() => {
    if (document) {
      setEditableTags(
        (document.tags ?? []).map((t) => ({
          id: String(t.id),
          tagKey: t.tag_key,
          tagValue: t.tag_value,
          confidence: t.confidence,
          confirmed: t.confirmed,
        }))
      );
      setTagsDirty(false);
    }
  }, [document]);

  // Focus trap and ESC key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);

    // Focus close button on open
    setTimeout(() => closeBtnRef.current?.focus(), 100);

    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleTagsChange = useCallback(
    (_: string, tags: EditableTag[]) => {
      setEditableTags(tags);
      setTagsDirty(true);
    },
    []
  );

  const tabs: { id: DrawerTab; label: string }[] = [
    { id: "tags", label: "タグ" },
    { id: "preview", label: "プレビュー" },
    { id: "versions", label: "バージョン" },
  ];

  if (!isOpen) return null;

  return (
    <>
      {/* Overlay */}
      <div
        aria-hidden="true"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.4)",
          zIndex: 200,
        }}
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label={document ? `${document.filename} の詳細` : "ドキュメント詳細"}
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: "min(560px, 100vw)",
          backgroundColor: "var(--sds-color-surface-default)",
          boxShadow: "-4px 0 24px rgba(0,0,0,0.15)",
          zIndex: 201,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Drawer header */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "12px",
            padding: "16px 20px",
            borderBottom: "1px solid var(--sds-color-outline-default)",
            backgroundColor: "var(--sds-color-surface-container)",
            flexShrink: 0,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2
              style={{
                margin: "0 0 4px 0",
                fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
                fontWeight: 700,
                color: "var(--sds-color-on-surface-default)",
                wordBreak: "break-all",
              }}
            >
              {document?.filename ?? "—"}
            </h2>
            {document && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "12px",
                  fontSize: "var(--sds-typography-body-small-font-size, 11px)",
                  color: "var(--sds-color-on-surface-variant)",
                }}
              >
                <span>
                  ステータス: <strong>{STATUS_LABELS[document.status] ?? document.status}</strong>
                </span>
                <span>v{document.version}</span>
                <span>アップロード: {formatDateTime(document.uploaded_at)}</span>
              </div>
            )}
          </div>
          <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
            {document && (
              <IconButton
                icon={<SerendieSymbolDownload style={{ width: 20, height: 20 }} />}
                aria-label={`${document.filename} をダウンロード`}
                shape="circle"
                styleType="ghost"
                size="medium"
                onClick={() => downloadDocument(document.id, document.filename)}
              />
            )}
            <IconButton
              ref={closeBtnRef as React.Ref<HTMLButtonElement>}
              icon={<SerendieSymbolClose style={{ width: 20, height: 20 }} />}
              aria-label="ドキュメント詳細を閉じる"
              shape="circle"
              styleType="ghost"
              size="medium"
              onClick={onClose}
            />
          </div>
        </div>

        {/* Tabs */}
        <div
          role="tablist"
          aria-label="詳細タブ"
          style={{
            display: "flex",
            borderBottom: "1px solid var(--sds-color-outline-default)",
            flexShrink: 0,
          }}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-controls={`drawer-panel-${tab.id}`}
              id={`drawer-tab-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              style={{
                flex: 1,
                padding: "10px 8px",
                border: "none",
                borderBottom:
                  activeTab === tab.id
                    ? "2px solid var(--sds-color-impression-primary)"
                    : "2px solid transparent",
                background: "none",
                cursor: "pointer",
                fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                fontWeight: activeTab === tab.id ? 700 : 400,
                color:
                  activeTab === tab.id
                    ? "var(--sds-color-impression-primary)"
                    : "var(--sds-color-on-surface-variant)",
                transition: "border-color 0.15s ease, color 0.15s ease",
              }}
              onFocus={(e) => {
                e.currentTarget.style.outline =
                  "2px solid var(--sds-color-impression-primary)";
                e.currentTarget.style.outlineOffset = "-2px";
              }}
              onBlur={(e) => {
                e.currentTarget.style.outline = "none";
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab panels */}
        <div style={{ flex: 1, overflow: "auto", padding: "16px 20px" }}>
          {/* Tags panel */}
          <div
            id="drawer-panel-tags"
            role="tabpanel"
            aria-labelledby="drawer-tab-tags"
            hidden={activeTab !== "tags"}
          >
            {document && (
              <TagEditor
                documentId={document.id}
                fileName={document.filename}
                tags={editableTags}
                onChange={handleTagsChange}
              />
            )}
            {tagsDirty && (
              <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
                <Button
                  styleType="filled"
                  size="small"
                  leftIcon={<SerendieSymbolSave style={{ width: 16, height: 16 }} />}
                  isLoading={saveMutation.isPending}
                  onClick={() => saveMutation.mutate()}
                >
                  タグを保存
                </Button>
              </div>
            )}
          </div>

          {/* Preview panel */}
          <div
            id="drawer-panel-preview"
            role="tabpanel"
            aria-labelledby="drawer-tab-preview"
            hidden={activeTab !== "preview"}
          >
            {detail?.converted_md ? (
              <pre
                style={{
                  margin: 0,
                  padding: "12px",
                  borderRadius: "var(--sds-border-radius-small, 8px)",
                  backgroundColor: "var(--sds-color-surface-container)",
                  fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                  color: "var(--sds-color-on-surface-default)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  fontFamily: "var(--sds-typography-mono-font-family, monospace)",
                  lineHeight: 1.6,
                }}
              >
                {detail.converted_md}
              </pre>
            ) : (
              <p
                style={{
                  color: "var(--sds-color-on-surface-variant)",
                  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                }}
              >
                変換済みMarkdownがありません。
              </p>
            )}
          </div>

          {/* Versions panel */}
          <div
            id="drawer-panel-versions"
            role="tabpanel"
            aria-labelledby="drawer-tab-versions"
            hidden={activeTab !== "versions"}
          >
            {versions.length === 0 ? (
              <p
                style={{
                  color: "var(--sds-color-on-surface-variant)",
                  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                }}
              >
                バージョン履歴がありません。
              </p>
            ) : (
              <ul
                aria-label="バージョン履歴"
                style={{ listStyle: "none", margin: 0, padding: 0 }}
              >
                {versions.map((ver) => (
                  <li
                    key={ver.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "10px 0",
                      borderBottom: "1px solid var(--sds-color-surface-variant)",
                    }}
                  >
                    <div>
                      <span
                        style={{
                          fontWeight: 600,
                          fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                          color: "var(--sds-color-on-surface-default)",
                        }}
                      >
                        v{ver.version}
                      </span>
                      <span
                        style={{
                          marginLeft: "12px",
                          fontSize: "11px",
                          color: "var(--sds-color-on-surface-variant)",
                        }}
                      >
                        {formatDateTime(ver.uploaded_at)}
                      </span>
                    </div>
                    <span
                      style={{
                        fontSize: "11px",
                        color: "var(--sds-color-on-surface-variant)",
                        padding: "2px 8px",
                        borderRadius: "var(--sds-border-radius-full, 9999px)",
                        border: "1px solid var(--sds-color-outline-default)",
                      }}
                    >
                      {STATUS_LABELS[ver.status] ?? ver.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
