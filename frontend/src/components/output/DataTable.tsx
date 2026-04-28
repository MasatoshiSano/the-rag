// DataTable: paginated, sortable table from TableData
// Supports CSV download (BOM UTF-8) and Markdown copy

import { useState, useCallback } from "react";
import { Button } from "@serendie/ui";
import {
  SerendieSymbolArrowUp,
  SerendieSymbolArrowDown,
  SerendieSymbolCopy,
  SerendieSymbolDownload,
} from "@serendie/symbols";
import type { TableData, ColumnDef } from "../../types/output";

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
type PageSize = (typeof PAGE_SIZE_OPTIONS)[number];

type SortDir = "asc" | "desc" | null;

interface SortState {
  key: string;
  dir: SortDir;
}

interface DataTableProps {
  data: TableData;
  onCsvDownload?: () => void;
}

const tableContainerStyle: React.CSSProperties = {
  overflowX: "auto",
  borderRadius: "var(--sds-border-radius-small, 8px)",
  border: "1px solid var(--sds-color-outline-variant)",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
};

const thBaseStyle: React.CSSProperties = {
  padding: "10px 12px",
  borderBottom: "2px solid var(--sds-color-outline-default)",
  backgroundColor: "var(--sds-color-surface-container)",
  textAlign: "left",
  fontWeight: 700,
  whiteSpace: "nowrap",
  color: "var(--sds-color-on-surface-default)",
};

const thButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: 0,
  font: "inherit",
  fontWeight: 700,
  color: "var(--sds-color-on-surface-default)",
  width: "100%",
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid var(--sds-color-outline-variant)",
  color: "var(--sds-color-on-surface-default)",
  verticalAlign: "middle",
};

const controlsStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: "12px",
  marginBottom: "8px",
};

const pagingStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
  color: "var(--sds-color-on-surface-default)",
};

const pagingButtonStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid var(--sds-color-outline-default)",
  borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
  padding: "4px 10px",
  cursor: "pointer",
  color: "var(--sds-color-on-surface-default)",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
};

const selectStyle: React.CSSProperties = {
  height: 32,
  border: "1px solid var(--sds-color-outline-default)",
  borderRadius: "var(--sds-border-radius-extraSmall, 4px)",
  padding: "0 6px",
  backgroundColor: "var(--sds-color-surface-default)",
  color: "var(--sds-color-on-surface-default)",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
  cursor: "pointer",
};

function sortRows(
  rows: TableData["rows"],
  columns: ColumnDef[],
  sort: SortState
): TableData["rows"] {
  if (!sort.dir) return rows;
  const col = columns.find((c) => c.key === sort.key);
  const isNumeric = col?.type === "number";
  return [...rows].sort((a, b) => {
    const av = a[sort.key];
    const bv = b[sort.key];
    let cmp = 0;
    if (isNumeric) {
      cmp = Number(av) - Number(bv);
    } else {
      cmp = String(av ?? "").localeCompare(String(bv ?? ""), "ja");
    }
    return sort.dir === "asc" ? cmp : -cmp;
  });
}

function rowsToMarkdown(columns: ColumnDef[], rows: TableData["rows"]): string {
  const header = `| ${columns.map((c) => c.label).join(" | ")} |`;
  const separator = `| ${columns.map(() => "---").join(" | ")} |`;
  const body = rows
    .map((row) => `| ${columns.map((c) => String(row[c.key] ?? "")).join(" | ")} |`)
    .join("\n");
  return `${header}\n${separator}\n${body}`;
}

