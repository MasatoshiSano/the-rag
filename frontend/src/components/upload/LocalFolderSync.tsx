// LocalFolderSync: ローカルフォルダソース登録・管理コンポーネント
import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, TextField } from "@serendie/ui";
import { SerendieSymbolDelete } from "@serendie/symbols";
import {
  validateFolderPath,
  createFolderSource,
  getFolderSources,
  deleteFolderSource,
  type FolderSourceResponse,
  type FolderSourceValidateResponse,
} from "../../api/documents";

interface LocalFolderSyncProps {
  knowledgeBaseId: string | null;
}

export function LocalFolderSync({ knowledgeBaseId }: LocalFolderSyncProps) {
  const queryClient = useQueryClient();
  const [folderPath, setFolderPath] = useState("");
  const [label, setLabel] = useState("");
  const [sourceType, setSourceType] = useState<"document" | "data">("document");
  const [validation, setValidation] = useState<FolderSourceValidateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { data: sources = [] } = useQuery({
    queryKey: ["folder-sources", knowledgeBaseId],
    queryFn: () => getFolderSources(knowledgeBaseId!),
    enabled: !!knowledgeBaseId,
  });

  const invalidateSources = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["folder-sources", knowledgeBaseId] });
  }, [queryClient, knowledgeBaseId]);

  const validateMutation = useMutation({
    mutationFn: () => validateFolderPath(folderPath.trim()),
    onSuccess: (result) => {
      setValidation(result);
      setError(result.valid ? null : result.error);
    },
    onError: (err: Error) => {
      setValidation(null);
      setError(err.message || "検証に失敗しました。");
    },
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!knowledgeBaseId) throw new Error("ナレッジベースを選択してください。");
      return createFolderSource({
        folder_path: folderPath.trim(),
        knowledge_base_id: knowledgeBaseId,
        label: label.trim() || undefined,
        source_type: sourceType,
      });
    },
    onSuccess: (source: FolderSourceResponse) => {
      setError(null);
      const countLabel = source.has_more ? `${source.file_count}件以上` : `${source.file_count}件`;
      setSuccess(`フォルダを登録しました（${countLabel}のファイル）`);
      setFolderPath("");
      setLabel("");
      setSourceType("document");
      setValidation(null);
      invalidateSources();
    },
    onError: (err: Error) => {
      setError(err.message || "登録に失敗しました。");
      setSuccess(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteFolderSource(id),
    onSuccess: invalidateSources,
  });

  const disabled = !knowledgeBaseId;

  return (
    <section aria-labelledby="folder-sync-label">
      <h2
        id="folder-sync-label"
        style={{
          margin: "0 0 12px 0",
          fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
          fontWeight: 600,
          color: "var(--sds-color-on-surface-default)",
        }}
      >
        ローカルフォルダ連携
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
        <p
          style={{
            margin: 0,
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-on-surface-variant)",
          }}
        >
          Windowsのフォルダパスを登録すると、深掘り検索時にフォルダ内のファイルを直接読み取って検索します。
          対応形式: .md, .txt, .csv, .json, .pdf, .pptx, .xlsx, .docx, .html
        </p>

        {/* 登録済みフォルダ一覧 */}
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
              登録済みフォルダ
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
                    <div
                      style={{
                        fontWeight: 500,
                        fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                        color: "var(--sds-color-on-surface-default)",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          padding: "1px 6px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 600,
                          backgroundColor:
                            source.source_type === "data"
                              ? "var(--sds-color-primary-container, #e8eaf6)"
                              : "var(--sds-color-surface-container, #f0f0f0)",
                          color:
                            source.source_type === "data"
                              ? "var(--sds-color-primary-default, #3f51b5)"
                              : "var(--sds-color-on-surface-variant)",
                        }}
                      >
                        {source.source_type === "data" ? "データ" : "文書"}
                      </span>
                      <span>
                        {source.label ? `${source.label}: ` : ""}
                        {source.folder_path}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "var(--sds-typography-caption-font-size, 12px)",
                        color: "var(--sds-color-on-surface-variant)",
                        marginTop: "2px",
                      }}
                    >
                      {source.has_more ? `${source.file_count}件以上` : `${source.file_count}件`}のファイル
                    </div>
                  </div>
                  <Button
                    styleType="outlined"
                    size="small"
                    onClick={() => deleteMutation.mutate(source.id)}
                    disabled={deleteMutation.isPending}
                    aria-label={`削除: ${source.folder_path}`}
                  >
                    <SerendieSymbolDelete style={{ width: 14, height: 14 }} />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 新規登録フォーム */}
        <TextField
          label="フォルダパス"
          placeholder="C:\Users\username\Documents\knowledge"
          value={folderPath}
          onChange={(e) => {
            setFolderPath(e.target.value);
            setValidation(null);
            setError(null);
            setSuccess(null);
          }}
          disabled={disabled}
        />

        <div style={{ maxWidth: "300px" }}>
          <TextField
            label="ラベル（任意）"
            placeholder="例: 設計資料"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            disabled={disabled}
          />
        </div>

        {/* ソース種別選択 */}
        <fieldset
          style={{
            border: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            alignItems: "center",
            gap: "16px",
          }}
        >
          <legend
            style={{
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              fontWeight: 500,
              color: "var(--sds-color-on-surface-default)",
              marginBottom: "4px",
            }}
          >
            ソース種別
          </legend>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              cursor: disabled ? "default" : "pointer",
            }}
          >
            <input
              type="radio"
              name="source-type"
              value="document"
              checked={sourceType === "document"}
              onChange={() => setSourceType("document")}
              disabled={disabled}
            />
            ドキュメント
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "var(--sds-typography-body-small-font-size, 13px)",
              cursor: disabled ? "default" : "pointer",
            }}
          >
            <input
              type="radio"
              name="source-type"
              value="data"
              checked={sourceType === "data"}
              onChange={() => setSourceType("data")}
              disabled={disabled}
            />
            データ（CSV/SQL）
          </label>
        </fieldset>

        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
          <Button
            styleType="outlined"
            size="medium"
            onClick={() => validateMutation.mutate()}
            isLoading={validateMutation.isPending}
            disabled={disabled || !folderPath.trim() || validateMutation.isPending}
          >
            検証
          </Button>
          <Button
            styleType="filled"
            size="medium"
            onClick={() => createMutation.mutate()}
            isLoading={createMutation.isPending}
            disabled={
              disabled ||
              !validation?.valid ||
              createMutation.isPending
            }
          >
            登録
          </Button>
        </div>

        {/* 検証結果 */}
        {validation?.valid && (
          <div
            role="status"
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
            {validation.has_more ? `${validation.file_count}件以上` : `${validation.file_count}件`}の対応ファイルが見つかりました
          </div>
        )}

        {/* エラー */}
        {error && (
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
            {error}
          </div>
        )}

        {/* 成功 */}
        {success && (
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
            {success}
          </div>
        )}
      </div>
    </section>
  );
}
