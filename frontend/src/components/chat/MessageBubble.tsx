import type { ReactNode } from "react";
import type { Message } from "../../types/message";
import { SourceList } from "./SourceList";
import { CopyButton } from "./CopyButton";
import { StarRating } from "./StarRating";

interface MessageBubbleProps {
  message: Message;
}

const headingStyle: Record<number, React.CSSProperties> = {
  1: { fontSize: "1.25em", fontWeight: 700, margin: "16px 0 8px 0", lineHeight: 1.3 },
  2: { fontSize: "1.15em", fontWeight: 700, margin: "14px 0 6px 0", lineHeight: 1.3 },
  3: { fontSize: "1.05em", fontWeight: 700, margin: "12px 0 4px 0", lineHeight: 1.3 },
  4: { fontSize: "1em", fontWeight: 700, margin: "10px 0 4px 0", lineHeight: 1.3 },
};

const listItemStyle: React.CSSProperties = {
  margin: "2px 0",
  lineHeight: 1.6,
};

const orderedListStyle: React.CSSProperties = {
  margin: "6px 0",
  paddingLeft: "1.5em",
  listStyleType: "decimal",
};

const unorderedListStyle: React.CSSProperties = {
  margin: "6px 0",
  paddingLeft: "1.5em",
  listStyleType: "disc",
};

const codeBlockStyle: React.CSSProperties = {
  backgroundColor: "var(--sds-color-surface-container-high)",
  borderRadius: "var(--sds-border-radius-extra-small, 4px)",
  padding: "var(--sds-spacing-medium, 12px)",
  overflowX: "auto",
  margin: "8px 0",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
  fontFamily: "var(--sds-typography-mono-font-family, monospace)",
};

const hrStyle: React.CSSProperties = {
  border: "none",
  borderTop: "1px solid var(--sds-color-outline-variant)",
  margin: "12px 0",
};

const tableStyle: React.CSSProperties = {
  borderCollapse: "collapse",
  margin: "8px 0",
  fontSize: "var(--sds-typography-body-small-font-size, 13px)",
  width: "100%",
  overflowX: "auto",
  display: "block",
};

const thStyle: React.CSSProperties = {
  border: "1px solid var(--sds-color-outline-variant)",
  padding: "6px 10px",
  backgroundColor: "var(--sds-color-surface-container-high)",
  fontWeight: 600,
  textAlign: "left",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  border: "1px solid var(--sds-color-outline-variant)",
  padding: "6px 10px",
  textAlign: "left",
};

