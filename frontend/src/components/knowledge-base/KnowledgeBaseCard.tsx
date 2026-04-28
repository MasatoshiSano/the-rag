// KnowledgeBaseCard: KBカード（お気に入りトグル・編集・削除アクション）
// WCAG 2.4: フォーカス可能なインタラクティブ要素、aria-label明示

import type { KnowledgeBase } from "../../types/knowledge-base";

interface KnowledgeBaseCardProps {
  kb: KnowledgeBase;
  onFavoriteToggle: (id: string, is_favorite: boolean) => void;
  onEdit: (kb: KnowledgeBase) => void;
  onDelete: (kb: KnowledgeBase) => void;
  onClick: (kb: KnowledgeBase) => void;
}

export function KnowledgeBaseCard({
  kb,
  onFavoriteToggle,
  onEdit,
  onDelete,
  onClick,
}: KnowledgeBaseCardProps) {
  return (
    <article
      aria-label={`ナレッジベース: ${kb.name}`}
      style={{
        backgroundColor: "var(--sds-color-surface-default)",
        border: "1px solid var(--sds-color-outline-default)",
        borderRadius: 8,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        position: "relative",
        cursor: "pointer",
        transition: "box-shadow 0.15s",
      }}
      onClick={() => onClick(kb)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(kb);
        }
      }}
      tabIndex={0}
      role="button"
    >
      {/* ヘッダー: カラードット + 名前 + お気に入りボタン */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          justifyContent: "space-between",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span
            aria-hidden="true"
            style={{
              width: 14,
              height: 14,
              borderRadius: "50%",
              backgroundColor: kb.color,
              flexShrink: 0,
              border: "1px solid rgba(0,0,0,0.15)",
            }}
          />
          <h3
            style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 600,
              color: "var(--sds-color-on-surface-default)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {kb.name}
          </h3>
        </div>

        {/* お気に入りトグル */}
        <button
          type="button"
          aria-label={kb.is_favorite ? `${kb.name}のお気に入りを解除` : `${kb.name}をお気に入りに追加`}
          aria-pressed={kb.is_favorite}
          onClick={(e) => {
            e.stopPropagation();
            onFavoriteToggle(kb.id, kb.is_favorite);
          }}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 4,
            borderRadius: 4,
            color: kb.is_favorite
              ? "var(--sds-color-impression-primary)"
              : "var(--sds-color-on-surface-variant)",
            fontSize: 18,
            lineHeight: 1,
            flexShrink: 0,
          }}
        >
          <span aria-hidden="true">{kb.is_favorite ? "★" : "☆"}</span>
        </button>
      </div>

      {/* 説明 */}
      {kb.description && (
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: "var(--sds-color-on-surface-variant)",
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            lineHeight: 1.5,
          }}
        >
          {kb.description}
        </p>
      )}

      {/* ドキュメント数 */}
      <div
        style={{
          fontSize: 12,
          color: "var(--sds-color-on-surface-variant)",
          display: "flex",
          alignItems: "center",
          gap: 4,
        }}
      >
        <span aria-hidden="true">📄</span>
        <span>{kb.document_count} ドキュメント</span>
      </div>

      {/* アクションボタン */}
      <div
        style={{
          display: "flex",
          gap: 8,
          marginTop: 4,
          justifyContent: "flex-end",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          aria-label={`${kb.name}を編集`}
          onClick={(e) => {
            e.stopPropagation();
            onEdit(kb);
          }}
          style={{
            padding: "4px 12px",
            fontSize: 12,
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: 4,
            backgroundColor: "transparent",
            color: "var(--sds-color-on-surface-default)",
            cursor: "pointer",
          }}
        >
          編集
        </button>
        <button
          type="button"
          aria-label={`${kb.name}を削除`}
          onClick={(e) => {
            e.stopPropagation();
            onDelete(kb);
          }}
          style={{
            padding: "4px 12px",
            fontSize: 12,
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: 4,
            backgroundColor: "transparent",
            color: "var(--sds-color-error-default, #B00020)",
            cursor: "pointer",
          }}
        >
          削除
        </button>
      </div>
    </article>
  );
}
