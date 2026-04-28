# The RAG - 外部アプリ連携セットアップガイド

The RAG の API を外部アプリケーションから利用するための設定手順です。

---

## 前提条件

- The RAG が Docker で起動済み（`docker compose up -d`）
- 外部アプリから The RAG ホストにネットワーク到達可能

---

## Step 1: API キーを設定する

デフォルトの API キー（`rag-phantom-default-key`）を本番用に変更します。

**`docker-compose.yml`** の `backend > environment` に追加:

```yaml
backend:
  environment:
    # ... 既存の設定 ...
    - API_KEYS=["your-secure-api-key-here"]
```

> 複数キーを発行する場合: `["key-for-app-a","key-for-app-b"]`

設定後、コンテナを再起動します。

```bash
docker compose restart backend
```

---

## Step 2: CORS を設定する

外部アプリがブラウザから直接 API を呼ぶ場合（JavaScript fetch 等）、CORS の許可が必要です。

**`docker-compose.yml`** の `backend > environment` に追加:

```yaml
backend:
  environment:
    # ... 既存の設定 ...
    - ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173","https://your-app.example.com"]
```

設定後、コンテナを再起動します。

```bash
docker compose restart backend
```

> サーバーサイドから API を呼ぶ場合（Python requests, Node.js fetch 等）は CORS 設定不要です。

---

## Step 3: ネットワークアクセスを確認する

外部アプリから The RAG のエンドポイントに到達できることを確認します。

```bash
curl -k https://<The RAGホストIP>:3443/health
# → {"status":"ok"} が返れば OK
```

**到達できない場合のチェックリスト**:

| 確認項目 | コマンド |
|---------|---------|
| Docker ポート公開 | `docker compose ps` で `0.0.0.0:3443->443` を確認 |
| Windows Firewall | 受信ルールでポート 3443 が許可されているか |
| WSL2 ポート転送 | `netsh interface portproxy show v4tov4` で確認 |

---

## Step 4: ナレッジベース ID を取得する

API で使用するナレッジベース ID を確認します。

```bash
curl -k https://<host>:3443/api/knowledge-bases/ \
  -H "X-User-Id: external-app-user"
```

レスポンスの `id` フィールドが、チャット API で指定する `knowledge_base_id` です。

---

## Step 5: 外部アプリに組み込む

### Python

```python
import requests

THE_RAG_URL = "https://10.168.124.32:3443"
API_KEY = "your-secure-api-key-here"
KB_ID = "取得したナレッジベースID"


def ask(question: str, session_id: str | None = None) -> dict:
    resp = requests.post(
        f"{THE_RAG_URL}/api/ext/chat/sync",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "question": question,
            "knowledge_base_id": KB_ID,
            "session_id": session_id,
        },
        verify=False,
    )
    resp.raise_for_status()
    return resp.json()


# 単発の質問
result = ask("設備Aの点検手順を教えて")
print(result["answer"])

# 会話の継続
follow_up = ask("もっと詳しく", session_id=result["session_id"])
print(follow_up["answer"])
```

### JavaScript / TypeScript

```typescript
const THE_RAG_URL = "https://10.168.124.32:3443";
const API_KEY = "your-secure-api-key-here";
const KB_ID = "取得したナレッジベースID";

async function ask(question: string, sessionId?: string) {
  const resp = await fetch(`${THE_RAG_URL}/api/ext/chat/sync`, {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      knowledge_base_id: KB_ID,
      session_id: sessionId ?? null,
    }),
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

// 使用例
const result = await ask("設備Aの点検手順を教えて");
console.log(result.answer);
console.log(result.sources);
```

### cURL

```bash
curl -k -X POST https://10.168.124.32:3443/api/ext/chat/sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secure-api-key-here" \
  -d '{"question":"設備Aの点検手順を教えて","knowledge_base_id":"KB_ID"}'
```

---

## レスポンス例

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

---

## エラー時の対応

| ステータス | 原因 | 対処 |
|-----------|------|------|
| 401 | `X-API-Key` ヘッダーがない | ヘッダーを追加する |
| 403 | API キーが間違っている | `docker-compose.yml` の `API_KEYS` と一致させる |
| 404 | `session_id` が存在しない | `session_id` を `null` にして新規セッションで再送 |
| 422 | リクエスト形式が不正 | `question` と `knowledge_base_id` が必須 |
| 502 | LLM（AWS Bedrock）が応答しない | バックエンドのログを確認する |

---

## 補足: ドキュメントを外部アプリから管理する場合

ドキュメントのアップロード・削除も API 経由で可能です。
詳細は [API ガイド](./api-guide.md) を参照してください。

```bash
# アップロード
curl -k -X POST "https://<host>:3443/api/documents/upload?knowledge_base_id=KB_ID" \
  -H "X-User-Id: external-app-user" \
  -F "files=@manual.pdf"

# 一覧確認
curl -k "https://<host>:3443/api/documents/?knowledge_base_id=KB_ID" \
  -H "X-User-Id: external-app-user"

# 削除
curl -k -X DELETE "https://<host>:3443/api/documents/DOC_ID" \
  -H "X-User-Id: external-app-user"
```
