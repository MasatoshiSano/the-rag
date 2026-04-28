---
title: "社内GiteaリポジトリをRAGナレッジベースに同期する — FastAPI + Gitea API構成"
emoji: "🔄"
type: "tech"
topics: ["Gitea", "RAG", "FastAPI", "Python", "Git"]
published: true
category: "Architecture"
date: "2026-04-28"
description: "社内GiteaリポジトリのMarkdownファイルをRAGナレッジベースに自動同期する仕組みを、バイト比較による差分検出とバックグラウンドインデックス処理の設計を含めて解説"
---

# 社内GiteaリポジトリをRAGナレッジベースに同期する

ドキュメント管理の現実的な課題：**ナレッジは複数の場所に分散している**。社内Wiki、GitHub、Gitea、Confluence...どこを見れば正しい情報があるのか、チーム全体で把握しきれないことが多いです。

RAG（Retrieval-Augmented Generation）を導入して、これらの分散ナレッジをひとつのナレッジベースに統合し、LLMが会話形式で検索・要約できる環境を構築できます。本記事では、**FastAPI + Gitea APIを組み合わせた自動同期パイプライン**の実装パターンを解説します。

## なぜGiteaリポジトリの同期が必要か

### 現状の問題

1. **手動アップロードの手間**: ドキュメント更新のたびに、人が手動でRAGに登録するはめに
2. **バージョン管理の分断**: Git履歴はGiteaにある。RAGにはいつ時点の情報か不明
3. **同期漏れ**: 「このファイル、同期済みだと思ってた」という人的ミス

### 自動同期の利点

- **Git as SSOT（Single Source of Truth）**: Giteaをドキュメントの唯一の正式版として機能
- **差分検出による効率化**: 変更なしファイルは再インデックスしない
- **バックグラウンド処理**: UI ブロッキングなし、ユーザー体験を損なわない

## Gitea API の基礎

### ツリー取得（ファイル一覧）

```
GET /api/v1/repos/{owner}/{repo}/git/trees/{branch}?recursive=true
```

レスポンス例：
```json
{
  "sha": "abc123...",
  "url": "...",
  "tree": [
    {
      "path": "docs/guide.md",
      "mode": "100644",
      "type": "blob",
      "size": 2048,
      "sha": "xyz789..."
    },
    {
      "path": "docs/",
      "mode": "040000",
      "type": "tree",
      "sha": "..."
    }
  ],
  "truncated": false
}
```

**重要**: `recursive=true` を指定すると、ネストされたフォルダも一度に取得できます。

### ファイル取得（内容の読み込み）

```
GET /api/v1/repos/{owner}/{repo}/raw/{path}?ref={branch}
```

このエンドポイントは生のファイル内容をバイナリで返します。

## URL パーサーの実装

Gitea の Web UI でコピーしたツリーURLをそのままパースできる関数が必須です。

```python
def _parse_gitea_url(url: str) -> tuple[str, str, str, str]:
    """
    Gitea URLをパース：
    - https://gitea.example.com/owner/repo/src/branch/main/docs
    - https://gitea.example.com/owner/repo
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = f"{parsed.scheme}://{parsed.netloc}"
    path_parts = parsed.path.strip('/').split('/')

    if len(path_parts) < 2:
        raise ValueError("Invalid Gitea URL format")

    owner, repo = path_parts[0], path_parts[1]

    # /src/branch/{branch}/{path} パターン
    branch = "main"  # デフォルト
    path = ""

    if len(path_parts) > 2 and path_parts[2] == "src":
        if len(path_parts) > 4 and path_parts[3] == "branch":
            branch = path_parts[4]
            path = '/'.join(path_parts[5:]) if len(path_parts) > 5 else ""

    return host, owner, repo, branch, path
```