// Markdown renderer: headings, lists, code blocks, bold, inline code, hr
export function renderMarkdown(text: string): ReactNode {
  const lines = text.split("\n");
  const elements: ReactNode[] = [];
  let i = 0;
  let key = 0;

  function nextKey() {
    return `md-${key++}`;
  }

  // Flush accumulated list items into a <ul> or <ol>
  function flushList(items: ReactNode[], ordered: boolean) {
    if (items.length === 0) return;
    const ListTag = ordered ? "ol" : "ul";
    elements.push(
      <ListTag key={nextKey()} style={ordered ? orderedListStyle : unorderedListStyle}>
        {items.map((item, idx) => (
          <li key={idx} style={listItemStyle}>{item}</li>
        ))}
      </ListTag>
    );
  }

  let listItems: ReactNode[] = [];
  let listOrdered = false;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      flushList(listItems, listOrdered);
      listItems = [];
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <pre key={nextKey()} style={codeBlockStyle}>
          {lang && (
            <span style={{ display: "block", fontSize: 11, color: "var(--sds-color-on-surface-low)", marginBottom: 4 }}>
              {lang}
            </span>
          )}
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      i++; // skip closing ```
      continue;
    }

    // Table: lines starting with |
    if (line.trimStart().startsWith("|") && line.trimEnd().endsWith("|")) {
      flushList(listItems, listOrdered);
      listItems = [];
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("|") && lines[i].trimEnd().endsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      if (tableLines.length >= 2) {
        const parseRow = (row: string) =>
          row.split("|").slice(1, -1).map((cell) => cell.trim());
        const headerCells = parseRow(tableLines[0]);
        // Check if second line is separator (all cells are dashes/colons)
        const isSeparator = parseRow(tableLines[1]).every((cell) => /^:?-+:?$/.test(cell));
        const bodyStart = isSeparator ? 2 : 1;
        const bodyRows = tableLines.slice(bodyStart).map(parseRow);

        elements.push(
          <table key={nextKey()} style={tableStyle}>
            <thead>
              <tr>
                {headerCells.map((cell, ci) => (
                  <th key={ci} style={thStyle}>{renderInline(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td key={ci} style={tdStyle}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      } else {
        // Single pipe line, render as normal text
        elements.push(<div key={nextKey()} style={{ margin: 0 }}>{renderInline(tableLines[0])}</div>);
      }
      continue;
    }

    // Heading: # ~ ####
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushList(listItems, listOrdered);
      listItems = [];
      const level = headingMatch[1].length as 1 | 2 | 3 | 4;
      const Tag = `h${Math.min(level + 2, 6)}` as "h3" | "h4" | "h5" | "h6"; // offset since h1/h2 used by page
      elements.push(
        <Tag key={nextKey()} style={headingStyle[level]}>{renderInline(headingMatch[2])}</Tag>
      );
      i++;
      continue;
    }

    // Horizontal rule
    if (/^-{3,}$/.test(line.trim()) || /^\*{3,}$/.test(line.trim())) {
      flushList(listItems, listOrdered);
      listItems = [];
      elements.push(<hr key={nextKey()} style={hrStyle} />);
      i++;
      continue;
    }

    // Unordered list: - item or * item
    const ulMatch = line.match(/^[-*]\s+(.+)$/);
    if (ulMatch) {
      if (listItems.length > 0 && listOrdered) {
        flushList(listItems, listOrdered);
        listItems = [];
      }
      listOrdered = false;
      listItems.push(renderInline(ulMatch[1]));
      i++;
      continue;
    }

    // Ordered list: 1. item
    const olMatch = line.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      if (listItems.length > 0 && !listOrdered) {
        flushList(listItems, listOrdered);
        listItems = [];
      }
      listOrdered = true;
      listItems.push(renderInline(olMatch[1]));
      i++;
      continue;
    }

    // Regular line — flush any pending list
    flushList(listItems, listOrdered);
    listItems = [];

    // Empty line → spacing
    if (line.trim() === "") {
      elements.push(<div key={nextKey()} style={{ height: 8 }} />);
      i++;
      continue;
    }

    // Normal paragraph
    elements.push(<div key={nextKey()} style={{ margin: 0 }}>{renderInline(line)}</div>);
    i++;
  }

  // Flush remaining list items
  flushList(listItems, listOrdered);

  return <>{elements}</>;
}

const linkStyle: React.CSSProperties = {
  color: "var(--sds-color-impression-primary)",
  textDecoration: "underline",
  wordBreak: "break-all",
};

function renderInline(text: string): ReactNode {
  const parts: ReactNode[] = [];
  // Match **bold**, `code`, or URLs
  const regex = /(\*\*(.+?)\*\*|`([^`]+)`|(https?:\/\/[^\s)>\]]+))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[0].startsWith("**")) {
      parts.push(<strong key={match.index}>{match[2]}</strong>);
    } else if (match[0].startsWith("`")) {
      parts.push(
        <code
          key={match.index}
          style={{
            backgroundColor: "var(--sds-color-surface-container-high)",
            borderRadius: "var(--sds-border-radius-extra-small, 4px)",
            padding: "1px 4px",
            fontSize: "0.9em",
            fontFamily: "var(--sds-typography-mono-font-family, monospace)",
          }}
        >
          {match[3]}
        </code>
      );
    } else {
      // URL
      const url = match[4];
      parts.push(
        <a
          key={match.index}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          style={linkStyle}
        >
          {url}
        </a>
      );
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <>{parts}</>;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  return (
    <article
      aria-label={isUser ? "あなたのメッセージ" : "アシスタントの回答"}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        maxWidth: "100%",
        padding: "0 var(--sds-spacing-large, 16px)",
      }}
    >
      {/* Role label */}
      <span
        aria-hidden="true"
        style={{
          fontSize: "var(--sds-typography-label-small-font-size, 11px)",
          color: "var(--sds-color-on-surface-low)",
          marginBottom: "var(--sds-spacing-extra-small, 4px)",
          fontWeight: 600,
        }}
      >
        {isUser ? "あなた" : "アシスタント"}
      </span>

      {/* Bubble */}
      <div
        style={{
          maxWidth: "min(640px, 80%)",
          padding: "var(--sds-spacing-medium, 12px) var(--sds-spacing-large, 16px)",
          borderRadius: isUser
            ? "var(--sds-border-radius-large, 16px) var(--sds-border-radius-large, 16px) var(--sds-border-radius-extra-small, 4px) var(--sds-border-radius-large, 16px)"
            : "var(--sds-border-radius-large, 16px) var(--sds-border-radius-large, 16px) var(--sds-border-radius-large, 16px) var(--sds-border-radius-extra-small, 4px)",
          backgroundColor: isUser
            ? "var(--sds-color-primary-default)"
            : "var(--sds-color-surface-container)",
          color: isUser
            ? "var(--sds-color-on-primary-default)"
            : "var(--sds-color-on-surface-default)",
          fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
          lineHeight: 1.6,
          wordBreak: "break-word",
          whiteSpace: isUser ? "pre-wrap" : "normal",
        }}
      >
        {isAssistant ? renderMarkdown(message.content) : message.content}

        {isAssistant && message.isCancelled && (
          <span
            style={{
              display: "block",
              marginTop: "var(--sds-spacing-small, 8px)",
              fontSize: "var(--sds-typography-label-small-font-size, 12px)",
              color: "var(--sds-color-caution-default)",
              fontStyle: "italic",
            }}
          >
            （回答が中断されました）
          </span>
        )}
      </div>

      {/* Assistant-only actions */}
      {isAssistant && !message.isCancelled && (
        <div
          style={{
            marginTop: "var(--sds-spacing-small, 8px)",
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            gap: "var(--sds-spacing-small, 8px)",
            maxWidth: "min(640px, 80%)",
            width: "100%",
          }}
        >
          {/* Sources */}
          {message.sources && message.sources.length > 0 && (
            <SourceList sources={message.sources} />
          )}

          {/* Action row: copy + rating */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--sds-spacing-medium, 12px)",
              flexWrap: "wrap",
            }}
          >
            <CopyButton content={message.content} />
            <StarRating messageId={message.id} initialRating={message.rating} />
          </div>
        </div>
      )}

      {/* Timestamp */}
      <time
        dateTime={message.createdAt}
        style={{
          marginTop: "var(--sds-spacing-extra-small, 4px)",
          fontSize: "var(--sds-typography-label-small-font-size, 11px)",
          color: "var(--sds-color-on-surface-low)",
        }}
      >
        {new Date(message.createdAt).toLocaleTimeString("ja-JP", {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </time>
    </article>
  );
}
