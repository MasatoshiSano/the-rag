"""
外部連携ルーターモジュール。
API キー認証付きの同期チャット API と GitHub リポジトリ同期エンドポイントを提供する。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import config
from app.infrastructure.db import get_db
from app.middleware.api_key import verify_api_key
from app.models.database import Document, GiteaSource, GitHubSource, KnowledgeBase, Session
from app.services.rag import run_rag_pipeline
from app.utils.url_security import validate_and_resolve, validate_external_url

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ext",
    tags=["external"],
    dependencies=[Depends(verify_api_key)],
)


# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


class SyncChatRequest(BaseModel):
    """POST /ext/chat/sync リクエストボディ。"""

    content: str = Field(..., min_length=1, description="質問テキスト")
    knowledge_base_id: str = Field(..., description="検索対象ナレッジベース ID")
    session_id: Optional[str] = Field(
        default=None, description="セッション ID（None で新規作成）"
    )
    user_id: str = Field(default="ext-api-user", description="ユーザー ID")


class SyncChatSource(BaseModel):
    """同期チャットレスポンス内のソース情報。"""

    chunk_id: str
    document_id: str
    document_name: str
    section_title: str
    score: float


class SyncChatResponse(BaseModel):
    """POST /ext/chat/sync レスポンス。"""

    answer: str
    sources: list[SyncChatSource]
    session_id: str
    message_id: str


class GitHubSyncRequest(BaseModel):
    """POST /ext/github/sync リクエストボディ。"""

    repository_url: str = Field(
        ..., description="GitHub リポジトリ URL (例: https://github.com/owner/repo)"
    )
    path: str = Field(
        default="", description="同期対象ディレクトリパス (例: docs/posts)"
    )
    branch: str = Field(default="main", description="ブランチ名")
    knowledge_base_id: str = Field(..., description="同期先ナレッジベース ID")
    user_id: str = Field(default="ext-api-user", description="ユーザー ID")


class GitHubSyncFileResult(BaseModel):
    """同期された各ファイルの結果。"""

    filename: str
    document_id: str
    status: str


class GitHubSyncResponse(BaseModel):
    """POST /ext/github/sync レスポンス。"""

    synced_files: list[GitHubSyncFileResult]
    total: int
    message: str


class GiteaSyncRequest(BaseModel):
    """POST /ext/gitea/sync リクエストボディ。"""

    repository_url: str = Field(
        ...,
        description=(
            "Gitea リポジトリ URL (例: https://gitea.example.com/owner/repo"
            " または .../owner/repo/src/branch/main/docs)"
        ),
    )
    path: str = Field(
        default="", description="同期対象ディレクトリパス (例: docs/posts)"
    )
    branch: str = Field(default="main", description="ブランチ名")
    knowledge_base_id: str = Field(..., description="同期先ナレッジベース ID")
    user_id: str = Field(default="ext-api-user", description="ユーザー ID")


class GiteaSyncFileResult(BaseModel):
    """Gitea 同期された各ファイルの結果。"""

    filename: str
    document_id: str
    status: str


class GiteaSyncResponse(BaseModel):
    """POST /ext/gitea/sync レスポンス。"""

    synced_files: list[GiteaSyncFileResult]
    total: int
    message: str


# ---------------------------------------------------------------------------
# 同期チャット API
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """UTC の現在時刻を ISO 8601 文字列で返す。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@router.post("/chat/sync", response_model=SyncChatResponse)
async def sync_chat(
    body: SyncChatRequest,
    db: AsyncSession = Depends(get_db),
) -> SyncChatResponse:
    """
    同期チャット API。RAG パイプラインの SSE イベントを内部消費し、
    全テキストを結合して JSON 一括レスポンスを返す。
    """
    # セッション取得または新規作成
    session_id = body.session_id
    if session_id is None:
        session_id = str(uuid4())
        new_session = Session(
            id=session_id,
            user_id=body.user_id,
            knowledge_base_id=body.knowledge_base_id,
            title=body.content[:50],
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        db.add(new_session)
        await db.commit()

    # RAG パイプラインの SSE イベントを全て収集
    answer_parts: list[str] = []
    sources: list[SyncChatSource] = []
    message_id = ""

    async for raw_event in run_rag_pipeline(
        query=body.content,
        session_id=session_id,
        knowledge_base_id=body.knowledge_base_id,
        user_id=body.user_id,
        db=db,
    ):
        # SSE フォーマット: "data: {...}\n\n"
        line = raw_event.strip()
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except json.JSONDecodeError:
            continue

        event_type = payload.get("event", "")
        data = payload.get("data", {})

        if event_type == "token":
            answer_parts.append(data.get("text", ""))
        elif event_type == "sources":
            for item in data.get("items", []):
                sources.append(
                    SyncChatSource(
                        chunk_id=item.get("chunk_id", ""),
                        document_id=item.get("document_id", ""),
                        document_name=item.get("document_name", ""),
                        section_title=item.get("section_title", ""),
                        score=item.get("score", 0.0),
                    )
                )
        elif event_type == "complete":
            message_id = data.get("message_id", "")
        elif event_type == "error":
            raise HTTPException(
                status_code=500,
                detail=data.get("message", "RAG pipeline error"),
            )

    return SyncChatResponse(
        answer="".join(answer_parts),
        sources=sources,
        session_id=session_id,
        message_id=message_id,
    )


# ---------------------------------------------------------------------------
# GitHub 同期 API
# ---------------------------------------------------------------------------


def _parse_github_url(url: str) -> tuple[str, str]:
    """
    GitHub URL から owner と repo を抽出する。

    URL のホスト名は github.com に厳密一致 (equality) でなければならない。
    部分一致 (例: github.com.attacker.com) は拒否する (SSRF 対策)。

    Args:
        url: GitHub リポジトリ URL。

    Returns:
        (owner, repo) のタプル。

    Raises:
        HTTPException(400): URL が不正な形式またはホスト名が不一致の場合。
    """
    cleaned = url.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]

    # ホスト名厳密一致チェック (HTTPException を送出する)
    validate_external_url(cleaned, allowed_hosts={"github.com"})

    parsed = urlparse(cleaned)
    # path は "/owner/repo" の形を期待する
    path_parts = [p for p in (parsed.path or "").split("/") if p]
    if len(path_parts) < 2:
        raise HTTPException(
            status_code=400, detail=f"Invalid GitHub URL (owner/repo not found): {url}"
        )

    return path_parts[0], path_parts[1]


