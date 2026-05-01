"""
ドキュメント管理ルーターモジュール。
ファイルアップロード、インデックス管理、ソフトデリート、バージョン管理の API エンドポイントを提供する。
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.config import config
from app.infrastructure.db import AsyncSessionLocal, get_db
from app.infrastructure import qdrant_client as qdrant
from app.models.database import (
    Document,
    DocumentTag,
    FolderSource,
    GiteaSource,
    GitHubSource,
    KnowledgeBase,
)
from app.utils.path_security import safe_remove_within
from app.utils.zip_security import ZipSecurityError, iter_safe_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# ---------------------------------------------------------------------------
# キャンセルフラグ管理（インメモリ）
# ---------------------------------------------------------------------------

_cancel_flags: dict[str, bool] = {}


def _check_cancelled(document_id: str) -> bool:
    """ドキュメントのキャンセルフラグを確認する。"""
    return _cancel_flags.get(document_id, False)


def _clear_cancel_flag(document_id: str) -> None:
    """キャンセルフラグをクリアする。"""
    _cancel_flags.pop(document_id, None)


# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    file_type: str
    status: str
    version: int
    retry_count: int = 0
    deleted_at: Optional[str]
    uploaded_by: Optional[str]
    uploaded_at: str
    tags: list[DocumentTagResponse] = []

    model_config = {"from_attributes": True}


class DocumentTagResponse(BaseModel):
    id: int
    tag_key: str
    tag_value: str
    confidence: float
    ai_suggested: bool
    confirmed: bool

    model_config = {"from_attributes": True}


class DocumentDetailResponse(DocumentResponse):
    converted_md: Optional[str]
    parent_document_id: Optional[str]


class UploadResponse(BaseModel):
    documents: list[DocumentResponse]
    message: str


class TagItem(BaseModel):
    tag_key: str = Field(..., min_length=1)
    tag_value: str = Field(..., min_length=1)
    confirmed: bool = False


class UpdateTagsRequest(BaseModel):
    tags: list[TagItem]


class BatchTagItem(BaseModel):
    document_id: str
    tags: list[TagItem]


class BatchTagUpdateRequest(BaseModel):
    documents: list[BatchTagItem]


class RatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)


class VersionResponse(BaseModel):
    id: str
    version: int
    filename: str
    status: str
    uploaded_at: str


# ---------------------------------------------------------------------------
# 依存性注入
# ---------------------------------------------------------------------------


def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """X-User-Id ヘッダーからユーザー ID を取得する。"""
    user_id = x_user_id.strip()
    if not user_id:
        raise HTTPException(
            status_code=400, detail="X-User-Id header must not be empty"
        )
    return user_id


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """現在時刻を UTC ISO 8601 文字列で返す。"""
    return datetime.now(UTC).isoformat()


async def _get_doc_or_404(doc_id: str, db: AsyncSession) -> Document:
    """ドキュメントを取得する。存在しない場合は 404 を送出する。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    return doc


def _doc_to_response(
    doc: Document, tags: list[DocumentTag] | None = None
) -> DocumentResponse:
    """Document ORM を DocumentResponse に変換する。"""
    tag_list = []
    if tags:
        tag_list = [
            DocumentTagResponse(
                id=t.id,
                tag_key=t.tag_key,
                tag_value=t.tag_value,
                confidence=t.confidence,
                ai_suggested=bool(t.ai_suggested),
                confirmed=bool(t.confirmed),
            )
            for t in tags
        ]
    return DocumentResponse(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        file_type=doc.file_type,
        status=doc.status,
        version=doc.version,
        retry_count=doc.retry_count,
        deleted_at=doc.deleted_at,
        uploaded_by=doc.uploaded_by,
        uploaded_at=doc.uploaded_at,
        tags=tag_list,
    )


async def _get_tags_for_document(doc_id: str, db: AsyncSession) -> list[DocumentTag]:
    """ドキュメントのタグ一覧を取得する。"""
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.document_id == doc_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# バックグラウンド処理パイプライン
# ---------------------------------------------------------------------------


