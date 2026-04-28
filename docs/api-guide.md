# The RAG - 外部連携 API ガイド

The RAG の RAG エンジンを外部アプリケーションから利用するためのガイドです。

---

## 目次

1. [概要](#概要)
2. [認証](#認証)
3. [チャット API（同期版）](#チャット-api同期版)
4. [ナレッジベース管理](#ナレッジベース管理)
5. [ドキュメント管理](#ドキュメント管理)
6. [セッション・履歴管理](#セッション履歴管理)
7. [マスターデータ](#マスターデータ)
8. [エラーハンドリング](#エラーハンドリング)
9. [利用シナリオ例](#利用シナリオ例)

---

## 概要

The RAG は2種類の認証方式で API を公開しています。

| 方式 | ヘッダー | 用途 |
|------|---------|------|
| API キー認証 | `X-API-Key` | 外部アプリ連携（同期チャット） |
| ユーザー ID 認証 | `X-User-Id` | ドキュメント・ナレッジベース管理 |

**ベース URL**: `https://<host>:3443/api`

**Swagger UI**: `https://<host>:3443/docs`

---

## 認証

### API キー認証（外部チャット API 用）

同期チャットエンドポイント (`/api/ext/chat/sync`) は API キーで認証します。

```
X-API-Key: rag-phantom-default-key
```

> **本番環境**: 環境変数 `API_KEYS` でカンマ区切りで設定してください。

### ユーザー ID 認証（管理 API 用）

ドキュメント・ナレッジベース等の管理 API は `X-User-Id` ヘッダーで認証します。
UUID を生成して固定で使用してください。

```
X-User-Id: your-app-user-id-here
```

---

## チャット API（同期版）

外部アプリから質問を送り、回答を JSON で受け取ります。

### `POST /api/ext/chat/sync`

**認証**: `X-API-Key` ヘッダー必須

#### リクエスト

```json
{
  "question": "設備Aの点検手順を教えてください",
  "knowledge_base_id": "kb-uuid-here",
  "user_id": "external-app-user-001",
  "session_id": null,
  "response_mode": "simple"
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `question` | string | Yes | 質問テキスト（1〜4000文字） |
| `knowledge_base_id` | string | Yes | 検索対象のナレッジベース ID |
| `user_id` | string | No | ユーザー ID（デフォルト: `external-api-user`） |
| `session_id` | string | No | 既存セッション ID。`null` で新規作成 |
| `response_mode` | string | No | `"simple"` または `"detailed"`（デフォルト: `simple`） |

#### レスポンス（200 OK）

```json
{
  "answer": "設備Aの点検手順は以下の通りです。\n1. 電源を切る\n2. ...",
  "sources": [
    {
      "document_id": "doc-uuid",
      "document_name": "設備A_点検マニュアル.pdf",
      "section_title": "第3章 定期点検",
      "score": 0.892,
      "snippet": "点検手順として、まず電源を切り..."
    }
  ],
  "session_id": "session-uuid",
  "message_id": "msg-uuid"
}
```

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `answer` | string | RAG による回答テキスト |
| `sources` | array | 参照元ドキュメントのリスト |
| `session_id` | string | セッション ID（会話継続に使用） |
| `message_id` | string | メッセージ ID（評価に使用可能） |

#### cURL 例

```bash
curl -X POST https://localhost:3443/api/ext/chat/sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rag-phantom-default-key" \
  -d '{
    "question": "設備Aの点検手順は？",
    "knowledge_base_id": "your-kb-id"
  }'
```

#### Python 例

```python
import requests

response = requests.post(
    "https://localhost:3443/api/ext/chat/sync",
    headers={"X-API-Key": "rag-phantom-default-key"},
    json={
        "question": "設備Aの点検手順は？",
        "knowledge_base_id": "your-kb-id",
    },
    verify=False,  # 自己署名証明書の場合
)
data = response.json()
print(data["answer"])
for src in data["sources"]:
    print(f"  - {src['document_name']} (score: {src['score']})")
```

#### エラーレスポンス

| ステータス | 説明 |
|-----------|------|
| 401 | `X-API-Key` ヘッダーがない |
| 403 | API キーが無効 |
| 404 | 指定された `session_id` が存在しない |
| 422 | リクエストバリデーションエラー |
| 502 | LLM 生成に失敗 |

---

## ナレッジベース管理

ドキュメントをグループ化するナレッジベースの CRUD です。

### `POST /api/knowledge-bases/` — ナレッジベース作成

```bash
curl -X POST https://localhost:3443/api/knowledge-bases/ \
  -H "Content-Type: application/json" \
  -H "X-User-Id: your-user-id" \
  -d '{"name": "設備マニュアル", "description": "工場設備の点検・保守マニュアル"}'
```

**レスポンス（201）**:
```json
{
  "id": "kb-uuid",
  "name": "設備マニュアル",
  "description": "工場設備の点検・保守マニュアル",
  "color": "#6366f1",
  "document_count": 0,
  "is_favorite": false,
  "created_at": "2025-03-25T10:00:00+00:00"
}
```

### `GET /api/knowledge-bases/` — 一覧取得

```bash
curl https://localhost:3443/api/knowledge-bases/ \
  -H "X-User-Id: your-user-id"
```

### `PUT /api/knowledge-bases/{id}` — 更新

```bash
curl -X PUT https://localhost:3443/api/knowledge-bases/{id} \
  -H "Content-Type: application/json" \
  -H "X-User-Id: your-user-id" \
  -d '{"name": "新しい名前"}'
```

### `DELETE /api/knowledge-bases/{id}` — 削除（カスケード）

ナレッジベース配下のドキュメント・ベクトルデータもすべて削除されます。

```bash
curl -X DELETE https://localhost:3443/api/knowledge-bases/{id} \
  -H "X-User-Id: your-user-id"
```

---

## ドキュメント管理

### `POST /api/documents/upload` — ドキュメントアップロード

ファイルをアップロードすると、自動でベクトル化・インデックスされます。

```bash
curl -X POST "https://localhost:3443/api/documents/upload?knowledge_base_id=kb-uuid" \
  -H "X-User-Id: your-user-id" \
  -F "files=@manual.pdf" \
  -F "files=@guide.docx"
```

**対応フォーマット**: `md`, `txt`, `csv`, `json`, `pdf`, `pptx`, `xlsx`, `docx`, `png`, `jpeg`, `jpg`, `html`

**制限**:
- 1ファイル最大 50MB
- 1回最大 20ファイル
- 合計最大 200MB
- ZIP ファイルは自動展開

**レスポンス（201）**:
```json
{
  "documents": [
    {
      "id": "doc-uuid",
      "filename": "manual.pdf",
      "file_type": "pdf",
      "status": "processing",
      "version": 1,
      "tags": []
    }
  ],
  "message": "2 files uploaded successfully"
}
```

### ドキュメント処理ステータス

アップロード後、バックグラウンドで以下のパイプラインが実行されます。

```
processing → converting → converted → tagging → tagged → chunking → chunked → indexing → indexed
```

`indexed` になると RAG チャットで検索可能になります。

### `GET /api/documents/` — ドキュメント一覧

```bash
curl "https://localhost:3443/api/documents/?knowledge_base_id=kb-uuid&limit=20&offset=0" \
  -H "X-User-Id: your-user-id"
```

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `knowledge_base_id` | string | 必須。対象 KB の ID |
| `limit` | int | 取得件数（1〜100、デフォルト: 20） |
| `offset` | int | オフセット（デフォルト: 0） |
| `status` | string | ステータスでフィルタ |
| `tag` | string | タグでフィルタ |

**レスポンス**:
```json
{
  "documents": [...],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### `GET /api/documents/{id}` — ドキュメント詳細

変換済み Markdown を含む詳細情報を返します。

```bash
curl https://localhost:3443/api/documents/{id} \
  -H "X-User-Id: your-user-id"
```

### `GET /api/documents/{id}/download` — ファイルダウンロード

元のアップロードファイルをダウンロードします。

```bash
curl -OJ https://localhost:3443/api/documents/{id}/download \
  -H "X-User-Id: your-user-id"
```

### `PATCH /api/documents/{id}/tags` — タグ更新

```bash
curl -X PATCH https://localhost:3443/api/documents/{id}/tags \
  -H "Content-Type: application/json" \
  -H "X-User-Id: your-user-id" \
  -d '{
    "tags": [
      {"tag_key": "設備", "tag_value": "設備A", "confirmed": true},
      {"tag_key": "種類", "tag_value": "点検マニュアル", "confirmed": true}
    ]
  }'
```

### `POST /api/documents/{id}/reindex` — 再インデックス

ベクトルデータを再作成します。

```bash
curl -X POST https://localhost:3443/api/documents/{id}/reindex \
  -H "X-User-Id: your-user-id"
```

### `DELETE /api/documents/{id}` — 論理削除

```bash
curl -X DELETE https://localhost:3443/api/documents/{id} \
  -H "X-User-Id: your-user-id"
```

### `POST /api/documents/{id}/restore` — 論理削除の復元

```bash
curl -X POST https://localhost:3443/api/documents/{id}/restore \
  -H "X-User-Id: your-user-id"
```

### `DELETE /api/documents/{id}/permanent` — 完全削除

ファイル・ベクトルデータ・DB レコードをすべて削除します。**復元不可**。

```bash
curl -X DELETE https://localhost:3443/api/documents/{id}/permanent \
  -H "X-User-Id: your-user-id"
```

---

## セッション・履歴管理

### `GET /api/chat/sessions` — セッション一覧

```bash
curl "https://localhost:3443/api/chat/sessions?limit=20&offset=0" \
  -H "X-User-Id: your-user-id"
```

**レスポンス**:
```json
{
  "sessions": [
    {
      "id": "session-uuid",
      "title": "設備Aの点検について",
      "knowledge_base_id": "kb-uuid",
      "message_count": 4,
      "last_message_preview": "点検手順は以下の...",
      "updated_at": "2025-03-25T12:00:00+00:00"
    }
  ],
  "total": 15
}
```

### `GET /api/chat/sessions/{session_id}` — セッション詳細（全メッセージ）

```bash
curl https://localhost:3443/api/chat/sessions/{session_id} \
  -H "X-User-Id: your-user-id"
```

### `DELETE /api/chat/sessions/{session_id}` — セッション削除

```bash
curl -X DELETE https://localhost:3443/api/chat/sessions/{session_id} \
  -H "X-User-Id: your-user-id"
```

### `GET /api/chat/sessions/search` — セッション全文検索

```bash
curl "https://localhost:3443/api/chat/sessions/search?q=点検手順" \
  -H "X-User-Id: your-user-id"
```

### `PUT /api/chat/messages/{message_id}/rating` — 回答評価

```bash
curl -X PUT https://localhost:3443/api/chat/messages/{message_id}/rating \
  -H "Content-Type: application/json" \
  -d '{"rating": 5}'
```

---

## マスターデータ

認証不要で参照できるマスターデータです。

| エンドポイント | 説明 | フィルタ |
|--------------|------|---------|
| `GET /api/master/sites` | 拠点一覧 | — |
| `GET /api/master/lines?site_code=XX` | ライン一覧 | `site_code` |
| `GET /api/master/processes?line_code=XX` | 工程一覧 | `line_code` |
| `GET /api/master/search?q=キーワード` | マスター横断検索 | `q`（必須） |

---

## エラーハンドリング

すべてのエラーは以下の形式で返されます。

```json
{
  "detail": "エラーメッセージ"
}
```

### 共通ステータスコード

| コード | 意味 |
|-------|------|
| 200 | 成功（GET / PUT） |
| 201 | 作成成功（POST） |
| 202 | 受理（非同期処理開始） |
| 204 | 成功（DELETE、レスポンスボディなし） |
| 400 | リクエスト不正（バリデーション、状態エラー） |
| 401 | 認証ヘッダーなし |
| 403 | 認証失敗またはアクセス権限なし |
| 404 | リソースが見つからない |
| 409 | 競合（重複データ） |
| 422 | バリデーションエラー（Pydantic） |
| 502 | バックエンド処理エラー（LLM 障害等） |

---

## 利用シナリオ例

### シナリオ1: 外部アプリから質問応答

```
1. GET  /api/knowledge-bases/           → KB ID を取得
2. POST /api/ext/chat/sync              → 質問を送信、回答を受信
3. POST /api/ext/chat/sync (session_id) → 同じセッションで追加質問
```

### シナリオ2: 外部アプリからドキュメント管理

```
1. POST   /api/knowledge-bases/                     → KB 作成
2. POST   /api/documents/upload?knowledge_base_id=X → ファイルアップロード
3. GET    /api/documents/?knowledge_base_id=X       → ステータス確認（indexed になるまでポーリング）
4. PATCH  /api/documents/{id}/tags                  → タグ設定
5. POST   /api/ext/chat/sync                        → 質問開始
```

### シナリオ3: ドキュメント更新フロー

```
1. POST   /api/documents/upload  → 同名ファイルを再アップロード（自動バージョニング）
2. GET    /api/documents/{id}    → ステータス確認
3. DELETE /api/documents/{id}    → 旧版を論理削除（必要に応じて）
```
