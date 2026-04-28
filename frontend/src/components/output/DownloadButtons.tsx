// DownloadButtons: CSV download from API, PNG capture, Markdown copy

import { useState } from "react";
import { Button } from "@serendie/ui";
import {
  SerendieSymbolDownload,
  SerendieSymbolCopy,
  SerendieSymbolImage,
} from "@serendie/symbols";
import { downloadCsv } from "../../api/output";
import type { TableData, ColumnDef } from "../../types/output";

interface DownloadButtonsProps {
  messageId: string;
  tableData?: TableData | null;
  chartRef?: React.RefObject<HTMLElement | null>;
}

function rowsToMarkdown(columns: ColumnDef[], rows: TableData["rows"]): string {
  const header = `| ${columns.map((c) => c.label).join(" | ")} |`;
  const separator = `| ${columns.map(() => "---").join(" | ")} |`;
  const body = rows
    .map((row) => `| ${columns.map((c) => String(row[c.key] ?? "")).join(" | ")} |`)
    .join("\n");
  return `${header}\n${separator}\n${body}`;
}

export function DownloadButtons({ messageId, tableData, chartRef }: DownloadButtonsProps) {
  const [csvLoading, setCsvLoading] = useState(false);
  const [pngLoading, setPngLoading] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCsvDownload() {
    setCsvLoading(true);
    setError(null);
    try {
      const blob = await downloadCsv(messageId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `output-${messageId}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("CSVのダウンロードに失敗しました。");
    } finally {
      setCsvLoading(false);
    }
  }

  async function handlePngDownload() {
    if (!chartRef?.current) return;
    setPngLoading(true);
    setError(null);
    try {
      // Dynamically import html-to-image to avoid mandatory dependency
      const { toPng } = await import("html-to-image" as string) as {
        toPng: (node: HTMLElement) => Promise<string>;
      };
      const dataUrl = await toPng(chartRef.current as HTMLElement);
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `chart-${messageId}.png`;
      link.click();
    } catch {
      setError("グラフのPNGダウンロードに失敗しました。");
    } finally {
      setPngLoading(false);
    }
  }

  async function handleMarkdownCopy() {
    if (!tableData) return;
    const md = rowsToMarkdown(tableData.columns, tableData.rows);
    try {
      await navigator.clipboard.writeText(md);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      setError("クリップボードへのコピーに失敗しました。");
    }
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <Button
          styleType="outlined"
          size="small"
          leftIcon={<SerendieSymbolDownload style={{ width: 16, height: 16 }} />}
          onClick={handleCsvDownload}
          isLoading={csvLoading}
          disabled={csvLoading}
          aria-label="CSVファイルをダウンロード"
        >
          CSV
        </Button>

        {chartRef && (
          <Button
            styleType="outlined"
            size="small"
            leftIcon={<SerendieSymbolImage style={{ width: 16, height: 16 }} />}
            onClick={handlePngDownload}
            isLoading={pngLoading}
            disabled={pngLoading}
            aria-label="グラフをPNG画像でダウンロード"
          >
            PNG
          </Button>
        )}

        {tableData && (
          <Button
            styleType="outlined"
            size="small"
            leftIcon={<SerendieSymbolCopy style={{ width: 16, height: 16 }} />}
            onClick={handleMarkdownCopy}
            aria-label="テーブルをMarkdown形式でクリップボードにコピー"
            aria-pressed={copySuccess}
          >
            {copySuccess ? "コピー済み" : "Markdown"}
          </Button>
        )}
      </div>

      {error && (
        <p
          role="alert"
          style={{
            color: "var(--sds-color-error-default)",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            margin: "8px 0 0 0",
          }}
        >
          {error}
        </p>
      )}
    </div>
  );
}
