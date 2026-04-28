// UploadPage: drag-and-drop upload with tag confirmation and index build
import { useState, useCallback } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button } from "@serendie/ui";
import { Tabs } from "@ark-ui/react/tabs";
import {
  SerendieSymbolUploadCloud,
  SerendieSymbolDataFilled,
} from "@serendie/symbols";
import { useKbStore } from "../stores/kbStore";
import { getKnowledgeBases } from "../api/knowledge-bases";
import { uploadDocuments, batchPatchTags } from "../api/documents";
import { DropZone } from "../components/upload/DropZone";
import { TextInput } from "../components/upload/TextInput";
import { UploadProgress } from "../components/upload/UploadProgress";
import { TagEditor } from "../components/upload/TagEditor";
import type { DocumentStatus } from "../types/document";
import { GitHubSync } from "../components/upload/GitHubSync";
import { GiteaSync } from "../components/upload/GiteaSync";
import { LocalFolderSync } from "../components/upload/LocalFolderSync";
import type { EditableTag } from "../components/upload/TagEditor";
import type { UploadedFile } from "../components/upload/UploadProgress";

interface FileEntry {
  file: File;
  uploaded: UploadedFile | null;
  tags: EditableTag[];
}

function generateLocalId(): string {
  return `local-${Math.random().toString(36).slice(2)}`;
}

