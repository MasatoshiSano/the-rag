// SourcePanel: right-side sliding panel showing reference documents
// WCAG 2.2 AA: dialog role, focus trap, Escape key, focus restoration

import { useRef, useEffect, useState } from "react";
import { IconButton } from "@serendie/ui";
import { SerendieSymbolClose, SerendieSymbolArrowLeft } from "@serendie/symbols";
import { useSourceStore } from "../../stores/sourceStore";
import type { Source } from "../../types/message";

const PANEL_WIDTH = 480;

/** ドキュメント単位にグループ化されたソース */
interface GroupedSource {
  documentId: string;
  documentName: string;
  bestScore: number;
  sections: { sectionTitle: string; score: number; snippet: string }[];
}

/** ソースをドキュメント単位に重複排除・グループ化する */
function groupByDocument(sources: Source[]): GroupedSource[] {
  const map = new Map<string, GroupedSource>();

  for (const s of sources) {
    const key = s.documentId || s.documentName || `${s.sectionTitle}-${s.score}`;
    const existing = map.get(key);

    if (existing) {
      if (s.score > existing.bestScore) {
        existing.bestScore = s.score;
      }
      // セクションタイトルが異なるチャンクのみ追加
      const alreadyHasSection = existing.sections.some(
        (sec) => sec.sectionTitle === s.sectionTitle && sec.snippet === s.snippet,
      );
      if (!alreadyHasSection) {
        existing.sections.push({
          sectionTitle: s.sectionTitle,
          score: s.score,
          snippet: s.snippet,
        });
      }
    } else {
      map.set(key, {
        documentId: s.documentId,
        documentName: s.documentName || s.sectionTitle || "不明なドキュメント",
        bestScore: s.score,
        sections: [
          {
            sectionTitle: s.sectionTitle,
            score: s.score,
            snippet: s.snippet,
          },
        ],
      });
    }
  }

  // スコア降順でソート
  return Array.from(map.values()).sort((a, b) => b.bestScore - a.bestScore);
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 200,
  display: "flex",
  justifyContent: "flex-end",
};

const backdropStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  backgroundColor: "rgba(0, 0, 0, 0.32)",
};

const panelStyle: React.CSSProperties = {
  position: "relative",
  zIndex: 1,
  width: PANEL_WIDTH,
  maxWidth: "100vw",
  height: "100%",
  backgroundColor: "var(--sds-color-surface-default)",
  boxShadow: "-4px 0 24px rgba(0,0,0,0.15)",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "12px 16px",
  borderBottom: "1px solid var(--sds-color-outline-variant)",
  backgroundColor: "var(--sds-color-surface-container-low)",
  flexShrink: 0,
};

const bodyStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "12px",
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