async def _run_indexing_pipeline(
    document_id: str, file_path: str, filename: str
) -> None:
    """
    ドキュメントのアップロード処理パイプラインをバックグラウンドで実行する。

    ステータス遷移:
      processing → converting → converted → tagging → tagged

    タグ付けまでで停止する。インデックス構築（チャンク→埋め込み→Qdrant登録）は
    ユーザーが明示的に確定ボタンを押した場合のみ _run_post_tag_pipeline で実行する。

    各ステージ開始前にキャンセルフラグを確認する。
    """
    from app.services.converter import convert_file
    from app.services.tagger import auto_tag_document
    from app.infrastructure.master_cache import get_master_cache

    async with AsyncSessionLocal() as db:
        try:
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc is None:
                logger.error("Document %s not found in pipeline", document_id)
                return

            # ---- Stage 1: Converting ----
            if _check_cancelled(document_id):
                doc.status = "cancelled"
                await db.commit()
                _clear_cancel_flag(document_id)
                return

            doc.status = "converting"
            await db.commit()

            try:
                conversion_result = await convert_file(file_path, filename)
                doc.converted_md = conversion_result.markdown
                doc.status = "converted"
                await db.commit()
            except Exception:
                logger.exception("Conversion failed for %s", document_id)
                doc.status = "convert_failed"
                doc.retry_count += 1
                if doc.retry_count >= config.MAX_RETRY_COUNT:
                    doc.status = "permanent_failed"
                await db.commit()
                return

            # ---- Stage 2: Tagging ----
            if _check_cancelled(document_id):
                doc.status = "cancelled"
                await db.commit()
                _clear_cancel_flag(document_id)
                return

            doc.status = "tagging"
            await db.commit()

            try:
                # 既存の AI 推奨タグを削除（手動確認済みタグは保持）
                existing_tags_result = await db.execute(
                    select(DocumentTag).where(
                        DocumentTag.document_id == document_id,
                        DocumentTag.ai_suggested == 1,
                        DocumentTag.confirmed == 0,
                    )
                )
                for old_tag in existing_tags_result.scalars().all():
                    await db.delete(old_tag)

                master_cache = get_master_cache()
                tag_suggestions = await auto_tag_document(
                    content=doc.converted_md,
                    db=db,
                    master_cache=master_cache,
                )
                for ts in tag_suggestions:
                    tag = DocumentTag(
                        document_id=document_id,
                        tag_key=ts.tag_key,
                        tag_value=ts.tag_value,
                        confidence=ts.confidence,
                        ai_suggested=1,
                        confirmed=0,
                    )
                    db.add(tag)
                doc.status = "tagged"
                await db.commit()
            except Exception:
                logger.exception("Tagging failed for %s", document_id)
                doc.status = "tag_failed"
                doc.retry_count += 1
                if doc.retry_count >= config.MAX_RETRY_COUNT:
                    doc.status = "permanent_failed"
                await db.commit()
                return

            # パイプラインはタグ付けまでで停止。
            # インデックス構築はユーザーが明示的に確定ボタンを押した場合のみ実行する。
            logger.info(
                "Upload pipeline completed (up to tagging) for document %s",
                document_id,
            )

        except Exception:
            logger.exception("Unexpected error in pipeline for %s", document_id)
        finally:
            _clear_cancel_flag(document_id)


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=201, response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    knowledge_base_id: str = Query(..., description="アップロード先ナレッジベース ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    複数ファイルをアップロードし、非同期インデックス処理を開始する。
    最大 20 ファイル/回、合計 200MB 上限。ZIP 自動展開対応。
    """
    # ナレッジベース存在確認
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == knowledge_base_id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404, detail=f"KnowledgeBase {knowledge_base_id} not found"
        )

    if len(files) > config.MAX_BATCH_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {config.MAX_BATCH_UPLOAD_FILES} files per upload",
        )

    # ファイルサイズ合計チェック
    total_size = 0
    for f in files:
        if f.size is not None:
            total_size += f.size
    if total_size > config.MAX_BATCH_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Total upload size exceeds {config.MAX_BATCH_UPLOAD_SIZE // (1024 * 1024)}MB limit",
        )

    uploaded_docs: list[DocumentResponse] = []
    files_to_process: list[tuple[str, str, str]] = []  # (doc_id, file_path, filename)

    for upload_file in files:
        filename = upload_file.filename or "unknown"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # ZIP 自動展開
        # NOTE: PPTX/XLSX/DOCX 等の Office 形式は内部的に zip 構造を持つが、
        # ここでは ext == "zip" のみを対象とする。Office 形式の二重展開リスクは
        # 入力サイズ制限 (MAX_UPLOAD_SIZE) で間接的にカバーする。
        if ext == "zip":
            content = await upload_file.read()
            zip_dir = os.path.join(config.UPLOAD_DIR, str(uuid4()))
            os.makedirs(zip_dir, exist_ok=True)

            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    # iter_safe_entries でストリーミング展開し、
                    # zip bomb / 各ファイルサイズ超過を防ぐ。
                    for zip_info, inner_content in iter_safe_entries(
                        zf,
                        max_total=config.MAX_BATCH_UPLOAD_SIZE,
                        max_per_file=config.MAX_UPLOAD_SIZE,
                    ):
                        # zip slip 緩和: basename のみを採用しパストラバーサルを防ぐ
                        inner_name = os.path.basename(zip_info.filename)
                        if not inner_name:
                            continue
                        inner_ext = (
                            inner_name.rsplit(".", 1)[-1].lower()
                            if "." in inner_name
                            else ""
                        )
                        if inner_ext not in config.ALLOWED_EXTENSIONS:
                            continue

                        doc_id = str(uuid4())
                        extracted_path = os.path.join(
                            zip_dir, f"{doc_id}_{inner_name}"
                        )
                        with open(extracted_path, "wb") as dst:
                            dst.write(inner_content)

                        # バージョン管理: 同一ファイル名の既存ドキュメントを検索
                        existing = await db.execute(
                            select(Document)
                            .where(
                                Document.knowledge_base_id == knowledge_base_id,
                                Document.filename == inner_name,
                                Document.deleted_at.is_(None),
                            )
                            .order_by(Document.version.desc())
                        )
                        prev_doc = existing.scalars().first()
                        parent_id = prev_doc.id if prev_doc else None
                        new_version = (prev_doc.version + 1) if prev_doc else 1

                        doc = Document(
                            id=doc_id,
                            knowledge_base_id=knowledge_base_id,
                            filename=inner_name,
                            file_type=inner_ext,
                            original_path=extracted_path,
                            status="processing",
                            version=new_version,
                            parent_document_id=parent_id,
                            uploaded_by=user_id,
                            uploaded_at=_now_iso(),
                            retry_count=0,
                        )
                        db.add(doc)
                        files_to_process.append((doc_id, extracted_path, inner_name))
                        uploaded_docs.append(_doc_to_response(doc))
            except ZipSecurityError as exc:
                logger.warning("ZIP rejected: %s", exc)
                raise HTTPException(
                    status_code=400, detail=f"ZIP file rejected: {exc}"
                ) from exc
            continue

        # 拡張子チェック
        if ext not in config.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Allowed: {', '.join(config.ALLOWED_EXTENSIONS)}",
            )

        # 個別ファイルサイズチェック
        if upload_file.size is not None and upload_file.size > config.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {filename} exceeds {config.MAX_UPLOAD_SIZE // (1024 * 1024)}MB limit",
            )

        # ファイル保存
        doc_id = str(uuid4())
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}_{filename}")
        content = await upload_file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # バージョン管理
        existing = await db.execute(
            select(Document)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.filename == filename,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.version.desc())
        )
        prev_doc = existing.scalars().first()
        parent_id = prev_doc.id if prev_doc else None
        new_version = (prev_doc.version + 1) if prev_doc else 1

        doc = Document(
            id=doc_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_type=ext,
            original_path=file_path,
            status="processing",
            version=new_version,
            parent_document_id=parent_id,
            uploaded_by=user_id,
            uploaded_at=_now_iso(),
            retry_count=0,
        )
        db.add(doc)
        files_to_process.append((doc_id, file_path, filename))
        uploaded_docs.append(_doc_to_response(doc))

    await db.flush()

    # バックグラウンドでインデックス処理を開始（最大3並行）
    for doc_id, file_path, filename in files_to_process:
        background_tasks.add_task(_run_indexing_pipeline, doc_id, file_path, filename)

    return UploadResponse(
        documents=uploaded_docs,
        message=f"{len(uploaded_docs)} file(s) uploaded and processing started",
    )


# ---------------------------------------------------------------------------
# GitHub 同期設定 (内部 UI 用)
# ---------------------------------------------------------------------------


class GitHubSourceResponse(BaseModel):
    id: str
    knowledge_base_id: str
    repository_url: str
    path: str
    branch: str
    synced_by: Optional[str]
    last_synced_at: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/github-sources", response_model=list[GitHubSourceResponse])
async def list_github_sources(
    knowledge_base_id: str = Query(..., description="ナレッジベース ID"),
    db: AsyncSession = Depends(get_db),
) -> list[GitHubSourceResponse]:
    """ナレッジベースに紐づく GitHub 同期設定一覧を返す。"""
    result = await db.execute(
        select(GitHubSource)
        .where(GitHubSource.knowledge_base_id == knowledge_base_id)
        .order_by(GitHubSource.last_synced_at.desc())
    )
    sources = result.scalars().all()
    return [GitHubSourceResponse.model_validate(s) for s in sources]


@router.delete("/github-sources/{source_id}", status_code=204, response_class=Response)
async def delete_github_source(
    source_id: str = Path(..., description="GitHub 同期設定 ID"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """GitHub 同期設定を削除する（ドキュメント自体は削除しない）。"""
    result = await db.execute(select(GitHubSource).where(GitHubSource.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status_code=404, detail=f"GitHub source {source_id} not found"
        )
    await db.delete(source)
    await db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GitHub / Gitea 同期 (内部 UI 用 - X-User-Id 認証ベース)
# ---------------------------------------------------------------------------
# フロントエンドからは /api/ext/* を直接呼ばず、これらの内部エンドポイントを経由する。
# 外部 API キー (config.API_KEYS) を Web ビルドに含めないようにするための間接化。


class GitHubSyncRequestBody(BaseModel):
    repository_url: str = Field(..., description="GitHub リポジトリ URL")
    path: str = Field(default="", description="同期対象ディレクトリパス")
    branch: str = Field(default="main", description="ブランチ名")
    knowledge_base_id: str = Field(..., description="同期先ナレッジベース ID")


class GiteaSyncRequestBody(BaseModel):
    repository_url: str = Field(..., description="Gitea リポジトリ URL")
    path: str = Field(default="", description="同期対象ディレクトリパス")
    branch: str = Field(default="main", description="ブランチ名")
    knowledge_base_id: str = Field(..., description="同期先ナレッジベース ID")


@router.post("/github-sync", status_code=200)
async def github_sync_internal(
    body: GitHubSyncRequestBody,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    GitHub 同期の内部用エンドポイント（X-User-Id ベース）。
    外部システム連携用の /api/ext/github/sync 実装に委譲し、API キーを
    フロントへ露出させずに同等機能を提供する。
    """
    from app.routers.external import GitHubSyncRequest, sync_github

    request = GitHubSyncRequest(
        repository_url=body.repository_url,
        path=body.path,
        branch=body.branch,
        knowledge_base_id=body.knowledge_base_id,
        user_id=user_id,
    )
    response = await sync_github(body=request, background_tasks=background_tasks, db=db)
    return response.model_dump()


@router.post("/gitea-sync", status_code=200)
async def gitea_sync_internal(
    body: GiteaSyncRequestBody,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Gitea 同期の内部用エンドポイント（X-User-Id ベース）。
    外部システム連携用の /api/ext/gitea/sync 実装に委譲し、API キーを
    フロントへ露出させずに同等機能を提供する。
    """
    from app.routers.external import GiteaSyncRequest, sync_gitea

    request = GiteaSyncRequest(
        repository_url=body.repository_url,
        path=body.path,
        branch=body.branch,
        knowledge_base_id=body.knowledge_base_id,
        user_id=user_id,
    )
    response = await sync_gitea(body=request, background_tasks=background_tasks, db=db)
    return response.model_dump()


# ---------------------------------------------------------------------------
# Gitea 同期設定 (内部 UI 用)
# ---------------------------------------------------------------------------


class GiteaSourceResponse(BaseModel):
    id: str
    knowledge_base_id: str
    repository_url: str
    path: str
    branch: str
    synced_by: Optional[str]
    last_synced_at: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/gitea-sources", response_model=list[GiteaSourceResponse])
async def list_gitea_sources(
    knowledge_base_id: str = Query(..., description="ナレッジベース ID"),
    db: AsyncSession = Depends(get_db),
) -> list[GiteaSourceResponse]:
    """ナレッジベースに紐づく Gitea 同期設定一覧を返す。"""
    result = await db.execute(
        select(GiteaSource)
        .where(GiteaSource.knowledge_base_id == knowledge_base_id)
        .order_by(GiteaSource.last_synced_at.desc())
    )
    sources = result.scalars().all()
    return [GiteaSourceResponse.model_validate(s) for s in sources]


@router.delete("/gitea-sources/{source_id}", status_code=204, response_class=Response)
async def delete_gitea_source(
    source_id: str = Path(..., description="Gitea 同期設定 ID"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Gitea 同期設定を削除する（ドキュメント自体は削除しない）。"""
    result = await db.execute(select(GiteaSource).where(GiteaSource.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status_code=404, detail=f"Gitea source {source_id} not found"
        )
    await db.delete(source)
    await db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# フォルダソース CRUD
# ---------------------------------------------------------------------------


class FolderSourceResponse(BaseModel):
    id: str
    knowledge_base_id: str
    folder_path: str
    container_path: str
    label: Optional[str]
    source_type: str = "document"
    file_count: int = 0
    has_more: bool = False
    registered_by: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class FolderSourceValidateRequest(BaseModel):
    folder_path: str = Field(..., min_length=2)


class FolderSourceValidateResponse(BaseModel):
    valid: bool
    container_path: str = ""
    file_count: int = 0
    has_more: bool = False
    error: str = ""


class FolderSourceCreateRequest(BaseModel):
    folder_path: str = Field(..., min_length=2)
    knowledge_base_id: str
    label: Optional[str] = None
    source_type: str = Field(default="document", pattern="^(document|data)$")


@router.post("/folder-sources/validate", response_model=FolderSourceValidateResponse)
async def validate_folder_path(
    body: FolderSourceValidateRequest,
    user_id: str = Depends(get_user_id),
) -> FolderSourceValidateResponse:
    """フォルダパスの有効性を検証し、ファイル数を返す。"""
    from app.services.folder_scanner import (
        scan_folder,
        windows_path_to_container_path,
    )

    try:
        container_path = windows_path_to_container_path(body.folder_path)
    except ValueError as exc:
        return FolderSourceValidateResponse(valid=False, error=str(exc))

    if not os.path.isdir(container_path):
        is_unc = container_path.startswith("/host_drives/unc/")
        hint = "（UNCパスはサーバー側のマウント設定が必要です。マップ済みのドライブレター（Z:\\等）で試してください）" if is_unc else ""
        return FolderSourceValidateResponse(
            valid=False,
            container_path=container_path,
            error=f"フォルダが見つかりません: {container_path}{hint}",
        )

    files = scan_folder(container_path, max_files=config.FOLDER_SOURCE_MAX_FILES + 1)
    has_more = len(files) > config.FOLDER_SOURCE_MAX_FILES
    return FolderSourceValidateResponse(
        valid=True,
        container_path=container_path,
        file_count=min(len(files), config.FOLDER_SOURCE_MAX_FILES),
        has_more=has_more,
    )


@router.post("/folder-sources", status_code=201, response_model=FolderSourceResponse)
async def create_folder_source(
    body: FolderSourceCreateRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> FolderSourceResponse:
    """フォルダソースを登録する。"""
    from app.services.folder_scanner import (
        scan_folder,
        windows_path_to_container_path,
    )

    # KB 存在確認
    kb_result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == body.knowledge_base_id)
    )
    if kb_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail=f"KnowledgeBase {body.knowledge_base_id} not found",
        )

    try:
        container_path = windows_path_to_container_path(body.folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not os.path.isdir(container_path):
        raise HTTPException(
            status_code=400, detail=f"フォルダが見つかりません: {container_path}"
        )

    # 重複チェック
    existing = await db.execute(
        select(FolderSource).where(
            FolderSource.knowledge_base_id == body.knowledge_base_id,
            FolderSource.folder_path == body.folder_path,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409, detail="このフォルダパスは既に登録されています。"
        )

    files = scan_folder(container_path, max_files=config.FOLDER_SOURCE_MAX_FILES + 1)
    has_more = len(files) > config.FOLDER_SOURCE_MAX_FILES

    source = FolderSource(
        id=str(uuid4()),
        knowledge_base_id=body.knowledge_base_id,
        folder_path=body.folder_path,
        container_path=container_path,
        label=body.label,
        source_type=body.source_type,
        registered_by=user_id,
        created_at=_now_iso(),
    )
    db.add(source)
    await db.flush()

    return FolderSourceResponse(
        id=source.id,
        knowledge_base_id=source.knowledge_base_id,
        folder_path=source.folder_path,
        container_path=source.container_path,
        label=source.label,
        source_type=source.source_type,
        file_count=min(len(files), config.FOLDER_SOURCE_MAX_FILES),
        has_more=has_more,
        registered_by=source.registered_by,
        created_at=source.created_at,
    )


@router.get("/folder-sources", response_model=list[FolderSourceResponse])
async def list_folder_sources(
    knowledge_base_id: str = Query(..., description="ナレッジベース ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[FolderSourceResponse]:
    """ナレッジベースに紐づくフォルダソース一覧を返す。"""
    from app.services.folder_scanner import scan_folder

    result = await db.execute(
        select(FolderSource)
        .where(FolderSource.knowledge_base_id == knowledge_base_id)
        .order_by(FolderSource.created_at.desc())
    )
    sources = result.scalars().all()

    responses: list[FolderSourceResponse] = []
    for s in sources:
        try:
            files = scan_folder(s.container_path, max_files=config.FOLDER_SOURCE_MAX_FILES + 1)
            has_more = len(files) > config.FOLDER_SOURCE_MAX_FILES
            file_count = min(len(files), config.FOLDER_SOURCE_MAX_FILES)
        except Exception:
            file_count = 0
            has_more = False

        responses.append(
            FolderSourceResponse(
                id=s.id,
                knowledge_base_id=s.knowledge_base_id,
                folder_path=s.folder_path,
                container_path=s.container_path,
                label=s.label,
                source_type=s.source_type,
                file_count=file_count,
                has_more=has_more,
                registered_by=s.registered_by,
                created_at=s.created_at,
            )
        )
    return responses


@router.delete(
    "/folder-sources/{source_id}", status_code=204, response_class=Response
)
async def delete_folder_source(
    source_id: str = Path(..., description="フォルダソース ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """フォルダソースを削除する。"""
    result = await db.execute(
        select(FolderSource).where(FolderSource.id == source_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status_code=404, detail=f"Folder source {source_id} not found"
        )

    # Parquet キャッシュを無効化（データソースの場合）
    if source.source_type == "data":
        from app.services.duckdb_query import invalidate_parquet_cache

        invalidate_parquet_cache(source_id)

    await db.delete(source)
    await db.flush()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# ドキュメント CRUD
# ---------------------------------------------------------------------------


@router.get("/", response_model=dict)
async def list_documents(
    knowledge_base_id: str = Query(..., description="ナレッジベース ID"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tag: str | None = Query(default=None, description="フィルタするタグ"),
    status: str | None = Query(
        default=None, description="インデックスステータスフィルタ"
    ),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """ドキュメント一覧を取得する（ソフトデリート済みは除外）。"""
    query = select(Document).where(
        Document.knowledge_base_id == knowledge_base_id,
        Document.deleted_at.is_(None),
    )

    if status is not None:
        query = query.where(Document.status == status)

    # タグフィルタ
    if tag is not None:
        query = query.join(DocumentTag).where(DocumentTag.tag_value == tag)

    # 総件数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # ページネーション
    query = query.order_by(Document.uploaded_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()

    doc_responses = []
    for doc in docs:
        tags = await _get_tags_for_document(doc.id, db)
        doc_responses.append(_doc_to_response(doc, tags))

    return {
        "documents": doc_responses,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{id}", response_model=DocumentDetailResponse)
async def get_document(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    """指定ドキュメントの詳細を取得する。"""
    doc = await _get_doc_or_404(id, db)
    tags = await _get_tags_for_document(id, db)
    tag_list = [
        DocumentTagResponse(
            id=t.id,
            tag_key=t.tag_key,
            tag_value=t.tag_value,
            confidence=t.confidence,
            ai_suggested=bool(t.ai_suggested),
            confirmed=bool(t.confirmed),
        )
        for t in tags
    ]
    return DocumentDetailResponse(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        filename=doc.filename,
        file_type=doc.file_type,
        status=doc.status,
        version=doc.version,
        retry_count=doc.retry_count,
        deleted_at=doc.deleted_at,
        uploaded_by=doc.uploaded_by,
        uploaded_at=doc.uploaded_at,
        tags=tag_list,
        converted_md=doc.converted_md,
        parent_document_id=doc.parent_document_id,
    )


@router.patch("/{id}/tags", status_code=200, response_model=DocumentResponse)
async def update_document_tags(
    id: str = Path(..., description="ドキュメント ID"),
    body: UpdateTagsRequest = ...,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """指定ドキュメントのタグを更新する。"""
    doc = await _get_doc_or_404(id, db)

    # 既存タグを削除
    existing_tags = await _get_tags_for_document(id, db)
    for t in existing_tags:
        await db.delete(t)

    # 新タグを追加
    for tag_item in body.tags:
        tag = DocumentTag(
            document_id=id,
            tag_key=tag_item.tag_key,
            tag_value=tag_item.tag_value,
            confidence=1.0,
            ai_suggested=0,
            confirmed=1 if tag_item.confirmed else 0,
        )
        db.add(tag)

    await db.flush()
    new_tags = await _get_tags_for_document(id, db)
    return _doc_to_response(doc, new_tags)


@router.patch("/batch-tags", status_code=200)
async def batch_update_tags(
    body: BatchTagUpdateRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """複数ドキュメントのタグを一括更新し、確定後にチャンク+インデックス処理を開始する。"""
    confirmed_ids: list[str] = []

    for item in body.documents:
        doc_result = await db.execute(
            select(Document).where(Document.id == item.document_id)
        )
        doc = doc_result.scalar_one_or_none()
        if doc is None:
            continue

        # 既存タグ削除
        existing = await _get_tags_for_document(item.document_id, db)
        for t in existing:
            await db.delete(t)

        # 新タグ追加
        for tag_item in item.tags:
            tag = DocumentTag(
                document_id=item.document_id,
                tag_key=tag_item.tag_key,
                tag_value=tag_item.tag_value,
                confidence=1.0,
                ai_suggested=0,
                confirmed=1,
            )
            db.add(tag)

        doc.status = "confirmed"
        confirmed_ids.append(item.document_id)

    await db.flush()

    # 確定済みドキュメントのチャンク+インデックス処理をバックグラウンドで開始
    for doc_id in confirmed_ids:
        background_tasks.add_task(
            _run_post_tag_pipeline,
            doc_id,
        )

    return {"confirmed": confirmed_ids}


async def _collect_previous_version_ids(
    document_id: str, db: AsyncSession
) -> list[str]:
    """対象ドキュメントの祖先（旧バージョン）ドキュメント ID 一覧を返す。

    Document.parent_document_id を辿って同一バージョン階層に属する祖先を全て収集する。
    （新規アップロードで親が無い場合は空リストを返す。）
    """
    ancestors: list[str] = []
    current_result = await db.execute(
        select(Document.parent_document_id).where(Document.id == document_id)
    )
    current_parent = current_result.scalar_one_or_none()
    visited: set[str] = {document_id}

    while current_parent is not None and current_parent not in visited:
        ancestors.append(current_parent)
        visited.add(current_parent)
        next_result = await db.execute(
            select(Document.parent_document_id).where(Document.id == current_parent)
        )
        current_parent = next_result.scalar_one_or_none()

    return ancestors


async def _run_post_tag_pipeline(document_id: str) -> None:
    """タグ確定後のチャンク+インデックス処理パイプライン。"""
    from app.services.chunker import chunk_document
    from app.services.embedder import (
        embed_chunks,
        mark_previous_versions_not_latest,
        upsert_embedded_chunks,
    )

    async with AsyncSessionLocal() as db:
        try:
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc is None or doc.converted_md is None:
                return

            # Chunking
            doc.status = "chunking"
            await db.commit()

            chunks = chunk_document(text=doc.converted_md, document_id=document_id)

            doc.status = "chunked"
            await db.commit()

            # Indexing
            doc.status = "indexing"
            await db.commit()

            embedded = await embed_chunks(chunks)

            tags_result = await db.execute(
                select(DocumentTag).where(DocumentTag.document_id == document_id)
            )
            doc_tags = list(tags_result.scalars().all())
            tag_dict: dict[str, list[str]] = {}
            for t in doc_tags:
                tag_dict.setdefault(t.tag_key, []).append(t.tag_value)

            # 旧バージョン（parent_document_id でリンクされた祖先群）の Qdrant ベクトルを
            # is_latest=False に切り替え、検索対象から除外する。
            # 物理削除はせず、バージョン履歴閲覧は引き続き可能とする。
            previous_ids = await _collect_previous_version_ids(document_id, db)
            if previous_ids:
                logger.info(
                    "旧バージョンの is_latest 切替: document_id=%s, previous_ids=%s",
                    document_id,
                    previous_ids,
                )
                try:
                    mark_previous_versions_not_latest(previous_ids)
                except Exception:
                    # Qdrant 側エラーがあっても新バージョンの indexing 自体は続行する。
                    logger.exception(
                        "旧バージョン無効化に失敗しました (document_id=%s)",
                        document_id,
                    )

            upsert_embedded_chunks(
                embedded_chunks=embedded,
                document_id=document_id,
                knowledge_base_id=doc.knowledge_base_id,
                tags=tag_dict,
                is_latest=True,
            )

            doc.status = "indexed"
            await db.commit()
            logger.info("Post-tag pipeline completed for %s", document_id)
        except Exception:
            logger.exception("Post-tag pipeline failed for %s", document_id)
            doc_result = await db.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = doc_result.scalar_one_or_none()
            if doc:
                doc.status = "index_failed"
                doc.retry_count += 1
                if doc.retry_count >= config.MAX_RETRY_COUNT:
                    doc.status = "permanent_failed"
                await db.commit()


@router.post("/{id}/reindex", status_code=202)
async def reindex_document(
    background_tasks: BackgroundTasks,
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """指定ドキュメントの再インデックス処理を開始する。"""
    doc = await _get_doc_or_404(id, db)

    if doc.status == "permanent_failed":
        raise HTTPException(
            status_code=400,
            detail="Document has permanently failed. Please delete and re-upload.",
        )

    if doc.retry_count >= config.MAX_RETRY_COUNT:
        doc.status = "permanent_failed"
        await db.flush()
        raise HTTPException(
            status_code=400,
            detail="Maximum retry count reached. Document marked as permanent_failed.",
        )

    # 既存 Qdrant ベクトルを削除
    try:
        qdrant.delete_by_document_id(id)
    except Exception:
        logger.exception("Failed to delete existing vectors for %s", id)

    # 変換済み（tagged/converted/confirmed/chunked）の場合はチャンク+インデックスのみ実行
    has_converted_content = doc.converted_md is not None and doc.status in {
        "tagged",
        "converted",
        "confirmed",
        "chunked",
        "indexed",
        "index_failed",
    }

    if has_converted_content:
        doc.status = "confirmed"
        await db.flush()
        background_tasks.add_task(_run_post_tag_pipeline, id)
    else:
        doc.status = "processing"
        await db.flush()
        background_tasks.add_task(
            _run_indexing_pipeline, id, doc.original_path, doc.filename
        )

    return {"document_id": id, "status": "reindex_started"}


@router.post("/{id}/cancel", status_code=202)
async def cancel_indexing(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """指定ドキュメントのインデックス処理をキャンセルする。"""
    doc = await _get_doc_or_404(id, db)

    processing_statuses = {
        "processing",
        "converting",
        "tagging",
        "chunking",
        "indexing",
    }
    if doc.status not in processing_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel document in status '{doc.status}'",
        )

    _cancel_flags[id] = True
    return {"document_id": id, "status": "cancel_requested"}


@router.delete("/{id}", status_code=204, response_class=Response)
async def soft_delete_document(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """指定ドキュメントをソフトデリートする（復元可能）。"""
    doc = await _get_doc_or_404(id, db)

    if doc.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Document is already deleted")

    doc.deleted_at = _now_iso()
    await db.flush()
    return Response(status_code=204)


@router.post("/{id}/restore", status_code=200, response_model=DocumentResponse)
async def restore_document(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """ソフトデリートされたドキュメントを復元する。"""
    doc = await _get_doc_or_404(id, db)

    if doc.deleted_at is None:
        raise HTTPException(status_code=400, detail="Document is not deleted")

    doc.deleted_at = None
    await db.flush()

    tags = await _get_tags_for_document(id, db)
    return _doc_to_response(doc, tags)


@router.delete("/{id}/permanent", status_code=204, response_class=Response)
async def permanent_delete_document(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """指定ドキュメントを物理削除する（復元不可）。Qdrant のベクトルも削除する。"""
    doc = await _get_doc_or_404(id, db)

    # Qdrant ベクトル削除
    try:
        qdrant.delete_by_document_id(id)
        logger.info("Deleted Qdrant vectors for document_id=%s", id)
    except Exception:
        logger.exception("Failed to delete Qdrant vectors for document_id=%s", id)

    # ファイル削除 (UPLOAD_DIR 配下に realpath が留まっていることを確認する)
    # safe_remove_within が is_within_root チェック・存在確認・削除失敗時の
    # 例外ログを内部で実施する。
    if doc.original_path:
        safe_remove_within(doc.original_path, config.UPLOAD_DIR)

    await db.delete(doc)
    logger.info("Permanently deleted document id=%s", id)
    return Response(status_code=204)


@router.get("/{id}/versions", response_model=list[VersionResponse])
async def get_document_versions(
    id: str = Path(..., description="ドキュメント ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[VersionResponse]:
    """指定ドキュメントのバージョン履歴を取得する。"""
    doc = await _get_doc_or_404(id, db)

    # 同一ファイル名のドキュメントをバージョン順で取得
    result = await db.execute(
        select(Document)
        .where(
            Document.knowledge_base_id == doc.knowledge_base_id,
            Document.filename == doc.filename,
        )
        .order_by(Document.version.desc())
    )
    versions = result.scalars().all()

    return [
        VersionResponse(
            id=v.id,
            version=v.version,
            filename=v.filename,
            status=v.status,
            uploaded_at=v.uploaded_at,
        )
        for v in versions
    ]
