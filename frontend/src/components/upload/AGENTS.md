<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# upload

## Purpose
アップロード画面の各種入力方式コンポーネント。ローカルファイルのドロップ、テキスト直接入力、GitHub / Gitea リポジトリ同期、ローカルフォルダ（Windows パス → コンテナ内 `/host_drives`）連携、タグ編集、進捗表示を提供する。

## Key Files
| File | Description |
|------|-------------|
| `DropZone.tsx` | ドラッグ&ドロップ + 多重ファイル選択 |
| `TextInput.tsx` | テキスト直接入力からドキュメントを生成 |
| `GitHubSync.tsx` | GitHub リポジトリ同期 UI（URL/ブランチ/パス指定） |
| `GiteaSync.tsx` | Gitea リポジトリ同期 UI（GitHub と同等。レート制限回避用のセカンダリソース） |
| `LocalFolderSync.tsx` | Windows ローカルフォルダパスを KB に紐付ける（コンテナ側は `/host_drives/...` でマウント） |
| `TagEditor.tsx` | サイト/ライン/工程タグの確認・修正（マスタからオートコンプリート） |
| `UploadProgress.tsx` | 各ファイルの変換 → タグ付け → チャンク化 → インデックス進捗 |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- 単一アップロード上限 50MB、バッチ上限 20 ファイル / 200MB（`backend/app/infrastructure/config.py` の `MAX_*` 値と整合）。
- 許可拡張子は `md/txt/csv/json/pdf/pptx/xlsx/docx/png/jpeg/jpg/html`。バックエンドの `ALLOWED_EXTENSIONS` と同期させる。
- LocalFolderSync は Docker でホストの `/mnt → /host_drives:ro` がマウントされている前提。WSL/Linux のマウントパス変換ロジックは `backend/app/services/folder_scanner.py` 側にある。
- ステータスは backend の Document.status（14 種類超）と一対一でマッピング。

## Dependencies

### Internal
- `../../api/documents`
- `../../types/document`, `../../types/tag`

### External
- `@serendie/ui`

<!-- MANUAL: -->