**使用例**:
```python
host, owner, repo, branch, path = _parse_gitea_url(
    "https://gitea.internal.co.jp/team/knowledge/src/branch/main/docs"
)
# host = "https://gitea.internal.co.jp"
# owner = "team"
# repo = "knowledge"
# branch = "main"
# path = "docs"
```

## バイト比較による差分検出

ファイルの内容が変更されているかを確認するもっとも確実な方法は、**バイト単位の比較**です。エンコーディング問題を避けるため、テキストではなくバイナリレベルで比較します。

```python
async def _sync_gitea_repo(
    kb_id: int,
    gitea_url: str,
    owner: str,
    repo: str,
    branch: str = "main",
    path_filter: str = "",
    db_session: AsyncSession = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Gitea リポジトリをナレッジベースに同期
    """
    import aiohttp

    gitea_base = gitea_url.rstrip('/')
    token = os.getenv("GITEA_TOKEN")
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"

    # 1. ツリー取得
    tree_url = (
        f"{gitea_base}/api/v1/repos/{owner}/{repo}/git/trees/{branch}"
        "?recursive=true"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(tree_url, headers=headers) as tree_resp:
            if tree_resp.status != 200:
                raise HTTPException(status_code=400, detail="Gitea tree fetch failed")
            tree_data = await tree_resp.json()

    # 2. 同期対象ファイルをフィルタ
    file_blobs = [
        item for item in tree_data.get("tree", [])
        if item["type"] == "blob" and (
            item["path"].endswith(".md") or
            item["path"].endswith(".markdown") or
            item["path"].endswith(".txt")
        )
    ]

    if path_filter:
        file_blobs = [f for f in file_blobs if f["path"].startswith(path_filter)]

    # 3. 既存ドキュメントを取得
    existing_docs = await db_session.execute(
        select(Document).where(
            Document.kb_id == kb_id,
            Document.source_id.startswith("gitea:"),
        )
    )
    existing_map = {
        doc.source_id: doc for doc in existing_docs.scalars()
    }

    # 4. ファイルごとにダウンロード＆差分検出
    documents_to_index = []

    async with aiohttp.ClientSession() as session:
        for blob in file_blobs:
            file_path = blob["path"]
            source_id = f"gitea:{owner}/{repo}/{branch}/{file_path}"

            file_url = (
                f"{gitea_base}/api/v1/repos/{owner}/{repo}/raw/{file_path}"
                f"?ref={branch}"
            )

            async with session.get(file_url, headers=headers) as file_resp:
                if file_resp.status != 200:
                    continue

                file_content = await file_resp.read()

            # 5. バイト比較で差分検出
            prev_doc = existing_map.get(source_id)
            if prev_doc and prev_doc.status == "indexed":
                # 前回キャッシュがあれば比較
                prev_path = _get_document_cache_path(prev_doc.id)
                if prev_path.exists():
                    with open(prev_path, "rb") as pf:
                        prev_content = pf.read()

                    if prev_content == file_content:
                        # 変更なし — スキップ
                        logger.debug(f"Skipping unchanged: {file_path}")
                        continue

            # 6. 新規または更新ドキュメント
            text_content = file_content.decode('utf-8', errors='replace')

            doc = Document(
                kb_id=kb_id,
                name=file_path,
                source_type="gitea",
                source_id=source_id,
                content=text_content,
                status="pending",
                retry_count=0,
            )

            db_session.add(doc)
            documents_to_index.append(doc)

    # 7. DB コミット
    await db_session.commit()

    # 8. バックグラウンドでインデックス処理
    if background_tasks and documents_to_index:
        background_tasks.add_task(
            _index_documents_background,
            [doc.id for doc in documents_to_index],
        )

    # 9. 同期履歴を記録
    gitea_source = (await db_session.execute(
        select(GiteaSource).where(
            GiteaSource.kb_id == kb_id,
            GiteaSource.owner == owner,
            GiteaSource.repo == repo,
        )
    )).scalar_one_or_none()

    if gitea_source:
        gitea_source.last_synced_at = datetime.utcnow()
        gitea_source.file_count = len(documents_to_index)
    else:
        gitea_source = GiteaSource(
            kb_id=kb_id,
            gitea_url=gitea_base,
            owner=owner,
            repo=repo,
            branch=branch,
            last_synced_at=datetime.utcnow(),
            file_count=len(documents_to_index),
        )
        db_session.add(gitea_source)

    await db_session.commit()

    return {
        "synced_files": len(documents_to_index),
        "total_files": len(file_blobs),
    }
```

