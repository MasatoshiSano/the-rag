<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# api

## Purpose
バックエンド REST API および SSE のクライアント層。ベース URL は `/the-rag/api`、ユーザー識別は `localStorage` の UUID を `X-User-Id` ヘッダーで自動付与する。

## Key Files
| File | Description |
|------|-------------|
| `client.ts` | `apiClient`（GET/POST/PUT/DELETE/PATCH）と `ApiError` の基底クライアント。`X-User-Id` 自動注入と JSON エンコード/デコード |
| `chat.ts` | チャットメッセージ送信、メッセージ評価、セッション関連 |
| `documents.ts` | アップロード（単発/バッチ）、一覧、タグ確認、再インデックス、ソフトデリート、復元 |
| `knowledge-bases.ts` | KB の CRUD とお気に入り |
| `master.ts` | サイト・ライン・工程マスタ参照（一部 TODO） |
| `output.ts` | 構造化出力データ取得、CSV ダウンロード |
| `sessions.ts` | セッション一覧・詳細・削除・FTS5 検索 |
| `sse.ts` | `streamChatResponse` — fetch + ReadableStream で SSE を消費。`SseEvent` 型で `status/token/complete/error/session/agentic_step` を識別 |
| `users.ts` | `/users/me` 設定・行動プロファイル・メモリ |

## For AI Agents

### Working In This Directory
- 全関数は `apiClient.<method>(...)` 経由（`sse.ts` を除く）。直接 `fetch` を呼ばない。
- `sse.ts` は `EventSource` を使わず（POST + body を送るため）`fetch` + `ReadableStream` の手書き実装。バックエンドが返す各イベント種別と一対一の `Sse*Event` インターフェースを維持する。
- `API_BASE_URL` は `client.ts` と `sse.ts` で 2 箇所に定数定義されている。変更時は両方更新する。
- ユーザー ID は `localStorage.getItem("the-rag-user-id")`。`utils/fingerprint.ts:getOrCreateFingerprint` と同じキーを参照している。

### Common Patterns
- リクエスト/レスポンス型を `interface` で定義し、エクスポートしてストアやコンポーネントから再利用する。
- 失敗時は `ApiError`（status + message）を throw し、TanStack Query の `error` で受ける。

## Dependencies

### Internal
- `../types/*` — レスポンス型

### External
- ブラウザの `fetch` のみ（追加 HTTP ライブラリ不使用）

<!-- MANUAL: -->