@router.post("/github/sync", response_model=GitHubSyncResponse)
async def sync_github(
    body: GitHubSyncRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> GitHubSyncResponse:
    """
    GitHub リポジトリから Markdown ファイルを取得してナレッジベースに同期する。
    パブリックリポジトリ前提（トークン不要）。
    """
    from app.routers.documents import _run_indexing_pipeline

    # GitHub URL をパース (HTTPException は呼び出し側に伝播する)
    try:
        owner, repo = _parse_github_url(body.repository_url)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # ナレッジベースの存在確認
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == body.knowledge_base_id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # GitHub API のホスト名 (api.github.com) と raw コンテンツ (raw.githubusercontent.com)
    # の DNS 解決後 IP を検証 (SSRF / DNS リバインディング対策)
    # NOTE: DNS リバインディング対策の限界 (事前検証と httpx リクエストの間で
    # DNS が再解決される TOCTOU 問題) については
    # app/utils/url_security.py の docstring を参照。
    validate_and_resolve(
        "https://api.github.com", allowed_hosts={"api.github.com"}
    )
    validate_and_resolve(
        "https://raw.githubusercontent.com",
        allowed_hosts={"raw.githubusercontent.com"},
    )

    # GitHub API でファイルツリーを取得
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{body.branch}?recursive=1"

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        tree_resp = await client.get(
            tree_url, headers={"Accept": "application/vnd.github.v3+json"}
        )

    if tree_resp.status_code != 200:
        # レート制限やリポジトリ未発見などをユーザーフレンドリーに表示
        status = tree_resp.status_code
        if status == 403:
            detail = "GitHub APIのレート制限に達しました。しばらく待ってから再試行してください。"
        elif status == 404:
            detail = (
                f"リポジトリが見つかりません: {owner}/{repo} (ブランチ: {body.branch})"
            )
        else:
            detail = f"GitHub APIエラー ({status})"
        raise HTTPException(status_code=400, detail=detail)

    tree_data = tree_resp.json()
    all_files = tree_data.get("tree", [])

    # パス指定とMDフィルタ
    target_path = body.path.strip("/")
    md_files = []
    for item in all_files:
        if item.get("type") != "blob":
            continue
        file_path: str = item.get("path", "")
        if (
            target_path
            and not file_path.startswith(target_path + "/")
            and file_path != target_path
        ):
            continue
        if file_path.lower().endswith((".md", ".markdown", ".txt")):
            md_files.append(file_path)

    if not md_files:
        return GitHubSyncResponse(
            synced_files=[],
            total=0,
            message=f"No markdown files found in {owner}/{repo}/{target_path}",
        )

    # 各ファイルをダウンロードしてドキュメント登録
    synced: list[GitHubSyncFileResult] = []

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for file_path in md_files:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{body.branch}/{file_path}"
            resp = await client.get(raw_url)
            if resp.status_code != 200:
                logger.warning("Failed to download %s: %s", raw_url, resp.status_code)
                continue

            filename = os.path.basename(file_path)
            doc_id = str(uuid4())

            # 一時ファイルに保存
            os.makedirs(config.UPLOAD_DIR, exist_ok=True)
            saved_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}_{filename}")
            with open(saved_path, "wb") as f:
                f.write(resp.content)

            # 既存ドキュメントを確認
            existing = await db.execute(
                select(Document)
                .where(
                    Document.knowledge_base_id == body.knowledge_base_id,
                    Document.filename == filename,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.version.desc())
            )
            prev_doc = existing.scalars().first()

            # インデックス済みなら内容を比較し、同一ならスキップ
            if prev_doc and prev_doc.status == "indexed":
                prev_path = prev_doc.original_path
                if prev_path and os.path.exists(prev_path):
                    with open(prev_path, "rb") as pf:
                        prev_content = pf.read()
                    if prev_content == resp.content:
                        # 変更なし — 一時ファイルを削除してスキップ
                        os.remove(saved_path)
                        synced.append(
                            GitHubSyncFileResult(
                                filename=filename,
                                document_id=prev_doc.id,
                                status="skipped",
                            )
                        )
                        continue

            parent_id = prev_doc.id if prev_doc else None
            new_version = (prev_doc.version + 1) if prev_doc else 1

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "md"

            doc = Document(
                id=doc_id,
                knowledge_base_id=body.knowledge_base_id,
                filename=filename,
                file_type=ext,
                original_path=saved_path,
                status="processing",
                version=new_version,
                parent_document_id=parent_id,
                uploaded_by=body.user_id,
                uploaded_at=_now_iso(),
                retry_count=0,
            )
            db.add(doc)

            synced.append(
                GitHubSyncFileResult(
                    filename=filename,
                    document_id=doc_id,
                    status="processing",
                )
            )

    await db.flush()

    # バックグラウンドでインデックス処理を開始（スキップ分は除外）
    new_files = [item for item in synced if item.status != "skipped"]
    for item in new_files:
        saved_path = os.path.join(
            config.UPLOAD_DIR, f"{item.document_id}_{item.filename}"
        )
        background_tasks.add_task(
            _run_indexing_pipeline, item.document_id, saved_path, item.filename
        )

    # GitHub 同期設定を upsert
    canonical_url = f"https://github.com/{owner}/{repo}"
    existing_source = await db.execute(
        select(GitHubSource).where(
            GitHubSource.knowledge_base_id == body.knowledge_base_id,
            GitHubSource.repository_url == canonical_url,
            GitHubSource.path == target_path,
            GitHubSource.branch == body.branch,
        )
    )
    source = existing_source.scalar_one_or_none()
    if source:
        source.last_synced_at = _now_iso()
        source.synced_by = body.user_id
    else:
        db.add(
            GitHubSource(
                id=str(uuid4()),
                knowledge_base_id=body.knowledge_base_id,
                repository_url=canonical_url,
                path=target_path,
                branch=body.branch,
                synced_by=body.user_id,
                last_synced_at=_now_iso(),
                created_at=_now_iso(),
            )
        )
    await db.commit()

    skipped_count = len(synced) - len(new_files)
    parts: list[str] = []
    if new_files:
        parts.append(f"{len(new_files)}件を新規/更新として処理開始")
    if skipped_count:
        parts.append(f"{skipped_count}件は変更なしのためスキップ")
    message = f"{owner}/{repo}: " + "、".join(parts) if parts else "対象ファイルなし"

    return GitHubSyncResponse(
        synced_files=synced,
        total=len(synced),
        message=message,
    )