## バックグラウンドインデックス処理

FastAPI の `BackgroundTasks` を使い、ドキュメント登録後に非同期でベクトル化・インデックス処理を行います。UI のレスポンスを遅延させません。

```python
async def _index_documents_background(document_ids: list[int]):
    """
    バックグラウンドでドキュメントをQdrantにインデックス
    """
    async with get_async_session_factory()() as db_session:
        for doc_id in document_ids:
            doc = await db_session.get(Document, doc_id)
            if not doc:
                continue

            try:
                # Bedrock Claude で埋め込みベクトルを生成
                embedding = await _get_embedding(doc.content)

                # Qdrant に登録
                await qdrant_client.upsert(
                    collection_name="documents",
                    points=[
                        Point(
                            id=doc_id,
                            vector=embedding,
                            payload={
                                "doc_id": doc_id,
                                "name": doc.name,
                                "source_type": doc.source_type,
                            },
                        )
                    ],
                )

                doc.status = "indexed"

            except Exception as e:
                logger.error(f"Indexing failed for doc {doc_id}: {e}")
                doc.status = "error"
                doc.retry_count = (doc.retry_count or 0) + 1

            await db_session.commit()
```

## FastAPI エンドポイント設計

```python
@router.post("/ext/gitea/sync")
async def sync_gitea_repo(
    payload: GiteaSyncRequest,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(get_async_session),
    current_user_id: str = Header(..., alias="X-User-Id"),
):
    """
    Gitea リポジトリをナレッジベースに同期

    リクエスト例：
    {
        "kb_id": 1,
        "gitea_url": "https://gitea.internal.co.jp",
        "owner": "team",
        "repo": "knowledge",
        "branch": "main",
        "path_filter": "docs/"  # optional
    }
    """

    # KB アクセス権限確認
    kb = await db_session.get(KnowledgeBase, payload.kb_id)
    if not kb or kb.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await _sync_gitea_repo(
        kb_id=payload.kb_id,
        gitea_url=payload.gitea_url,
        owner=payload.owner,
        repo=payload.repo,
        branch=payload.branch or "main",
        path_filter=payload.path_filter or "",
        db_session=db_session,
        background_tasks=background_tasks,
    )

    return {
        "status": "syncing",
        "synced_files": result["synced_files"],
        "total_files": result["total_files"],
    }
```

## DBスキーマ（SQLAlchemy）

```python
class GiteaSource(Base):
    """Gitea リポジトリ同期設定"""
    __tablename__ = "gitea_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"))
    gitea_url: Mapped[str]
    owner: Mapped[str]
    repo: Mapped[str]
    branch: Mapped[str] = mapped_column(default="main")
    path_filter: Mapped[str] = mapped_column(default="")
    last_synced_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    file_count: Mapped[int] = mapped_column(default=0)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="gitea_sources")
```

## GitHub 版との共通パターン

本システムは GitHub/Gitea 両方に対応した設計です。

### 違い

| 項目 | GitHub | Gitea |
|------|--------|-------|
| **認証** | Token 不要（public only） | GITEA_TOKEN 環境変数 |
| **API Base** | `api.github.com` | リポジトリホスト |
| **ツリー API** | `/repos/{owner}/{repo}/git/trees/{sha}` | `/api/v1/repos/{owner}/{repo}/git/trees/{branch}` |
| **ファイル取得** | `/repos/{owner}/{repo}/contents/{path}` | `/api/v1/repos/{owner}/{repo}/raw/{path}` |

