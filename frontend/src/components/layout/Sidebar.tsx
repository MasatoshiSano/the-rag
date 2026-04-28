// Sidebar: ナビゲーション・お気に入りKB・最近のセッション一覧
// WCAG 2.4.1: landmark nav, keyboard navigation

import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getFavoriteKnowledgeBases } from "../../api/knowledge-bases";
import { getSessions } from "../../api/sessions";
import { useKbStore } from "../../stores/kbStore";
import { useUiStore } from "../../stores/uiStore";

interface SidebarProps {
  isOpen: boolean;
}

const NAV_ITEMS = [
  { to: "/chat", label: "チャット" },
  { to: "/knowledge-bases", label: "ナレッジベース" },
  { to: "/upload", label: "アップロード" },
  { to: "/documents", label: "ドキュメント" },
  { to: "/settings", label: "設定" },
] as const;

export function Sidebar({ isOpen }: SidebarProps) {
  const navigate = useNavigate();
  const setSelectedKbId = useKbStore((s) => s.setSelectedKbId);
  const selectedKbId = useKbStore((s) => s.selectedKbId);
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen);

  const { data: favoriteKbs = [] } = useQuery({
    queryKey: ["knowledge-bases", "favorites"],
    queryFn: getFavoriteKnowledgeBases,
  });

  const { data: recentSessions = [] } = useQuery({
    queryKey: ["sessions", { limit: 10 }],
    queryFn: () => getSessions({ limit: 10 }),
  });

  const handleKbClick = (id: string) => {
    setSelectedKbId(id);
    navigate("/chat");
  };

  const handleSessionClick = (sessionId: string) => {
    navigate(`/chat/${sessionId}`);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* モバイル用オーバーレイ（768px未満で表示） */}
      <div
        aria-hidden="true"
        onClick={() => setSidebarOpen(false)}
        className="sidebar-overlay"
      />

      <nav
        aria-label="サイドバーナビゲーション"
        className="sidebar-nav"
      >
        {/* メインナビゲーション */}
        <div style={{ padding: "8px 0" }}>
          <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  onClick={() => {
                    if (window.innerWidth < 768) setSidebarOpen(false);
                  }}
                  style={({ isActive }) => ({
                    display: "block",
                    padding: "10px 16px",
                    textDecoration: "none",
                    color: isActive
                      ? "var(--sds-color-on-primary-container)"
                      : "var(--sds-color-on-surface-default)",
                    backgroundColor: isActive
                      ? "var(--sds-color-impression-primaryContainer)"
                      : "transparent",
                    borderRadius: 6,
                    margin: "2px 8px",
                    fontWeight: isActive ? 600 : 400,
                    fontSize: 14,
                    transition: "background-color 0.1s",
                  })}
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>

        <hr
          style={{
            border: "none",
            borderTop: "1px solid var(--sds-color-outline-default)",
            margin: "4px 0",
          }}
        />

        {/* お気に入りKB */}
        <div style={{ overflow: "auto", flex: "0 0 auto", maxHeight: 200 }}>
          <p
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--sds-color-on-surface-variant)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              padding: "8px 16px 4px",
              margin: 0,
            }}
          >
            お気に入りKB
          </p>
          {favoriteKbs.length === 0 ? (
            <p
              style={{
                fontSize: 13,
                color: "var(--sds-color-on-surface-variant)",
                padding: "4px 16px 8px",
                margin: 0,
              }}
            >
              なし
            </p>
          ) : (
            <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {favoriteKbs.map((kb) => (
                <li key={kb.id}>
                  <button
                    type="button"
                    aria-pressed={selectedKbId === kb.id}
                    aria-label={`ナレッジベース: ${kb.name}`}
                    onClick={() => handleKbClick(kb.id)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      width: "calc(100% - 16px)",
                      padding: "6px 16px",
                      background: selectedKbId === kb.id
                        ? "var(--sds-color-impression-primaryContainer)"
                        : "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      color: "var(--sds-color-on-surface-default)",
                      fontSize: 13,
                      borderRadius: 4,
                      margin: "1px 8px",
                    }}
                  >
                    {/* カラードット */}
                    <span
                      aria-hidden="true"
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        backgroundColor: kb.color,
                        flexShrink: 0,
                        border: "1px solid rgba(0,0,0,0.15)",
                      }}
                    />
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        flex: 1,
                      }}
                    >
                      {kb.name}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <hr
          style={{
            border: "none",
            borderTop: "1px solid var(--sds-color-outline-default)",
            margin: "4px 0",
          }}
        />

        {/* 最近のセッション */}
        <div style={{ overflow: "auto", flex: 1 }}>
          <p
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--sds-color-on-surface-variant)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              padding: "8px 16px 4px",
              margin: 0,
            }}
          >
            最近のセッション
          </p>
          {recentSessions.length === 0 ? (
            <p
              style={{
                fontSize: 13,
                color: "var(--sds-color-on-surface-variant)",
                padding: "4px 16px 8px",
                margin: 0,
              }}
            >
              セッションがありません
            </p>
          ) : (
            <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {recentSessions.map((session) => (
                <li key={session.id}>
                  <button
                    type="button"
                    aria-label={`セッション: ${session.title}`}
                    onClick={() => handleSessionClick(session.id)}
                    style={{
                      display: "block",
                      width: "calc(100% - 16px)",
                      padding: "6px 16px",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      color: "var(--sds-color-on-surface-default)",
                      fontSize: 13,
                      borderRadius: 4,
                      margin: "1px 8px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {session.title || "無題のセッション"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <hr
          style={{
            border: "none",
            borderTop: "1px solid var(--sds-color-outline-default)",
            margin: "4px 0",
          }}
        />

        {/* API関連リンク */}
        <div style={{ padding: "4px 0 8px", flexShrink: 0 }}>
          <p
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "var(--sds-color-on-surface-variant)",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              padding: "4px 16px",
              margin: 0,
            }}
          >
            開発者向け
          </p>
          <ul role="list" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <li>
              <a
                href="/the-rag/docs"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "block",
                  padding: "6px 16px",
                  textDecoration: "none",
                  color: "var(--sds-color-on-surface-default)",
                  fontSize: 13,
                  borderRadius: 4,
                  margin: "1px 8px",
                }}
              >
                API仕様・動作確認 ↗
              </a>
            </li>
            <li>
              <a
                href="/the-rag/guide.html"
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "block",
                  padding: "6px 16px",
                  textDecoration: "none",
                  color: "var(--sds-color-on-surface-default)",
                  fontSize: 13,
                  borderRadius: 4,
                  margin: "1px 8px",
                }}
              >
                外部連携ガイド ↗
              </a>
            </li>
          </ul>
        </div>
      </nav>
    </>
  );
}
