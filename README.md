# RAG Phantom (the-rag)

社内ナレッジ・マスタデータ・Oracle/CSV データを統合した日本語向け RAG（Retrieval-Augmented Generation）アプリケーション。

- **backend** — FastAPI + SQLAlchemy(SQLite) + Qdrant、LLM レイヤは AWS Bedrock（Claude Sonnet / Cohere Embed / Cohere Rerank）
- **frontend** — React 18 + TypeScript + Vite + Serendie UI
- **qdrant** — ハイブリッド検索（dense 1024次元 + sparse）用ベクトル DB

各ディレクトリの詳細は `AGENTS.md`（`backend/AGENTS.md`, `frontend/src/AGENTS.md` など）を参照。

---

## 別 PC での導入手順（Docker Compose）

最も簡単なのは Docker Compose です。Docker（24.x 以降）と Docker Compose v2 が入っていれば OK。

### 1. リポジトリを取得

```bash
git clone https://github.com/MasatoshiSano/the-rag.git
cd the-rag
```

### 2. 環境変数ファイルを用意

```bash
cp .env.example .env
```

`.env` を編集して最低限以下を設定する（`docker-compose.yml` がここから値を読み込む）:

| 変数 | 必須 | 説明 |
|------|------|------|
| `SECRET_KEY` | **必須** | ランダムな文字列。未設定 or `dev-secret-key-change-in-production` だとバックエンドは起動しない。`python -c "import secrets; print(secrets.token_urlsafe(48))"` で生成 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Bedrock を使うなら必須 | AWS 認証情報。STS 一時クレデンシャルを使う場合は `AWS_SESSION_TOKEN` も設定する |
| `AWS_DEFAULT_REGION` / `BEDROCK_REGION` | 任意 | 既定 `ap-northeast-1` |
| `BEDROCK_MODEL_ID` / `BEDROCK_EMBED_MODEL_ID` / `BEDROCK_RERANK_MODEL_ID` | 任意 | 利用する Bedrock モデル ID |
| `API_KEYS` | 任意 | `/api/external/*`（GitHub/Gitea 同期・同期チャット API）の `X-API-Key` 認証用。**JSON 配列形式**で指定（例: `API_KEYS=["my-secret-key"]`）。未設定なら外部 API は無効化される。`the-rag-default-key` を含めると起動しない |
| `ORACLE_*` | 任意 | Oracle 連携を使う場合のみ。使わないなら `ORACLE_ENABLED=false` |
| `GITEA_BASE_URL` / `GITEA_TOKEN` | 任意 | Gitea 同期を使う場合のみ |

> AWS 認証は `.env` に書く代わりに、ホストの `~/.aws/credentials` を使う方法でも構いません（その場合は `docker-compose.yml` の backend に `volumes: - ~/.aws:/root/.aws:ro` を追加し、`AWS_PROFILE` を環境変数で渡す）。

### 3. マスタデータの確認

製造拠点・ライン・工程のマスタは `backend/data/master/master-flat-with-place-aliases.md` に置く（リポジトリに同梱）。これが無いと起動時に警告が出ますが、マスタ依存機能が縮退するだけで API 自体は起動します。

### 4. 起動

```bash
docker compose up --build
```

| サービス | URL |
|----------|-----|
| フロントエンド | http://localhost:3000 |
| バックエンド API | http://localhost:8010 （ヘルスチェック: `GET http://localhost:8010/health` → `{"status":"ok"}`） |
| Qdrant | http://localhost:6333 |

`docker compose down` で停止。Qdrant のデータは名前付きボリューム `qdrant_data` に、SQLite/アップロードファイルは `./backend/data` / `./uploads` に永続化されます。

### 5. （任意）ローカルフォルダ連携

Windows/ネットワークフォルダを直接読む「フォルダソース」機能を使う場合、ホストの `/mnt`（WSL なら Windows ドライブ）が `docker-compose.yml` で `/host_drives:ro` としてマウントされます。別 PC でマウント元が違う場合は `docker-compose.yml` の `volumes` を環境に合わせて変更してください。

---

## ローカル開発（Docker を使わない場合）

### バックエンド

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Python 3.12
pip install -r requirements.txt
# 環境変数（最低限 SECRET_KEY、Bedrock を使うなら AWS 認証情報）をシェルに export しておく
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
# Qdrant は別途必要: docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant
uvicorn app.main:app --reload --port 8000
```

テスト（外部サービスはスタブ化されるので AWS/Qdrant 不要）:

```bash
cd backend && pytest
```

### フロントエンド

```bash
cd frontend
npm install                 # Node 20
npm run dev                 # http://localhost:5173 （/api は localhost:8000 へプロキシ）
npm run build               # 本番ビルド（tsc -b && vite build）
npm run typecheck           # tsc --noEmit
npm run lint                # eslint
npx playwright test         # E2E（docker compose up 済みが前提、baseURL=http://localhost:3000）
```

---

## トラブルシューティング

- **バックエンドが起動直後に落ちる / `RuntimeError: SECRET_KEY ...`** — `.env` の `SECRET_KEY` が未設定か弱い既定値のまま。ランダム値を設定する。
- **`docker compose up` が `SECRET_KEY must be set` で失敗する** — `.env` を作成し `SECRET_KEY` を設定する（`.env.example` をコピー）。
- **Bedrock 呼び出しが認証エラー** — `.env` の AWS 認証情報を確認。STS 一時クレデンシャルなら `AWS_SESSION_TOKEN` も必要。
- **`/api/external/*` が常に 403** — `API_KEYS`（JSON 配列）が未設定。利用する場合は `.env` に設定する。
- **マスタ関連のタグ付け/フィルタが効かない** — `backend/data/master/master-flat-with-place-aliases.md` の有無と内容を確認。
