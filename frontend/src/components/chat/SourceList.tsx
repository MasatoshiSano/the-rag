import { useMemo } from "react";
import type { Source } from "../../types/message";
import { useSourceStore } from "../../stores/sourceStore";

interface SourceListProps {
  sources: Source[];
}

export function SourceList({ sources }: SourceListProps) {
  const openSourcePanel = useSourceStore((s) => s.openSourcePanel);

  // ドキュメント単位の重複排除カウント
  const uniqueCount = useMemo(() => {
    const seen = new Set<string>();
    for (const s of sources) {
      seen.add(s.documentId || s.documentName || `${s.sectionTitle}-${s.score}`);
    }
    return seen.size;
  }, [sources]);

  if (sources.length === 0) return null;

  return (
    <section aria-label="参照ドキュメント" style={{ marginTop: "var(--sds-spacing-medium, 12px)" }}>
      <button
        type="button"
        onClick={() => openSourcePanel(sources)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          margin: 0,
          padding: "4px 10px",
          border: "1px solid var(--sds-color-outline-default)",
          borderRadius: "var(--sds-border-radius-small, 6px)",
          backgroundColor: "var(--sds-color-surface-container)",
          cursor: "pointer",
          fontSize: "var(--sds-typography-label-small-font-size, 12px)",
          color: "var(--sds-color-on-surface-low)",
          fontWeight: 600,
          transition: "background-color 0.15s",
        }}
        aria-label={`参照ドキュメント ${uniqueCount}件を表示`}
      >
        <span aria-hidden="true" style={{ fontSize: 10 }}>▶</span>
        参照ドキュメント ({uniqueCount})
      </button>
    </section>
  );
}
