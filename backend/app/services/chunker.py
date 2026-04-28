"""
テキストチャンキングサービスモジュール。
ドキュメントをベクトル検索に適したチャンクに分割する。
見出し階層に基づく構造的チャンキングと親子関係の構築をサポートする。
"""

import re
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class ChunkingConfig:
    """チャンキング設定を保持するデータクラス。"""

    max_tokens: int = 512
    overlap: int = 64


@dataclass
class TextChunk:
    """テキストチャンクを表すデータクラス。"""

    content: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict
    parent_chunk_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    chunk_id: str = field(default_factory=lambda: str(uuid4()))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|", re.MULTILINE)
_IMAGE_MARKER_RE = re.compile(r"\[\[IMAGE:[0-9a-f-]+\]\]")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。．！？!?])\s*|(?<=\.)\s+")


def _count_tokens(text: str) -> int:
    """
    簡易トークン数推定。
    日本語文字は1文字1トークン、ASCII単語は空白区切りでカウントする。
    厳密な tokenizer への依存を避けるため近似値として使用する。
    """
    # 日本語・中国語等の CJK 文字は1文字1トークンとして扱う
    cjk_count = sum(
        1
        for ch in text
        if "\u3000" <= ch or "\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff"
    )
    ascii_words = len(text.split()) if text.strip() else 0
    # CJK 以外の文字数から ASCII 単語数を引いた残りは文字単位で近似
    return max(cjk_count + ascii_words, len(text) // 4)


def _split_on_natural_boundary(text: str, max_chars: int) -> tuple[str, str]:
    """
    max_chars 以内で自然な境界（段落 → 文末 → 空白）でテキストを二分する。

    Returns:
        (head, tail) のタプル。head は max_chars 以内の先頭部分、
        tail は残りのテキスト。
    """
    if len(text) <= max_chars:
        return text, ""

    candidate = text[:max_chars]

    # 1. 段落境界を優先
    para_pos = candidate.rfind("\n\n")
    if para_pos > max_chars // 4:
        return text[: para_pos + 2].rstrip(), text[para_pos + 2 :].lstrip()

    # 2. 改行境界
    nl_pos = candidate.rfind("\n")
    if nl_pos > max_chars // 4:
        return text[:nl_pos].rstrip(), text[nl_pos + 1 :].lstrip()

    # 3. 文末境界
    matches = list(_SENTENCE_BOUNDARY_RE.finditer(candidate))
    if matches:
        last = matches[-1]
        pos = last.end()
        if pos > max_chars // 4:
            return text[:pos].rstrip(), text[pos:].lstrip()

    # 4. 空白境界
    space_pos = candidate.rfind(" ")
    if space_pos > max_chars // 4:
        return text[:space_pos].rstrip(), text[space_pos + 1 :].lstrip()

    # 5. フォールバック: 強制分割
    return text[:max_chars], text[max_chars:]


def _extract_table_blocks(text: str) -> list[tuple[int, int, str]]:
    """
    テキスト中のテーブルブロックの位置と内容を抽出する。

    Returns:
        (start, end, table_text) のリスト。
    """
    tables: list[tuple[int, int, str]] = []
    lines = text.split("\n")
    in_table = False
    table_start = 0
    table_start_char = 0
    char_offset = 0

    for i, line in enumerate(lines):
        line_len = len(line) + 1  # +1 for the newline
        if _TABLE_ROW_RE.match(line):
            if not in_table:
                in_table = True
                table_start = i
                table_start_char = char_offset
        else:
            if in_table:
                table_text = "\n".join(lines[table_start:i])
                tables.append((table_start_char, char_offset - 1, table_text))
                in_table = False
        char_offset += line_len

    if in_table:
        table_text = "\n".join(lines[table_start:])
        tables.append((table_start_char, char_offset, table_text))

    return tables


def _find_surrounding_header(text: str, pos: int) -> str:
    """pos より前にある直近の見出し行を返す。見つからない場合は空文字列。"""
    preceding = text[:pos]
    headers = _HEADER_RE.findall(preceding)
    if headers:
        level, title = headers[-1]
        return f"{'#' * len(level)} {title}"
    return ""


# ---------------------------------------------------------------------------
# Public chunking strategies
# ---------------------------------------------------------------------------


def chunk_markdown(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    document_id: str = "",
) -> list[TextChunk]:
    """
    Markdown テキストを見出し階層に基づいて構造的にチャンク分割する。

    見出しレベルに応じた親子関係を構築する:
    - # (H1) → ルートセクション（親チャンク）
    - ## (H2) → H1 の子チャンク
    - ### (H3) → H2 の孫チャンク（H2 がなければ H1 の子）

    セクション内容が chunk_size を超える場合はさらに分割し、
    先頭チャンクが親・後続チャンクが子となる。

    Args:
        text: 分割対象の Markdown テキスト。
        chunk_size: チャンクあたりの最大文字数。
        chunk_overlap: 隣接チャンク間のオーバーラップ文字数。
        document_id: チャンクのメタデータに付与するドキュメント ID。

    Returns:
        TextChunk オブジェクトのリスト（chunk_index 昇順）。
    """
    if not text.strip():
        return []

    # --- セクションの解析 ---
    # 各セクションを (header_level, header_text, body, start_char) で表す
    sections: list[tuple[int, str, str, int]] = []

    matches = list(_HEADER_RE.finditer(text))
    for idx, m in enumerate(matches):
        level = len(m.group(1))
        header_text = m.group(2).strip()
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((level, header_text, body, m.start()))

    # 見出しの前にあるプリアンブルを扱う
    if matches:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.insert(0, (0, "", preamble, 0))
    else:
        # 見出しが全くない場合は plain text にフォールバック
        return chunk_plain_text(text, chunk_size, chunk_overlap, document_id)

    chunks: list[TextChunk] = []
    chunk_index = 0
    # level -> 直近の親 chunk_id のマッピング
    parent_map: dict[int, str] = {}

    def _make_chunks_for_section(
        header_prefix: str,
        body: str,
        section_start: int,
        parent_chunk_id: str | None,
        level: int,
    ) -> list[TextChunk]:
        """
        1 セクション分のチャンクリストを生成する。
        body が chunk_size を超える場合はさらに分割し、
        先頭チャンクが親・後続チャンクが子となる。
        """
        nonlocal chunk_index

        full_text = (header_prefix + "\n\n" + body).strip() if header_prefix else body
        if not full_text:
            return []

        result: list[TextChunk] = []
        remaining = full_text
        char_pos = section_start
        first_chunk_id: str | None = None

        while remaining:
            head, tail = _split_on_natural_boundary(remaining, chunk_size)
            if not head:
                head = remaining
                tail = ""

            cid = str(uuid4())
            # 先頭チャンクは渡された parent を継承、後続は先頭チャンクを親とする
            effective_parent = (
                parent_chunk_id if first_chunk_id is None else first_chunk_id
            )

            chunk = TextChunk(
                content=head,
                chunk_index=chunk_index,
                start_char=char_pos,
                end_char=char_pos + len(head),
                metadata={
                    "document_id": document_id,
                    "section_level": level,
                    "section_title": header_prefix.lstrip("# ").strip(),
                },
                parent_chunk_id=effective_parent,
                children_ids=[],
                chunk_id=cid,
            )
            result.append(chunk)
            chunk_index += 1

            if first_chunk_id is None:
                first_chunk_id = cid

            char_pos += len(head)
            if tail and chunk_overlap > 0:
                # オーバーラップ: tail の先頭から overlap 文字分を次チャンクに含める
                overlap_text = (
                    head[-chunk_overlap:] if len(head) >= chunk_overlap else head
                )
                remaining = overlap_text + tail
                char_pos -= len(overlap_text)
            else:
                remaining = tail

        return result

    for level, header_text, body, sec_start in sections:
        if level == 0:
            # プリアンブル: 親なし
            new_chunks = _make_chunks_for_section("", body, sec_start, None, 0)
        else:
            # この見出しの親レベルを特定: 直近の低いレベルを探す
            parent_level = max((lvl for lvl in parent_map if lvl < level), default=None)
            parent_id = parent_map[parent_level] if parent_level is not None else None
            header_prefix = "#" * level + " " + header_text
            new_chunks = _make_chunks_for_section(
                header_prefix, body, sec_start, parent_id, level
            )

        if new_chunks:
            # parent_map を更新: このセクションの先頭チャンクをこのレベルの親とする
            if level > 0:
                parent_map[level] = new_chunks[0].chunk_id
                # このレベル以下のエントリをクリア（兄弟セクションに誤って引き継がれないよう）
                for lvl in list(parent_map.keys()):
                    if lvl > level:
                        del parent_map[lvl]

            # 親チャンクの children_ids を更新する
            for ch in new_chunks:
                if ch.parent_chunk_id is not None:
                    # 既存チャンクの中から親を探す
                    for parent_ch in chunks:
                        if parent_ch.chunk_id == ch.parent_chunk_id:
                            parent_ch.children_ids.append(ch.chunk_id)
                            break

            chunks.extend(new_chunks)

    return chunks


def chunk_plain_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    document_id: str = "",
) -> list[TextChunk]:
    """
    プレーンテキストをスライディングウィンドウ方式でチャンクに分割する。
    段落・文末境界を優先して分割点を選択する。

    Args:
        text: 分割対象のプレーンテキスト。
        chunk_size: チャンクあたりの最大文字数。
        chunk_overlap: 隣接チャンク間のオーバーラップ文字数。
        document_id: チャンクのメタデータに付与するドキュメント ID。

    Returns:
        TextChunk オブジェクトのリスト（chunk_index 昇順）。
    """
    if not text.strip():
        return []

    # テキスト全体が chunk_size 以下なら単一チャンク
    if len(text) <= chunk_size:
        return [
            TextChunk(
                content=text.strip(),
                chunk_index=0,
                start_char=0,
                end_char=len(text),
                metadata={"document_id": document_id},
                parent_chunk_id=None,
                children_ids=[],
                chunk_id=str(uuid4()),
            )
        ]

    chunks: list[TextChunk] = []
    chunk_index = 0
    remaining = text
    char_pos = 0

    while remaining.strip():
        head, tail = _split_on_natural_boundary(remaining, chunk_size)
        if not head.strip():
            # 残りが空白のみ
            break

        chunk = TextChunk(
            content=head.strip(),
            chunk_index=chunk_index,
            start_char=char_pos,
            end_char=char_pos + len(head),
            metadata={"document_id": document_id},
            parent_chunk_id=None,
            children_ids=[],
            chunk_id=str(uuid4()),
        )
        chunks.append(chunk)
        chunk_index += 1

        if not tail.strip():
            break

        # オーバーラップを適用して次チャンクの開始位置を調整する
        if chunk_overlap > 0:
            overlap_text = head[-chunk_overlap:] if len(head) >= chunk_overlap else head
            char_advance = len(head) - len(overlap_text)
            char_pos += char_advance
            remaining = overlap_text + tail
        else:
            char_pos += len(head)
            remaining = tail

    return chunks


