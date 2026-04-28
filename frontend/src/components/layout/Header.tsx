// Header: top app bar with sidebar toggle and session search
// TODO: Integrate Serendie TopAppBar component

import { useUiStore } from "../../stores/uiStore";
import { SessionSearch } from "./SessionSearch";

export function Header() {
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const isSidebarOpen = useUiStore((s) => s.isSidebarOpen);

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        backgroundColor: "var(--sds-color-surface-default)",
        borderBottom: "1px solid var(--sds-color-outline-default)",
        display: "flex",
        alignItems: "center",
        padding: "0 16px",
        height: 56,
        gap: 16,
      }}
    >
      {/* Sidebar toggle */}
      <button
        type="button"
        aria-label={isSidebarOpen ? "サイドバーを閉じる" : "サイドバーを開く"}
        aria-expanded={isSidebarOpen}
        onClick={toggleSidebar}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 8,
          borderRadius: 4,
          color: "var(--sds-color-on-surface-default)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* TODO: Replace with SerendieSymbol icon */}
        <span aria-hidden="true" style={{ fontSize: 20 }}>
          {isSidebarOpen ? "✕" : "☰"}
        </span>
      </button>

      {/* App title */}
      <span
        style={{
          fontWeight: 700,
          fontSize: 18,
          color: "var(--sds-color-on-surface-default)",
          flexShrink: 0,
        }}
      >
        THE RAG
      </span>

      {/* Session search */}
      <div style={{ flex: 1, maxWidth: 480 }}>
        <SessionSearch />
      </div>

      {/* TODO: User avatar / profile button */}
    </header>
  );
}
