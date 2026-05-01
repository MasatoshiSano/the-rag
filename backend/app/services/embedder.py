"""
埋め込みベクトル生成サービスモジュール。
テキストチャンクを密・疎の両ベクトルに変換し Qdrant に保存する。

密ベクトル: AWS Bedrock の Cohere Embed Multilingual v3 (1024次元)
疎ベクトル: TF ベースの term hashing（collections.Counter を使用）
"""

import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass

from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    SparseVector,
)

from app.infrastructure import bedrock_client
from app.infrastructure import qdrant_client as qdrant_infra
from app.infrastructure.config import config
from app.services.chunker import TextChunk
from app.services.text_normalizer import normalize_text

logger = logging.getLogger(__name__)

# 疎ベクトルのインデックス衝突を避けるためのハッシュ空間サイズ
_SPARSE_HASH_SPACE: int = 2**31


@dataclass
class EmbeddedChunk:
    """埋め込み済みチャンクを表すデータクラス。

    Attributes:
        chunk: 元の TextChunk オブジェクト。
        dense_vector: Cohere Embed による 1024 次元の密ベクトル。
        sparse_indices: 疎ベクトルのインデックスリスト（term ハッシュ値）。
        sparse_values: 疎ベクトルの値リスト（TF 正規化済み）。
    """

    chunk: TextChunk
    dense_vector: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


def generate_sparse_vector(text: str) -> tuple[list[int], list[float]]:
    """テキストから TF ベースの疎ベクトルを生成する。

    トークン化はホワイトスペースおよび句読点で分割する。
    各トークンのハッシュ値をインデックスとして使用し、
    正規化された Term Frequency を値として返す。

    Args:
        text: 疎ベクトル化対象のテキスト文字列。

    Returns:
        (indices, values) のタプル。
        indices: 各トークンのハッシュ値（正の整数、2**31 未満）。
        values: 各トークンの正規化 TF 値（0.0〜1.0）。

    Examples:
        >>> indices, values = generate_sparse_vector("hello world hello")
        >>> len(indices) == len(values)
        True
        >>> all(v > 0 for v in values)
        True
    """
    # NFKC 正規化してから小文字化
    normalized = normalize_text(text).lower()

    # ホワイトスペースおよび句読点（ASCII + Unicode 句読点）で分割
    tokens = re.split(r"[\s\W]+", normalized, flags=re.UNICODE)

    # 空文字列トークンを除去
    tokens = [t for t in tokens if t]

    if not tokens:
        return [], []

    # TF（Term Frequency）を Counter で計算
    term_counts: Counter[str] = Counter(tokens)
    total_count = sum(term_counts.values())

    indices: list[int] = []
    values: list[float] = []

    for term, count in term_counts.items():
        # 正の整数ハッシュインデックスを生成（2**31 未満に収める）
        idx = hash(term) % _SPARSE_HASH_SPACE
        tf = count / total_count
        indices.append(idx)
        values.append(tf)

    return indices, values


async def embed_chunks(
    chunks: list[TextChunk],
    batch_size: int = 96,
) -> list[EmbeddedChunk]:
    """テキストチャンクを密ベクトルと疎ベクトルに変換する。

    Bedrock Cohere Embed モデルを使用して密ベクトルを生成し、
    TF ベースの term hashing で疎ベクトルを生成する。
    バッチサイズは Cohere API の最大値である 96 に準拠する。

    Args:
        chunks: 埋め込み対象の TextChunk リスト。
        batch_size: バッチ処理のサイズ（最大 96、Cohere API 制限）。

    Returns:
        EmbeddedChunk オブジェクトのリスト（入力と同順）。

    Raises:
        ValueError: batch_size が 1 未満または 96 超の場合。
    """
    if not 1 <= batch_size <= 96:
        raise ValueError(
            f"batch_size は 1 以上 96 以下である必要があります。得られた値: {batch_size}"
        )

    if not chunks:
        return []

    embedded_chunks: list[EmbeddedChunk] = []

    # chunks を batch_size ごとに分割してバッチ処理
    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]

        # NFKC 正規化済みテキストを密ベクトル化に使用
        normalized_texts = [normalize_text(chunk.content) for chunk in batch]

        # Bedrock Cohere Embed で密ベクトルを一括取得（同期関数を非同期スレッドで実行）
        dense_vectors = await bedrock_client.embed_texts(normalized_texts)

        # 各チャンクの疎ベクトルを生成して EmbeddedChunk を構築
        for chunk, dense_vector in zip(batch, dense_vectors, strict=True):
            sparse_indices, sparse_values = generate_sparse_vector(chunk.content)
            embedded_chunks.append(
                EmbeddedChunk(
                    chunk=chunk,
                    dense_vector=dense_vector,
                    sparse_indices=sparse_indices,
                    sparse_values=sparse_values,
                )
            )

        logger.debug(
            "バッチ %d〜%d のチャンク埋め込みが完了しました（合計 %d チャンク）",
            batch_start,
            batch_start + len(batch) - 1,
            len(chunks),
        )

    logger.info("全 %d チャンクの埋め込みが完了しました", len(chunks))
    return embedded_chunks