function downloadLocalCsv(columns: ColumnDef[], rows: TableData["rows"]) {
  const header = columns.map((c) => `"${c.label}"`).join(",");
  const body = rows
    .map((row) =>
      columns.map((c) => `"${String(row[c.key] ?? "").replace(/"/g, '""')}"`).join(",")
    )
    .join("\n");
  const csv = `${header}\n${body}`;
  const bom = "\uFEFF";
  const blob = new Blob([bom + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "data.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function DataTable({ data, onCsvDownload }: DataTableProps) {
  const { columns, rows } = data;
  const [sort, setSort] = useState<SortState>({ key: "", dir: null });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<PageSize>(20);
  const [copySuccess, setCopySuccess] = useState(false);

  const sortedRows = sortRows(rows, columns, sort);
  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize));
  const pagedRows = sortedRows.slice((page - 1) * pageSize, page * pageSize);

  function toggleSort(key: string) {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return { key: "", dir: null };
    });
    setPage(1);
  }

  function handlePageSizeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setPageSize(Number(e.target.value) as PageSize);
    setPage(1);
  }

  const handleMarkdownCopy = useCallback(async () => {
    const md = rowsToMarkdown(columns, sortedRows);
    try {
      await navigator.clipboard.writeText(md);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      // clipboard access denied - silently fail
    }
  }, [columns, sortedRows]);

  function handleCsvDownload() {
    if (onCsvDownload) {
      onCsvDownload();
    } else {
      downloadLocalCsv(columns, sortedRows);
    }
  }

  return (
    <div>
      <div style={controlsStyle}>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <Button
            styleType="outlined"
            size="small"
            leftIcon={<SerendieSymbolDownload style={{ width: 16, height: 16 }} />}
            onClick={handleCsvDownload}
            aria-label="CSVファイルをダウンロード"
          >
            CSV
          </Button>
          <Button
            styleType="outlined"
            size="small"
            leftIcon={<SerendieSymbolCopy style={{ width: 16, height: 16 }} />}
            onClick={handleMarkdownCopy}
            aria-label="テーブルをMarkdown形式でコピー"
            aria-pressed={copySuccess}
          >
            {copySuccess ? "コピー済み" : "Markdownコピー"}
          </Button>
        </div>

        <div style={pagingStyle}>
          <label htmlFor="page-size-select" style={{ whiteSpace: "nowrap" }}>
            表示件数:
          </label>
          <select
            id="page-size-select"
            value={pageSize}
            onChange={handlePageSizeChange}
            style={selectStyle}
            aria-label="1ページの表示件数"
          >
            {PAGE_SIZE_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}件
              </option>
            ))}
          </select>
          <span aria-live="polite" aria-atomic="true">
            {(page - 1) * pageSize + 1}–
            {Math.min(page * pageSize, rows.length)} / {rows.length}件
          </span>
        </div>
      </div>

      <div style={tableContainerStyle}>
        <table style={tableStyle} aria-label="データテーブル" aria-rowcount={rows.length}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  style={thBaseStyle}
                  aria-sort={
                    sort.key === col.key
                      ? sort.dir === "asc"
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    type="button"
                    style={thButtonStyle}
                    onClick={() => toggleSort(col.key)}
                  >
                    {col.label}
                    {sort.key === col.key && sort.dir === "asc" && (
                      <SerendieSymbolArrowUp
                        style={{ width: 14, height: 14 }}
                        aria-hidden="true"
                      />
                    )}
                    {sort.key === col.key && sort.dir === "desc" && (
                      <SerendieSymbolArrowDown
                        style={{ width: 14, height: 14 }}
                        aria-hidden="true"
                      />
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row, rowIdx) => (
              <tr
                key={rowIdx}
                style={{
                  backgroundColor:
                    rowIdx % 2 === 0
                      ? "var(--sds-color-surface-default)"
                      : "var(--sds-color-surface-container-lowest)",
                }}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{
                      ...tdStyle,
                      textAlign: col.type === "number" ? "right" : "left",
                    }}
                  >
                    {String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination controls */}
      <nav
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: "8px",
          marginTop: "12px",
        }}
        aria-label="ページネーション"
      >
        <button
          type="button"
          style={{
            ...pagingButtonStyle,
            opacity: page === 1 ? 0.4 : 1,
            cursor: page === 1 ? "not-allowed" : "pointer",
          }}
          onClick={() => setPage(1)}
          disabled={page === 1}
          aria-label="最初のページ"
        >
          «
        </button>
        <button
          type="button"
          style={{
            ...pagingButtonStyle,
            opacity: page === 1 ? 0.4 : 1,
            cursor: page === 1 ? "not-allowed" : "pointer",
          }}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
          aria-label="前のページ"
        >
          ‹
        </button>

        <span aria-current="page" style={{ padding: "0 8px" }}>
          {page} / {totalPages}
        </span>

        <button
          type="button"
          style={{
            ...pagingButtonStyle,
            opacity: page === totalPages ? 0.4 : 1,
            cursor: page === totalPages ? "not-allowed" : "pointer",
          }}
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page === totalPages}
          aria-label="次のページ"
        >
          ›
        </button>
        <button
          type="button"
          style={{
            ...pagingButtonStyle,
            opacity: page === totalPages ? 0.4 : 1,
            cursor: page === totalPages ? "not-allowed" : "pointer",
          }}
          onClick={() => setPage(totalPages)}
          disabled={page === totalPages}
          aria-label="最後のページ"
        >
          »
        </button>
      </nav>
    </div>
  );
}
