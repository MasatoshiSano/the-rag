// GitHubSync: GitHub repository sync section for UploadPage
import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, TextField } from "@serendie/ui";
import { SerendieSymbolDelete, SerendieSymbolRefresh } from "@serendie/symbols";
import {
  syncGitHub,
  getGitHubSources,
  deleteGitHubSource,
  type GitHubSyncResponse,
  type GitHubSourceResponse,
} from "../../api/documents";
import { UploadProgress } from "./UploadProgress";
import type { UploadedFile } from "./UploadProgress";
import type { DocumentStatus } from "../../types/document";

interface GitHubSyncProps {
  knowledgeBaseId: string | null;
}

function parseGitHubUrl(url: string): { owner: string; repo: string; path: string } | null {
  try {
    const u = new URL(url);
    if (!u.hostname.includes("github.com")) return null;
    const parts = u.pathname.replace(/^\//, "").replace(/\.git$/, "").split("/");
    if (parts.length < 2) return null;
    const owner = parts[0];
    const repo = parts[1];
    let path = "";
    if (parts.length > 3 && parts[2] === "tree") {
      path = parts.slice(4).join("/");
    }
    return { owner, repo, path };
  } catch {
    return null;
  }
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function GitHubSync({ knowledgeBaseId }: GitHubSyncProps) {
  const queryClient = useQueryClient();
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [syncedFiles, setSyncedFiles] = useState<UploadedFile[]>([]);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncSuccess, setSyncSuccess] = useState<string | null>(null);

  // 同期済みリポジトリ一覧を取得
  const { data: sources = [] } = useQuery({
    queryKey: ["github-sources", knowledgeBaseId],
    queryFn: () => getGitHubSources(knowledgeBaseId!),
    enabled: !!knowledgeBaseId,
  });

  const handleUrlChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setRepoUrl(e.target.value);
  }, []);

  const invalidateSources = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["github-sources", knowledgeBaseId] });
  }, [queryClient, knowledgeBaseId]);

  const syncMutation = useMutation({
    mutationFn: async (source?: GitHubSourceResponse) => {
      const targetUrl = source ? source.repository_url : repoUrl;
      const targetBranch = source ? source.branch : branch;

      if (!knowledgeBaseId) throw new Error("ナレッジベースを選択してください。");
      if (!targetUrl.trim()) throw new Error("リポジトリURLを入力してください。");

      let canonicalUrl: string;
      let path: string;

      if (source) {
        canonicalUrl = source.repository_url;
        path = source.path;
      } else {
        const parsed = parseGitHubUrl(targetUrl);
        if (!parsed) throw new Error("無効なGitHub URLです。");
        canonicalUrl = `https://github.com/${parsed.owner}/${parsed.repo}`;
        path = parsed.path;
      }

      return syncGitHub({
        repository_url: canonicalUrl,
        path,
        branch: targetBranch,
        knowledge_base_id: knowledgeBaseId,
      });
    },
    onSuccess: (response: GitHubSyncResponse) => {
      setSyncError(null);
      setSyncSuccess(response.message);
      invalidateSources();
      const files: UploadedFile[] = response.synced_files
        .filter((f) => f.status !== "skipped")
        .map((f) => ({
          documentId: f.document_id,
          fileName: f.filename,
          fileSize: 0,
          status: f.status as DocumentStatus,
        }));
      setSyncedFiles(files);
    },
    onError: (err: Error) => {
      setSyncError(err.message || "GitHub同期に失敗しました。");
      setSyncSuccess(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteGitHubSource(id),
    onSuccess: invalidateSources,
  });

  const handleStatusUpdate = useCallback(
    (documentId: string, status: DocumentStatus) => {
      setSyncedFiles((prev) =>
        prev.map((f) =>
          f.documentId === documentId ? { ...f, status } : f
        )
      );
    },
    []
  );

  const handleRemove = useCallback((documentId: string) => {
    setSyncedFiles((prev) => prev.filter((f) => f.documentId !== documentId));
  }, []);

  const disabled = !knowledgeBaseId || syncMutation.isPending;

  return (
    <section aria-labelledby="github-sync-label">
      <h2
        id="github-sync-label"
        style={{
          margin: "0 0 12px 0",
          fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
          fontWeight: 600,
          color: "var(--sds-color-on-surface-default)",
        }}
      >
        GitHub連携
      </h2>

      <div
        style={{
          padding: "16px",
          borderRadius: "var(--sds-border-radius-small, 8px)",
          border: "1px solid var(--sds-color-outline-default)",
          backgroundColor: "var(--sds-color-surface-default)",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
          boxSizing: "border-box",
        }}
      >
        {/* 同期済みリポジトリ一覧 */}
        {sources.length > 0 && (
          <div>
            <h3
              style={{
                margin: "0 0 8px 0",
                fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                fontWeight: 600,
                color: "var(--sds-color-on-surface-variant)",
              }}
            >
              同期済みリポジトリ
            </h3>
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
              {sources.map((source) => (
                <li
                  key={source.id}
                  style={{
                    padding: "10px 12px",
                    borderRadius: "var(--sds-border-radius-small, 6px)",
                    border: "1px solid var(--sds-color-outline-variant, #e0e0e0)",
                    backgroundColor: "var(--sds-color-surface-container-low, #f8f8f8)",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ flex: "1 1 0", minWidth: "200px" }}>
                    <a
                      href={source.repository_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        color: "var(--sds-color-primary-default)",
                        textDecoration: "none",
                        fontWeight: 500,
                        fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                      }}
                    >
                      {source.repository_url.replace("https://github.com/", "")}
                    </a>
                    <div
                      style={{
                        fontSize: "var(--sds-typography-caption-font-size, 12px)",
                        color: "var(--sds-color-on-surface-variant)",
                        marginTop: "2px",
                      }}
                    >
                      {source.branch}
                      {source.path ? ` / ${source.path}` : ""}
                      {" — "}
                      最終同期: {formatDateTime(source.last_synced_at)}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: "4px", flexShrink: 0 }}>
                    <Button
                      styleType="outlined"
                      size="small"
                      onClick={() => syncMutation.mutate(source)}
                      disabled={syncMutation.isPending}
                      aria-label={`再同期: ${source.repository_url}`}
                    >
                      <SerendieSymbolRefresh style={{ width: 14, height: 14 }} />
                      再同期
                    </Button>
                    <Button
                      styleType="outlined"
                      size="small"
                      onClick={() => deleteMutation.mutate(source.id)}
                      disabled={deleteMutation.isPending}
                      aria-label={`削除: ${source.repository_url}`}
                    >
                      <SerendieSymbolDelete style={{ width: 14, height: 14 }} />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 新規同期フォーム */}
        <TextField
          label="GitHub URL"
          placeholder="https://github.com/owner/repo/tree/main/docs"
          value={repoUrl}
          onChange={handleUrlChange}
          disabled={syncMutation.isPending}
        />

        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 120px", maxWidth: "200px" }}>
            <TextField
              label="ブランチ"
              placeholder="main"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
              disabled={syncMutation.isPending}
            />
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button
            styleType="filled"
            size="medium"
            onClick={() => syncMutation.mutate(undefined)}
            isLoading={syncMutation.isPending}
            disabled={disabled || !repoUrl.trim()}
          >
            同期する
          </Button>
        </div>

        {/* Error */}
        {syncError && (
          <div
            role="alert"
            aria-live="assertive"
            style={{
              padding: "10px 14px",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              backgroundColor: "var(--sds-color-negative-container, #fdecea)",
              border: "1px solid var(--sds-color-negative-default, #d32f2f)",
              color: "var(--sds-color-negative-default, #d32f2f)",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            }}
          >
            {syncError}
          </div>
        )}

        {/* Success */}
        {syncSuccess && (
          <div
            role="alert"
            aria-live="polite"
            style={{
              padding: "10px 14px",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              backgroundColor: "var(--sds-color-positive-container, #e8f5e9)",
              border: "1px solid var(--sds-color-positive-default, #2e7d32)",
              color: "var(--sds-color-positive-default, #2e7d32)",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            }}
          >
            {syncSuccess}
          </div>
        )}

        {/* Progress */}
        {syncedFiles.length > 0 && (
          <UploadProgress
            files={syncedFiles}
            onStatusUpdate={handleStatusUpdate}
            onRemove={handleRemove}
          />
        )}
      </div>
    </section>
  );
}