def upsert_embedded_chunks(
    embedded_chunks: list[EmbeddedChunk],
    document_id: str,
    knowledge_base_id: str,
    tags: dict[str, str | list[str]],
    is_latest: bool = True,
) -> None:
    """埋め込み済みチャンクを Qdrant コレクションにアップサートする。

    各 EmbeddedChunk を PointStruct に変換して Qdrant に保存する。
    chunk_id を Qdrant のポイント ID として使用する。
    chunk_id がない場合は chunk_index ベースの決定論的 UUID を生成する。

    Args:
        embedded_chunks: アップサートする EmbeddedChunk のリスト。
        document_id: 対象ドキュメントの ID。
        knowledge_base_id: 対象ナレッジベースの ID。
        tags: ペイロードに含めるタグ辞書。
            キーには site_code、line_code、process_codes などを含む。
            値は文字列またはリスト（process_codes など）。
        is_latest: このバージョンのベクトルが最新かどうか。

    Examples:
        >>> upsert_embedded_chunks(
        ...     embedded_chunks=chunks,
        ...     document_id="doc-001",
        ...     knowledge_base_id="kb-001",
        ...     tags={"site_code": "S01", "line_code": "L01", "process_codes": ["P01", "P02"]},
        ...     is_latest=True,
        ... )
    """
    if not embedded_chunks:
        logger.warning("アップサートするチャンクがありません。処理をスキップします。")
        return

    # 親チャンク展開用: chunk_id → content のマップを構築
    chunk_content_map: dict[str, str] = {}
    for ec in embedded_chunks:
        chunk_content_map[ec.chunk.chunk_id] = ec.chunk.content

    points: list[PointStruct] = []

    for ec in embedded_chunks:
        chunk = ec.chunk

        # ポイント ID の決定: chunk_id を直接使用
        chunk_id_raw = chunk.chunk_id
        # Qdrant は有効な UUID を要求するため uuid5 で変換
        try:
            # 既に有効な UUID ならそのまま使用
            point_id = str(uuid.UUID(chunk_id_raw))
        except ValueError:
            # 有効な UUID でなければ決定論的に生成
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id_raw))

        # ペイロードを構築（固定フィールド）
        payload: dict = {
            "document_id": document_id,
            "knowledge_base_id": knowledge_base_id,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "chunk_id": chunk.chunk_id,
            "is_latest": is_latest,
            # metadata に格納された任意フィールドをペイロードにマージ
            **chunk.metadata,
        }

        # 親チャンク情報を追加（子チャンクの場合は parent_content を保存）
        if chunk.parent_chunk_id is not None:
            payload["parent_chunk_id"] = chunk.parent_chunk_id
            parent_content = chunk_content_map.get(chunk.parent_chunk_id)
            if parent_content is not None:
                payload["parent_content"] = parent_content

        # タグ辞書の全エントリをペイロードに展開（site_code, line_code, process_codes など）
        for tag_key, tag_value in tags.items():
            payload[tag_key] = tag_value

        # 疎ベクトルが空の場合はダミーの疎ベクトルを使用（Qdrant は空インデックスを許容するが明示的に扱う）
        if ec.sparse_indices:
            sparse_vec = SparseVector(
                indices=ec.sparse_indices,
                values=ec.sparse_values,
            )
        else:
            # テキストが空または記号のみの場合のフォールバック
            sparse_vec = SparseVector(indices=[0], values=[0.0])

        point = PointStruct(
            id=point_id,
            vector={
                "dense": ec.dense_vector,
                "sparse": sparse_vec,
            },
            payload=payload,
        )
        points.append(point)

    qdrant_infra.upsert_vectors(
        collection=config.QDRANT_COLLECTION,
        points=points,
    )
    logger.info(
        "document_id=%s の %d ポイントを Qdrant にアップサートしました",
        document_id,
        len(points),
    )


def mark_previous_versions_not_latest(previous_document_ids: list[str]) -> None:
    """指定したドキュメント ID 群の旧バージョンベクトルを is_latest=False に更新する。

    新しいバージョンを upsert する直前に呼び出すことで、同一バージョン階層に属する
    古いドキュメント ID のチャンクを検索対象から除外する（ソフトデプリケーション）。
    バージョンチェーンは Document.parent_document_id によって表現されるため、
    呼び出し側でルートを辿った祖先 ID 一覧を渡すこと。

    Qdrant フィルタは `must` 句で `is_latest=True` AND
    `document_id` が `previous_document_ids` のいずれかに一致するチャンクを対象とする。
    （`MatchAny` を使うことで、`should` 句による OR 表現を避けて意図を明示する。）

    Args:
        previous_document_ids: 旧バージョンとして無効化したいドキュメント ID のリスト。
            空リストの場合は何もしない。
    """
    if not previous_document_ids:
        return

    client = qdrant_infra.get_qdrant_client()

    # is_latest=True かつ document_id が previous_document_ids のいずれかに一致するベクトルが対象
    target_filter = Filter(
        must=[
            FieldCondition(
                key="is_latest",
                match=MatchValue(value=True),
            ),
            FieldCondition(
                key="document_id",
                match=MatchAny(any=previous_document_ids),
            ),
        ],
    )

    client.set_payload(
        collection_name=config.QDRANT_COLLECTION,
        payload={"is_latest": False},
        points=target_filter,
    )
    logger.info(
        "%d 件の旧バージョンドキュメント (ids=%s) のベクトルを is_latest=False に更新しました",
        len(previous_document_ids),
        previous_document_ids,
    )


# 後方互換: 単一 ID 指定の旧 API も残す（内部の reindex などでベクトル直接無効化用）。
def mark_previous_version_not_latest(document_id: str) -> None:
    """単一ドキュメント ID の is_latest=True ベクトルを is_latest=False に更新する。

    Args:
        document_id: 無効化対象のドキュメント ID。
    """
    mark_previous_versions_not_latest([document_id])