def _chunk_table_aware(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    document_id: str,
) -> list[TextChunk]:
    """
    テーブルを含むテキストを分割する。
    テーブルブロックは分割せず 1 チャンクとして扱い、
    周囲のセクションコンテキストをメタデータに保持する。

    Args:
        text: 分割対象のテキスト（テーブルを含む Markdown）。
        chunk_size: チャンクあたりの最大文字数。
        chunk_overlap: 隣接チャンク間のオーバーラップ文字数。
        document_id: チャンクのメタデータに付与するドキュメント ID。

    Returns:
        TextChunk オブジェクトのリスト。
    """
    if not text.strip():
        return []

    tables = _extract_table_blocks(text)
    if not tables:
        return chunk_plain_text(text, chunk_size, chunk_overlap, document_id)

    chunks: list[TextChunk] = []
    chunk_index = 0
    cursor = 0

    for tbl_start, tbl_end, tbl_text in tables:
        # テーブル前のテキストを plain text として分割
        pre_text = text[cursor:tbl_start]
        if pre_text.strip():
            pre_chunks = chunk_plain_text(
                pre_text, chunk_size, chunk_overlap, document_id
            )
            for ch in pre_chunks:
                ch.chunk_index = chunk_index
                ch.start_char += cursor
                ch.end_char += cursor
                chunk_index += 1
            chunks.extend(pre_chunks)

        # 周囲の見出しコンテキストを取得する
        surrounding_header = _find_surrounding_header(text, tbl_start)

        # テーブルチャンク（分割しない）
        tbl_chunk = TextChunk(
            content=tbl_text,
            chunk_index=chunk_index,
            start_char=tbl_start,
            end_char=tbl_end,
            metadata={
                "document_id": document_id,
                "content_type": "table",
                "section_context": surrounding_header,
            },
            parent_chunk_id=None,
            children_ids=[],
            chunk_id=str(uuid4()),
        )
        chunks.append(tbl_chunk)
        chunk_index += 1
        cursor = tbl_end

    # テーブル後の残りテキスト
    post_text = text[cursor:]
    if post_text.strip():
        post_chunks = chunk_plain_text(
            post_text, chunk_size, chunk_overlap, document_id
        )
        for ch in post_chunks:
            ch.chunk_index = chunk_index
            ch.start_char += cursor
            ch.end_char += cursor
            chunk_index += 1
        chunks.extend(post_chunks)

    return chunks


