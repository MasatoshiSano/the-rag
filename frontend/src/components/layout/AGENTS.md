<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# layout

## Purpose
全画面共通のシェル。AppShell が `<Outlet>` を内側に置き、Sidebar・Header・セッション検索ポップオーバーを配置する。

## Key Files
| File | Description |
|------|-------------|
| `AppShell.tsx` | グリッドレイアウトのシェル。Sidebar + Header + 本文（`<Outlet>`） |
| `Sidebar.tsx` | ナビゲーション（チャット/ドキュメント/アップロード/KB/設定） + セッション履歴 + 折り畳み |
| `Header.tsx` | 上部のページタイトル/アクション領域 |
| `SessionSearch.tsx` | FTS5 ベースのセッション横断検索ポップオーバー |

## For AI Agents

### Working In This Directory
- このディレクトリには `index.ts` がない（直接 import される）。新規追加時は import 経路を確認する。
- Sidebar の開閉状態は `useUiStore` の `isSidebarOpen`。
- 検索ポップオーバーは `/api/sessions/search` を叩く。デバウンスはコンポーネント内で行う。

## Dependencies

### Internal
- `../../stores/uiStore`, `../../stores/userStore`
- `../../api/sessions`

### External
- `react-router-dom`, `@serendie/ui`

<!-- MANUAL: -->
