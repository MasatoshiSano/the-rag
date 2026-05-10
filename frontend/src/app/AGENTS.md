<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# app

## Purpose
アプリ全体のシェル。ルーティング・プロバイダ（TanStack Query / Serendie）の組み立てと App コンポーネントを定義する。

## Key Files
| File | Description |
|------|-------------|
| `App.tsx` | `<Providers>` で `<RouterProvider>` をラップした最上位コンポーネント |
| `providers.tsx` | `QueryClientProvider`（staleTime 5 分、retry 1）+ `SerendieProvider` |
| `router.tsx` | `createBrowserRouter` で `AppShell` を親に `/chat` `/upload` `/documents` `/settings` `/knowledge-bases` を子ルートとして登録 |

## For AI Agents

### Working In This Directory
- 新ページは `pages/` にコンポーネントを作成し、`router.tsx` の `routes` 配列に追加する。
- `BrowserRouter` の `basename` は Vite の `base: "/the-rag/"` と整合する必要がある。`router.tsx` の `createBrowserRouter` 第 2 引数を確認する。
- TanStack Query の `staleTime` / `retry` を変えたい場合は `providers.tsx` の `defaultOptions` を修正する。

### Common Patterns
- レイアウト共通化は `<AppShell>`（`components/layout/`）が担い、`<Outlet>` で子ページを描画する。

## Dependencies

### Internal
- `../components/layout/AppShell`
- `../pages/*`

### External
- `react-router-dom`, `@tanstack/react-query`, `@serendie/ui`

<!-- MANUAL: -->
