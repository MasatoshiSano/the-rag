<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# types

## Purpose
バックエンド API レスポンスと整合する TypeScript 型定義。基本的に各ファイルが 1 つのドメインを担う。

## Key Files
| File | Description |
|------|-------------|
| `document.ts` | `Document`, `DocumentTag`, ステータスユニオン、変換済み MD などの型 |
| `knowledge-base.ts` | `KnowledgeBase`, `CreateKBRequest`, お気に入り型 |
| `master.ts` | `SiteMaster`, `LineMaster`, `ProcessMaster` |
| `message.ts` | `Message`, `Source`, `StreamingStatus` などチャット関連 |
| `output.ts` | `OutputData`, テーブル/チャート設定、`chart_config` JSON 形式 |
| `session.ts` | `Session`, `SessionSearchResult`（FTS5 検索結果）|
| `tag.ts` | サイト/ライン/工程タグの編集状態 |
| `user.ts` | `User`, `UserBehavior`, `UserMemoryItem`, `ProfileItem` |

## For AI Agents

### Working In This Directory
- バックエンド `app/models/database.py` のフィールド変更時は対応するこのディレクトリのファイルも更新する。`api/*.ts` のリクエスト型もあわせて確認。
- `Document.status` のような列挙は文字列リテラルユニオン (`"processing" | "converting" | ...`) で表現するのが慣習。新しい状態を追加するときは backend のコメント（`app/models/database.py` の Document.status コメント）と同期する。
- 日付は `string`（ISO 8601）で受け取る。`Date` への変換が必要な箇所のみコンポーネント側で行う。

## Dependencies

### Internal
- 他のソースから一方的に参照される（依存先なし）

<!-- MANUAL: -->