def _chunk_image_aware(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    document_id: str,
) -> list[TextChunk]:
    """
    [[IMAGE:uuid]] マーカーを含むテキストを分割する。
    画像マーカーは前後のコンテキストテキストと一緒にチャンク化される。
    チャンクに画像が含まれる場合、メタデータに image_ids を記録する。

    Args:
        text: 分割対象のテキスト（[[IMAGE:uuid]] マーカーを含む）。
        chunk_size: チャンクあたりの最大文字数。
        chunk_overlap: 隣接チャンク間のオーバーラップ文字数。
        document_id: チャンクのメタデータに付与するドキュメント ID。

    Returns:
        TextChunk オブジェクトのリスト。
    """
    if not text.strip():
        return []

    # まず plain text としてチャンク化し、各チャンクに画像 ID を付与する
    base_chunks = chunk_plain_text(text, chunk_size, chunk_overlap, document_id)

    for ch in base_chunks:
        image_ids = _IMAGE_MARKER_RE.findall(ch.content)
        if image_ids:
            # "[[IMAGE:uuid]]" から uuid 部分を抽出する
            uuids = [m[len("[[IMAGE:") : -2] for m in image_ids]
            ch.metadata["image_ids"] = uuids
            ch.metadata["content_type"] = "image_context"

    return base_chunks


