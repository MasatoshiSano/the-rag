// SearchSettings: toggle switches for rerank/hybrid search, retrieval count, response mode
// Auto-saves on change via TanStack Query mutation

import { useState } from "react";
import { Switch } from "@serendie/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateSettings } from "../../api/users";
import { useUserStore } from "../../stores/userStore";
import type { User } from "../../types/user";

const sectionStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container-low)",
  borderRadius: "var(--sds-border-radius-medium, 12px)",
  padding: "24px",
  display: "flex",
  flexDirection: "column",
  gap: "20px",
};

const fieldsetStyle: React.CSSProperties = {
  border: "none",
  margin: 0,
  padding: 0,
};

const legendStyle: React.CSSProperties = {
  fontSize: "var(--sds-typography-label-large-font-size, 14px)",
  fontWeight: 700,
  color: "var(--sds-color-on-surface-default)",
  marginBottom: "12px",
};

const radioGroupStyle: React.CSSProperties = {
  display: "flex",
  gap: "16px",
  flexWrap: "wrap",
};

const radioLabelStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  cursor: "pointer",
  fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
  color: "var(--sds-color-on-surface-default)",
};

const radioInputStyle: React.CSSProperties = {
  accentColor: "var(--sds-color-primary-default)",
  width: 18,
  height: 18,
  cursor: "pointer",
};

const dividerStyle: React.CSSProperties = {
  borderTop: "1px solid var(--sds-color-outline-variant)",
  margin: 0,
};

interface SearchSettingsProps {
  user: User;
}

