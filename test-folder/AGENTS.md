<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# test-folder

## Purpose
LocalFolderSync 機能（`backend/app/services/folder_scanner.py`）の動作確認用 PDF サンプル。Windows ローカルフォルダ → コンテナ `/host_drives` マウントの一連の経路を再現できる。

## Key Files
| File | Description |
|------|-------------|
| `MD-2096*.pdf` 等 | xEV-MC ステータ ASSY ライン関連の検証 PDF（半角カナ含むファイル名のテストにもなる） |

## For AI Agents

### Working In This Directory
- ファイル名に半角カナ・濁点・括弧が含まれているため、URL エンコード／HTTP マルチパートでのファイル名処理のリグレッション検出に有効。
- LocalFolderSync テストで使う場合は、Windows パス（例: `C:\path\to\test-folder`）をフロントから入力 → `folder_scanner` が `/host_drives/...` に変換 → スキャンする流れを通す。

## Dependencies

### Internal
- `backend/app/services/folder_scanner.py`（読み取り側）

<!-- MANUAL: -->
