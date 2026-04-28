// AppShell: 3カラムレイアウト（サイドバー・メイン・出力パネル）
// WCAG 2.4.1: スキップリンク・ランドマーク対応

import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { useUiStore } from "../../stores/uiStore";
import { OutputPanel } from "../output/OutputPanel";
import { SourcePanel } from "../chat/SourcePanel";

export function AppShell() {
  const isSidebarOpen = useUiStore((s) => s.isSidebarOpen);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        backgroundColor: "var(--sds-color-surface-default)",
      }}
    >
      {/* WCAG 2.4.1: スキップナビゲーションリンク */}
      <a
        href="#main-content"
        style={{
          position: "absolute",
          top: -40,
          left: 0,
          backgroundColor: "var(--sds-color-primary-default)",
          color: "var(--sds-color-on-primary-container)",
          padding: "8px 16px",
          zIndex: 200,
          textDecoration: "none",
          fontWeight: 600,
          borderRadius: "0 0 4px 0",
          transition: "top 0.1s",
        }}
        onFocus={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.top = "0";
        }}
        onBlur={(e) => {
          (e.currentTarget as HTMLAnchorElement).style.top = "-40px";
        }}
      >
        メインコンテンツへスキップ
      </a>

      {/* トップヘッダー */}
      <Header />

      {/* 3カラムコンテナ */}
      <div
        style={{
          display: "flex",
          flex: 1,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {/* 左カラム: サイドバー (240px固定、モバイルはオーバーレイ) */}
        <Sidebar isOpen={isSidebarOpen} />

        {/* 中央カラム: メインコンテンツ */}
        <main
          id="main-content"
          tabIndex={-1}
          style={{
            flex: 1,
            overflow: "auto",
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            outline: "none",
          }}
        >
          <Outlet />
        </main>

      </div>

      {/* 出力パネル: position:fixed のオーバーレイとして描画 */}
      <OutputPanel />
      <SourcePanel />
    </div>
  );
}
