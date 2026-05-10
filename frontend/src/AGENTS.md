<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# src

## Purpose
React アプリのソースコードルート。`main.tsx` がエントリ、`app/` がルーティング/プロバイダ、`pages/` が画面、`components/` が再利用可能 UI、`api/` が HTTP クライアント、`stores/` が Zustand 状態、`types/` が型定義、`hooks/` がカスタムフック、`utils/` が雑多なユーティリティ。

## Key Files
| File | Description |
|------|-------------|
| `main.tsx` | ReactDOM へのマウントエントリ |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `api/` | バックエンド HTTP / SSE クライアント（`api/AGENTS.md`） |
| `app/` | App ルート、Providers、Router 設定（`app/AGENTS.md`） |
| `components/` | 機能別 UI コンポーネント（`components/AGENTS.md`） |
| `hooks/` | カスタム React フック（`hooks/AGENTS.md`） |
| `pages/` | ルート単位のページコンポーネント（`pages/AGENTS.md`） |
| `stores/` | Zustand グローバルストア（`stores/AGENTS.md`） |
| `types/` | TypeScript 型定義（`types/AGENTS.md`） |
| `utils/` | 共通ユーティリティ（`utils/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 各サブディレクトリには `index.ts`（barrel export）がある場合とない場合が混在している。`components/*` は barrel あり、`stores/` は無し。新規ファイル追加時は隣接の慣習に合わせる。
- 絶対パスエイリアスは未設定。相対 import (`../api/client` など) を使う。
- ルーター登録は `app/router.tsx`。新ページは `pages/` に追加し `router.tsx` の `routes` 配列に登録する。

### Common Patterns
- 1 コンポーネント 1 ファイル、ファイル名は PascalCase（`ChatInput.tsx`）。
- 型は `types/<feature>.ts` にまとめ、API スキーマと密結合。バックエンド変更があれば `types/*` も更新する。
- 状態は機能ごとに別ストアファイルに分割（`chatStore` / `kbStore` / `outputStore` / `sourceStore` / `uiStore` / `userStore`）。

## Dependencies

### Internal
- すべての子ディレクトリ

### External
- react, react-router-dom, @tanstack/react-query, zustand, @serendie/ui

<!-- MANUAL: -->
