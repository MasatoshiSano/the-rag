<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# documents

## Purpose
ドキュメント管理画面のテーブル・詳細・ゴミ箱コンポーネント。バックエンドの `/api/documents` 系エンドポイントと一対一で対応。

## Key Files
| File | Description |
|------|-------------|
| `DocumentTable.tsx` | ドキュメント一覧テーブル。ステータスバッジ、タグ、操作（再インデックス/削除）を表示 |
| `DocumentDetail.tsx` | 1 ドキュメントの詳細パネル（変換済み MD・タグ確認・バージョン履歴） |
| `TrashList.tsx` | ソフトデリート済みドキュメントの一覧と復元/完全削除操作 |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- ステータスは 14 種類超（`processing/converting/converted/tagging/.../indexed/cancelled` 等）。バッジの色マップは UI 側で集中管理する。
- 再インデックス（`POST /api/documents/{id}/reindex`）は status を `processing` に戻す副作用がある。連打防止のため操作中はボタンを `disabled` に。
- ソフトデリート保持期間は 30 日（`SOFT_DELETE_RETENTION_DAYS`）。`TrashList` の表示にはバックエンドの `deleted_at` を使う。

## Dependencies

### Internal
- `../../api/documents`
- `../../types/document`

### External
- `@serendie/ui`

<!-- MANUAL: -->
