<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# components

## Purpose
機能ドメインごとに分割した再利用 UI コンポーネント。`@serendie/ui` のプリミティブをラップして本アプリ固有の表示要件を満たす。

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `chat/` | チャット画面のメッセージ表示・入力・評価系（`chat/AGENTS.md`） |
| `documents/` | ドキュメント一覧・詳細・ゴミ箱（`documents/AGENTS.md`） |
| `knowledge-base/` | KB のカード・作成/編集ダイアログ・削除確認（`knowledge-base/AGENTS.md`） |
| `layout/` | AppShell・Sidebar・Header・セッション検索（`layout/AGENTS.md`） |
| `output/` | データテーブル・チャート・ダウンロード・出力パネル（`output/AGENTS.md`） |
| `settings/` | プロフィール・検索設定（`settings/AGENTS.md`） |
| `shared/` | 横断的な共有コンポーネント置き場（現状 `index.ts` のみ） |
| `upload/` | アップロード関連（DropZone, GitHub/Gitea/LocalFolder Sync, TagEditor, TextInput, UploadProgress）（`upload/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 各サブディレクトリには `index.ts` があり、外部からの import は `from "../components/<feature>"` を使えるようになっている。新規コンポーネントは barrel に追加する。
- 機能境界（例: チャット系コンポーネントが KB のドメインを直接知らない）を尊重する。横断的に必要な汎用 UI は `shared/` に置く。

### Common Patterns
- ファイル名 = エクスポート名（PascalCase）。1 ファイル 1 デフォルトコンポーネント。
- スタイルは `@serendie/ui` のトークンとプロップス経由。CSS-in-JS や独自 CSS ファイルは原則使わない。

## Dependencies

### Internal
- `../api/*`, `../stores/*`, `../types/*`, `../hooks/*`

### External
- `@serendie/ui`, `@serendie/symbols`, `recharts`, `react-router-dom`

<!-- MANUAL: -->
