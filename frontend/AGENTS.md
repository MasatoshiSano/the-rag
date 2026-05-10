<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# frontend

## Purpose
React 18 + TypeScript + Vite 製のシングルページアプリケーション。Serendie Design System を UI ライブラリに、TanStack Query をサーバ状態に、Zustand をクライアント状態に、React Router v7 をルーティングに使う。本番ビルドは Nginx で配信し、`/the-rag/api/*` をバックエンドにリバースプロキシする。

## Key Files
| File | Description |
|------|-------------|
| `package.json` | `dev` (Vite), `build` (`tsc -b && vite build`), `preview`, `lint` (ESLint flat config), `typecheck` の npm scripts と依存定義 |
| `vite.config.ts` | `base: "/the-rag/"`、開発サーバ port 5173、`/api → http://localhost:8000` プロキシ |
| `tsconfig.json` | TypeScript 設定（strict 系オプション含む） |
| `eslint.config.js` | ESLint flat config（typescript-eslint + react-hooks + react-refresh） |
| `playwright.config.ts` | E2E: `baseURL=http://localhost:3000`, `locale=ja-JP`, Chromium のみ |
| `index.html` | Vite のエントリ HTML |
| `Dockerfile` | `node:20-alpine` でビルド → `nginx:alpine` で `/usr/share/nginx/html` に配信 |
| `nginx.conf` / `nginx-default.conf` / `nginx-http.conf` | Nginx の各構成（HTTPS/HTTP/デフォルト） |
| `.dockerignore` | Docker ビルド時の除外設定 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/` | アプリケーションソース（`src/AGENTS.md`） |
| `e2e/` | Playwright E2E テスト（`e2e/AGENTS.md`） |
| `public/` | 静的アセット（favicon・guide.html） |
| `ssl/` | 開発用自己署名証明書（`ssl.crt` / `ssl.key`） |
| `test-results/` | Playwright の実行結果（生成物、git 管理外） |

## For AI Agents

### Working In This Directory
- 開発: `npm run dev` で `http://localhost:5173`。バックエンドは `localhost:8000` で別途起動が必要（または `docker compose up backend qdrant`）。
- 本番ビルド検証: `npm run build && npm run preview`。
- 型チェック: `npm run typecheck`（`tsc --noEmit`）。リント: `npm run lint`。
- E2E: `npx playwright test`（`docker compose up` 済み前提、`baseURL=http://localhost:3000`）。
- Vite の `base: "/the-rag/"` のため、ビルド後のアセットパスは `/the-rag/...` になる。Nginx 側で同じパスにマッピングする。
- API ベース URL は `/the-rag/api`。`api/client.ts` と `api/sse.ts` でハードコードされているので、変更時は両方を同期する。

### Testing Requirements
- ユニット/コンポーネントテストは未整備（追加歓迎）。
- E2E は `e2e/` 配下の `*.spec.ts`。新ページ追加時は最低 1 ケース追加するのが望ましい。
- 型エラーゼロ（`tsc -b`）はマージの最低条件。

### Common Patterns
- API 呼び出しは `src/api/*.ts` のラッパ関数経由のみ。コンポーネントから直接 `fetch` しない。
- グローバル状態は Zustand（`src/stores/*`）、サーバ状態は TanStack Query。`useState` はローカル UI のみ。
- ストリーミングは `api/sse.ts` の `streamChatResponse` ＋ `hooks/useStreamChat.ts` で実装。
- Serendie の `<SerendieProvider>` を `app/providers.tsx` でラップし、`@serendie/ui` のコンポーネントを使う。

## Dependencies

### External
- React 18, react-router-dom 7, @tanstack/react-query 5, zustand 4
- @serendie/ui, @serendie/symbols（三菱電機 Serendie Design System）
- recharts（チャート）, html-to-image（出力ダウンロード）
- Vite 5, TypeScript 5.5, ESLint 9, Playwright 1.45

<!-- MANUAL: -->