export function SearchSettings({ user }: SearchSettingsProps) {
  const queryClient = useQueryClient();
  const updateUserSettings = useUserStore((s) => s.updateUserSettings);

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (updated) => {
      updateUserSettings({
        rerank_enabled: updated.rerank_enabled,
        hybrid_search_enabled: updated.hybrid_search_enabled,
        retrieval_count: updated.retrieval_count,
        response_mode: updated.response_mode,
        agentic_max_iterations: updated.agentic_max_iterations,
      });
      queryClient.setQueryData(["user", "me"], updated);
    },
  });

  const [localRetrievalCount, setLocalRetrievalCount] = useState<string>(
    String(user.retrieval_count ?? 10)
  );

  const [localAgenticMaxIterations, setLocalAgenticMaxIterations] =
    useState<string>(String(user.agentic_max_iterations ?? 5));

  function handleRetrievalCountBlur() {
    const parsed = parseInt(localRetrievalCount, 10);
    if (isNaN(parsed) || parsed < 1 || parsed > 50) {
      setLocalRetrievalCount(String(user.retrieval_count ?? 10));
      return;
    }
    if (parsed !== user.retrieval_count) {
      mutation.mutate({ retrieval_count: parsed });
    }
  }

  function handleAgenticMaxIterationsBlur() {
    const parsed = parseInt(localAgenticMaxIterations, 10);
    if (isNaN(parsed) || parsed < 1 || parsed > 15) {
      setLocalAgenticMaxIterations(String(user.agentic_max_iterations ?? 5));
      return;
    }
    if (parsed !== user.agentic_max_iterations) {
      mutation.mutate({ agentic_max_iterations: parsed });
    }
  }

  function handleRerankChange(e: { checked: boolean }) {
    mutation.mutate({ rerank_enabled: e.checked });
  }

  function handleHybridSearchChange(e: { checked: boolean }) {
    mutation.mutate({ hybrid_search_enabled: e.checked });
  }

  function handleResponseModeChange(mode: "simple" | "detailed") {
    mutation.mutate({ response_mode: mode });
  }

  return (
    <section aria-labelledby="search-settings-heading" style={sectionStyle}>
      <h2
        id="search-settings-heading"
        style={{
          margin: 0,
          fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
          fontWeight: 700,
          color: "var(--sds-color-on-surface-default)",
        }}
      >
        検索設定
      </h2>

      {/* Rerank toggle */}
      <div>
        <Switch
          label="リランク"
          helperText="検索結果の関連度を再評価して精度を向上します"
          checked={user.rerank_enabled}
          onCheckedChange={handleRerankChange}
        />
      </div>

      <hr style={dividerStyle} aria-hidden="true" />

      {/* Hybrid search toggle */}
      <div>
        <Switch
          label="ハイブリッド検索"
          helperText="キーワード検索とベクトル検索を組み合わせて検索します"
          checked={user.hybrid_search_enabled}
          onCheckedChange={handleHybridSearchChange}
        />
      </div>

      <hr style={dividerStyle} aria-hidden="true" />

      {/* Retrieval count */}
      <div>
        <label
          htmlFor="retrieval-count-input"
          style={{
            display: "block",
            fontSize: "var(--sds-typography-label-large-font-size, 14px)",
            fontWeight: 700,
            color: "var(--sds-color-on-surface-default)",
            marginBottom: "4px",
          }}
        >
          検索取得件数
        </label>
        <p
          style={{
            margin: "0 0 8px 0",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-on-surface-low)",
          }}
        >
          RAG検索で取得するドキュメントチャンクの件数です（1〜50）
        </p>
        <input
          id="retrieval-count-input"
          type="number"
          min={1}
          max={50}
          value={localRetrievalCount}
          onChange={(e) => setLocalRetrievalCount(e.target.value)}
          onBlur={handleRetrievalCountBlur}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              (e.target as HTMLInputElement).blur();
            }
          }}
          style={{
            width: 80,
            height: 40,
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: "var(--sds-border-radius-small, 8px)",
            padding: "0 12px",
            backgroundColor: "var(--sds-color-surface-default)",
            color: "var(--sds-color-on-surface-default)",
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            textAlign: "center",
          }}
        />
      </div>

      <hr style={dividerStyle} aria-hidden="true" />

      {/* Agentic max iterations */}
      <div>
        <label
          htmlFor="agentic-max-iterations-input"
          style={{
            display: "block",
            fontSize: "var(--sds-typography-label-large-font-size, 14px)",
            fontWeight: 700,
            color: "var(--sds-color-on-surface-default)",
            marginBottom: "4px",
          }}
        >
          深掘り最大反復回数
        </label>
        <p
          style={{
            margin: "0 0 8px 0",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-on-surface-low)",
          }}
        >
          深掘りモードでClaudeがドキュメントを読み込む最大回数です（1〜15）。多いほど精度が上がるが応答が遅くなります。
        </p>
        <input
          id="agentic-max-iterations-input"
          type="number"
          min={1}
          max={15}
          value={localAgenticMaxIterations}
          onChange={(e) => setLocalAgenticMaxIterations(e.target.value)}
          onBlur={handleAgenticMaxIterationsBlur}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              (e.target as HTMLInputElement).blur();
            }
          }}
          style={{
            width: 80,
            height: 40,
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: "var(--sds-border-radius-small, 8px)",
            padding: "0 12px",
            backgroundColor: "var(--sds-color-surface-default)",
            color: "var(--sds-color-on-surface-default)",
            fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
            textAlign: "center",
          }}
        />
      </div>

      <hr style={dividerStyle} aria-hidden="true" />

      {/* Response mode radio group */}
      <fieldset style={fieldsetStyle}>
        <legend style={legendStyle}>応答モード</legend>
        <div style={radioGroupStyle} role="radiogroup">
          <label style={radioLabelStyle}>
            <input
              type="radio"
              name="response-mode"
              value="simple"
              checked={user.response_mode === "simple"}
              onChange={() => handleResponseModeChange("simple")}
              style={radioInputStyle}
            />
            シンプル
          </label>
          <label style={radioLabelStyle}>
            <input
              type="radio"
              name="response-mode"
              value="detailed"
              checked={user.response_mode === "detailed"}
              onChange={() => handleResponseModeChange("detailed")}
              style={radioInputStyle}
            />
            詳細
          </label>
        </div>
      </fieldset>

      {mutation.isError && (
        <p
          role="alert"
          style={{
            color: "var(--sds-color-error-default)",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            margin: 0,
          }}
        >
          設定の保存に失敗しました。再度お試しください。
        </p>
      )}
    </section>
  );
}