export function UploadPage() {
  const { selectedKbId, setSelectedKbId } = useKbStore();
  const [fileEntries, setFileEntries] = useState<FileEntry[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [confirmSuccess, setConfirmSuccess] = useState(false);

  const { data: knowledgeBases = [] } = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: getKnowledgeBases,
  });

  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      if (!selectedKbId) throw new Error("ナレッジベースを選択してください。");
      return uploadDocuments(selectedKbId, files);
    },
    onSuccess: (response, files) => {
      setUploadError(null);
      setFileEntries((prev) => {
        const newEntries: FileEntry[] = files.map((file, idx) => {
          const doc = response.documents[idx];
          const existing = prev.find((e) => e.file === file);
          if (doc) {
            return {
              file,
              uploaded: {
                documentId: doc.id,
                fileName: doc.filename,
                fileSize: 0,
                status: doc.status,
              },
              tags: (doc.tags ?? []).map((t) => ({
                id: String(t.id),
                tagKey: t.tag_key,
                tagValue: t.tag_value,
                confidence: t.confidence,
                confirmed: t.confirmed,
              })),
            };
          }
          return existing ?? { file, uploaded: null, tags: [] };
        });

        // Keep previously uploaded entries that are not in this batch
        const previousUploaded = prev.filter(
          (e) => e.uploaded && !files.includes(e.file)
        );
        return [...previousUploaded, ...newEntries];
      });
    },
    onError: (err: Error) => {
      setUploadError(err.message || "アップロードに失敗しました。");
    },
  });

  const confirmMutation = useMutation({
    mutationFn: async () => {
      const uploadedEntries = fileEntries.filter((e) => e.uploaded);
      if (uploadedEntries.length === 0) return;

      // Batch patch tags for all documents
      const batchDocs = uploadedEntries.map((entry) => ({
        document_id: entry.uploaded!.documentId,
        tags: entry.tags.map((t) => ({
          tag_key: t.tagKey,
          tag_value: t.tagValue,
          confirmed: t.confirmed,
        })),
      }));
      await batchPatchTags(batchDocs);
    },
    onSuccess: () => {
      setConfirmSuccess(true);
      // fileEntries をクリアしない → UploadProgress のポーリングが継続する
    },
    onError: (err: Error) => {
      setUploadError(err.message || "確定処理に失敗しました。");
    },
  });

  const handleFilesSelected = useCallback(
    (files: File[]) => {
      if (!selectedKbId) {
        setUploadError("先にナレッジベースを選択してください。");
        return;
      }
      setUploadError(null);
      setConfirmSuccess(false);

      // Add pending entries immediately for feedback
      const pendingEntries: FileEntry[] = files.map((f) => ({
        file: f,
        uploaded: null,
        tags: [],
      }));
      setFileEntries((prev) => [...prev, ...pendingEntries]);

      uploadMutation.mutate(files);
    },
    [selectedKbId, uploadMutation]
  );

  const handleStatusUpdate = useCallback(
    (documentId: string, status: DocumentStatus) => {
      setFileEntries((prev) =>
        prev.map((entry) =>
          entry.uploaded?.documentId === documentId
            ? {
                ...entry,
                uploaded: { ...entry.uploaded, status },
              }
            : entry
        )
      );
    },
    []
  );

  const handleRemove = useCallback((documentId: string) => {
    setFileEntries((prev) =>
      prev.filter((e) => e.uploaded?.documentId !== documentId)
    );
  }, []);

  const handleTagsChange = useCallback(
    (documentId: string, tags: EditableTag[]) => {
      setFileEntries((prev) =>
        prev.map((entry) =>
          entry.uploaded?.documentId === documentId
            ? { ...entry, tags }
            : entry
        )
      );
    },
    []
  );

  const uploadedEntries = fileEntries.filter((e) => e.uploaded);
  const pendingEntries = fileEntries.filter((e) => !e.uploaded);
  const currentFileCount = fileEntries.length;
  const uploadedFiles: UploadedFile[] = uploadedEntries
    .map((e) => e.uploaded!)
    .filter(Boolean);

  const TERMINAL_STATUSES: DocumentStatus[] = [
    "tagged",
    "indexed",
    "convert_failed",
    "tag_failed",
    "index_failed",
    "permanent_failed",
    "cancelled",
  ];
  const allFilesCompleted =
    uploadedFiles.length > 0 &&
    uploadedFiles.every((f) => TERMINAL_STATUSES.includes(f.status));

  // Add pending files as placeholder UploadedFile entries
  const pendingUploads: UploadedFile[] = pendingEntries.map((e) => ({
    documentId: generateLocalId(),
    fileName: e.file.name,
    fileSize: e.file.size,
    status: "processing" as DocumentStatus,
  }));

  const allUploadFiles = [...uploadedFiles, ...pendingUploads];

  return (
    <section aria-label="ドキュメントアップロード">
      <div
        style={{
          maxWidth: "900px",
          margin: "0 auto",
          padding: "16px",
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          gap: "24px",
        }}
      >
        {/* Page heading */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <SerendieSymbolUploadCloud
            style={{ width: 28, height: 28, color: "var(--sds-color-impression-primary)" }}
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
            ドキュメントアップロード
          </h1>
        </div>

        {/* KB selector */}
        <section aria-labelledby="kb-selector-label">
          <label
            id="kb-selector-label"
            htmlFor="kb-select"
            style={{
              display: "block",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              fontWeight: 600,
              color: "var(--sds-color-on-surface-default)",
              marginBottom: "6px",
            }}
          >
            <SerendieSymbolDataFilled
              style={{ width: 14, height: 14, verticalAlign: "middle", marginRight: "4px" }}
              aria-hidden="true"
            />
            ナレッジベース
          </label>
          <select
            id="kb-select"
            value={selectedKbId ?? ""}
            onChange={(e) => setSelectedKbId(e.target.value || null)}
            aria-required="true"
            style={{
              width: "100%",
              maxWidth: "480px",
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
          {!selectedKbId && (
            <p
              style={{
                marginTop: "4px",
                fontSize: "var(--sds-typography-body-small-font-size, 12px)",
                color: "var(--sds-color-on-surface-variant)",
              }}
            >
              アップロード前にナレッジベースを選択してください。
            </p>
          )}
        </section>

        {/* Upload method tabs */}
        <style>{`
          .upload-tab[data-selected] {
            color: var(--sds-color-impression-primary) !important;
            border-bottom-color: var(--sds-color-impression-primary) !important;
          }
          .upload-tab:hover:not([data-selected]) {
            color: var(--sds-color-on-surface-default);
          }
          .upload-tab:focus-visible {
            outline: 2px solid var(--sds-color-impression-primary);
            outline-offset: -2px;
            border-radius: 4px 4px 0 0;
          }
        `}</style>
        <Tabs.Root defaultValue="folder" lazyMount>
          <Tabs.List
            style={{
              display: "flex",
              gap: "0",
              borderBottom: "2px solid var(--sds-color-outline-default)",
            }}
          >
            {[
              { value: "folder", label: "ローカル" },
              { value: "file", label: "ファイル" },
              { value: "text", label: "テキスト" },
              { value: "github", label: "GitHub" },
              { value: "gitea", label: "Gitea" },
            ].map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className="upload-tab"
                style={{
                  padding: "10px 20px",
                  fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
                  fontWeight: 600,
                  color: "var(--sds-color-on-surface-variant)",
                  background: "none",
                  border: "none",
                  borderBottom: "2px solid transparent",
                  marginBottom: "-2px",
                  cursor: "pointer",
                  transition: "color 0.15s, border-color 0.15s",
                }}
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          <Tabs.Content value="folder" style={{ paddingTop: "16px" }}>
            <LocalFolderSync knowledgeBaseId={selectedKbId} />
          </Tabs.Content>
          <Tabs.Content value="file" style={{ paddingTop: "16px" }}>
            <DropZone
              onFilesSelected={handleFilesSelected}
              currentFileCount={currentFileCount}
              disabled={!selectedKbId || uploadMutation.isPending || confirmSuccess}
            />
          </Tabs.Content>
          <Tabs.Content value="text" style={{ paddingTop: "16px" }}>
            <TextInput
              onSubmit={(file) => handleFilesSelected([file])}
              disabled={!selectedKbId || uploadMutation.isPending || confirmSuccess}
            />
          </Tabs.Content>
          <Tabs.Content value="github" style={{ paddingTop: "16px" }}>
            <GitHubSync knowledgeBaseId={selectedKbId} />
          </Tabs.Content>
          <Tabs.Content value="gitea" style={{ paddingTop: "16px" }}>
            <GiteaSync knowledgeBaseId={selectedKbId} />
          </Tabs.Content>
        </Tabs.Root>

        {/* Error message */}
        {uploadError && (
          <div
            role="alert"
            aria-live="assertive"
            style={{
              padding: "12px 16px",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              backgroundColor: "var(--sds-color-negative-container, #fdecea)",
              border: "1px solid var(--sds-color-negative-default, #d32f2f)",
              color: "var(--sds-color-negative-default, #d32f2f)",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            }}
          >
            {uploadError}
          </div>
        )}

        {/* Success message */}
        {confirmSuccess && (
          <div
            role="alert"
            aria-live="polite"
            style={{
              padding: "12px 16px",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              backgroundColor: "var(--sds-color-positive-container, #e8f5e9)",
              border: "1px solid var(--sds-color-positive-default, #2e7d32)",
              color: "var(--sds-color-positive-default, #2e7d32)",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            }}
          >
            タグを確定し、インデックス構築を開始しました。
          </div>
        )}

        {/* File progress list */}
        {allUploadFiles.length > 0 && (
          <section aria-labelledby="progress-section-label">
            <h2
              id="progress-section-label"
              style={{
                margin: "0 0 8px 0",
                fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
                fontWeight: 600,
                color: "var(--sds-color-on-surface-default)",
              }}
            >
              アップロード状況
            </h2>
            <UploadProgress
              files={allUploadFiles}
              onStatusUpdate={handleStatusUpdate}
              onRemove={handleRemove}
            />
          </section>
        )}

        {/* Clear button when all files completed */}
        {allFilesCompleted && (
          <div style={{ display: "flex", justifyContent: "center" }}>
            <Button
              styleType="outlined"
              size="medium"
              onClick={() => {
                setFileEntries([]);
                setConfirmSuccess(false);
              }}
            >
              新しいアップロード
            </Button>
          </div>
        )}

        {/* Tag editor for uploaded files */}
        {uploadedEntries.length > 0 && !confirmSuccess && (
          <section aria-labelledby="tags-section-label">
            <h2
              id="tags-section-label"
              style={{
                margin: "0 0 12px 0",
                fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
                fontWeight: 600,
                color: "var(--sds-color-on-surface-default)",
              }}
            >
              AIタグ確認・編集
            </h2>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              {uploadedEntries.map((entry) => (
                <TagEditor
                  key={entry.uploaded!.documentId}
                  documentId={entry.uploaded!.documentId}
                  fileName={entry.uploaded!.fileName}
                  tags={entry.tags}
                  onChange={handleTagsChange}
                />
              ))}
            </div>

            {/* Confirm and index button */}
            <div style={{ marginTop: "20px", display: "flex", justifyContent: "flex-end" }}>
              <Button
                styleType="filled"
                size="medium"
                isLoading={confirmMutation.isPending}
                disabled={confirmMutation.isPending || uploadMutation.isPending}
                onClick={() => confirmMutation.mutate()}
              >
                確定してインデックス構築
              </Button>
            </div>
          </section>
        )}
      </div>
    </section>
  );
}
