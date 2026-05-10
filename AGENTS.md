<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# the-rag (RAG Phantom)

## Purpose
社内ナレッジ・マスタデータ・Oracle DB を統合した日本語向け RAG（Retrieval-Augmented Generation）アプリケーション。FastAPI バックエンド + React/Vite フロントエンド + Qdrant ベクトル DB の 3 サービス構成で、AWS Bedrock（Claude Sonnet 4.5、Cohere Embed/Rerank）をモデルレイヤとして利用する。製造業の拠点・ライン・工程マスタを起点とした検索フィルタリングと、CSV/Oracle データ可視化が特徴。

## Key Files
| File | Description |
|------|-------------|
| `docker-compose.yml` | `frontend` (3000)・`backend` (8010)・`qdrant` (6333/6334) の 3 サービス定義。バックエンドは `/mnt:/host_drives:ro` でホストドライブを読み取り専用マウント |
| `.env.example` | 必要な環境変数のテンプレート（Bedrock / Oracle / Qdrant / SECRET_KEY） |
| `.env` / `.env.local` | 開発用シークレット（git 管理外） |
| `EntraID認証ガイド.md` | Microsoft Entra ID 認証連携の参考ドキュメント |
| `ragas_eval.py` | RAGAS による検索品質の自動評価スクリプト |
| `ragas_report.json` | 直近の RAGAS 評価結果 |
| `report.md` / `report_template.md` | 検証レポートの本体とテンプレート |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `backend/` | FastAPI + SQLAlchemy 非同期バックエンド（`backend/AGENTS.md`） |
| `frontend/` | React 18 + Vite + Serendie UI フロントエンド（`frontend/AGENTS.md`） |
| `docs/` | MQTT / API / 外部セットアップガイドの開発者向けドキュメント（`docs/AGENTS.md`） |
| `content/` | サンプル投入用の長文コンテンツ（`content/AGENTS.md`） |
| `maintenance/` | 設備保全マニュアル等のサンプル投入データ（`maintenance/AGENTS.md`） |
| `meeting_minutes/` | 議事録形式のサンプル投入データ（`meeting_minutes/AGENTS.md`） |
| `sample/` | STA_NO2 ガイドなどの製造ドキュメントサンプル（`sample/AGENTS.md`） |
| `test-folder/` | LocalFolderSync の動作確認用 PDF サンプル（`test-folder/AGENTS.md`） |
| `uploads/` | 実行時のアップロードファイル保管領域（生成物のためドキュメント対象外） |

## For AI Agents

### Working In This Directory
- 3 サービスは `docker compose up` で起動する。Backend は `host:8010 → container:8000`、Frontend は `host:3000 → container:80` にマップ。
- 開発時にフロントエンドのみ動かす場合は `frontend/` で `npm run dev`（Vite が `localhost:8000` の API へプロキシ）。
- Bedrock を使うため AWS 認証情報が必須。`.env` / `.env.local` に `AWS_ACCESS_KEY_ID` 等を設定するか、ホストの `~/.aws/credentials` を Docker に渡す。
- マスター MD（`backend/data/master/master-flat-with-place-aliases.md`）が読めないと起動時警告が出るが、API 自体は起動する（マスタ依存機能のみ縮退）。
- Backend のヘルスチェックは `GET /health` → `{"status": "ok"}`。

### Testing Requirements
- Backend: `cd backend && pytest`（インメモリ SQLite + Bedrock/Qdrant スタブで完結。実 AWS 不要）。
- Frontend ユニット系テストは未整備。E2E は Playwright で `cd frontend && npx playwright test`（`docker compose up` 済み前提、`baseURL=http://localhost:3000`）。
- RAGAS 評価は `python ragas_eval.py` で `ragas_report.json` を更新する（実 Bedrock 接続が必要）。

### Common Patterns
- Python は async/await + SQLAlchemy 2.0 マッピングスタイル。datetime は ISO 8601 文字列（TEXT 型）として SQLite に格納。
- フロントエンドの API 呼び出しは `/the-rag/api/*` の URL プレフィックスを介す（Vite 開発サーバ・Nginx 共通）。
- ユーザー識別は `localStorage` の UUID を `X-User-Id` ヘッダーで送信する匿名認証方式。

## Dependencies

### External
- AWS Bedrock — Claude Sonnet 4.5（生成）、Cohere Embed Multilingual v3（埋め込み）、Cohere Rerank v3.5（再ランク）
- Qdrant — ハイブリッド検索（dense 1024 次元 + sparse）対応のベクトル DB
- Oracle DB（任意）— 構造化データ参照用、`ORACLE_ENABLED=false` で無効化可能
- Gitea / GitHub — リポジトリ同期ソース（`backend/app/routers/external.py`）

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
