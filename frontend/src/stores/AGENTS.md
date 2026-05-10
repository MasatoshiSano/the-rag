<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# stores

## Purpose
Zustand によるグローバルクライアント状態。サーバ状態は TanStack Query が担い、ここには「サーバから取らない情報」と「ストリーミング中の一時状態」を置く。

## Key Files
| File | Description |
|------|-------------|
| `chatStore.ts` | 現在のチャットメッセージ配列、ストリーミングステータス、エージェントステップ進捗 |
| `kbStore.ts` | 選択中の KB ID（`persist` で `localStorage` に保存） |
| `outputStore.ts` | 出力パネルの開閉状態と表示中の `OutputData`、対象メッセージ ID |
| `sourceStore.ts` | ソースパネルの開閉と表示中の `Source[]` / 選択中の `Source` |
| `uiStore.ts` | サイドバー開閉、モーダル開閉スタック、モーダルペイロード |
| `userStore.ts` | ユーザー ID（fingerprint）、`User` 設定オブジェクト、ローディング状態。`persist` 利用 |

## For AI Agents

### Working In This Directory
- `persist` ミドルウェアは `localStorage` を使う。キー名衝突を避けるため、ストア固有の `name` を必ず指定する（`kbStore` / `userStore` のパターンを踏襲）。
- ストア間の依存は避け、必要なら hooks 側で複数ストアを参照して合成する。
- `Set<ModalId>` のような不変でない構造を state に置くときは `new Set(prev)` で複製してから返すのが Zustand の慣習。

## Dependencies

### Internal
- `../types/*`

### External
- `zustand`, `zustand/middleware`

<!-- MANUAL: -->