### 共通部分

- **差分検出**: バイト比較（両者共通）
- **バックグラウンド処理**: FastAPI BackgroundTasks（両者共通）
- **DB スキーマ**: `github_sources` / `gitea_sources` で分離（拡張性）
- **ドキュメント生成**: markdown/txt のみ（両者共通）

## 実装のポイント

### 1. エンコーディング対応

Gitea から取得したファイルは常にバイナリです。

```python
# 推奨：エラーを許容しつつ UTF-8 でデコード
text_content = file_content.decode('utf-8', errors='replace')
```

### 2. ネットワーク設定

```python
# 環境変数で Gitea 設定
GITEA_BASE_URL = os.getenv("GITEA_BASE_URL", "https://gitea.internal.co.jp")
GITEA_TOKEN = os.getenv("GITEA_TOKEN")
```

### 3. ファイルキャッシュ

差分検出用に前回のファイル内容をディスク保存：

```python
def _get_document_cache_path(doc_id: int) -> Path:
    cache_dir = Path("/app/cache/documents")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"doc_{doc_id}.bin"

# 保存
cache_path = _get_document_cache_path(doc.id)
with open(cache_path, "wb") as f:
    f.write(file_content)
```

### 4. ロギング

```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Syncing {owner}/{repo}:{branch}")
logger.debug(f"Skipping unchanged: {file_path}")
logger.error(f"Gitea sync failed: {e}")
```

## パフォーマンス最適化

### 並列処理

複数ファイルのダウンロードを並列化：

```python
async with aiohttp.ClientSession() as session:
    tasks = [
        session.get(f"{gitea_base}/api/v1/repos/{owner}/{repo}/raw/{f['path']}?ref={branch}")
        for f in file_blobs
    ]
    responses = await asyncio.gather(*tasks)
```

### インデックス処理の分散

ドキュメント数が大量の場合、バッチに分割：

```python
BATCH_SIZE = 50
for i in range(0, len(documents_to_index), BATCH_SIZE):
    batch = documents_to_index[i:i+BATCH_SIZE]
    background_tasks.add_task(_index_documents_background, [doc.id for doc in batch])
```

## トラブルシューティング

### 403 Forbidden

トークンが無効、またはリポジトリへのアクセス権がない：

```python
# 確認コマンド（Gitea 環境内）
curl -H "Authorization: token $GITEA_TOKEN" \
  "https://gitea.internal.co.jp/api/v1/repos/owner/repo"
```

### ツリー API が truncated

大規模リポジトリの場合、`recursive=true` でも一部ファイルが返されないことがあります：

```python
if tree_data.get("truncated"):
    logger.warning("Tree response truncated — consider filtering by path")
```

### エンコーディングエラー

特定のファイルが UTF-8 ではなく Shift-JIS など：

```python
# replace で破損文字をスキップ
text_content = file_content.decode('utf-8', errors='replace')

# strict だと例外が発生（非推奨）
# text_content = file_content.decode('utf-8')  # ValueError!
```

## まとめ

社内 Gitea リポジトリを RAG ナレッジベースに自動同期する仕組みを実装することで、以下が実現できます：

1. **Git as SSOT**: ドキュメントの唯一の正式版として Gitea を機能させる
2. **差分検出効率化**: バイト比較で未変更ファイルをスキップ
3. **非ブロッキング処理**: バックグラウンドインデックスでUI ハング防止
4. **拡張性**: GitHub/Gitea 両対応で、複数ソースを統合可能

FastAPI + Gitea API の組み合わせは、社内知識管理を次のレベルへ引き上げる有力な選択肢となります。

---

**参考リソース**

- [Gitea API Documentation](https://gitea.io/en-us/docs/api/)
- [FastAPI BackgroundTasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Qdrant Vector Database](https://qdrant.tech/)
- [AWS Bedrock Embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/embeddings.html)
