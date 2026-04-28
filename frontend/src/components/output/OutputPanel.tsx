// OutputPanel: right-side sliding panel (400px) showing DataTable and/or ChartView
// Includes SQL display (collapsible), row count, and download buttons
// WCAG 2.2 AA: dialog role, focus trap, Escape key, focus restoration

import { useRef, useEffect, useState } from "react";
import { IconButton } from "@serendie/ui";
import {
  SerendieSymbolClose,
  SerendieSymbolArrowDown,
  SerendieSymbolArrowUp,
} from "@serendie/symbols";
import { useOutputStore } from "../../stores/outputStore";
import { DataTable } from "./DataTable";
import { ChartView } from "./ChartView";
import { DownloadButtons } from "./DownloadButtons";
import { downloadCsv } from "../../api/output";

const PANEL_WIDTH = 400;

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
  padding: "16px",
  display: "flex",
  flexDirection: "column",
  gap: "20px",
};

const sectionCardStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container-low)",
  borderRadius: "var(--sds-border-radius-small, 8px)",
  padding: "16px",
};

const codeBlockStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container)",
  border: "1px solid var(--sds-color-outline-variant)",
  borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
  padding: "12px",
  fontFamily: "monospace",
  fontSize: "12px",
  color: "var(--sds-color-on-surface-default)",
  overflowX: "auto",
  whiteSpace: "pre",
  margin: 0,
};

const metaLabelStyle: React.CSSProperties = {
  fontSize: "var(--sds-typography-label-small-font-size, 12px)",
  color: "var(--sds-color-on-surface-low)",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  margin: "0 0 8px 0",
};

const collapseTriggerStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  width: "100%",
  padding: 0,
  color: "var(--sds-color-on-surface-default)",
  textAlign: "left",
};

export function OutputPanel() {
  const isOpen = useOutputStore((s) => s.isOutputPanelOpen);
  const outputData = useOutputStore((s) => s.outputData);
  const closeOutputPanel = useOutputStore((s) => s.closeOutputPanel);

  const [sqlExpanded, setSqlExpanded] = useState(false);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Focus the close button when the panel opens (WCAG 2.4.3)
  useEffect(() => {
    if (isOpen) {
      setSqlExpanded(false);
      requestAnimationFrame(() => {
        closeBtnRef.current?.focus();
      });
    }
  }, [isOpen]);

  // Close on Escape key (WCAG 2.1.1)
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") closeOutputPanel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, closeOutputPanel]);

  // Trap focus within panel (WCAG 2.4.3)
  useEffect(() => {
    if (!isOpen || !panelRef.current) return;
    const focusable = panelRef.current.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    function onTab(e: KeyboardEvent) {
      if (e.key !== "Tab") return;
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

  if (!isOpen || !outputData) return null;

  async function handleCsvDownload() {
    if (!outputData) return;
    try {
      const blob = await downloadCsv(outputData.messageId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `output-${outputData.messageId}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // DownloadButtons component handles its own error state for the API path
    }
  }

  return (
    <div
      style={overlayStyle}
      role="dialog"
      aria-modal="true"
      aria-labelledby="output-panel-title"
    >
      {/* Backdrop */}
      <div
        style={backdropStyle}
        onClick={closeOutputPanel}
        aria-hidden="true"
      />

      {/* Panel */}
      <div style={panelStyle} ref={panelRef}>
        {/* Header */}
        <div style={headerStyle}>
          <h2
            id="output-panel-title"
            style={{
              margin: 0,
              fontSize: "var(--sds-typography-title-medium-font-size, 16px)",
              fontWeight: 700,
              color: "var(--sds-color-on-surface-default)",
            }}
          >
            出力データ
          </h2>
          <IconButton
            ref={closeBtnRef}
            icon={<SerendieSymbolClose style={{ width: 20, height: 20 }} />}
            aria-label="出力パネルを閉じる"
            onClick={closeOutputPanel}
            shape="circle"
            styleType="ghost"
            size="small"
          />
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          {/* Row count */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ ...metaLabelStyle, margin: 0 }}>取得行数:</span>
            <span
              style={{
                fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
                fontWeight: 700,
                color: "var(--sds-color-primary-default)",
              }}
            >
              {outputData.rowCount.toLocaleString("ja-JP")} 行
            </span>
          </div>

          {/* Download buttons */}
          <DownloadButtons
            messageId={outputData.messageId}
            tableData={outputData.tableData}
            chartRef={chartContainerRef}
          />

          {/* SQL collapsible */}
          {outputData.sqlExecuted && (
            <div style={sectionCardStyle}>
              <button
                type="button"
                style={collapseTriggerStyle}
                onClick={() => setSqlExpanded((v) => !v)}
                aria-expanded={sqlExpanded}
                aria-controls="sql-code-block"
              >
                <span style={{ ...metaLabelStyle, margin: 0, display: "block" }}>実行SQL</span>
                {sqlExpanded ? (
                  <SerendieSymbolArrowUp
                    style={{ width: 18, height: 18 }}
                    aria-hidden="true"
                  />
                ) : (
                  <SerendieSymbolArrowDown
                    style={{ width: 18, height: 18 }}
                    aria-hidden="true"
                  />
                )}
              </button>
              {sqlExpanded && (
                <pre id="sql-code-block" style={{ ...codeBlockStyle, marginTop: "10px" }}>
                  {outputData.sqlExecuted}
                </pre>
              )}
            </div>
          )}

          {/* Chart */}
          {outputData.chartConfig && outputData.tableData && (
            <div style={sectionCardStyle} ref={chartContainerRef}>
              <h3 style={{ ...metaLabelStyle, margin: "0 0 8px 0" }}>グラフ</h3>
              <ChartView
                config={outputData.chartConfig}
                data={outputData.tableData.rows}
              />
            </div>
          )}

          {/* Data table */}
          {outputData.tableData && (
            <div style={sectionCardStyle}>
              <h3 style={{ ...metaLabelStyle, margin: "0 0 8px 0" }}>テーブル</h3>
              <DataTable
                data={outputData.tableData}
                onCsvDownload={handleCsvDownload}
              />
            </div>
          )}

          {/* No data state */}
          {!outputData.tableData && !outputData.chartConfig && (
            <div
              style={{
                textAlign: "center",
                padding: "48px 24px",
                color: "var(--sds-color-on-surface-low)",
              }}
              aria-live="polite"
            >
              <p style={{ margin: 0 }}>表示できるデータがありません。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