# ---------------------------------------------------------------------------
# Gitea 同期 API
# ---------------------------------------------------------------------------


def _parse_gitea_url(url: str, base_url: str) -> tuple[str, str, str, Optional[str]]:
    """
    Gitea URL から owner, repo, path, branch を抽出する。

    対応 URL 形式:
      - {base_url}/owner/repo
      - {base_url}/owner/repo.git
      - {base_url}/owner/repo/src/branch/{branch}/{path}

    URL のホスト名は base_url のホスト名と equality で完全一致しなければ
    ならない (例: gitea.example.com.attacker.com は拒否)。

    Args:
        url: Gitea リポジトリ URL。
        base_url: 設定された Gitea ベース URL（末尾スラッシュなし）。

    Returns:
        (owner, repo, path, branch) のタプル。branch が URL に含まれない場合は None。

    Raises:
        HTTPException(400): URL が不正な形式または設定されたベース URL に属さない場合。
    """
    cleaned_url = url.rstrip("/")
    base = base_url.rstrip("/")

    base_parsed = urlparse(base)
    if not base_parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail=f"GITEA_BASE_URL が不正です: {base_url}",
        )

    # URL のホスト名を base のホスト名と equality 一致でチェック
    validate_external_url(
        cleaned_url, allowed_hosts={base_parsed.hostname.lower()}
    )

    # base のパスプレフィックス (例: https://host/gitea) も維持されているかチェック
    if not cleaned_url.startswith(base + "/") and cleaned_url != base:
        raise HTTPException(
            status_code=400,
            detail=f"URL はGitea ベース URL ({base}) 配下である必要があります: {url}",
        )

    remainder = cleaned_url[len(base) + 1 :] if cleaned_url != base else ""
    if remainder.endswith(".git"):
        remainder = remainder[:-4]

    parts = remainder.split("/") if remainder else []
    if len(parts) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"owner/repo 形式が見つかりません: {url}",
        )

    owner, repo = parts[0], parts[1]
    path = ""
    branch: Optional[str] = None

    # .../owner/repo/src/branch/{branch}/{path...}
    if len(parts) >= 5 and parts[2] == "src" and parts[3] == "branch":
        branch = parts[4]
        path = "/".join(parts[5:])

    return owner, repo, path, branch


