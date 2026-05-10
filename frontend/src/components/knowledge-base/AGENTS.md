<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# knowledge-base

## Purpose
ナレッジベース（KB）の一覧表示カードと、作成/編集/削除のダイアログ。

## Key Files
| File | Description |
|------|-------------|
| `KnowledgeBaseCard.tsx` | 一覧用のカード（名前・色・ドキュメント数・お気に入り） |
| `KBFormDialog.tsx` | 作成・編集の共通ダイアログ |
| `DeleteKBDialog.tsx` | 削除確認ダイアログ（カスケード削除の警告を表示） |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- 削除はバックエンドで SQLite カスケード + Qdrant ベクトル削除の両方を行う破壊的操作。確認ダイアログを必ず通す。
- 選択中 KB は `useKbStore`（persist 付き）で `localStorage` に永続化される。

## Dependencies

### Internal
- `../../api/knowledge-bases`
- `../../stores/kbStore`
- `../../types/knowledge-base`

### External
- `@serendie/ui`

<!-- MANUAL: -->