/** ドキュメント一覧用カード */
function SourceCard({
  group,
  onClick,
}: {
  group: GroupedSource;
  onClick: () => void;
}) {
  const scorePercent = Math.round(group.bestScore * 100);
  const sectionCount = group.sections.length;

  return (
    <button
      type="button"
      aria-label={`${group.documentName} (関連度${scorePercent}%) - クリックでプレビュー表示`}
      onClick={onClick}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        padding: "12px",
        backgroundColor: "var(--sds-color-surface-container)",
        border: "1px solid var(--sds-color-outline-variant)",
        borderRadius: "var(--sds-border-radius-small, 8px)",
        cursor: "pointer",
        textAlign: "left",
        width: "100%",
        transition: "background-color 0.15s, border-color 0.15s",
      }}
    >
      {/* Header row: score + name */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span
          aria-hidden="true"
          style={{
            flexShrink: 0,
            fontSize: "11px",
            backgroundColor: "var(--sds-color-primary-default)",
            color: "var(--sds-color-on-primary-default)",
            borderRadius: "var(--sds-border-radius-full, 9999px)",
            padding: "1px 8px",
            fontWeight: 700,
            minWidth: 36,
            textAlign: "center",
          }}
        >
          {scorePercent}%
        </span>
        <span
          style={{
            flex: 1,
            fontWeight: 600,
            fontSize: "var(--sds-typography-body-small-font-size, 13px)",
            color: "var(--sds-color-on-surface-default)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {group.documentName}
        </span>
      </div>

      {/* Section count hint */}
      {sectionCount > 1 && (
        <span
          style={{
            fontSize: "var(--sds-typography-label-small-font-size, 11px)",
            color: "var(--sds-color-on-surface-low)",
          }}
        >
          {sectionCount}件のセクション
        </span>
      )}
    </button>
  );
}

/** プレビュー画面: ドキュメントのセクション・スニペットを表示 */
function PreviewView({
  group,
  onBack,
}: {
  group: GroupedSource;
  onBack: () => void;
}) {
  return (
    <>
      {/* Back button header */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, minWidth: 0 }}>
          <IconButton
            icon={<SerendieSymbolArrowLeft style={{ width: 20, height: 20 }} />}
            aria-label="一覧に戻る"
            onClick={onBack}
            shape="circle"
            styleType="ghost"
            size="small"
          />
          <h2
            style={{
              margin: 0,
              fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
              fontWeight: 700,
              color: "var(--sds-color-on-surface-default)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {group.documentName}
          </h2>
        </div>
      </div>

      {/* Sections */}
      <div style={bodyStyle}>
        {group.sections.map((section, idx) => (
          <div
            key={`${section.sectionTitle}-${idx}`}
            style={{
              padding: "12px",
              backgroundColor: "var(--sds-color-surface-container)",
              border: "1px solid var(--sds-color-outline-variant)",
              borderRadius: "var(--sds-border-radius-small, 8px)",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            {/* Section header */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span
                aria-hidden="true"
                style={{
                  flexShrink: 0,
                  fontSize: "11px",
                  backgroundColor: "var(--sds-color-primary-default)",
                  color: "var(--sds-color-on-primary-default)",
                  borderRadius: "var(--sds-border-radius-full, 9999px)",
                  padding: "1px 8px",
                  fontWeight: 700,
                  minWidth: 36,
                  textAlign: "center",
                }}
              >
                {Math.round(section.score * 100)}%
              </span>
              {section.sectionTitle && (
                <span
                  style={{
                    fontWeight: 600,
                    fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                    color: "var(--sds-color-on-surface-default)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {section.sectionTitle}
                </span>
              )}
            </div>

            {/* Snippet content */}
            {section.snippet && (
              <div
                style={{
                  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                  color: "var(--sds-color-on-surface-default)",
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: "200px",
                  overflowY: "auto",
                }}
              >
                {section.snippet}
              </div>
            )}

            {!section.snippet && (
              <div
                style={{
                  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
                  color: "var(--sds-color-on-surface-low)",
                  fontStyle: "italic",
                }}
              >
                プレビューなし
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

export function SourcePanel() {
  const isOpen = useSourceStore((s) => s.isSourcePanelOpen);
  const sources = useSourceStore((s) => s.panelSources);
  const closeSourcePanel = useSourceStore((s) => s.closeSourcePanel);

  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // null = 一覧表示, GroupedSource = プレビュー表示
  const [selectedGroup, setSelectedGroup] = useState<GroupedSource | null>(null);

  // パネルが開かれるたびにリセット
  useEffect(() => {
    if (isOpen) {
      setSelectedGroup(null);
    }
  }, [isOpen]);

  const grouped = groupByDocument(sources);

  // Focus close button on open (WCAG 2.4.3)
  useEffect(() => {
    if (isOpen) {
      requestAnimationFrame(() => closeBtnRef.current?.focus());
    }
  }, [isOpen]);

  // Close on Escape (WCAG 2.1.1)
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (selectedGroup) {
          setSelectedGroup(null);
        } else {
          closeSourcePanel();
        }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, closeSourcePanel, selectedGroup]);

  // Focus trap (WCAG 2.4.3)
  useEffect(() => {
    if (!isOpen || !panelRef.current) return;
    function onTab(e: KeyboardEvent) {
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", onTab);
    return () => document.removeEventListener("keydown", onTab);
  }, [isOpen]);

  if (!isOpen || sources.length === 0) return null;

  return (
    <div
      style={overlayStyle}
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-panel-title"
    >
      <div style={backdropStyle} onClick={closeSourcePanel} aria-hidden="true" />

      <div style={panelStyle} ref={panelRef}>
        {selectedGroup ? (
          /* プレビュー表示 */
          <PreviewView
            group={selectedGroup}
            onBack={() => setSelectedGroup(null)}
          />
        ) : (
          /* 一覧表示 */
          <>
            <div style={headerStyle}>
              <h2
                id="source-panel-title"
                style={{
                  margin: 0,
                  fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
                  fontWeight: 700,
                  color: "var(--sds-color-on-surface-default)",
                }}
              >
                参照ドキュメント ({grouped.length})
              </h2>
              <IconButton
                ref={closeBtnRef}
                icon={<SerendieSymbolClose style={{ width: 20, height: 20 }} />}
                aria-label="参照パネルを閉じる"
                onClick={closeSourcePanel}
                shape="circle"
                styleType="ghost"
                size="small"
              />
            </div>

            <div style={bodyStyle}>
              {grouped.map((group) => (
                <SourceCard
                  key={group.documentId}
                  group={group}
                  onClick={() => setSelectedGroup(group)}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