def _gitea_headers() -> dict[str, str]:
    """Gitea API 呼び出し用のヘッダーを返す。"""
    headers = {"Accept": "application/json"}
    if config.GITEA_TOKEN:
        headers["Authorization"] = f"token {config.GITEA_TOKEN}"
    return headers


@router.post("/gitea/sync", response_model=GiteaSyncResponse)
async def sync_gitea(
    body: GiteaSyncRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> GiteaSyncResponse:
    """
    Gitea リポジトリから Markdown ファイルを取得してナレッジベースに同期する。
    GITEA_BASE_URL と GITEA_TOKEN 環境変数で認証する。
    """
    from app.routers.documents import _run_indexing_pipeline

    if not config.GITEA_BASE_URL:
        raise HTTPException(
            status_code=400,
            detail="Gitea 連携が設定されていません（GITEA_BASE_URL 未設定）。",
        )

    # Gitea URL をパース (HTTPException は呼び出し側に伝播する)
    try:
        owner, repo, url_path, url_branch = _parse_gitea_url(
            body.repository_url, config.GITEA_BASE_URL
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # URL にパス/ブランチが含まれていればボディより優先
    target_path = (url_path or body.path).strip("/")
    branch = url_branch or body.branch

    # ナレッジベースの存在確認
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == body.knowledge_base_id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    base = config.GITEA_BASE_URL.rstrip("/")
    headers = _gitea_headers()

    # base_url の DNS 解決後 IP を検証 (SSRF / DNS リバインディング対策)
    # 注: Gitea がプライベートネットワーク上にある場合、本検証は環境に応じて
    # 緩める必要がある。現状は public Gitea を想定して厳格にする。
    # NOTE: DNS リバインディング対策の限界 (事前検証と httpx リクエストの間で
    # DNS が再解決される TOCTOU 問題) については
    # app/utils/url_security.py の docstring を参照。
    base_parsed = urlparse(base)
    if base_parsed.hostname:
        try:
            validate_and_resolve(base, allowed_hosts={base_parsed.hostname.lower()})
        except HTTPException:
            # プライベート Gitea を許容するケース向けの抜け道は当面なし。
            # 本番運用で内部 Gitea を使う場合は専用 allowlist 設定が必要。
            raise

    # デフォルトブランチを解決（branch が空の場合のみ）
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        if not branch:
            repo_resp = await client.get(
                f"{base}/api/v1/repos/{owner}/{repo}", headers=headers
            )
            if repo_resp.status_code != 200:
                status = repo_resp.status_code
                if status == 401:
                    detail = "Gitea 認証に失敗しました。GITEA_TOKEN を確認してください。"
                elif status == 404:
                    detail = f"リポジトリが見つかりません: {owner}/{repo}"
                else:
                    detail = f"Gitea API エラー ({status})"
                raise HTTPException(status_code=400, detail=detail)
            branch = repo_resp.json().get("default_branch") or "main"

        tree_url = (
            f"{base}/api/v1/repos/{owner}/{repo}/git/trees/{branch}?recursive=true"
        )
        tree_resp = await client.get(tree_url, headers=headers)

    if tree_resp.status_code != 200:
        status = tree_resp.status_code
        if status == 401:
            detail = "Gitea 認証に失敗しました。GITEA_TOKEN を確認してください。"
        elif status == 404:
            detail = (
                f"リポジトリ/ブランチが見つかりません: {owner}/{repo} (ブランチ: {branch})"
            )
        else:
            detail = f"Gitea API エラー ({status})"
        raise HTTPException(status_code=400, detail=detail)

    tree_data = tree_resp.json()
    all_files = tree_data.get("tree", [])

    # パス指定と対象拡張子フィルタ（GitHub 同期と同じ .md/.markdown/.txt）
    md_files: list[str] = []
    for item in all_files:
        if item.get("type") != "blob":
            continue
        file_path: str = item.get("path", "")
        if (
            target_path
            and not file_path.startswith(target_path + "/")
            and file_path != target_path
        ):
            continue
        if file_path.lower().endswith((".md", ".markdown", ".txt")):
            md_files.append(file_path)

    if not md_files:
        return GiteaSyncResponse(
            synced_files=[],
            total=0,
            message=f"No markdown files found in {owner}/{repo}/{target_path}",
        )

    # 各ファイルをダウンロードしてドキュメント登録
    synced: list[GiteaSyncFileResult] = []

    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        for file_path in md_files:
            raw_url = (
                f"{base}/api/v1/repos/{owner}/{repo}/raw/{file_path}?ref={branch}"
            )
            resp = await client.get(raw_url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Failed to download %s: %s", raw_url, resp.status_code)
                continue

            filename = os.path.basename(file_path)
            doc_id = str(uuid4())

            os.makedirs(config.UPLOAD_DIR, exist_ok=True)
            saved_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}_{filename}")
            with open(saved_path, "wb") as f:
                f.write(resp.content)

            # 既存ドキュメントを確認
            existing = await db.execute(
                select(Document)
                .where(
                    Document.knowledge_base_id == body.knowledge_base_id,
                    Document.filename == filename,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.version.desc())
            )
            prev_doc = existing.scalars().first()

            if prev_doc and prev_doc.status == "indexed":
                prev_path = prev_doc.original_path
                if prev_path and os.path.exists(prev_path):
                    with open(prev_path, "rb") as pf:
                        prev_content = pf.read()
                    if prev_content == resp.content:
                        os.remove(saved_path)
                        synced.append(
                            GiteaSyncFileResult(
                                filename=filename,
                                document_id=prev_doc.id,
                                status="skipped",
                            )
                        )
                        continue

            parent_id = prev_doc.id if prev_doc else None
            new_version = (prev_doc.version + 1) if prev_doc else 1
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "md"

            doc = Document(
                id=doc_id,
                knowledge_base_id=body.knowledge_base_id,
                filename=filename,
                file_type=ext,
                original_path=saved_path,
                status="processing",
                version=new_version,
                parent_document_id=parent_id,
                uploaded_by=body.user_id,
                uploaded_at=_now_iso(),
                retry_count=0,
            )
            db.add(doc)

            synced.append(
                GiteaSyncFileResult(
                    filename=filename,
                    document_id=doc_id,
                    status="processing",
                )
            )

    await db.flush()

    new_files = [item for item in synced if item.status != "skipped"]
    for item in new_files:
        saved_path = os.path.join(
            config.UPLOAD_DIR, f"{item.document_id}_{item.filename}"
        )
        background_tasks.add_task(
            _run_indexing_pipeline, item.document_id, saved_path, item.filename
        )

    # Gitea 同期設定を upsert（URL は正規化済みの base/owner/repo のみを保存）
    canonical_url = f"{base}/{owner}/{repo}"
    existing_source = await db.execute(
        select(GiteaSource).where(
            GiteaSource.knowledge_base_id == body.knowledge_base_id,
            GiteaSource.repository_url == canonical_url,
            GiteaSource.path == target_path,
            GiteaSource.branch == branch,
        )
    )
    source = existing_source.scalar_one_or_none()
    if source:
        source.last_synced_at = _now_iso()
        source.synced_by = body.user_id
    else:
        db.add(
            GiteaSource(
                id=str(uuid4()),
                knowledge_base_id=body.knowledge_base_id,
                repository_url=canonical_url,
                path=target_path,
                branch=branch,
                synced_by=body.user_id,
                last_synced_at=_now_iso(),
                created_at=_now_iso(),
            )
        )
    await db.commit()

    skipped_count = len(synced) - len(new_files)
    parts: list[str] = []
    if new_files:
        parts.append(f"{len(new_files)}件を新規/更新として処理開始")
    if skipped_count:
        parts.append(f"{skipped_count}件は変更なしのためスキップ")
    message = f"{owner}/{repo}: " + "、".join(parts) if parts else "対象ファイルなし"

    return GiteaSyncResponse(
        synced_files=synced,
        total=len(synced),
        message=message,
    )