# ---------------------------------------------------------------------------
# Content-type detection
# ---------------------------------------------------------------------------


def _has_headers(text: str) -> bool:
    """テキストに Markdown 見出し（#）が含まれているかを判定する。"""
    return bool(_HEADER_RE.search(text))


def _has_tables(text: str) -> bool:
    """テキストに Markdown テーブル行が含まれているかを判定する。"""
    return bool(_TABLE_ROW_RE.search(text))


def _has_images(text: str) -> bool:
    """テキストに [[IMAGE:uuid]] マーカーが含まれているかを判定する。"""
    return bool(_IMAGE_MARKER_RE.search(text))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def chunk_document(
    text: str,
    document_id: str,
    config: ChunkingConfig | None = None,
) -> list[TextChunk]:
    """
    ドキュメントテキストをコンテンツタイプに応じて適切な戦略でチャンク分割する。

    コンテンツタイプの判定優先順位:
    1. 見出し（#, ##, ###）がある → 構造的チャンキング（chunk_markdown）
    2. テーブル行（|...|）がある → テーブル考慮チャンキング
    3. [[IMAGE:uuid]] マーカーがある → 画像考慮チャンキング
    4. それ以外 → プレーンテキストのスライディングウィンドウ（chunk_plain_text）

    Args:
        text: 分割対象のドキュメントテキスト。
        document_id: チャンクのメタデータに付与するドキュメント ID。
        config: チャンキング設定（None の場合はデフォルト設定を使用）。

    Returns:
        TextChunk オブジェクトのリスト（chunk_index 昇順）。
        空テキストの場合は空リストを返す。
    """
    if not text or not text.strip():
        return []

    cfg = config if config is not None else ChunkingConfig()
    chunk_size = cfg.max_tokens
    chunk_overlap = cfg.overlap

    if _has_headers(text):
        return chunk_markdown(text, chunk_size, chunk_overlap, document_id)

    if _has_tables(text):
        return _chunk_table_aware(text, chunk_size, chunk_overlap, document_id)

    if _has_images(text):
        return _chunk_image_aware(text, chunk_size, chunk_overlap, document_id)

    return chunk_plain_text(text, chunk_size, chunk_overlap, document_id)
