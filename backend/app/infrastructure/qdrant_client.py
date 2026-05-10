"""
Qdrant ベクトルデータベースクライアントモジュール。
documents と master_data コレクションの CRUD 操作を提供する。
"""

import logging
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    OptimizersConfigDiff,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
    SearchParams,
    NamedVector,
    NamedSparseVector,
    SparseVector,
)

from app.infrastructure.config import config

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


@dataclass
class SearchResult:
    id: str
    score: float
    payload: dict


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client singleton."""
    global _client
    if _client is None:
        _client = QdrantClient(
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
            grpc_port=config.QDRANT_GRPC_PORT,
            prefer_grpc=True,
        )
    return _client


def init_collections() -> None:
    """Create collections if they don't exist."""
    client = get_qdrant_client()
    collections = {c.name for c in client.get_collections().collections}

    # documents collection
    if config.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config={
                "dense": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(),
            },
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=10000,
            ),
            on_disk_payload=True,
        )
        # Create payload indexes for filtering
        for field, schema in [
            ("is_latest", PayloadSchemaType.BOOL),
            ("knowledge_base_id", PayloadSchemaType.KEYWORD),
            ("site_code", PayloadSchemaType.KEYWORD),
            ("line_code", PayloadSchemaType.KEYWORD),
            ("process_codes", PayloadSchemaType.KEYWORD),
            ("document_id", PayloadSchemaType.KEYWORD),
        ]:
            client.create_payload_index(
                collection_name=config.QDRANT_COLLECTION,
                field_name=field,
                field_schema=schema,
            )
        logger.info("Created '%s' collection with indexes", config.QDRANT_COLLECTION)

    # master_data collection
    if config.QDRANT_MASTER_COLLECTION not in collections:
        client.create_collection(
            collection_name=config.QDRANT_MASTER_COLLECTION,
            vectors_config=VectorParams(
                size=1024,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created '%s' collection", config.QDRANT_MASTER_COLLECTION)


def upsert_vectors(
    collection: str,
    points: list[PointStruct],
    batch_size: int = 100,
) -> None:
    """Upsert vectors in batches."""
    client = get_qdrant_client()
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(
            collection_name=collection,
            points=batch,
        )
    logger.info("Upserted %d points to '%s'", len(points), collection)


def search_vectors(
    collection: str,
    query_vector: list[float],
    limit: int = 10,
    filters: Filter | None = None,
    score_threshold: float | None = None,
) -> list[SearchResult]:
    """密ベクトルで検索する。

    documents コレクションは named vector "dense"、master_data コレクションは
    unnamed vector を使用する。スパース検索は search_sparse_vectors を使う。

    Args:
        collection: 検索対象コレクション名。
        query_vector: 密クエリベクトル（1024 次元）。
        limit: 取得件数の上限。
        filters: 適用する Qdrant フィルタ。
        score_threshold: コサイン類似度の下限（None なら制限なし）。

    Returns:
        SearchResult のリスト（スコア降順）。
    """
    client = get_qdrant_client()

    if collection == config.QDRANT_MASTER_COLLECTION:
        # master_data uses unnamed vector
        results = client.search(
            collection_name=collection,
            query_vector=query_vector,
            query_filter=filters,
            limit=limit,
            score_threshold=score_threshold,
        )
    else:
        results = client.search(
            collection_name=collection,
            query_vector=NamedVector(name="dense", vector=query_vector),
            query_filter=filters,
            limit=limit,
            score_threshold=score_threshold,
            search_params=SearchParams(exact=False, hnsw_ef=128),
        )

    return [
        SearchResult(
            id=str(r.id),
            score=r.score,
            payload=r.payload or {},
        )
        for r in results
    ]


def search_sparse_vectors(
    collection: str,
    sparse_indices: list[int],
    sparse_values: list[float],
    limit: int = 10,
    filters: Filter | None = None,
) -> list[SearchResult]:
    """疎ベクトル（named sparse vector "sparse"）で検索する。

    documents コレクションの "sparse" インデックスに対して term-frequency ベースの
    キーワード一致検索を行う。密検索（search_vectors）と組み合わせて
    呼び出し側で RRF 融合することでハイブリッド検索を実現する。

    Args:
        collection: 検索対象コレクション名（documents を想定）。
        sparse_indices: 疎クエリベクトルのインデックスリスト。
        sparse_values: 疎クエリベクトルの値リスト（indices と同長）。
        limit: 取得件数の上限。
        filters: 適用する Qdrant フィルタ。

    Returns:
        SearchResult のリスト（スコア降順）。indices が空の場合は空リスト。
    """
    if not sparse_indices:
        return []

    client = get_qdrant_client()
    results = client.search(
        collection_name=collection,
        query_vector=NamedSparseVector(
            name="sparse",
            vector=SparseVector(indices=sparse_indices, values=sparse_values),
        ),
        query_filter=filters,
        limit=limit,
    )

    return [
        SearchResult(
            id=str(r.id),
            score=r.score,
            payload=r.payload or {},
        )
        for r in results
    ]


def delete_vectors(
    collection: str,
    filter_conditions: Filter,
) -> None:
    """Delete vectors matching filter conditions."""
    client = get_qdrant_client()
    client.delete(
        collection_name=collection,
        points_selector=filter_conditions,
    )
    logger.info("Deleted vectors from '%s'", collection)


def delete_by_document_id(document_id: str) -> None:
    """Delete all vectors for a specific document."""
    delete_vectors(
        collection=config.QDRANT_COLLECTION,
        filter_conditions=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
    )


def delete_by_knowledge_base_id(knowledge_base_id: str) -> None:
    """Delete all vectors for a specific knowledge base (cascade delete)."""
    delete_vectors(
        collection=config.QDRANT_COLLECTION,
        filter_conditions=Filter(
            must=[
                FieldCondition(
                    key="knowledge_base_id",
                    match=MatchValue(value=knowledge_base_id),
                )
            ]
        ),
    )


def build_search_filter(
    knowledge_base_id: str,
    site_code: str | None = None,
    line_code: str | None = None,
    process_codes: list[str] | None = None,
    exclude_document_ids: list[str] | None = None,
) -> Filter:
    """Build a Qdrant filter for scoped search."""
    must_conditions = [
        FieldCondition(key="is_latest", match=MatchValue(value=True)),
        FieldCondition(
            key="knowledge_base_id", match=MatchValue(value=knowledge_base_id)
        ),
    ]

    if site_code:
        must_conditions.append(
            FieldCondition(key="site_code", match=MatchValue(value=site_code))
        )
    if line_code:
        must_conditions.append(
            FieldCondition(key="line_code", match=MatchValue(value=line_code))
        )
    if process_codes:
        for code in process_codes:
            must_conditions.append(
                FieldCondition(key="process_codes", match=MatchValue(value=code))
            )

    must_not_conditions = []
    if exclude_document_ids:
        for doc_id in exclude_document_ids:
            must_not_conditions.append(
                FieldCondition(key="document_id", match=MatchValue(value=doc_id))
            )

    return Filter(
        must=must_conditions,
        must_not=must_not_conditions if must_not_conditions else None,
    )
