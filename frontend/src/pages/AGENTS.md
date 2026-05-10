<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# pages

## Purpose
ルートに対応するページコンポーネント。`app/router.tsx` で `/chat` `/upload` `/documents` `/settings` `/knowledge-bases` にマウントされる。

## Key Files
| File | Description |
|------|-------------|
| `ChatPage.tsx` | RAG チャット画面。`MessageList` + `ChatInput` + `SourcePanel` + `OutputPanel` を統合 |
| `UploadPage.tsx` | アップロード画面。DropZone / TextInput / GitHubSync / GiteaSync / LocalFolderSync をタブ切替 |
| `DocumentsPage.tsx` | ドキュメント管理画面。テーブル + 詳細 + ゴミ箱タブ |
| `SettingsPage.tsx` | ユーザー設定画面。プロフィール + 検索設定 |
| `KnowledgeBasesPage.tsx` | KB の一覧・作成・削除 |

## For AI Agents

### Working In This Directory
- ページコンポーネントは「ストアからデータを引く」+「子コンポーネントに props を渡す」の薄い層に保つ。ロジックは hooks / stores / components に押し出す。
- 新ページを追加したら `app/router.tsx` の `routes` 配列にも登録する（`/chat` のような子ルートは `AppShell` の children として）。

## Dependencies

### Internal
- `../components/*`
- `../stores/*`
- `../api/*`

### External
- `react-router-dom`, `@tanstack/react-query`

<!-- MANUAL: -->
