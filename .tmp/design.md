# RAG Phantom - 技術設計書

**バージョン**: 1.0.0
**作成日**: 2026-03-19
**ステータス**: ドラフト

---

## 目次

1. [システムアーキテクチャ全体像](#1-システムアーキテクチャ全体像)
2. [バックエンド設計](#2-バックエンド設計)
   - 2.17 text_normalizer.py 設計（半角/全角カタカナ正規化）
   - 2.18 セッション横断キーワード検索設計
   - 2.19 複数ファイル一括アップロード設計
3. [フロントエンド設計](#3-フロントエンド設計)
4. [データフロー図](#4-データフロー図)
5. [Docker Compose 構成](#5-docker-compose-構成)
6. [Qdrant コレクション設計](#6-qdrant-コレクション設計)
7. [ボトルネックと対策](#7-ボトルネックと対策)

---

## 1. システムアーキテクチャ全体像

### 1.1 コンポーネント概要

RAG Phantom は製造業ナレッジ管理を目的とした RAG（Retrieval-Augmented Generation）システムである。フロントエンド・バックエンド・ベクターDB・メタデータDB・本番DBを分離したマイクロサービス指向の構成を採用する。

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                              Docker Compose Network                                │
│                                                                                    │
│  ┌─────────────────────┐        ┌──────────────────────────────────────────────┐  │
│  │   FRONTEND          │        │   BACKEND (FastAPI)                          │  │
│  │   Vite + React      │◄──────►│                                              │  │
│  │   Serendie DS       │  HTTP  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │   (Nginx :3000)     │  SSE   │  │ routers/ │  │services/ │  │  infra/  │  │  │
│  │                     │        │  │ chat.py  │  │  rag.py  │  │ config   │  │  │
│  │  ┌───────────────┐  │        │  │documents.py│ │ conv.py  │  │ db.py    │  │  │
│  │  │ TanStack Query│  │        │  │ users.py │  │ tagger   │  │ bedrock  │  │  │
│  │  │ Zustand       │  │        │  └──────────┘  │ chunker  │  │ qdrant   │  │  │
│  │  │ React Router  │  │        │                │ embedder │  └──────────┘  │  │
│  │  └───────────────┘  │        │                └──────────┘                │  │
│  └─────────────────────┘        └──────────┬────────────────┬────────────────┘  │
│                                             │                │                    │
│              ┌──────────────────────────────┼────────────────┼──────────────┐    │
│              │                              │                │              │    │
│  ┌───────────▼──────────┐    ┌─────────────▼──────┐   ┌────▼───────────┐  │    │
│  │   Qdrant             │    │   SQLite            │   │ Oracle DB      │  │    │
│  │   Vector DB :6333    │    │   (metadata)        │   │ (本番/品質DB)  │  │    │
│  │                      │    │                     │   │ READ ONLY      │  │    │
│  │  Collection:         │    │  - documents        │   │ :1521          │  │    │
│  │  - documents         │    │  - sessions         │   │                │  │    │
│  │  - master_data       │    │  - messages         │   │ oracledb pool  │  │    │
│  │                      │    │  - users            │   │ min=2, max=10  │  │    │
│  │  Dense: 1024-dim     │    │  - user_terms       │   └────────────────┘  │    │
│  │  Sparse: BM25-like   │    │  - chat_outputs     │                        │    │
│  │                      │    │  - master_sites     │                        │    │
│  │                      │    │  - master_lines     │                        │    │
│  │                      │    │  - master_processes │                        │    │
│  └──────────────────────┘    └─────────────────────┘                        │    │
│                                                                              │    │
└──────────────────────────────────────────────────────────────────────────────┘    │
                                                                                    │
                    ┌───────────────────────────────────────────┐                  │
                    │   AWS Bedrock                             │                  │
                    │                                           │                  │
                    │  ┌─────────────────────┐                 │                  │
                    │  │ Claude Sonnet 4.5   │ ← RAG回答生成    │                  │
                    │  │ (streaming)         │ ← クエリ解析     │                  │
                    │  │                     │ ← SQL生成        │                  │
                    │  │                     │ ← タグ付け       │                  │
                    │  └─────────────────────┘                 │                  │
                    │  ┌─────────────────────┐                 │                  │
                    │  │ Cohere Embed v3     │ ← 1024次元      │                  │
                    │  │ (batch: 96 texts)   │   ベクトル生成   │                  │
                    │  └─────────────────────┘                 │                  │
                    │  ┌─────────────────────┐                 │                  │
                    │  │ Cohere Rerank v3    │ ← 検索結果       │                  │
                    │  │ (optional)          │   リランキング   │                  │
                    │  └─────────────────────┘                 │                  │
                    └───────────────────────────────────────────┘                  │
```

### 1.2 ページレイアウト

チャットページは3カラムレイアウトを採用し、出力パネルでデータの可視化を行う。

```
Desktop (1280px+):
  [Sidebar 240px] | [Chat Area flex] | [Output Panel 400px]

Desktop (1024-1279px):
  [Sidebar 240px] | [Chat Area flex] | Output Panel as overlay/drawer

Mobile (~1023px):
  [Chat full-width] | Output Panel as bottom sheet / タブ切替
```

出力パネルはデータがない時は非表示となり、チャットエリアが全幅を使用する。SSE `output` イベント受信で自動展開される。

### 1.3 設計原則

| 原則 | 内容 |
|------|------|
| 非同期ファースト | 全てのI/O処理はasync/awaitで実装。OracleDBのみasyncio.to_threadで包む |
| フェイルセーフ | Oracleが利用不能でもドキュメント検索のみで継続 |
| 段階的処理 | アップロード後の処理はバックグラウンドタスクで非同期実行 |
| スキーマレス柔軟性 | Qdrantのpayloadで動的にメタデータを保存 |
| ゼロダウンタイム更新 | ドキュメントの新バージョン追加時も旧バージョンを保持 |

---

## 2. バックエンド設計

### 2.1 モジュール依存グラフ

```
FastAPI (main.py)
  │
  ├── routers/
  │     ├── chat.py       ← POST /api/chat (SSE), GET /api/sessions, GET /api/chat/output/:messageId
  │     ├── documents.py  ← POST /api/documents/upload, GET/PATCH /api/documents/:id
  │     ├── users.py      ← GET /api/users/me, PUT /api/users/me/settings, POST /api/users/me/terms
  │     ├── master.py     ← GET /api/master/sites, lines, processes, search
  │     └── knowledge_bases.py ← POST/GET/PUT/DELETE /api/knowledge-bases, favorites
  │
  ├── services/
  │     ├── rag.py
  │     │     ├── embedder.py
  │     │     ├── oracle_query.py
  │     │     └── user_profile.py
  │     │
  │     ├── converter.py    (純粋関数、外部依存なし)
  │     │
  │     ├── tagger.py
  │     │     ├── master_cache (MasterDataCache)
  │     │     ├── bedrock_client
  │     │     └── qdrant_client
  │     │
  │     ├── chunker.py
  │     │     └── bedrock_client (agenticチャンキング時)
  │     │
  │     ├── embedder.py
  │     │     ├── bedrock_client
  │     │     └── qdrant_client
  │     │
  │     ├── oracle_query.py
  │     │     └── oracledb pool
  │     │
  │     └── user_profile.py
  │           └── SQLAlchemy (users, user_terms テーブル)
  │
  └── infrastructure/
        ├── config.py         ← 環境変数管理 (pydantic-settings)
        ├── db.py             ← SQLite セッション管理 (SQLAlchemy async)
        ├── bedrock_client.py ← boto3 Bedrock Runtime クライアント
        ├── qdrant_client.py  ← Qdrant Python Client
        └── master_cache.py   ← インメモリマスターデータキャッシュ
```

### 2.2 converter.py 設計

#### 責務

アップロードされたファイルをMarkdownテキストおよび画像データに変換する純粋モジュール。外部サービスへの依存を持たない。

#### ファイルタイプ別変換ライブラリ

| ファイル種別 | ライブラリ | 備考 |
|-------------|-----------|------|
| PDF | `pdf2md` | ページ構造保持 |
| PowerPoint (.pptx) | `pptx2md` (ConversionConfig) | スライドノート含む |
| Excel (.xlsx/.xls) | `xl2md` (excel2md) | 複数シート対応 |
| Word (.docx) | `python-docx` | スタイル情報抽出 |
| HTML | `beautifulsoup4` + `markdownify` | タグ除去 + MD変換 |
| PNG/JPEG | Claude Vision (AWS Bedrock) | 画像内容のテキスト化 |

#### データモデル

```python
@dataclass
class ConversionResult:
    markdown: str                        # 変換後Markdownテキスト
    images: list[ExtractedImage]         # 抽出された画像リスト
    metadata_hints: dict[str, Any]       # タイトル・作成者・日付などのヒント

@dataclass
class ExtractedImage:
    uuid: str                            # [[IMAGE:uuid]] マーカーで参照
    data: bytes                          # 画像バイナリ
    mime_type: str                       # "image/png" | "image/jpeg"
    caption: str | None                  # 図表タイトル（取得可能な場合）
    page: int | None                     # 元のページ番号
```

#### 画像マーカー仕様

Markdown本文中の画像は `[[IMAGE:550e8400-e29b-41d4-a716-446655440000]]` 形式のプレースホルダーで参照される。後続のtagger.pyおよびembedder.pyがこのマーカーを処理する。

#### エラー処理方針

部分失敗時は例外を投げず、Markdownに `[変換失敗: {reason}]` プレースホルダーを挿入して処理を継続する。これにより、1ページの変換失敗が全体の処理を停止させない。

```python
def convert_page(page_data: bytes, page_num: int) -> str:
    try:
        return _extract_text(page_data)
    except ExtractionError as e:
        return f"[変換失敗: ページ{page_num} - {e.reason}]"
```

### 2.3 tagger.py 設計

#### 3段階マスターマッチング

タグ候補の決定には以下の3段階を順に試みる。前段でマッチした場合は後段を実行しない。

```
Stage 1: エイリアス辞書完全一致
  → site_by_alias / line_by_alias / process_by_sta_no2 のdictキーと一致するか確認
  → O(1)の高速マッチング

Stage 2: SQLite LIKE 検索
  → Stage 1で未マッチの用語をSQLiteのmaster_sites/master_lines/master_processesテーブルでLIKE検索
  → 部分一致・表記揺れを吸収

Stage 3: Qdrant セマンティック検索
  → Stage 2でも未マッチの場合のみ実行
  → Collection: "master_data" でベクトル類似検索
  → スコア閾値: 0.75以上のみ採用
```

#### Claude タグ付けプロンプト設計

```
入力:
  - ドキュメント先頭2000文字 + 末尾500文字 (コンテキスト効率化)
  - マスターデータ候補JSON (3段階マッチングで抽出した候補のみ)

設定:
  - temperature=0 (決定論的出力)
  - 構造化出力 (JSON mode)

出力 (TagSuggestion):
  - site_code: str          # 工場コード
  - line_code: str          # ライン番号
  - process_codes: list[str] # 工程コードリスト
  - doc_category: str       # 文書カテゴリ
  - keywords: list[str]     # キーワードリスト
  - equipment: list[str]    # 設備・機器名
  - workers: list[str]      # 担当者・部署
  - confidence: float       # 信頼度スコア 0.0-1.0
```

#### 2層タグ構造

| タグ層 | 対象 | 確定方法 |
|--------|------|---------|
| ドキュメントレベル | 文書全体のメタデータ | ユーザーが確認・修正後に確定 |
| チャンクレベル | 各チャンクの付加情報 | AI自動付与、親チャンクのタグを継承 |

### 2.4 chunker.py 設計

#### 4つのチャンキング戦略

**戦略選択ロジック:**

```python
def select_strategy(markdown: str) -> ChunkStrategy:
    header_density = count_headers(markdown) / len(markdown.split('\n'))

    if is_meeting_minutes(markdown):
        return ChunkStrategy.MEETING_MINUTES
    elif header_density > 0.05:
        return ChunkStrategy.STRUCTURAL
    elif has_dense_tables(markdown):
        return ChunkStrategy.TABLE_EXTRACTION
    else:
        return ChunkStrategy.AGENTIC
```

**Structural（構造的チャンキング）:**
- ヘッダー密度が高い文書（技術仕様書・手順書など）に適用
- ヘッダー階層でチャンクを分割
- 親チャンク = セクション（H2レベル）
- 子チャンク = サブセクション（H3以下）

**Agentic（エージェントチャンキング）:**
- ヘッダーが少ない文書（レポート・報告書など）に適用
- Claudeが意味的な区切りを判断してチャンク境界を決定
- プロンプトで「話題の転換点」を指定

**Meeting Minutes（議事録）:**
- 議事録・会議メモに特化
- Claudeが以下のカテゴリに分解:
  - `decisions`: 決定事項
  - `action_items`: アクション項目（担当者・期日含む）
  - `issues`: 課題・問題点
  - `countermeasures`: 対策・解決策

**Table Extraction（テーブル抽出）:**
- 表が多い文書（品質管理表・検査記録など）に適用
- 行グループ単位でチャンク化
- 各チャンクにセクションコンテキストを付与

#### 親子チャンク実装

```python
@dataclass
class Chunk:
    chunk_id: str
    parent_chunk_id: str | None        # Noneならルートチャンク
    children_ids: list[str]
    document_id: str
    text: str
    chunk_type: ChunkType
    page: int | None
    section: str | None
    is_latest: bool = True
```

**検索時の親子展開:**
- 検索ヒット: 子チャンク（細粒度、高精度なスコアリング）
- LLM入力: 親チャンク（広いコンテキスト、回答品質向上）
- Qdrant payload の `parent_chunk_id` を使って親を取得

### 2.5 embedder.py 設計

#### Cohere Embed via Bedrock

```python
# boto3でBedrockのCohereモデルを呼び出す
response = bedrock_client.invoke_model(
    modelId="cohere.embed-multilingual-v3",
    body=json.dumps({
        "texts": batch_texts,
        "input_type": input_type,  # "search_document" | "search_query"
        "truncate": "END"
    })
)
```

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| ベクトル次元数 | 1024 | Cosine距離 |
| input_type (インデックス) | `search_document` | 文書埋め込み時 |
| input_type (クエリ) | `search_query` | クエリ埋め込み時 |
| バッチサイズ | 96 texts/call | API制限内の最大値 |
| スパースベクトル | BM25-like | ハイブリッド検索用 |

#### ハイブリッドインデックス設計

```python
# Qdrantへのupsert
qdrant_client.upsert(
    collection_name="documents",
    points=[
        PointStruct(
            id=chunk.chunk_id,
            vector={
                "dense": dense_vector,   # Cohere Embed 1024次元
                "sparse": sparse_vector  # BM25スパースベクトル
            },
            payload=chunk_payload
        )
    ]
)
```

#### バッチ処理フロー

```
chunks (N個)
  → 96個ずつバッチ分割
  → 各バッチをCohereに送信 (並行処理: asyncio.gather, 最大3並行)
  → 結果を集約
  → Qdrant upsert (100 points/batch, gRPC接続)
```

### 2.6 rag.py 設計（SSEコア）

#### 検索フロー全体

```
1. analyze_query (Claude)
   ├── intent分類: DOC_SEARCH | ORACLE_QUERY | HYBRID
   ├── フィルター抽出: site_code, line_code, process_codes, date_range
   └── 検索キーワード精錬

1.5. normalize_text (text_normalizer.py)
   └── NFKC正規化: 半角カタカナ→全角、全角英数字→半角
   └── ベクトル検索・用語照合前にクエリテキストを正規化

2. translate_query_terms (user_profile.py)
   └── ユーザー個人辞書のスラング→正式名称変換 (最長マッチ優先)

3. detect_unknown_terms (user_profile.py)
   └── マスターにも個人辞書にもない固有名詞を検出
   └── SSE terms イベントで候補をフロントに送信

4. Vector Search (Qdrant)
   ├── Dense vector検索 (Cohere Embed クエリベクトル)
   ├── Sparse vector検索 (BM25-like、オプション)
   ├── knowledge_base_id フィルター (必須: 選択中のナレッジベースに限定)
   │     → FieldCondition(key="knowledge_base_id", match=MatchValue(value=kb_id))
   ├── メタデータフィルター適用 (site/line/process)
   └── is_latest=True フィルター (デフォルト)

5. Parent-Child Expansion
   └── ヒットした子チャンク → parent_chunk_idで親チャンクを取得

6. Rerank (オプション)
   └── Cohere Rerank via Bedrock でスコア再計算

6.5. 信頼度による回答拒否
   └── Rerank/スコアリング後、最高スコアが閾値未満の場合は回答を拒否
   └── 閾値: RELEVANCE_THRESHOLD = 0.3
   └── 拒否時: 「選択されたナレッジベース内に該当する情報が見つかりませんでした。」を返却

7. Oracle Query (HYBRID/ORACLE_QUERYインテント時)
   ├── Claude が SQL を生成（対象: 5テーブル — HF1R6M01, HF1REM01, HF1SGM01, HF1RFM01, HF1SKM01）
   ├── validate_sql で安全性検証
   ├── Oracle でクエリ実行 (READ ONLY, 30s timeout)
   └── 結果をコンテキストに追加

8. Oracle結果をテーブル/グラフ用に構造化
   ├── table_data: {columns: [{key, label, type}], rows: [...]}
   ├── Claude がデータの性質とユーザーの質問意図を判断:
   │     推移データ → chart_type: "line"
   │     比較データ → chart_type: "bar"
   │     構成比 → chart_type: "pie"
   │     分布 → chart_type: "histogram"
   ├── chart_config: {type, x_axis, y_axis, series, title}
   └── SSE output イベントで出力パネルに送信

9. Answer Generation (Claude Sonnet 4.5, ストリーミング)
   ├── システムプロンプト: ユーザープロファイル + モード指示
   ├── コンテキスト: 展開済みチャンク + Oracle結果
   └── ストリーミング出力 → SSE tokenイベント
```

#### SSE イベント仕様

| イベント名 | ペイロード | タイミング |
|-----------|-----------|-----------|
| `session` | `{"session_id": "uuid", "knowledge_base_id": "uuid"}` | ストリーム開始時 |
| `status` | `{"stage": "query_analysis"}` | 各処理段階の開始時 |
| `token` | `{"text": "..."}` | LLM出力トークンごと |
| `sources` | `[{"file": "...", "section": "...", "page": 1, "chunk_id": "..."}]` | 回答生成前 |
| `terms` | `[{"unknown_term": "KJCW43", "candidates": [{"code": "...", "name": "..."}]}]` | 未知語検出時 |
| `complete` | `{"message_id": "uuid", "oracle_used": true}` | 生成完了時 |
| `error` | `{"code": "BEDROCK_THROTTLING", "message": "...", "recoverable": true}` | エラー発生時 |
| `output` | `{"output_type": "table"\|"chart"\|"both", "table_data": {"columns": [{"key", "label", "type"}], "rows": [...]}, "chart_config": {"type", "x_axis", "y_axis", "series", "title"}}` | 出力パネルにデータ送信 |
| `done` | `{}` | ストリーム終了 |

#### ステータス遷移

```
query_analysis → text_normalization → vector_search → (oracle_query → structuring_output →) generating → done
```

#### システムプロンプト設計

```
あなたは製造現場のナレッジアシスタントです。

[厳格なRAG制約]
あなたは以下の「参照文書」に記載された情報のみを使って回答してください。
- 参照文書に含まれない情報は、一般常識や自身の学習データに基づく知識であっても、絶対に使用しないでください。
- 回答できない場合は「選択されたナレッジベース内に該当する情報が見つかりませんでした。」と回答してください。
- 推測や補完をしないでください。文書に書かれていることだけを述べてください。
- 「一般的には〜」「通常〜」などの表現で自身の知識を混入させないでください。

[ユーザープロファイル]
- よく担当するライン: {user.frequent_lines}
- 最近の検索履歴のコンテキスト: {user.recent_context}
- 用語マッピング: {user.term_mappings}

[回答モード]
{if response_mode == "simple"}
簡潔に要点のみ回答してください。箇条書きを優先してください。
{else}
根拠・経緯・関連情報を含めて詳しく回答してください。
{endif}

[参照文書]
{retrieved_chunks}
```

#### 信頼度による回答拒否

Rerank/スコアリング後、取得チャンクの最高関連度スコアが閾値未満の場合はLLM呼び出しを行わず、即座に拒否応答を返す。これによりハルシネーションを防止する。

```python
# 信頼度による回答拒否
if not retrieved_chunks or max(c.score for c in retrieved_chunks) < config.RELEVANCE_THRESHOLD:
    yield SSEEvent(event="token", data={"text": "選択されたナレッジベース内に該当する情報が見つかりませんでした。"})
    yield SSEEvent(event="done", data={})
    return
```

### 2.7 出力データ構造化（rag.py 拡張）

Oracle クエリ結果を出力パネル向けに構造化する。回答生成と同一の Claude 呼び出しで chart_config を決定し、追加のAPI呼び出しを避ける。

#### 出力データフロー

```
Oracle Query結果 (rows, columns)
  │
  ├── table_data 構築
  │     columns: [{key: "col_name", label: "表示名", type: "string"|"number"|"date"}]
  │     rows: [{col_name: value, ...}, ...]
  │
  ├── chart_config 決定 (Claude が回答生成と同時に判断)
  │     ユーザーの質問意図 + データの性質から最適なグラフ種別を選択:
  │       推移（時系列）→ chart_type: "line"
  │       比較         → chart_type: "bar"
  │       構成比       → chart_type: "pie"
  │       分布         → chart_type: "histogram"
  │     chart_config: {type, x_axis, y_axis, series: [{dataKey, name, color}], title}
  │
  └── SSE output イベント送信
        event: output
        data: {
          output_type: "table" | "chart" | "both",
          table_data: {...},
          chart_config: {...},
          sql_executed: "SELECT ...",
          row_count: 42
        }
```

#### chat_outputs テーブル（SQLite）

Oracle クエリ結果は Qdrant には保存しない。一時的なデータであり、履歴参照用に SQLite の chat_outputs テーブルにのみ保存する。

```sql
CREATE TABLE chat_outputs (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    output_type TEXT NOT NULL CHECK(output_type IN ('table', 'chart', 'both')),
    table_data JSON,
    chart_config JSON,
    sql_executed TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2.8 oracle_query.py 設計

#### API エンドポイント（出力データ関連）

| メソッド | パス | 説明 |
|----------|------|------|
| GET | `/api/chat/output/:messageId` | メッセージに紐づく出力データ取得 |
| GET | `/api/chat/output/:messageId/csv` | テーブルデータのCSVダウンロード（BOM付きUTF-8） |

#### 5層安全機構

```
Layer 1: SQL生成プロンプト制約
  → "SELECT文またはWITH CTEのみ生成してください"
  → "WHERE句に必ずフィルター条件を含めてください"

Layer 2: validate_sql (sqlparse ASTによる静的解析)
  → 許可: SELECT, WITH CTE
  → 拒否: INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, EXEC
  → 拒否: セミコロンによる複数文実行

Layer 3: Oracle セッション READ ONLYロール
  → 接続時に SET TRANSACTION READ ONLY を実行
  → DB側でも書き込みを物理的にブロック

Layer 4: タイムアウト (30秒)
  → asyncio.wait_for でラップ
  → タイムアウト時は OracleTimeoutError を raise

Layer 5: 行数制限 (500行)
  → SQLにROWNUM <= 500 を自動付加
  → または FETCH FIRST 500 ROWS ONLY
```

#### グレースフルフォールバック

```python
async def execute_oracle_query(sql: str) -> OracleResult:
    try:
        return await _execute_with_timeout(sql, timeout=30)
    except OracleUnavailableError:
        # Oracle が利用不能な場合はドキュメント検索のみで継続
        await sse_queue.put(SSEEvent(
            event="error",
            data={"code": "ORACLE_UNAVAILABLE", "message": "...", "recoverable": True}
        ))
        return OracleResult(rows=[], columns=[], skipped=True)
```

#### 接続プール設定

```python
pool = oracledb.create_pool(
    dsn=config.ORACLE_DSN,
    user=config.ORACLE_USER,
    password=config.ORACLE_PASSWORD,
    min=2,
    max=10,
    increment=1
)

# async互換ラッパー
result = await asyncio.to_thread(pool.acquire)
```

#### Oracleテーブルスキーマ参照（5テーブル）

oracle_query.py は以下の5テーブルに対してSQLを生成する。Claude のSQL生成プロンプトにスキーマ情報を提供し、正確なSQL生成を支援する。

```
■ HF1R6M01（生産トレーサビリティデータ）
  MK_DATE (DATE), STA_NO1 (VARCHAR), STA_NO2 (VARCHAR), STA_NO3 (VARCHAR),
  M_SERIAL (VARCHAR), INSP_ITEMNAME (VARCHAR), MEASURE (NUMBER)

■ HF1REM01（品質結果データ）— 約166,248件
  MK_DATE (VARCHAR, 形式: "YYYYMMDDHHmmss"), STA_NO1 (VARCHAR), STA_NO2 (VARCHAR), STA_NO3 (VARCHAR),
  SUB_NO (NUMBER), CORRECT_SEQ (NUMBER), M_SERIAL (VARCHAR), MANAGEID (VARCHAR), PARTSNAME (VARCHAR),
  OPEFIN_RESULT (NUMBER) ← ★重要: 1=良品(OK), 2=不良(NG) → 不良率算出の核心,
  QTY (NUMBER), SKIP_CHK_MODE (VARCHAR), OPE_CODE (VARCHAR),
  EXCEPT_FLAG (NUMBER) ← ★重要: 0,1=集計対象, 2=除外, 30代=OKマスタ定義, 40代=NGマスタ定義, 50代=その他マスタ定義。集計クエリには必ず EXCEPT_FLAG IN (0, 1) を付与,
  PLT_NO (VARCHAR), NG_CODE (VARCHAR) → HF1SGM01.CODE_NO で不良内容を解決（★NULLの場合あり。LEFT JOIN必須、NULL時は「未分類」）,
  REWORK_CNT (NUMBER), RETRY_CNT (NUMBER), PENDING_FLAG (VARCHAR),
  S_SERIAL00〜S_SERIAL39 (VARCHAR, 40カラム) → HF1SKM01.PARTS_NO で部品名を解決,
  T3_HANDSHAKE (NUMBER), RUNNING_NO (VARCHAR), UPCMPFLG (NUMBER),
  ORDER_NO (VARCHAR), SOURCE_CAT (VARCHAR), CONTENTS (VARCHAR)

■ HF1SGM01（トラブルマスター）— 約11,821件
  STA_NO1 (VARCHAR), STA_NO2 (VARCHAR), STA_NO3 (VARCHAR),
  CODE_NO (NUMBER), TROUBLE_NG_INFO (VARCHAR), TROUBLE_NG_INFO_L (VARCHAR),
  TROUBLE_NG_INFO_EN (VARCHAR), STA_NO4 (VARCHAR), WITHOUT_FLAG (VARCHAR),
  MK_DATE (DATE), UP_DATE (DATE), MK_USER (VARCHAR), UP_USER (VARCHAR), MEMO (VARCHAR)

■ HF1RFM01（トラブル発生実績データ）
  MK_DATE (VARCHAR, 形式: "YYYYMMDDHHmmss"), STA_NO1 (VARCHAR), STA_NO2 (VARCHAR),
  STA_NO3 (VARCHAR),
  EXCEPT_FLAG (VARCHAR) ← ★重要: 0,1=集計対象, 2=除外, 30代=OKマスタ定義, 40代=NGマスタ定義, 50代=その他マスタ定義。集計クエリには必ず EXCEPT_FLAG IN (0, 1) を付与,
  M_SERIAL (VARCHAR),
  T4_STATUS (NUMBER) ← ★フィルタ不要（無視してよい）,
  CODE_NO (NUMBER),
  T4_UPDATE_CHECK (NUMBER) ← ★重要: 4=ブザー鳴動（異常発生）時刻のレコード, 5=ブザー停止（オペレーター対応）時刻のレコード。
    ※異常停止時刻ではない。同じトラブルが4と5のペアで記録される。トラブル発生件数カウントには T4_UPDATE_CHECK=4 を使用,
  PARTSNAME (VARCHAR), OPE_CODE (VARCHAR), PLT_NO (VARCHAR),
  ON_TIME (VARCHAR), REP_START_TIME (VARCHAR), RESTART_TIME (VARCHAR),
  SOURCE_CAT (VARCHAR), MEMO (VARCHAR)

■ HF1SKM01（シリアル/部品マスター）— 約958件
  STA_NO1 (VARCHAR), STA_NO2 (VARCHAR), STA_NO3 (VARCHAR),
  PARTS_NO (NUMBER), MAIN_PARTS_NAME (VARCHAR), SUB_PARTS_NAME (VARCHAR),
  MAIN_LOT_START (NUMBER), MAIN_LOT_LENGTH (NUMBER),
  SUB_LOT_START (NUMBER), SUB_LOT_LENGTH (NUMBER),
  MAIN_PARTS_NAME_EN (VARCHAR), SUB_PARTS_NAME_EN (VARCHAR),
  OYAKO_HANTEN (VARCHAR), NO_MANAGE (VARCHAR), HINCODE (VARCHAR),
  MK_DATE (DATE), UP_DATE (DATE), MEMO (VARCHAR)
```

#### テーブル間リレーション（ER）

```
HF1R6M01 (生産トレサビ) ─── STA_NO1/2/3 ──→ マスターデータ（工程特定）
                         ─── M_SERIAL ────→ HF1REM01 (品質結果とのトレーサビリティ結合)
HF1REM01 (品質結果)    ─── STA_NO1/2/3 ──→ マスターデータ（工程特定）
                        ─── NG_CODE ─────→ HF1SGM01.CODE_NO (不良内容を解決)
                        ─── S_SERIAL00~39 → HF1SKM01.PARTS_NO (部品名を解決)
                        ─── M_SERIAL ────→ HF1R6M01 (トレーサビリティ結合)
HF1RFM01 (トラブルデータ) ─ STA_NO1/2/3 + CODE_NO → HF1SGM01 (トラブル名を解決)
HF1SGM01 (トラブルマスタ) ─ STA_NO1/2/3 ──→ マスターデータ（工程特定）
HF1SKM01 (部品マスタ)   ─── STA_NO1/2/3 ──→ マスターデータ（工程特定）

結合キーまとめ:
  - 全テーブル共通: STA_NO1 (サイト) + STA_NO2 (ライン) + STA_NO3 (工程)
  - トラブル分析: HF1RFM01.CODE_NO = HF1SGM01.CODE_NO
  - 部品解決: HF1REM01 × HF1SKM01 (STA_NO1/2/3 + PARTS_NO)
  - 不良内容解決: HF1REM01.NG_CODE = HF1SGM01.CODE_NO（★LEFT JOIN必須 — NG_CODEはNULLの場合あり）
  - トレーサビリティ: HF1REM01.M_SERIAL = HF1R6M01.M_SERIAL
  - ★EXCEPT_FLAGフィルタ: HF1REM01/HF1RFM01の集計には必ず EXCEPT_FLAG IN (0, 1) を付与
  - トラブル時間算出（クロステーブル）: HF1RFM01(T4_UPDATE_CHECK=4).MK_DATE → 同一STA_NO1/2/3で次のHF1REM01.MK_DATE
    ※トラブル時間 = 生産復帰時刻(HF1REM01.MK_DATE) - トラブル発生時刻(HF1RFM01.MK_DATE)
```

#### SQL生成テンプレート（Claudeリファレンス用）

以下のテンプレートをClaudeのSQL生成プロンプトにリファレンスとして提供する。

```python
ORACLE_SQL_TEMPLATES = [
    {
        "name": "特定ラインのトラブル発生件数",
        "description": "指定ラインにおけるトラブル内容別の発生件数を集計する（T4_UPDATE_CHECK=4でカウント）",
        "sql": """
            SELECT sgm.TROUBLE_NG_INFO AS トラブル内容, COUNT(*) AS 発生件数
            FROM HF1RFM01 rfm
            JOIN HF1SGM01 sgm
                ON rfm.STA_NO1 = sgm.STA_NO1
               AND rfm.STA_NO2 = sgm.STA_NO2
               AND rfm.STA_NO3 = sgm.STA_NO3
               AND rfm.CODE_NO = sgm.CODE_NO
            WHERE rfm.T4_UPDATE_CHECK = 4
              AND rfm.EXCEPT_FLAG IN (0, 1)
              AND rfm.STA_NO2 = :line_code
              AND rfm.MK_DATE BETWEEN :start_date AND :end_date
            GROUP BY sgm.TROUBLE_NG_INFO
            ORDER BY 発生件数 DESC
            FETCH FIRST 500 ROWS ONLY
        """,
        "parameters": {"line_code": "ラインコード", "start_date": "開始日", "end_date": "終了日"}
    },
    {
        "name": "トラブル内容別の時系列推移",
        "description": "トラブル発生件数の日別推移を取得する（T4_UPDATE_CHECK=4でカウント、グラフ表示用）",
        "sql": """
            SELECT SUBSTR(rfm.MK_DATE, 1, 8) AS 発生日,
                   sgm.TROUBLE_NG_INFO AS トラブル内容,
                   COUNT(*) AS 件数
            FROM HF1RFM01 rfm
            JOIN HF1SGM01 sgm
                ON rfm.STA_NO1 = sgm.STA_NO1
               AND rfm.STA_NO2 = sgm.STA_NO2
               AND rfm.STA_NO3 = sgm.STA_NO3
               AND rfm.CODE_NO = sgm.CODE_NO
            WHERE rfm.T4_UPDATE_CHECK = 4
              AND rfm.EXCEPT_FLAG IN (0, 1)
              AND rfm.STA_NO1 = :site_code
              AND rfm.MK_DATE >= :start_date
            GROUP BY SUBSTR(rfm.MK_DATE, 1, 8), sgm.TROUBLE_NG_INFO
            ORDER BY 発生日
            FETCH FIRST 500 ROWS ONLY
        """,
        "parameters": {"site_code": "サイトコード", "start_date": "開始日時（YYYYMMDDHHmmss形式）"}
    },
    {
        "name": "部品名称の解決（品質結果×部品マスター）",
        "description": "品質結果データに部品名を付与して取得する",
        "sql": """
            SELECT rem.MK_DATE, rem.M_SERIAL,
                   skm.MAIN_PARTS_NAME AS 部品名,
                   rem.PARTSNAME, rem.OPEFIN_RESULT
            FROM HF1REM01 rem
            JOIN HF1SKM01 skm
                ON rem.STA_NO1 = skm.STA_NO1
               AND rem.STA_NO2 = skm.STA_NO2
               AND rem.STA_NO3 = skm.STA_NO3
            WHERE rem.EXCEPT_FLAG IN (0, 1)
              AND rem.STA_NO2 = :line_code
              AND rem.MK_DATE >= :start_date
            FETCH FIRST 500 ROWS ONLY
        """,
        "parameters": {"line_code": "ラインコード", "start_date": "開始日"}
    },
    {
        "name": "工程別不良率の算出",
        "description": "OPEFIN_RESULT(1=良品,2=不良)を使い、工程別の不良率を算出する",
        "sql": """
            SELECT STA_NO2 AS ライン, STA_NO3 AS 工程,
                   COUNT(*) AS 総数,
                   SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) AS 不良数,
                   ROUND(SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS 不良率
            FROM HF1REM01
            WHERE EXCEPT_FLAG IN (0, 1)
              AND STA_NO1 = :site_code AND STA_NO2 = :line_code
              AND MK_DATE BETWEEN :start_date AND :end_date
            GROUP BY STA_NO2, STA_NO3
        """,
        "parameters": {"site_code": "サイトコード", "line_code": "ラインコード", "start_date": "開始日", "end_date": "終了日"}
    },
    {
        "name": "不良内容別の集計（品質結果×トラブルマスター）",
        "description": "不良品(OPEFIN_RESULT=2)のNG_CODEをHF1SGM01とLEFT JOINで結合し、不良内容別に集計する（NG_CODEがNULLの不良品は「未分類」として含む）",
        "sql": """
            SELECT r.STA_NO3 AS 工程, NVL(s.TROUBLE_NG_INFO, '未分類') AS 不良内容, COUNT(*) AS 件数
            FROM HF1REM01 r
            LEFT JOIN HF1SGM01 s
                ON r.STA_NO1 = s.STA_NO1
               AND r.STA_NO2 = s.STA_NO2
               AND r.STA_NO3 = s.STA_NO3
               AND r.NG_CODE = s.CODE_NO
            WHERE r.OPEFIN_RESULT = 2
              AND r.EXCEPT_FLAG IN (0, 1)
              AND r.STA_NO1 = :site_code AND r.STA_NO2 = :line_code
            GROUP BY r.STA_NO3, NVL(s.TROUBLE_NG_INFO, '未分類')
            ORDER BY 件数 DESC
        """,
        "parameters": {"site_code": "サイトコード", "line_code": "ラインコード"}
    },
    {
        "name": "トラブル時間の算出（クロステーブル計算）",
        "description": "トラブル発生（ブザー鳴動）から同一設備で生産復帰（品質結果記録）までの実影響時間を算出する。HF1RFM01(T4_UPDATE_CHECK=4) → HF1REM01 のクロステーブル計算",
        "sql": """
            SELECT rf.STA_NO2 AS ライン,
                   rf.STA_NO3 AS 工程,
                   sg.TROUBLE_NG_INFO AS トラブル内容,
                   rf.MK_DATE AS トラブル発生時刻,
                   (SELECT MIN(re.MK_DATE)
                    FROM HF1REM01 re
                    WHERE re.STA_NO1 = rf.STA_NO1
                      AND re.STA_NO2 = rf.STA_NO2
                      AND re.STA_NO3 = rf.STA_NO3
                      AND re.MK_DATE > rf.MK_DATE
                      AND re.EXCEPT_FLAG IN (0, 1)) AS 生産復帰時刻,
                   rf.OPE_CODE AS オペレーター
            FROM HF1RFM01 rf
            JOIN HF1SGM01 sg
                ON rf.STA_NO1 = sg.STA_NO1
               AND rf.STA_NO2 = sg.STA_NO2
               AND rf.STA_NO3 = sg.STA_NO3
               AND rf.CODE_NO = sg.CODE_NO
            WHERE rf.T4_UPDATE_CHECK = 4
              AND rf.EXCEPT_FLAG IN (0, 1)
              AND rf.STA_NO1 = :site_code
              AND rf.STA_NO2 = :line_code
              AND rf.MK_DATE BETWEEN :start_date AND :end_date
            ORDER BY rf.MK_DATE DESC
            FETCH FIRST 500 ROWS ONLY
        """,
        "parameters": {"site_code": "サイトコード", "line_code": "ラインコード", "start_date": "開始日", "end_date": "終了日"}
    }
]
```

#### SQL生成プロンプト設計（更新）

```
あなたはOracle DBに対するSQLクエリを生成するアシスタントです。

[利用可能なテーブル]
以下の5テーブルが利用可能です:
1. HF1R6M01 — 生産トレーサビリティデータ
2. HF1REM01 — 品質結果データ（OPEFIN_RESULT: 1=良品, 2=不良 → 不良率算出、NG_CODE→HF1SGM01で不良内容解決）
3. HF1SGM01 — トラブルマスター（CODE_NOでトラブル名を解決）
4. HF1RFM01 — トラブル発生実績データ（CODE_NOでHF1SGM01と結合）
5. HF1SKM01 — シリアル/部品マスター（PARTS_NOで部品名を解決）

[結合ルール]
- 全テーブルは STA_NO1, STA_NO2, STA_NO3 で工程を特定
- トラブル分析: HF1RFM01 JOIN HF1SGM01 ON STA_NO1/2/3 + CODE_NO
- 部品解決: HF1REM01 JOIN HF1SKM01 ON STA_NO1/2/3 + PARTS_NO
- 不良内容解決: HF1REM01.NG_CODE = HF1SGM01.CODE_NO（STA_NO1/2/3 も結合条件に含む）
- トレーサビリティ: HF1REM01.M_SERIAL = HF1R6M01.M_SERIAL
- HF1RFM01.MK_DATE は VARCHAR 型（"YYYYMMDDHHmmss" 形式）であることに注意
- HF1REM01.MK_DATE も VARCHAR 型（"YYYYMMDDHHmmss" 形式）であることに注意

[ビジネスルール]
- HF1REM01.OPEFIN_RESULT: 1=良品(OK), 2=不良(NG)
- 不良率の算出: SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
- 不良品の抽出条件: WHERE OPEFIN_RESULT = 2
- 不良内容の特定: HF1REM01.NG_CODE → HF1SGM01.TROUBLE_NG_INFO で結合
- ★EXCEPT_FLAGフィルタ（最重要・必須）: HF1REM01およびHF1RFM01への全ての集計クエリには必ず WHERE EXCEPT_FLAG IN (0, 1) を付与すること。値の意味: 0,1=通常データ（集計対象）, 2=除外データ, 30代=OKマスタ定義, 40代=NGマスタ定義, 50代=その他マスタ定義。このフィルタがないとマスタ定義レコードや除外データが集計結果を汚染する
- ★NG_CODEのNULL許容: OPEFIN_RESULT=2（不良）でもNG_CODEがNULLの場合がある。NG_CODEでHF1SGM01と結合する際はLEFT JOIN（INNER JOINではない）を使用すること。NG_CODEがNULLの不良品は「未分類」として扱い、NVL(s.TROUBLE_NG_INFO, '未分類') で表示する
- HF1RFM01.T4_UPDATE_CHECK: 4=ブザー鳴動（異常発生）, 5=ブザー停止（オペレーター対応）。これは設備の異常停止時刻ではない
- トラブル発生件数のカウント: WHERE T4_UPDATE_CHECK = 4 を必ず付与する
- HF1RFM01.T4_STATUS: フィルタ不要（無視してよい）
- トラブル時間の算出（最重要ルール）: HF1RFM01(T4_UPDATE_CHECK=4).MK_DATE を開始時刻とし、同一STA_NO1/2/3で次にHF1REM01に品質結果が記録されたMK_DATEを終了（生産復帰）時刻とするクロステーブル計算。ON_TIME/REP_START_TIME/RESTART_TIMEカラムは存在するが、トラブル時間算出には使用しない。サブクエリ内のHF1REM01にもEXCEPT_FLAG IN (0, 1)フィルタを付与すること

[制約]
- SELECT文またはWITH CTEのみ生成してください
- WHERE句に必ずフィルター条件を含めてください
- FETCH FIRST 500 ROWS ONLY を必ず付与してください

[テンプレート参照]
{oracle_query_templates}
```

### 2.9 user_profile.py 設計

#### 用語翻訳（スラング→正式名称）

```python
def translate_query_terms(query: str, user_terms: list[UserTerm]) -> str:
    """
    最長マッチ優先で置換する。
    例: "KJCW43" → "巻線43号ライン" (個人辞書)
        "KJ" → マスターの工場コード (マスター辞書)
    最長マッチ優先により "KJCW43" が "KJ" より先にマッチする。
    """
    # スラングを長い順にソート
    sorted_terms = sorted(user_terms, key=lambda t: len(t.user_term), reverse=True)
    result = query
    for term in sorted_terms:
        result = result.replace(term.user_term, term.official_name)
    return result
```

#### 未知語検出

```python
def detect_unknown_terms(query: str, master_cache: MasterDataCache, user_terms: list[UserTerm]) -> list[str]:
    """
    マスターデータにも個人辞書にも存在しない固有名詞を検出する。
    品詞タグ付け（MeCab or spaCy）で名詞・固有名詞を抽出後、各辞書と照合。
    """
    nouns = extract_nouns(query)  # MeCabで名詞抽出
    known = master_cache.all_codes | {t.user_term for t in user_terms}
    return [n for n in nouns if n not in known]
```

#### 行動データ自動集計

```python
async def update_behavior(user_id: str, query: str, selected_docs: list[Document]) -> None:
    """
    クエリ履歴から自動的に:
    - frequent_lines: よく参照するラインコード
    - frequent_categories: よく参照する文書カテゴリ
    を集計し、ユーザープロファイルを更新する。
    """
```

#### ユーザー別用語テーブル設計

同じ用語 `"ウキ"` がユーザーAでは `"浮き子センサー"` に、ユーザーBでは `"浮き彫り工程"` にマッピングされる。per-user設計により混在を防ぐ。

```sql
CREATE TABLE user_terms (
    id          INTEGER PRIMARY KEY,
    user_id     TEXT NOT NULL,
    user_term   TEXT NOT NULL,
    master_key  TEXT NOT NULL,  -- マスターデータのcode
    master_type TEXT NOT NULL,  -- "site" | "line" | "process"
    created_at  TEXT NOT NULL,
    UNIQUE(user_id, user_term)  -- ユーザーごとに用語は一意
);
```

### 2.10 MasterDataCache 設計

#### メモリ消費見積もり

| データ | レコード数 | 推定メモリ |
|--------|-----------|-----------|
| 工場マスター (site) | ~50件 | ~0.5MB |
| ラインマスター (line) | ~500件 | ~2MB |
| 工程マスター (process) | ~9,568件 | ~12MB |
| **合計** | **~10,118件** | **~14.5MB** |

#### 起動シーケンス

```
アプリ起動
  │
  ├── 1. マスターMDパース (~1秒)
  │       master-flat-with-place-aliases.md を読み込み
  │
  ├── 2. SQLite UPSERT (~2秒)
  │       master_sites, master_lines, master_processes テーブルに全レコードをUPSERT
  │
  ├── 3. インメモリキャッシュ構築 (~1秒)
  │       site_by_alias: dict[str, SiteMaster]
  │       line_by_alias: dict[str, LineMaster]
  │       process_by_sta_no2: dict[str, ProcessMaster]
  │
  ├── 4. サービス起動 (SQLiteフォールバックモード)
  │       ← エンドポイントが応答を開始する
  │
  └── 5. バックグラウンド: Qdrantエンベッディング (~2分, 初回のみ)
          Cohere Embedで全マスターをベクトル化
          Collection "master_data" にupsert
          完了後: セマンティック検索が利用可能になる
```

#### キャッシュ構造

```python
@dataclass
class MasterDataCache:
    # エイリアス→マスターの高速ルックアップ
    site_by_alias: dict[str, SiteMaster]
    line_by_alias: dict[str, LineMaster]
    process_by_sta_no2: dict[str, ProcessMaster]

    # 全コードセット（未知語検出用）
    all_codes: set[str]

    # 最終更新時刻
    last_updated: datetime
```

### 2.11 バックグラウンドタスク設計

#### パイプライン全体

**永続性**: インデックス構築（変換→タグ付け→チャンキング→ベクトル化）はサーバーサイドで完全に実行される。FastAPI BackgroundTasks でサーバーサイドのみで処理するため、フロントエンドの接続は不要。ユーザーがブラウザを閉じても、画面をリロードしても、処理は継続する。

```
POST /api/documents/upload (multipart/form-data, files[], knowledge_base_id 必須)
  │ → 複数ファイル受付（最大20ファイル、ZIP展開対応）
  │ → 各ファイル保存
  │ → documents テーブルにレコード作成 (status="processing", knowledge_base_id を設定, retry_count=0)
  │ → [{id, filename, status}, ...] を即座に返却
  │
  └── FastAPI BackgroundTasks で非同期実行（最大3並行: asyncio.Semaphore(3)）:

       [1] convert
           → status: "processing" → "converting" → "converted"
           → ConversionResult (markdown, images, metadata_hints) を保存
           → 各ステージ開始前にキャンセルフラグをチェック（後述）

       [2] tag (AIタグ付け)
           → status: "converting" → "tagging" → "tagged"
           → TagSuggestion をDBに保存
           → 単一ファイル: フロントエンドがTagEditorを表示
           → 複数ファイル: 全ファイルが "tagged" になったらBatchTagEditorを表示

       [3] ユーザータグ確認待ち（無期限待機）
           → status: "tagged" のまま無期限に待機する（自動確定なし・タイムアウトなし）
           → ユーザーが明示的にタグを確認・確定するまでインデックスされない
           → ドキュメント一覧画面では「未確認」バッジで目立たせる

       [3'] ユーザータグ確認 (フロントエンドからのPATCH)
           → 単一ファイル: PATCH /api/documents/:id/tags → status: "confirmed"
           → 複数ファイル: PATCH /api/documents/batch-tags → 全対象を "confirmed"
           → 個別ファイルの先行確定も可能

       [4] chunk
           → status: "confirmed" → "chunking" → "chunked"
           → キャンセルフラグチェック

       [5] embed + index
           → status: "chunking" → "indexing" → "indexed"
           → キャンセルフラグチェック
```

#### フロントエンドのポーリング

```
GET /api/documents/:id
  → 2秒間隔でポーリング
  → 単一ファイル: status が "tagged" になったらTagEditorを表示
  → 複数ファイル: 全ファイルの status が "tagged" になったらBatchTagEditorを表示
    （未完了ファイルはBatchTagEditor内でスピナー表示）
  → status が "indexed" になったら完了表示
  → status が "cancelled" になったら中止表示（再試行/削除ボタン表示）
  → status が "permanent_failed" になったらリトライ上限メッセージ表示
  → タイムアウト: 5分 (ネットワーク障害検出)
  → 画面を開き直した時、処理中のドキュメントがあれば自動的にポーリングを再開する
```

#### キャンセル機構

```python
# インメモリのキャンセルフラグ辞書
_cancel_flags: dict[str, bool] = {}

async def request_cancel(document_id: str, db: Session) -> None:
    """POST /api/documents/{id}/cancel から呼び出される"""
    _cancel_flags[document_id] = True

def is_cancelled(document_id: str) -> bool:
    """各ステージの開始前にチェック"""
    return _cancel_flags.get(document_id, False)

async def process_pipeline(document_id: str, ...) -> None:
    """バックグラウンドパイプライン"""
    for stage in [convert, tag, chunk, embed]:
        if is_cancelled(document_id):
            update_status(document_id, "cancelled")
            _cancel_flags.pop(document_id, None)
            return
        await stage(document_id, ...)

    _cancel_flags.pop(document_id, None)
```

- `POST /api/documents/{id}/cancel` でキャンセルフラグをセット
- 現在実行中のステージが完了したら次のステージ開始前にフラグを検知して停止
- status を "cancelled" に変更
- "cancelled" 状態のドキュメントは「再試行」（retry_count をリセットして再開）または「削除」が可能

#### 失敗状態と再試行（リトライ上限3回）

| 失敗ステータス | トリガー | 再試行エンドポイント |
|---------------|---------|-------------------|
| `convert_failed` | 変換エラー | POST /api/documents/:id/reindex |
| `tag_failed` | タグ付けエラー | POST /api/documents/:id/reindex |
| `index_failed` | Qdrant upsertエラー | POST /api/documents/:id/reindex |
| `permanent_failed` | retry_count >= 3 | 再試行不可（削除のみ） |
| `cancelled` | ユーザーによる中止 | POST /api/documents/:id/reindex（retry_countリセット） |

再試行時は失敗した段階から再開する（全パイプラインの再実行は不要）。

```python
async def reindex_document(document_id: str, db: Session) -> dict:
    doc = get_document(db, document_id)

    # cancelled の場合は retry_count をリセットして再開
    if doc.status == "cancelled":
        doc.retry_count = 0

    # permanent_failed は再試行不可
    if doc.status == "permanent_failed":
        raise HTTPException(409, "リトライ上限に達しました。削除のみ可能です。")

    # リトライ回数をインクリメント
    doc.retry_count += 1

    if doc.retry_count >= 3:
        doc.status = "permanent_failed"
        db.commit()
        return {
            "error": "retry_limit_exceeded",
            "message": "このファイル形式は対応できない可能性があります。別の形式で再アップロードしてください。",
            "retry_count": doc.retry_count
        }

    # 失敗箇所から再開
    restart_stage = determine_restart_stage(doc.status)
    background_tasks.add_task(process_pipeline, document_id, start_from=restart_stage)
    return {"status": restart_stage, "retry_count": doc.retry_count}
```

### 2.12 ドキュメントバージョニング

#### バージョン管理方針

```
ドキュメントAの初回アップロード:
  document_id: "doc-001", version: 1, parent_document_id: null, is_latest: true
  chunks: chunk_id: "chunk-001-*", is_latest: true

ドキュメントAの更新（同名ファイル再アップロード）:
  → VersionConflictDialog でユーザーが「バージョン更新」を選択
  → 旧バージョンのチャンクを is_latest: false に更新 (削除しない)
  → 新バージョン作成:
     document_id: "doc-002", version: 2, parent_document_id: "doc-001", is_latest: true
     chunks: chunk_id: "chunk-002-*", is_latest: true
```

#### バージョン対応検索

```python
# 通常検索 (最新版のみ)
filter = Filter(must=[FieldCondition(key="is_latest", match=MatchValue(value=True))])

# 差分質問 ("前と変わった?")
# is_latest フィルターを除去して全バージョン検索
filter = Filter(must=[FieldCondition(key="document_id", match=MatchAny(any=["doc-001", "doc-002"]))])
```

### 2.12.1 ドキュメントのソフトデリートと復元

#### 概要

ドキュメント削除は即座に物理削除せず、ソフトデリート（論理削除）を行う。`documents` テーブルの `deleted_at` カラムに削除日時をセットし、30日間はゴミ箱から復元可能にする。

#### ソフトデリートフロー

```
DELETE /api/documents/{id}（ソフトデリート）
  → documents.deleted_at = datetime.now() をセット
  → Qdrant のベクトルは即座には削除しない
  → 一覧・検索から除外される（deleted_at IS NOT NULL を除外フィルタとして適用）
  → Qdrant 検索時も document_id ベースで除外フィルタを適用

POST /api/documents/{id}/restore（復元）
  → documents.deleted_at = NULL にリセット
  → 一覧・検索に再表示される

DELETE /api/documents/{id}/permanent（物理削除）
  → Qdrant: 当該 document_id のベクトルをすべて削除
  → SQLite: documents, document_tags レコードを削除
  → ファイルシステム: /app/uploads の元ファイルを削除
```

#### バックグラウンド物理削除ジョブ

```python
async def cleanup_soft_deleted_documents() -> None:
    """
    30日以上経過したソフトデリート済みドキュメントを物理削除する。
    FastAPI の startup イベントで定期実行（1日1回）をスケジューリングする。
    """
    threshold = datetime.utcnow() - timedelta(days=30)
    expired_docs = db.query(Document).filter(
        Document.deleted_at.isnot(None),
        Document.deleted_at < threshold.isoformat()
    ).all()

    for doc in expired_docs:
        # Qdrant からベクトル削除
        await qdrant_client.delete(
            collection_name="documents",
            points_selector=FilterSelector(
                filter=Filter(must=[
                    FieldCondition(key="document_id", match=MatchValue(value=doc.id))
                ])
            )
        )
        # アップロードファイル削除
        if os.path.exists(doc.original_path):
            os.remove(doc.original_path)
        # SQLite レコード削除（CASCADE で document_tags も削除）
        db.delete(doc)

    db.commit()
```

#### Qdrant 検索時の除外フィルタ

通常検索時、ソフトデリート済みドキュメントの chunk を除外するため、`deleted_document_ids` リストを取得して `must_not` フィルタに適用する。

```python
# ソフトデリート済みの document_id を取得
deleted_ids = db.query(Document.id).filter(Document.deleted_at.isnot(None)).all()
deleted_id_list = [d.id for d in deleted_ids]

# Qdrant 検索フィルタに追加
if deleted_id_list:
    filter_conditions.append(
        FieldCondition(key="document_id", match=MatchExcept(except_values=deleted_id_list))
    )
```

#### ゴミ箱 API

| メソッド | パス | 説明 |
|----------|------|------|
| DELETE | `/api/documents/{id}` | ソフトデリート（deleted_at をセット） |
| POST | `/api/documents/{id}/restore` | ゴミ箱から復元（deleted_at を NULL に） |
| GET | `/api/documents?deleted=true` | ゴミ箱一覧（deleted_at IS NOT NULL のドキュメント） |
| DELETE | `/api/documents/{id}/permanent` | 物理削除（Qdrant + SQLite + ファイル） |

### 2.13 エラー処理

#### 例外クラス階層

```python
class RagPhantomError(Exception):
    """全アプリケーション例外の基底クラス"""
    error_code: str
    recoverable: bool = False

class ConversionError(RagPhantomError):
    error_code = "CONVERSION_ERROR"
    file_type: str
    reason: str

class TaggingError(RagPhantomError):
    error_code = "TAGGING_ERROR"

class LLMResponseParseError(TaggingError):
    error_code = "LLM_PARSE_ERROR"
    raw_response: str  # デバッグ用

class OracleError(RagPhantomError):
    error_code = "ORACLE_ERROR"

class OracleUnavailableError(OracleError):
    error_code = "ORACLE_UNAVAILABLE"
    recoverable = True  # ドキュメント検索のみで継続可能

class OracleTimeoutError(OracleError):
    error_code = "ORACLE_TIMEOUT"
    recoverable = True

class SqlValidationError(OracleError):
    error_code = "SQL_VALIDATION_ERROR"
    invalid_sql: str
    violation: str  # 違反した制約の説明

class BedrockThrottlingError(RagPhantomError):
    error_code = "BEDROCK_THROTTLING"
    recoverable = True  # テナシティでリトライ
```

#### Bedrockレートリミット対策（tenacity）

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True
)
async def invoke_bedrock(payload: dict) -> dict:
    """
    リトライスケジュール (stop_after_attempt(3) = 最大3回試行):
    1回目失敗 → 1秒待機 → 2回目
    2回目失敗 → 2秒待機 → 3回目
    3回目失敗 → BedrockThrottlingError を raise
    """
```

### 2.14 設定管理（config.py）

#### 環境変数一覧

```python
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    # AWS Bedrock
    BEDROCK_REGION: str = "ap-northeast-1"
    BEDROCK_MODEL_ID: str = "anthropic.claude-sonnet-4-5"
    BEDROCK_EMBED_MODEL_ID: str = "cohere.embed-multilingual-v3"
    BEDROCK_RERANK_MODEL_ID: str = "cohere.rerank-v3-5"

    # Oracle DB
    ORACLE_DSN: str
    ORACLE_USER: str
    ORACLE_PASSWORD: str
    ORACLE_ENABLED: bool = True
    ORACLE_POOL_MIN: int = 2
    ORACLE_POOL_MAX: int = 10
    ORACLE_QUERY_TIMEOUT: int = 30
    ORACLE_ROW_LIMIT: int = 500

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_COLLECTION: str = "documents"
    QDRANT_MASTER_COLLECTION: str = "master_data"

    # SQLite
    SQLITE_DB_PATH: str = "/app/data/ragphantom.db"

    # ファイルアップロード
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    MAX_BATCH_UPLOAD_FILES: int = 20  # 一括アップロード最大ファイル数
    MAX_BATCH_UPLOAD_SIZE: int = 200 * 1024 * 1024  # 200MB（一括アップロード合計）
    ALLOWED_EXTENSIONS: list[str] = ["md", "txt", "csv", "json", "pdf", "pptx", "xlsx", "docx", "png", "jpeg", "jpg", "html"]
    UPLOAD_DIR: str = "/app/uploads"

    # マスターデータ
    MASTER_MD_PATH: str = "/app/data/master-flat-with-place-aliases.md"

    # RAG
    RELEVANCE_THRESHOLD: float = 0.3  # 信頼度による回答拒否の閾値

    # セキュリティ
    SECRET_KEY: str
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
```

### 2.15 マスターデータAPI（master.py）

#### エンドポイント一覧

| メソッド | パス | 説明 | クエリパラメータ |
|----------|------|------|-----------------|
| GET | `/api/master/sites` | 拠点一覧 | — |
| GET | `/api/master/lines` | ライン一覧 | `?site_code=xxx` |
| GET | `/api/master/processes` | 工程一覧 | `?line_code=xxx` |
| GET | `/api/master/search` | マスター曖昧検索 | `?q=検索語` |

#### レスポンス例

```python
# GET /api/master/sites
[
    {"code": "KJ", "name": "鹿島事業所", "aliases": ["KJ", "鹿島"]},
    ...
]

# GET /api/master/lines?site_code=KJ
[
    {"code": "KJCW43", "name": "巻線43号ライン", "site_code": "KJ"},
    ...
]

# GET /api/master/processes?line_code=KJCW43
[
    {"code": "KJCW43-010", "name": "素線整列", "line_code": "KJCW43", "sta_no2": "010"},
    ...
]

# GET /api/master/search?q=巻線
# → sites, lines, processes を横断して曖昧検索
{
    "sites": [...],
    "lines": [...],
    "processes": [...]
}
```

### 2.16 knowledge_bases.py 設計

#### 責務

ナレッジベースのCRUD操作およびお気に入り管理を提供するルーターモジュール。ユーザーは複数のナレッジベースを作成し、各ナレッジベースにドキュメントを格納できる。チャット時にどのナレッジベースを検索対象とするかを選択する。

#### エンドポイント一覧

| メソッド | パス | 説明 |
|----------|------|------|
| POST | `/api/knowledge-bases` | ナレッジベース作成 |
| GET | `/api/knowledge-bases` | ナレッジベース一覧取得 |
| GET | `/api/knowledge-bases/favorites` | お気に入りのナレッジベースのみ取得 |
| PUT | `/api/knowledge-bases/{id}` | ナレッジベース更新 |
| DELETE | `/api/knowledge-bases/{id}` | ナレッジベース削除 |
| POST | `/api/knowledge-bases/{id}/favorite` | お気に入りに追加 |
| DELETE | `/api/knowledge-bases/{id}/favorite` | お気に入りから削除 |

#### ナレッジベースCRUD

```python
# POST /api/knowledge-bases
@router.post("/api/knowledge-bases")
async def create_knowledge_base(body: CreateKBRequest, user_id: str = Depends(get_user_id)):
    ...

# GET /api/knowledge-bases
# GET /api/knowledge-bases/favorites (お気に入りのみ)
# PUT /api/knowledge-bases/{id}
# DELETE /api/knowledge-bases/{id}
# POST /api/knowledge-bases/{id}/favorite
# DELETE /api/knowledge-bases/{id}/favorite
```

#### データモデル

```python
@dataclass
class KnowledgeBase:
    id: str
    name: str
    description: str | None
    color: str  # hex color for UI display
    created_by: str
    document_count: int  # computed from documents table
    created_at: str
    updated_at: str
    is_favorite: bool  # computed per-user
```

#### SQLiteテーブル設計

```sql
CREATE TABLE knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT NOT NULL DEFAULT '#6366f1',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE knowledge_base_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, knowledge_base_id)
);
```

### 2.17 text_normalizer.py 設計

#### 責務

テキストの Unicode 正規化を行うユーティリティモジュール。Oracle トラブルマスター（HF1SGM01）等で使用される半角カタカナ（例: ｻｲｸﾙﾀｲﾑｵｰﾊﾞｰ）を全角カタカナ（サイクルタイムオーバー）に統一し、全角英数字を半角に変換する。これにより、ユーザーが全角カタカナで検索した際にマスターデータの半角カタカナと一致しない問題を解消する。

#### 実装

```python
import unicodedata

def normalize_text(text: str) -> str:
    """
    NFKC正規化: 半角カタカナ→全角、全角英数字→半角
    Oracle trouble master (HF1SGM01) uses half-width katakana like ｻｲｸﾙﾀｲﾑｵｰﾊﾞｰ
    Users search in full-width: サイクルタイムオーバー
    """
    return unicodedata.normalize('NFKC', text)
```

#### 適用箇所

| モジュール | 適用タイミング | 目的 |
|-----------|---------------|------|
| rag.py | クエリテキスト正規化（ベクトル検索前） | ユーザー入力の表記揺れ吸収 |
| tagger.py | マスター照合前 | タグ候補の一致率向上 |
| user_profile.py | 個人用語辞書登録・照合時 | 辞書エントリの一貫性保証 |
| oracle_query.py | SQL生成プロンプトへのクエリ投入前 | プロンプト内の表記統一 |
| embedder.py | テキスト埋め込み前（インデックス時・クエリ時の両方） | ベクトル空間での一貫性保証 |
| master_cache.py | マスターデータキャッシュ構築時 | エイリアスも含めた正規化 |

#### 配置

新規ファイルは不要。`services/` 配下のユーティリティ関数として配置するか、各モジュールでインライン使用する。推奨は `services/text_normalizer.py` として単一モジュール化し、各サービスから import する方式。

### 2.18 セッション横断キーワード検索設計

#### 責務

ユーザーが過去のチャットセッションを横断的にキーワード検索できる機能を提供する。SQLite FTS5（Full-Text Search）を活用し、高速な全文検索を実現する。

#### SQLite FTS5 テーブル設計

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- FTS同期トリガー
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

#### API設計

```
GET /api/sessions/search?q=keyword&knowledge_base_id=xxx
```

- SQLite FTS5 で全文検索
- `knowledge_base_id` でフィルタ（セッションの KB でスコープ）
- レスポンス: セッション単位にグルーピング、マッチしたメッセージのスニペット付き

```python
@router.get("/api/sessions/search")
async def search_sessions(q: str, knowledge_base_id: str, user_id: str = Depends(get_user_id)):
    results = db.execute(
        "SELECT s.id, s.title, m.content, snippet(messages_fts, 0, '<mark>', '</mark>', '...', 32) as snippet "
        "FROM messages_fts f "
        "JOIN messages m ON m.rowid = f.rowid "
        "JOIN sessions s ON s.id = m.session_id "
        "WHERE messages_fts MATCH :query AND s.user_id = :user_id AND s.knowledge_base_id = :kb_id",
        {"query": q, "user_id": user_id, "kb_id": knowledge_base_id}
    )
    # Group by session
    ...
```

#### フロントエンド

- Sidebar に `SessionSearch` コンポーネントを追加
- 検索結果をドロップダウンで表示
- セッションクリックで該当セッションに遷移

### 2.19 複数ファイル一括アップロード設計

#### 責務

複数ファイルの同時アップロードおよび ZIP ファイル展開をサポートする。バックグラウンドで最大3ファイルを並行処理し、処理効率を向上させる。

#### バッチアップロード API

```
POST /api/documents/upload
  Content-Type: multipart/form-data
  files: File[] (最大20ファイル)
  knowledge_base_id: string

  → 各ファイルにdocument_idを発行
  → レスポンス: [{id, filename, status}, ...]
  → バックグラウンドで最大3並行処理 (asyncio.Semaphore(3))
```

```python
BATCH_SEMAPHORE = asyncio.Semaphore(3)

async def process_document(doc_id: str, file_path: str):
    async with BATCH_SEMAPHORE:
        await convert(doc_id, file_path)
        await tag(doc_id)
        # ... rest of pipeline
```

#### ZIP ファイル対応

```python
import zipfile

async def handle_upload(files: list[UploadFile], knowledge_base_id: str):
    expanded_files = []
    for file in files:
        if file.filename.endswith('.zip'):
            with zipfile.ZipFile(file.file) as zf:
                for name in zf.namelist():
                    ext = name.rsplit('.', 1)[-1].lower()
                    if ext in config.ALLOWED_EXTENSIONS:
                        expanded_files.append(...)
        else:
            expanded_files.append(file)

    if len(expanded_files) > config.MAX_BATCH_UPLOAD_FILES:
        raise HTTPException(400, "最大20ファイルまで")
```

#### 一括タグ確認 API

```
PATCH /api/documents/batch-tags
  Content-Type: application/json
  body: {
    documents: [
      { document_id: "uuid", tags: [{tag_key, tag_value, confirmed}] },
      ...
    ]
  }

  → 各ドキュメントのタグを一括更新
  → 各ドキュメントの status を "tagged" → "confirmed" に遷移
  → confirmed 後、バックグラウンドで chunk + embed + index を開始（最大3並行）
  → レスポンス: { confirmed: ["uuid1", "uuid2", ...] }
```

```python
@router.patch("/documents/batch-tags")
async def batch_confirm_tags(
    payload: BatchTagConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    confirmed_ids = []
    for doc in payload.documents:
        # 各ドキュメントのタグを更新
        update_document_tags(db, doc.document_id, doc.tags)
        update_document_status(db, doc.document_id, "confirmed")
        confirmed_ids.append(doc.document_id)
        # バックグラウンドで chunk + index パイプラインを開始
        background_tasks.add_task(
            process_after_confirm, doc.document_id
        )
    return {"confirmed": confirmed_ids}
```

#### 一括タグ確認フロー（複数ファイル）

```
複数ファイル D&D
  → ファイル保存、document_id 発行
  → バックグラウンド: convert（並行、最大3）
  → バックグラウンド: AI tag（並行、最大3）
  → 全ファイル "tagged" → BatchTagEditor 表示
  → ユーザーがテーブルでタグ確認・編集
  → 「全て確定」クリック → PATCH /api/documents/batch-tags
  → バックグラウンド: chunk + index（並行、最大3）
  → 完了
```

#### 制約

- 最大ファイル数: `MAX_BATCH_UPLOAD_FILES` (20)
- 合計最大サイズ: `MAX_BATCH_UPLOAD_SIZE` (200MB)
- ZIP 内のファイルも `ALLOWED_EXTENSIONS` でフィルタリング

---

## 3. フロントエンド設計

### 3.1 ディレクトリ構成

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── app/
│   │   ├── App.tsx              # ルートコンポーネント
│   │   ├── router.tsx           # React Router v7 設定
│   │   └── providers.tsx        # QueryClient, Theme プロバイダー
│   │
│   ├── pages/
│   │   ├── ChatPage.tsx         # メインチャット画面
│   │   ├── UploadPage.tsx       # ドキュメントアップロード
│   │   ├── DocumentsPage.tsx    # ドキュメント一覧・管理
│   │   ├── KnowledgeBasesPage.tsx # ナレッジベース管理
│   │   └── SettingsPage.tsx     # ユーザー設定
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx     # Outlet ラッパー
│   │   │   ├── Sidebar.tsx      # ナビゲーションサイドバー
│   │   │   ├── Header.tsx       # モバイル用ヘッダー
│   │   │   └── SessionSearch.tsx # セッション横断キーワード検索
│   │   │
│   │   ├── chat/
│   │   │   ├── MessageList.tsx          # role="log" + 仮想スクロール
│   │   │   ├── MessageBubble.tsx        # ユーザー/AI メッセージ
│   │   │   ├── ChatInput.tsx            # テキスト入力 + 音声 + 送信
│   │   │   ├── SourceList.tsx           # 参照元ドキュメントリスト
│   │   │   ├── StarRating.tsx           # 回答評価 (1-5星)
│   │   │   ├── TermSuggestions.tsx      # 未知語候補チップ
│   │   │   └── ResponseModeToggle.tsx   # シンプル/詳細モード切替
│   │   │
│   │   ├── upload/
│   │   │   ├── DropZone.tsx             # ファイルドロップエリア
│   │   │   ├── ConversionPreview.tsx    # 変換プレビュー
│   │   │   ├── TagEditor.tsx            # AIタグ確認・編集（単一ファイル）
│   │   │   ├── BatchTagEditor.tsx      # 一括タグ確認・編集（複数ファイル）
│   │   │   └── VersionConflictDialog.tsx # 重複ファイル処理
│   │   │
│   │   ├── documents/
│   │   │   ├── DocumentTable.tsx        # ドキュメント一覧テーブル（未確認バッジ表示対応）
│   │   │   ├── TagFilter.tsx            # タグでフィルタリング
│   │   │   ├── VersionHistory.tsx       # バージョン履歴
│   │   │   └── MarkdownPreview.tsx      # ドキュメントプレビュー
│   │   │
│   │   ├── output/
│   │   │   ├── OutputPanel.tsx          # 出力パネルコンテナ（開閉制御）
│   │   │   ├── DataTable.tsx            # ページネーション付きテーブル
│   │   │   ├── ChartView.tsx            # Recharts グラフ表示
│   │   │   └── DownloadButtons.tsx      # CSV/PNG/SVG ダウンロード
│   │   │
│   │   ├── knowledge-base/
│   │   │   ├── KnowledgeBaseList.tsx    # KB一覧（お気に入りフィルター付き）
│   │   │   ├── KnowledgeBaseCard.tsx    # KB表示カード（お気に入りボタン付き）
│   │   │   └── CreateKBDialog.tsx       # KB作成ダイアログ
│   │   │
│   │   ├── settings/
│   │   │   ├── SettingsForm.tsx         # 設定フォーム
│   │   │   ├── TermDictionary.tsx       # 個人用語辞書管理
│   │   │   └── ProfileInfo.tsx          # プロファイル情報表示
│   │   │
│   │   └── shared/
│   │       ├── CopyButton.tsx           # Markdown コピー
│   │       ├── VoiceButton.tsx          # 音声入力ボタン
│   │       └── SourcePreviewModal.tsx   # ソースプレビューモーダル
│   │
│   ├── hooks/
│   │   ├── useChat.ts           # SSEストリーミング + チャット状態
│   │   ├── useVoiceInput.ts     # Web Speech API
│   │   ├── useStarRating.ts     # 星評価ロジック
│   │   ├── useSessions.ts       # セッション一覧 (TanStack Query)
│   │   ├── useDocuments.ts      # ドキュメント操作 (TanStack Query)
│   │   ├── useUser.ts           # ユーザープロファイル
│   │   ├── useOutput.ts         # 出力データ取得・ダウンロード
│   │   └── useKnowledgeBases.ts # KB操作フック（TanStack Query）
│   │
│   ├── api/
│   │   ├── client.ts            # fetch ベースAPIクライアント
│   │   ├── chat.ts              # チャットAPI
│   │   ├── sessions.ts          # セッションAPI
│   │   ├── documents.ts         # ドキュメントAPI
│   │   ├── users.ts             # ユーザーAPI
│   │   ├── master.ts            # マスターデータAPI
│   │   ├── output.ts            # 出力データAPI（取得・CSVダウンロード）
│   │   ├── knowledge-bases.ts   # KB API（CRUD・お気に入り）
│   │   └── sse.ts               # SSEストリーミング処理
│   │
│   ├── stores/
│   │   ├── chatStore.ts         # ストリーミング中の状態 (Zustand)
│   │   ├── userStore.ts         # ユーザーID・設定 (Zustand + localStorage)
│   │   ├── outputStore.ts       # 出力パネル状態 (Zustand)
│   │   ├── kbStore.ts           # 選択中のKB状態管理 (Zustand)
│   │   └── uiStore.ts           # サイドバー開閉・モーダル (Zustand)
│   │
│   ├── types/
│   │   ├── message.ts           # Message, StreamChunk 型
│   │   ├── document.ts          # Document, DocumentStatus 型
│   │   ├── user.ts              # User, UserTerm 型
│   │   ├── session.ts           # Session 型
│   │   ├── master.ts            # SiteMaster, LineMaster, ProcessMaster 型
│   │   ├── tag.ts               # TagSuggestion, Tag 型
│   │   ├── output.ts            # OutputData, TableData, ChartConfig 型
│   │   └── knowledge-base.ts    # KnowledgeBase, CreateKBRequest 型
│   │
│   └── utils/
│       ├── fingerprint.ts       # ユーザーIDの永続化
│       ├── markdown.ts          # Markdownレンダリングヘルパー
│       └── date.ts              # 日付フォーマット
│
├── index.html
├── vite.config.ts
├── tsconfig.json
└── package.json
```

### 3.2 ルーティング（React Router v7）

```typescript
// router.tsx
export const router = createBrowserRouter([
    {
        path: "/",
        element: <AppShell />,      // Sidebar は AppShell で管理、ナビゲーション時にアンマウントしない
        children: [
            { index: true, element: <Navigate to="/chat" replace /> },
            { path: "chat", element: <ChatPage /> },
            { path: "chat/:sessionId", element: <ChatPage /> },
            { path: "upload", element: <UploadPage /> },
            { path: "documents", element: <DocumentsPage /> },
            { path: "documents/:id", element: <DocumentsPage /> },  // ドロワー自動展開
            { path: "settings", element: <SettingsPage /> },
            { path: "knowledge-bases", element: <KnowledgeBasesPage /> },
        ],
    },
]);
```

**設計上の注意:**
- `AppShell` が `<Outlet />` をラップするため、Sidebar はページ遷移でアンマウントされない
- `/documents/:id` は DocumentsPage 内でドロワーを自動展開する（URL共有対応）
- Sidebar にお気に入りナレッジベースを常時表示し、クリックでチャット対象KBを選択

### 3.3 状態管理

| 状態種別 | 管理方法 | 理由 |
|---------|---------|------|
| サーバーデータ（セッション一覧・ドキュメント） | TanStack Query | キャッシュ・リフェッチ・楽観的更新 |
| SSEストリーミングテキスト | Zustand chatStore | 高頻度更新（トークンごと）でRerender最適化 |
| 出力パネルデータ・開閉状態 | Zustand outputStore | SSE output イベントでの状態更新 |
| UI状態（サイドバー・モーダル） | Zustand uiStore | コンポーネント間共有が必要 |
| ユーザーID・設定 | Zustand userStore + localStorage永続化 | アプリ再起動後も維持 |
| 選択中ナレッジベース | Zustand kbStore + localStorage永続化 | KB選択をセッション跨ぎで維持 |
| フォーム一時状態 | コンポーネントローカルのuseState | スコープが限定的 |

#### chatStore の型定義

```typescript
interface ChatState {
    // 現在ストリーミング中のメッセージ
    streamingText: string;
    streamingStatus: "idle" | "query_analysis" | "vector_search" | "oracle_query" | "structuring_output" | "generating";
    sources: Source[];
    unknownTerms: UnknownTerm[];
    isStreaming: boolean;
    abortController: AbortController | null;

    // アクション
    appendStreamChunk: (text: string) => void;
    updateStatus: (status: StreamingStatus) => void;
    updateSources: (sources: Source[]) => void;
    showTermSuggestions: (terms: UnknownTerm[]) => void;
    finalizeStreaming: (messageId: string) => void;
    cancelStreaming: () => void;
    // cancelStreaming の詳細挙動:
    // 1. abortController.abort() を呼び出してSSEストリームを中断
    // 2. 途中までの streamingText を保持し、末尾に「（回答が中断されました）」を付与
    // 3. messagesテーブルに途中のcontentを role="assistant" で保存（API呼び出し）
    // 4. sources は受信済み分のみ表示
    // 5. 中断されたメッセージには isCancelled: true を設定し、StarRating を非表示にする
    // 6. outputStore のデータも受信済み分のみ保持
    // 7. isStreaming を false に設定 → ChatInput の disabled が解除され、入力可能に戻る

    // ストリーミング中の入力制御:
    // isStreaming が true の間:
    //   - ChatInput の TextField は disabled（キーボード入力不可）
    //   - 送信ボタンは disabled（停止ボタンに切り替え表示）
    //   - placeholder は「回答中...」に変更
    //   - 質問のキューイングは行わない（シンプルさ優先）
}
```

#### outputStore の型定義

```typescript
interface OutputState {
    // 出力パネルデータ
    outputData: {
        tableData: TableData | null;
        chartConfig: ChartConfig | null;
        sqlExecuted: string | null;
        rowCount: number;
    } | null;
    isOutputPanelOpen: boolean;

    // アクション
    setOutputData: (data: OutputData) => void;
    clearOutput: () => void;
    toggleOutputPanel: () => void;
}

interface TableData {
    columns: Array<{ key: string; label: string; type: "string" | "number" | "date" }>;
    rows: Array<Record<string, string | number>>;
}

interface ChartConfig {
    type: "line" | "bar" | "pie" | "area" | "histogram";
    x_axis: string;
    y_axis: string;
    series: Array<{ dataKey: string; name: string; color: string }>;
    title: string;
}
```

#### kbStore の型定義

```typescript
interface KBState {
    selectedKBId: string | null;
    setSelectedKB: (id: string) => void;  // KB切り替え時は新規セッションを自動作成
    clearSelectedKB: () => void;
}
```

#### Sidebar の変更

- Sidebar 上部にお気に入りナレッジベースを表示
- 各KBカードは name、color インジケーター、document_count を表示
- KBをクリックするとチャット対象として選択（kbStore.setSelectedKB）
  - チャット中に別のKBを選択した場合、現在のセッションを保持したまま新規セッションを自動作成する
  - セッションは常に1つのKBに紐付き、途中でKBを変更することはない
- 「全てのナレッジベース」リンクで `/knowledge-bases` ページへ遷移

#### ChatPage の変更

- チャットヘッダーに選択中のナレッジベース名を表示
- ナレッジベースが未選択の場合、ユーザーに選択を促すメッセージを表示
- ナレッジベースが未選択の場合、チャット入力は無効化（disabled）
- POST `/api/chat` のリクエストボディに `knowledge_base_id` を含める
- KB切り替え時は新規セッションが自動開始される（kbStore.setSelectedKB 内で sessionStore に新規セッション作成を通知）

### 3.4 SSEストリーミング設計

#### EventSource を使わない理由

EventSource はGETリクエストのみ対応しており、POSTリクエストボディでクエリを送信できない。そのため `fetch` + `ReadableStream` + `TextDecoder` でSSEを手動パースする。

```typescript
// api/sse.ts
export async function streamChat(
    request: ChatRequest,
    handlers: SSEHandlers,
    signal: AbortSignal
): Promise<void> {
    const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal,
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";  // 未完結行をバッファに残す

        for (const line of lines) {
            if (line.startsWith("event: ")) {
                // イベント名を記録
            } else if (line.startsWith("data: ")) {
                const data = JSON.parse(line.slice(6));
                dispatchSSEEvent(eventName, data, handlers);
            }
        }
    }
}
```

#### SSEストリーミング中断処理

AbortController.abort() によりストリームが中断された場合の処理フロー:

1. `streamChat` 内で `AbortError` をキャッチし、`handlers.onError` ではなく専用の中断ハンドラを呼び出す
2. `chatStore.cancelStreaming` が以下を実行:
   - `abortController.abort()` でストリームを停止
   - 途中までの `streamingText` を保持
   - テキスト末尾に `\n\n（回答が中断されました）` を付与
   - `POST /api/messages` で途中の content を `role="assistant"`, `is_cancelled=true` として保存
   - `sources` は受信済み分のみ保持
   - `outputStore` のデータは受信済み分のみ保持（クリアしない）
   - `isStreaming` を `false` に設定
3. `StarRating` コンポーネントは `isCancelled: true` のメッセージに対して非表示となる

#### useChat フックの役割

```typescript
// hooks/useChat.ts
export function useChat(sessionId: string | undefined) {
    const chatStore = useChatStore();
    const userStore = useUserStore();
    const kbStore = useKBStore();

    const sendMessage = useCallback(async (text: string) => {
        const abortController = new AbortController();
        chatStore.startStreaming(abortController);

        await streamChat(
            {
                session_id: sessionId,
                message: text,
                response_mode: userStore.responseMode,
                filters: userStore.activeFilters,
                knowledge_base_id: kbStore.selectedKBId,
            },
            {
                onToken: chatStore.appendStreamChunk,
                onStatus: chatStore.updateStatus,
                onSources: chatStore.updateSources,
                onTerms: chatStore.showTermSuggestions,
                onOutput: outputStore.setOutputData,
                onComplete: chatStore.finalizeStreaming,
                onError: chatStore.handleError,
            },
            abortController.signal
        );
    }, [sessionId, chatStore, userStore]);

    return { sendMessage, cancelStreaming: chatStore.cancelStreaming };
}
```

### 3.5 主要コンポーネント設計

#### StarRating

```typescript
// components/chat/StarRating.tsx
function StarRating({ messageId, onRate }: StarRatingProps) {
    const [hoverValue, setHoverValue] = useState<number | null>(null);
    const [confirmedValue, setConfirmedValue] = useState<number | null>(null);

    // 表示値: ホバー中の値 → 確定値 → 0
    const displayValue = hoverValue ?? confirmedValue ?? 0;

    const handleConfirm = async (rating: number) => {
        const prev = confirmedValue;
        setConfirmedValue(rating);  // 楽観的更新
        try {
            await rateMessage(messageId, rating);
        } catch {
            setConfirmedValue(prev);  // 失敗時ロールバック
        }
    };

    return (
        // role="radiogroup" + ローバービングタブインデックス
        <div role="radiogroup" aria-label="回答を評価">
            {[1, 2, 3, 4, 5].map((star) => (
                <SerendieSymbolStar
                    key={star}
                    filled={star <= displayValue}
                    tabIndex={star === (confirmedValue ?? 1) ? 0 : -1}  // ローバービング
                    onMouseEnter={() => setHoverValue(star)}
                    onMouseLeave={() => setHoverValue(null)}
                    onClick={() => handleConfirm(star)}
                    onKeyDown={(e) => handleArrowKey(e, star)}  // ← → Space
                    aria-label={`${star}星`}
                    aria-checked={confirmedValue === star}
                />
            ))}
        </div>
    );
}
```

#### VoiceButton

```typescript
// components/shared/VoiceButton.tsx
type VoiceState = "idle" | "listening" | "done" | "error" | "unsupported";

function VoiceButton({ onTranscript }: VoiceButtonProps) {
    const [state, setState] = useState<VoiceState>(
        "SpeechRecognition" in window ? "idle" : "unsupported"
    );

    const start = () => {
        const recognition = new window.SpeechRecognition();
        recognition.lang = "ja-JP";
        recognition.interimResults = true;
        recognition.continuous = false;

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(r => r[0].transcript)
                .join("");
            onTranscript(transcript, event.results[event.results.length - 1].isFinal);
        };

        recognition.onend = () => setState("done");
        recognition.onerror = () => setState("error");
        recognition.start();
        setState("listening");
    };

    if (state === "unsupported") {
        return (
            <Tooltip content="このブラウザは音声入力に対応していません">
                <button disabled aria-label="音声入力（未対応）" aria-pressed="false">
                    <MicIcon style={{ opacity: 0.4 }} />
                </button>
            </Tooltip>
        );
    }

    return (
        <button
            onClick={state === "listening" ? stop : start}
            aria-pressed={state === "listening"}
            aria-label={state === "listening" ? "音声入力停止" : "音声入力開始"}
        >
            <MicIcon data-state={state} />
        </button>
    );
}
```

#### ChatInput（ストリーミング中の入力制御）

```typescript
// components/chat/ChatInput.tsx
function ChatInput({ onSend, isStreaming, onCancel }: ChatInputProps) {
    const [text, setText] = useState("");

    return (
        <div>
            <TextField
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={isStreaming}
                placeholder={isStreaming ? "回答中..." : "メッセージを入力"}
                aria-label={isStreaming ? "回答中のため入力できません" : "メッセージを入力"}
                onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !isStreaming) {
                        e.preventDefault();
                        onSend(text);
                        setText("");
                    }
                }}
            />
            <VoiceButton onTranscript={(t) => setText(t)} disabled={isStreaming} />
            {isStreaming ? (
                <button onClick={onCancel} aria-label="回答を停止">
                    <StopIcon />
                </button>
            ) : (
                <button
                    onClick={() => { onSend(text); setText(""); }}
                    disabled={!text.trim() || isStreaming}
                    aria-label="送信"
                >
                    <SendIcon />
                </button>
            )}
        </div>
    );
}
```

**ストリーミング中の挙動:**
- `isStreaming=true` の間、TextField は `disabled` 属性が設定され、キーボード入力を受け付けない
- プレースホルダーが「回答中...」に変更される
- 送信ボタンが停止ボタンに切り替わる
- キャンセル（停止ボタン）押下で `chatStore.cancelStreaming()` が呼び出され、入力可能に戻る
- 質問のキューイングは行わない（シンプルさ優先）

#### TermSuggestions（チャットインライン表示）

```typescript
// components/chat/TermSuggestions.tsx
function TermSuggestions({ terms, onLearn }: TermSuggestionsProps) {
    const [masterSearchOpen, setMasterSearchOpen] = useState(false);

    return (
        <div role="region" aria-label="未知の用語候補">
            <p>以下の用語が見つかりました。正式名称を確認してください：</p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                {terms.slice(0, 3).map(term => (
                    <TermChip key={term.unknown_term} term={term} onLearn={onLearn} />
                ))}
                {terms.length > 3 && (
                    <button onClick={() => setMasterSearchOpen(true)}>
                        その他 {terms.length - 3}件...
                    </button>
                )}
            </div>

            <MasterSearchModal
                open={masterSearchOpen}
                terms={terms.slice(3)}
                onClose={() => setMasterSearchOpen(false)}
                onLearn={onLearn}
            />
        </div>
    );
}

function TermChip({ term, onLearn }: TermChipProps) {
    const [rememberChecked, setRememberChecked] = useState(false);

    const handleConfirm = async (selectedCode: string) => {
        if (rememberChecked) {
            await onLearn(term.unknown_term, selectedCode);
            toast.success("用語を辞書に追加しました");
        }
    };

    return (
        <div>
            <span>{term.unknown_term}</span>
            <select onChange={(e) => handleConfirm(e.target.value)}>
                {term.candidates.map(c => (
                    <option key={c.code} value={c.code}>{c.name}</option>
                ))}
            </select>
            <label>
                <input
                    type="checkbox"
                    checked={rememberChecked}
                    onChange={e => setRememberChecked(e.target.checked)}
                />
                この用語を覚える
            </label>
        </div>
    );
}
```

#### DropZone

```typescript
// components/upload/DropZone.tsx
type BatchUploadItem = { id: string; filename: string; status: string };

function DropZone({ onUploadComplete }: DropZoneProps) {
    const [dragOver, setDragOver] = useState(false);
    const [uploadState, setUploadState] = useState<UploadState>("idle");
    const [batchItems, setBatchItems] = useState<BatchUploadItem[]>([]);

    const handleDrop = async (files: File[]) => {
        if (files.length > 20) {
            // エラー表示: 最大20ファイルまで
            return;
        }
        setUploadState("uploading");

        // 一括アップロード API（複数ファイル + ZIP対応）
        const formData = new FormData();
        for (const file of files) {
            formData.append("files", file);
        }
        formData.append("knowledge_base_id", selectedKbId);

        const results: BatchUploadItem[] = await uploadDocuments(formData);
        setBatchItems(results);

        // 各ドキュメントのステータスをポーリング
        for (const item of results) {
            pollDocumentStatus(item.id, {
                onTagged: () => updateItemStatus(item.id, "tagged"),
                onIndexed: () => {
                    updateItemStatus(item.id, "indexed");
                    onUploadComplete(item.id);
                },
                onError: (stage) => updateItemStatus(item.id, `${stage}_failed`),
                timeout: 5 * 60 * 1000,  // 5分
            });
        }
    };

    return (
        <div
            role="region"
            aria-dropeffect="copy"
            aria-label="ファイルをドロップしてアップロード（複数ファイル・ZIP対応）"
            data-drag-over={dragOver}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleDrop([...e.dataTransfer.files]); }}
        >
            {uploadState === "idle" && (
                <p>ファイルをドロップ、またはクリックして選択（最大20ファイル、ZIP対応）</p>
            )}
            {uploadState === "uploading" && (
                <div>
                    {batchItems.map(item => (
                        <div key={item.id}>
                            <span>{item.filename}</span>
                            <ProgressIndicator status={item.status} />
                        </div>
                    ))}
                </div>
            )}
            {uploadState === "tagged" && batchItems.length === 1 && (
                <TagEditor onConfirm={confirmTags} />
            )}
            {uploadState === "tagged" && batchItems.length > 1 && (
                <BatchTagEditor
                    items={batchItems}
                    onConfirmAll={confirmBatchTags}
                    onConfirmSingle={confirmTags}
                />
            )}
        </div>
    );
}
```

#### BatchTagEditor

```typescript
// components/upload/BatchTagEditor.tsx
type BatchTagRow = {
    document_id: string;
    filename: string;
    status: string;  // "tagged" | "tagging" | "convert_failed" etc.
    tags: {
        site: string;
        line: string;
        process: string;
        category: string;
        keywords: string[];
        confidence: number;
    };
};

type BatchTagEditorProps = {
    items: BatchTagRow[];
    onConfirmAll: (documents: BatchTagConfirmPayload[]) => void;
    onConfirmSingle: (documentId: string, tags: TagUpdate[]) => void;
};

function BatchTagEditor({ items, onConfirmAll, onConfirmSingle }: BatchTagEditorProps) {
    const [editableRows, setEditableRows] = useState<BatchTagRow[]>(items);

    const handleCellEdit = (docId: string, field: string, value: string) => {
        setEditableRows(prev =>
            prev.map(row =>
                row.document_id === docId
                    ? { ...row, tags: { ...row.tags, [field]: value } }
                    : row
            )
        );
    };

    const allTagged = editableRows.every(row => row.status === "tagged");

    return (
        <div role="region" aria-label="一括タグ確認">
            <table role="grid" aria-label="アップロードファイル一覧">
                <thead>
                    <tr>
                        <th>ファイル名</th>
                        <th>サイト</th>
                        <th>ライン</th>
                        <th>工程</th>
                        <th>カテゴリ</th>
                        <th>キーワード</th>
                        <th>AI信頼度</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    {editableRows.map(row => (
                        <tr key={row.document_id}>
                            <td>{row.filename}</td>
                            {row.status === "tagged" ? (
                                <>
                                    <td onClick={() => /* inline edit */}>
                                        {row.tags.site}
                                    </td>
                                    <td>{row.tags.line}</td>
                                    <td>{row.tags.process}</td>
                                    <td>{row.tags.category}</td>
                                    <td>{row.tags.keywords.join(", ")}</td>
                                    <td>{Math.round(row.tags.confidence * 100)}%</td>
                                    <td>
                                        <button onClick={() => onConfirmSingle(row.document_id, ...)}>
                                            個別確定
                                        </button>
                                    </td>
                                </>
                            ) : (
                                <td colSpan={7}>
                                    <Spinner /> タグ付け中...
                                </td>
                            )}
                        </tr>
                    ))}
                </tbody>
            </table>
            <button
                disabled={!allTagged}
                onClick={() => onConfirmAll(buildPayload(editableRows))}
            >
                全て確定
            </button>
        </div>
    );
}
```

#### ResponseModeToggle

```typescript
// components/chat/ResponseModeToggle.tsx
function ResponseModeToggle() {
    const { simpleMode, setSimpleMode } = useUserStore();

    return (
        <div role="group" aria-label="回答モード">
            <button
                aria-pressed={simpleMode}
                onClick={() => setSimpleMode(true)}
            >
                シンプル
            </button>
            <button
                aria-pressed={!simpleMode}
                onClick={() => setSimpleMode(false)}
            >
                詳細
            </button>
        </div>
    );
}
```

#### SourcePreviewModal

```typescript
// components/shared/SourcePreviewModal.tsx
function SourcePreviewModal({ source, onClose }: SourcePreviewModalProps) {
    const modalRef = useRef<HTMLDivElement>(null);

    // フォーカストラップ
    useFocusTrap(modalRef);

    // Escapeキーで閉じる
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

    return (
        <div
            ref={modalRef}
            role="dialog"
            aria-modal="true"
            aria-label={`ソースプレビュー: ${source.file}`}
        >
            <button onClick={onClose} aria-label="閉じる">×</button>
            <MarkdownPreview content={source.content} />
        </div>
    );
}
```

### 3.6 OutputPanel コンポーネント設計

#### コンポーネント構成

```
components/output/
├── OutputPanel.tsx        # 出力パネルコンテナ（開閉制御）
├── DataTable.tsx          # ページネーション付きテーブル
├── ChartView.tsx          # Recharts グラフ表示
└── DownloadButtons.tsx    # CSV/PNG/SVG ダウンロード
```

#### OutputPanel

- チャットエリアの右側に固定配置（Desktop 1280px+ で width: 400px）
- データがない時は非表示（チャットが全幅を使用）
- SSE `output` イベント受信で自動展開（outputStore.setOutputData → isOutputPanelOpen = true）
- 閉じるボタンで非表示に戻る（outputStore.toggleOutputPanel）
- output_type に応じてタブ切替（テーブル / グラフ / 両方）

```typescript
// components/output/OutputPanel.tsx
function OutputPanel() {
    const { outputData, isOutputPanelOpen, toggleOutputPanel } = useOutputStore();

    if (!outputData || !isOutputPanelOpen) return null;

    return (
        <aside aria-label="出力パネル" style={{ width: "400px", flexShrink: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2>出力結果</h2>
                <IconButton onClick={toggleOutputPanel} aria-label="出力パネルを閉じる">
                    <SerendieSymbolClose />
                </IconButton>
            </div>

            {outputData.tableData && (
                <DataTable data={outputData.tableData} />
            )}
            {outputData.chartConfig && (
                <ChartView config={outputData.chartConfig} data={outputData.tableData} />
            )}
            <DownloadButtons outputData={outputData} />
        </aside>
    );
}
```

#### DataTable（Serendie DataTable 拡張）

- Serendie の DataTable コンポーネントをベースに拡張
- ページネーション: 1ページ20行、変更可能（10/20/50/100）
- カラムソート: onSortingChange でソート状態管理
- CSVダウンロード: Blob で生成、日本語対応（BOM付きUTF-8）
- Markdownコピー: テーブルを Markdown 形式でクリップボードにコピー

```typescript
// components/output/DataTable.tsx
function DataTable({ data }: { data: TableData }) {
    const [page, setPage] = useState(0);
    const [pageSize, setPageSize] = useState(20);
    const [sorting, setSorting] = useState<SortingState>([]);

    const sortedRows = useMemo(() => {
        if (sorting.length === 0) return data.rows;
        return [...data.rows].sort((a, b) => {
            const col = sorting[0];
            const aVal = a[col.id];
            const bVal = b[col.id];
            return col.desc ? (bVal > aVal ? 1 : -1) : (aVal > bVal ? 1 : -1);
        });
    }, [data.rows, sorting]);

    const pageRows = sortedRows.slice(page * pageSize, (page + 1) * pageSize);

    return (
        <div role="region" aria-label="検索結果テーブル">
            <SerendieDataTable
                columns={data.columns.map(col => ({
                    accessorKey: col.key,
                    header: col.label,
                }))}
                data={pageRows}
                onSortingChange={setSorting}
            />
            <Pagination
                page={page}
                pageSize={pageSize}
                total={data.rows.length}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                pageSizeOptions={[10, 20, 50, 100]}
            />
        </div>
    );
}
```

#### ChartView（Recharts）

- chart_config に基づき動的にグラフ種別を切替
- 対応グラフ: LineChart, BarChart, PieChart, AreaChart
- ResponsiveContainer でパネル幅に自動フィット
- ダウンロード: SVG 要素を PNG/SVG に変換してダウンロード
  - PNG: SVG → Canvas → PNG（html2canvas 不要、ネイティブ SVG → Canvas 変換）
  - SVG: SVG 要素の outerHTML を Blob で出力

```typescript
// components/output/ChartView.tsx
function ChartView({ config, data }: { config: ChartConfig; data: TableData | null }) {
    const chartRef = useRef<HTMLDivElement>(null);

    if (!data) return null;

    const renderChart = () => {
        switch (config.type) {
            case "line":
                return (
                    <LineChart data={data.rows}>
                        <XAxis dataKey={config.x_axis} />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        {config.series.map(s => (
                            <Line key={s.dataKey} dataKey={s.dataKey} name={s.name} stroke={s.color} />
                        ))}
                    </LineChart>
                );
            case "bar":
                return (
                    <BarChart data={data.rows}>
                        <XAxis dataKey={config.x_axis} />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        {config.series.map(s => (
                            <Bar key={s.dataKey} dataKey={s.dataKey} name={s.name} fill={s.color} />
                        ))}
                    </BarChart>
                );
            case "pie":
                return (
                    <PieChart>
                        <Pie data={data.rows} dataKey={config.y_axis} nameKey={config.x_axis} label />
                        <RechartsTooltip />
                        <Legend />
                    </PieChart>
                );
            case "area":
                return (
                    <AreaChart data={data.rows}>
                        <XAxis dataKey={config.x_axis} />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        {config.series.map(s => (
                            <Area key={s.dataKey} dataKey={s.dataKey} name={s.name} fill={s.color} stroke={s.color} />
                        ))}
                    </AreaChart>
                );
        }
    };

    return (
        <div ref={chartRef} role="img" aria-label={config.title}>
            <h3>{config.title}</h3>
            <ResponsiveContainer width="100%" height={300}>
                {renderChart()}
            </ResponsiveContainer>
        </div>
    );
}
```

#### DownloadButtons

- テーブル用: [CSVダウンロード] [Markdownコピー]
- グラフ用: [PNGダウンロード] [SVGダウンロード]
- Serendie IconButton + SerendieSymbolDownload アイコン

```typescript
// components/output/DownloadButtons.tsx
function DownloadButtons({ outputData }: { outputData: OutputData }) {
    const downloadCSV = () => {
        if (!outputData.tableData) return;
        const bom = "\uFEFF"; // BOM付きUTF-8
        const header = outputData.tableData.columns.map(c => c.label).join(",");
        const rows = outputData.tableData.rows.map(row =>
            outputData.tableData!.columns.map(c => `"${String(row[c.key]).replace(/"/g, '""')}"`).join(",")
        );
        const csv = bom + [header, ...rows].join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        downloadBlob(blob, "output.csv");
    };

    const copyMarkdown = async () => {
        if (!outputData.tableData) return;
        const { columns, rows } = outputData.tableData;
        const header = `| ${columns.map(c => c.label).join(" | ")} |`;
        const separator = `| ${columns.map(() => "---").join(" | ")} |`;
        const body = rows.map(row =>
            `| ${columns.map(c => String(row[c.key])).join(" | ")} |`
        ).join("\n");
        await navigator.clipboard.writeText([header, separator, body].join("\n"));
    };

    return (
        <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
            {outputData.tableData && (
                <>
                    <IconButton onClick={downloadCSV} aria-label="CSVダウンロード">
                        <SerendieSymbolDownload />
                    </IconButton>
                    <IconButton onClick={copyMarkdown} aria-label="Markdownコピー">
                        <SerendieSymbolCopy />
                    </IconButton>
                </>
            )}
            {outputData.chartConfig && (
                <>
                    <IconButton onClick={() => downloadChartAsPNG()} aria-label="PNGダウンロード">
                        <SerendieSymbolDownload />
                    </IconButton>
                    <IconButton onClick={() => downloadChartAsSVG()} aria-label="SVGダウンロード">
                        <SerendieSymbolDownload />
                    </IconButton>
                </>
            )}
        </div>
    );
}
```

### 3.7 レスポンシブレイアウト

```
Desktop (1280px+): チャットページは3カラム
┌──────────────────────────────────────────────────────────────────┐
│ [Sidebar 240px] │ [Chat Area flex]      │ [Output Panel 400px]  │
│                 │                       │                       │
│ ナビゲーション   │  チャットコンテンツ    │  テーブル / グラフ      │
│ セッション履歴   │                       │  ダウンロードボタン    │
│                 │                       │  ※データなし時は非表示  │
└──────────────────────────────────────────────────────────────────┘

Desktop (1024-1279px): Output Panel は overlay/drawer
┌─────────────────────────────────────────────┐
│ [Sidebar 240px] │ [Chat Area flex]          │
│                 │                           │
│ ナビゲーション   │  チャットコンテンツ        │
│ セッション履歴   │                           │
│                 │  [Output: overlay/drawer] │
└─────────────────────────────────────────────┘

Mobile (~1023px):
┌─────────────────────────────────────────────┐
│ [TopBar: ☰ タイトル]                         │
├─────────────────────────────────────────────┤
│ [Chat full-width]                            │
│                                             │
│ チャットコンテンツ                            │
│                                             │
├─────────────────────────────────────────────┤
│ [Output: ボトムシート]                        │
├─────────────────────────────────────────────┤
│ [BottomNavigation]                           │
└─────────────────────────────────────────────┘

Sidebar（モバイル時）:
  → オーバーレイドロワーとして表示
  → Serendie の Drawer コンポーネントを使用
  → aria-expanded, aria-controls で制御

Output Panel（モバイル時）:
  → ボトムシートとして表示（ドラッグでリサイズ可能）
  → または、チャットとOutputのタブ切替
```

```typescript
// layout/AppShell.tsx
const breakpoint = useBreakpoint();  // Serendie トークンのブレークポイント使用
const { isOutputPanelOpen } = useOutputStore();

return (
    <div data-layout={breakpoint >= 1280 ? "desktop-wide" : breakpoint >= 1024 ? "desktop" : "mobile"}>
        {breakpoint >= 1024 ? (
            <Sidebar variant="fixed" width="240px" />
        ) : (
            <>
                <Header onMenuClick={uiStore.openSidebar} />
                <Drawer open={uiStore.sidebarOpen} onClose={uiStore.closeSidebar}>
                    <Sidebar variant="drawer" />
                </Drawer>
            </>
        )}
        <main style={{ display: "flex", flex: 1 }}>
            <Outlet />
            {breakpoint >= 1280 && <OutputPanel />}
        </main>
        {breakpoint >= 1024 && breakpoint < 1280 && isOutputPanelOpen && (
            <Drawer anchor="right" open={isOutputPanelOpen} onClose={outputStore.toggleOutputPanel}>
                <OutputPanel />
            </Drawer>
        )}
        {breakpoint < 1024 && isOutputPanelOpen && (
            <BottomSheet open={isOutputPanelOpen} onClose={outputStore.toggleOutputPanel}>
                <OutputPanel />
            </BottomSheet>
        )}
        {breakpoint < 1024 && <BottomNavigation />}
    </div>
);
```

### 3.8 Serendie Design System 使用方針

**テーマ**: `data-panda-theme="konjo"` （藍色系、製造業向け）

| RAG Phantom パーツ | Serendie コンポーネント | 補足 |
|-------------------|----------------------|------|
| 送信ボタン | `Button` (primary) | |
| テキスト入力 | `TextField` | 複数行対応 |
| Rerank/Hybridトグル | `Switch` | |
| タグフィルター | `Select` | 複数選択 |
| モーダル | `Dialog` | |
| サイドバー（モバイル） | `Drawer` | |
| トースト通知 | `Toast` | |
| 進捗表示 | `ProgressIndicator` | |
| ドキュメント一覧 | `DataTable` | |
| ナビゲーション（デスクトップ） | `Tabs` | |
| ナビゲーション（モバイル） | `BottomNavigation` | |
| StarRating | カスタム | Ark UI RadioGroup + SerendieSymbolStar |
| DropZone | カスタム | HTML5 DnD + Serendie デザイントークン |
| ResponseModeToggle | カスタム | ChoiceBox または SegmentedControl 相当 |
| OutputPanel | カスタム | Serendie DataTable + Recharts + IconButton |
| DownloadButtons | `IconButton` + `SerendieSymbolDownload` | CSV/PNG/SVG ダウンロード |

### 3.9 アクセシビリティ（WCAG 2.2 AA）

| コンポーネント | ARIA実装 | 備考 |
|--------------|---------|------|
| MessageList | `role="log"` `aria-live="polite"` | 新メッセージを読み上げ |
| StarRating | `role="radiogroup"` + ローバービングタブインデックス | ←→キー + Spaceで操作 |
| VoiceButton | `aria-pressed` + `aria-label` | 状態変化を通知 |
| DropZone | `role="region"` `aria-dropeffect="copy"` | |
| SourcePreviewModal | `role="dialog"` `aria-modal="true"` + フォーカストラップ | Escapeで閉じる |
| StreamingCursor | `aria-hidden="true"` | 読み上げ対象外 |
| ChatInput | `aria-label="メッセージを入力"` / ストリーミング中: `aria-label="回答中のため入力できません"` `disabled` | ストリーミング中は `placeholder="回答中..."` |
| TermSuggestions | `role="region"` `aria-label="未知の用語候補"` | |
| OutputPanel | `role="complementary"` `aria-label="出力パネル"` | 閉じるボタンにフォーカス管理 |
| DataTable | `role="region"` `aria-label="検索結果テーブル"` | ページネーション操作対応 |
| ChartView | `role="img"` `aria-label="{title}"` | グラフ内容をaria-labelで説明 |

#### キーボードショートカット

| ショートカット | 動作 |
|-------------|------|
| `Ctrl+Enter` | メッセージ送信 |
| `Escape` | モーダルを閉じる |
| `←` / `→` | StarRating の評価変更 |
| `Space` | StarRating の評価確定 |

#### カラーコントラスト要件

- テキスト: コントラスト比 4.5:1 以上（AA）
- 大きなテキスト (18pt+): コントラスト比 3:1 以上
- フォーカスインジケーター: コントラスト比 3:1 以上（WCAG 2.2 新規）
- Serendie konjo テーマは製造業向けに設計されており、上記基準を満たすことを確認

### 3.10 パフォーマンス

| 最適化 | 実装 | 理由 |
|--------|------|------|
| コード分割 | `React.lazy` + `Suspense`（ページレベル） | 初期バンドルサイズ削減 |
| 仮想スクロール | `@tanstack/react-virtual`（MessageList） | 長いセッションのレンダリング最適化 |
| サーバーキャッシュ | TanStack Query `staleTime` | マスターデータ: Infinity、メッセージ: 0 |
| 画像遅延読み込み | `loading="lazy"` | MarkdownPreview内の画像 |
| メモ化 | `React.memo` + `useMemo`（重いコンポーネント） | MessageBubble、SourceList |

---

## 4. データフロー図

### 4.1 ドキュメントアップロードフロー

```
[ユーザー]
  │
  │ ファイル（複数可・ZIP対応）をDropZoneにドロップ
  ▼
[フロントエンド: DropZone]
  │
  │ POST /api/documents/upload (multipart/form-data, files[], knowledge_base_id 必須)
  ▼
[バックエンド: documents.py]
  │ ZIP展開（対象拡張子のみ抽出）
  │ 各ファイルを /app/uploads に保存
  │ documents テーブルにレコード作成 (status="processing", knowledge_base_id を設定)
  │ [{id, filename, status}, ...] を即座に返却
  │ バックグラウンドで最大3並行処理 (asyncio.Semaphore(3))
  ▼
[フロントエンド]
  │ GET /api/documents/:id を2秒間隔でポーリング開始
  │
  └─ (並行してバックグラウンド処理)
        │
        ▼
       [1] converter.py
            PDF/PPTX/XLSX/DOCX/HTML/PNG を Markdown + 画像 に変換
            status: "converting" → "converted"
        │
        ▼
       [2] tagger.py
            3段階マスターマッチング:
              alias辞書 → SQLite LIKE → Qdrant semantic (>0.75)
            Claude (temperature=0): TagSuggestion 生成
            status: "tagging" → "tagged"
        │
        ▼
       [フロントエンド: タグ確認画面]
            単一ファイル: TagEditor 表示
            複数ファイル: BatchTagEditor 表示（テーブル形式で全ファイル一覧）
            ユーザーがAIタグ候補を確認・修正
            単一: PATCH /api/documents/:id/tags → status: "confirmed"
            複数: PATCH /api/documents/batch-tags → 全対象 status: "confirmed"
        │
        ▼
       [3] chunker.py
            戦略選択 (structural/agentic/meeting/table)
            親子チャンク構造を生成
            status: "chunking" → "chunked"
        │
        ▼
       [4] embedder.py
            Cohere Embed (96件バッチ):
              Dense 1024次元 + Sparse BM25-like
            Qdrant upsert (100件バッチ, gRPC)
            status: "indexing" → "indexed"
        │
        ▼
       [フロントエンド: 完了通知]
```

### 4.2 チャット検索フロー

```
[ユーザー]
  │
  │ テキスト入力（または音声入力 → Web Speech API → テキスト）
  │ ResponseModeToggle でシンプル/詳細モード選択
  ▼
[フロントエンド: useChat hook]
  │
  │ POST /api/chat (fetch + ReadableStream SSE)
  │ body: { message, session_id, response_mode, filters, knowledge_base_id }
  ▼
[バックエンド: rag.py]
  │
  ├─ [1] analyze_query (Claude)
  │       → intent: DOC_SEARCH | ORACLE_QUERY | HYBRID
  │       → filters: site_code, line_code, process_codes
  │       SSE: event: status, data: {"stage": "query_analysis"}
  │
  ├─ [2] translate_query_terms (user_profile.py)
  │       → スラング → 正式名称変換 (最長マッチ優先)
  │
  ├─ [3] detect_unknown_terms (user_profile.py)
  │       → マスター/個人辞書にない固有名詞を検出
  │       SSE: event: terms, data: [{unknown_term, candidates}]
  │       ← フロントエンド: TermSuggestions チップ表示
  │
  ├─ [4] Vector Search (Qdrant)
  │       → Cohere Embed でクエリベクトル生成 (input_type="search_query")
  │       → Dense + Sparse ハイブリッド検索 (オプション)
  │       → knowledge_base_id フィルター (必須) + メタデータフィルター + is_latest=True
  │       SSE: event: status, data: {"stage": "vector_search"}
  │
  ├─ [5] Parent-Child Expansion
  │       → ヒット子チャンク → parent_chunk_id で親取得
  │       → LLMへの入力は親チャンク (広いコンテキスト)
  │
  ├─ [6] Rerank (Cohere Rerank, オプション)
  │       → 検索結果を質問との関連度で再スコアリング
  │
  ├─ [6.5] 信頼度による回答拒否
  │       → 最高スコア < RELEVANCE_THRESHOLD (0.3) の場合
  │       → SSE: event: token, data: {"text": "選択されたナレッジベース内に該当する情報が見つかりませんでした。"}
  │       → SSE: event: done → 処理終了（LLM呼び出しをスキップ）
  │
  ├─ [7] Oracle Query (HYBRID/ORACLE_QUERYインテント時)
  │       → Claude が SQL 生成（対象: 5テーブル — HF1R6M01, HF1REM01, HF1SGM01, HF1RFM01, HF1SKM01）
  │       → トラブル分析: HF1RFM01 × HF1SGM01 (CODE_NO結合)
  │       → 部品解決: HF1REM01 × HF1SKM01 (PARTS_NO結合)
  │       → validate_sql (sqlparse AST解析)
  │       → Oracle実行 (READ ONLY, 30s timeout, 500行制限)
  │       → エラー時: SSE error (recoverable=true) → ドキュメント検索のみで継続
  │       SSE: event: status, data: {"stage": "oracle_query"}
  │
  ├─ [8] Oracle結果をテーブル/グラフ用に構造化
  │       → table_data: {columns: [{key, label, type}], rows: [...]}
  │       → Claude がデータの性質とユーザーの質問意図を判断:
  │           推移データ → chart_type: "line"
  │           比較データ → chart_type: "bar"
  │           構成比 → chart_type: "pie"
  │           分布 → chart_type: "histogram"
  │       → chart_config 生成（回答生成と同一のClaude呼び出し内で決定）
  │       → chat_outputs テーブルに保存
  │       SSE: event: output, data: {output_type, table_data, chart_config}
  │       SSE: event: status, data: {"stage": "structuring_output"}
  │
  └─ [9] Answer Generation (Claude Sonnet 4.5, ストリーミング)
          システムプロンプト:
            - ユーザープロファイル (frequent_lines, term_mappings)
            - モード: response_mode="simple" → "簡潔に要点のみ"
                      detailed → "根拠・経緯・関連情報を含めて詳しく"
          コンテキスト: 展開済み親チャンク + Oracle結果
          SSE: event: token (トークンごと)
          SSE: event: sources
          SSE: event: complete
          SSE: event: done

[フロントエンド]
  → token イベント: MessageBubble にストリーミング表示
  → sources イベント: SourceList に参照元表示
  → output イベント: OutputPanel 自動展開（テーブル/グラフ表示）
  → complete イベント: StarRating 表示 + CopyButton 表示
  → done イベント: ストリーミング状態終了
```

---

## 5. Docker Compose 構成

```yaml
version: "3.9"

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      # マルチステージ: Vite ビルド → Nginx 配信
    ports:
      - "3000:80"
    depends_on:
      - backend

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - ./backend/data:/app/data      # SQLite 永続化
      - ./uploads:/app/uploads        # アップロードファイル永続化
    environment:
      - BEDROCK_REGION=${BEDROCK_REGION}
      - BEDROCK_MODEL_ID=${BEDROCK_MODEL_ID}
      - ORACLE_DSN=${ORACLE_DSN}
      - ORACLE_USER=${ORACLE_USER}
      - ORACLE_PASSWORD=${ORACLE_PASSWORD}
      - ORACLE_ENABLED=${ORACLE_ENABLED:-true}
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - SQLITE_DB_PATH=/app/data/ragphantom.db
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - qdrant
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"    # REST API
      - "6334:6334"    # gRPC
    volumes:
      - ./qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334

volumes:
  qdrant_data:
```

**Dockerfile（バックエンド概要）:**

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

# Oracle Instant Client（oracledb用）
RUN apt-get update && apt-get install -y libaio1

# 依存関係インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dockerfile（フロントエンド概要）:**

```dockerfile
# ステージ1: ビルド
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

# ステージ2: Nginx配信
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# /api/* → http://backend:8000 へプロキシ
EXPOSE 80
```

---

## 6. Qdrant コレクション設計

### 6.1 documents コレクション

```python
# qdrant_client.py での作成
qdrant_client.recreate_collection(
    collection_name="documents",
    vectors_config={
        "dense": VectorParams(
            size=1024,
            distance=Distance.COSINE,  # Cohere Embed 推奨
        ),
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams(),  # BM25-like ハイブリッド検索用
    },
    optimizers_config=OptimizersConfigDiff(
        indexing_threshold=10000,  # 小規模: インデックスなし、高速 upsert
    ),
    on_disk_payload=True,  # ペイロードをディスクに保存（メモリ節約）
)
```

**ペイロードスキーマ:**

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `chunk_id` | string | チャンクの一意ID |
| `document_id` | string | 親ドキュメントID |
| `knowledge_base_id` | string | 所属ナレッジベースID |
| `parent_chunk_id` | string \| null | 親チャンクID（null=ルート） |
| `children_ids` | string[] | 子チャンクIDリスト |
| `is_latest` | boolean | 最新バージョンかどうか |
| `site_code` | string | 工場コード |
| `line_code` | string | ラインコード |
| `process_codes` | string[] | 工程コードリスト |
| `doc_category` | string | 文書カテゴリ |
| `chunk_type` | string | structural/agentic/decision/action_item/issue/countermeasure/table/image |
| `text` | string | チャンクテキスト |
| `page` | integer \| null | 元のページ番号 |
| `section` | string \| null | セクション見出し |
| `source_file` | string | 元のファイル名 |
| `version` | integer | ドキュメントのバージョン番号 |
| `created_at` | string | ISO 8601 形式の作成日時 |

**インデックス設定（高速フィルタリング用）:**

```python
qdrant_client.create_payload_index(
    collection_name="documents",
    field_name="is_latest",
    field_schema=PayloadSchemaType.BOOL,
)
qdrant_client.create_payload_index(
    collection_name="documents",
    field_name="knowledge_base_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
qdrant_client.create_payload_index(
    collection_name="documents",
    field_name="site_code",
    field_schema=PayloadSchemaType.KEYWORD,
)
qdrant_client.create_payload_index(
    collection_name="documents",
    field_name="line_code",
    field_schema=PayloadSchemaType.KEYWORD,
)
qdrant_client.create_payload_index(
    collection_name="documents",
    field_name="process_codes",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

**注意: Oracle クエリ結果の保存先について**

Oracle クエリ結果は Qdrant には保存しない。これらは一時的なデータであり、履歴参照用に SQLite の `chat_outputs` テーブルにのみ保存する。Qdrant はドキュメントチャンクとマスターデータのベクトル検索専用である。

### 6.2 master_data コレクション

```python
qdrant_client.recreate_collection(
    collection_name="master_data",
    vectors_config=VectorParams(
        size=1024,
        distance=Distance.COSINE,
    ),
)
```

**ペイロードスキーマ:**

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `type` | string | "site" / "line" / "process" |
| `code` | string | マスターコード |
| `name` | string | 正式名称 |
| `aliases` | string[] | エイリアス（別称）リスト |
| `site_code` | string | 所属工場コード |
| `line_code` | string \| null | 所属ラインコード |

---

## 7. ボトルネックと対策

### 7.1 技術的ボトルネック一覧

| ボトルネック | 状況 | 対策 |
|------------|------|------|
| Bedrock レートリミット | Claudeへの高頻度リクエスト | tenacity 指数バックオフ（1s→2s→4s、3リトライ） |
| Oracle クエリ遅延 | 複雑なSQLの実行時間 | asyncio.to_thread + 30秒タイムアウト + SSE status表示 |
| SQLite 書き込み競合 | 複数アップロード並行時 | WAL（Write-Ahead Logging）モード有効化 |
| Qdrant 大量 upsert | 議事録など長文の大量チャンク | gRPC接続 + 100ポイント/バッチ |
| 長文ドキュメント処理 | 100ページ超のPDF変換 | FastAPI BackgroundTasks で完全非同期化 |
| Cohere Embed レート | 大量インデックス時 | 96件バッチ + asyncio.gather（最大3並行） |

### 7.2 スケーリング考慮事項

**現状（シングルノード Docker Compose）:**
- 想定同時ユーザー数: ~20名
- ドキュメント総量: ~10,000件（数GB）
- Qdrantメモリ使用量: 1024次元 × 10万チャンク × 4bytes ≈ 400MB

**スケールアウト時の考慮点:**
- FastAPI: 複数インスタンス（ステートレス設計済み）
- SQLite → PostgreSQL への移行パス（SQLAlchemy使用で容易）
- Qdrant: クラスター構成（qdrant/qdrant-distributed）
- ファイルストレージ: ローカルvolume → S3互換ストレージへの移行

### 7.3 セキュリティ考慮事項

| 脅威 | 対策 |
|------|------|
| SQLインジェクション（Oracle） | sqlparse AST解析 + READ ONLYロール |
| 大量ファイルアップロード | MAX_UPLOAD_SIZE=50MB + ALLOWED_EXTENSIONS ホワイトリスト |
| SSRF（URL系コンバーター） | HTML変換時はURL取得を禁止 |
| 機密情報漏洩 | Oracle接続情報は環境変数のみ、ログに出力しない |
| CORS | ALLOWED_ORIGINS ホワイトリスト（config.py） |

---

## 8. 技術スタック一覧

### バックエンド

| カテゴリ | ライブラリ | バージョン | 選定理由 |
|---------|-----------|-----------|---------|
| Webフレームワーク | FastAPI | 0.115+ | 非同期ネイティブ、SSE対応、型安全 |
| ASGI サーバー | Uvicorn | 0.30+ | FastAPI推奨 |
| ORM | SQLAlchemy | 2.0+ | async対応、マイグレーション容易 |
| ベクターDB クライアント | qdrant-client | 1.9+ | Python SDK、gRPC対応 |
| AWS SDK | boto3 | 1.34+ | Bedrock invoke_model |
| Oracle クライアント | python-oracledb | 2.0+ | シンアーキテクチャ、接続プール |
| PDF変換 | pdf2md | 最新 | 構造保持変換 |
| PPTX変換 | pptx2md | 最新 | スライドノート対応 |
| Excel変換 | xl2md (excel2md) | 最新 | 複数シート対応 |
| Word変換 | python-docx | 最新 | スタイル情報保持 |
| HTML変換 | beautifulsoup4 + markdownify | 最新 | 安定したHTML解析 |
| SQL解析 | sqlparse | 0.5+ | AST解析でSQLバリデーション |
| リトライ | tenacity | 8.0+ | 指数バックオフ |
| 設定管理 | pydantic-settings | 2.0+ | 型安全な環境変数管理 |

### フロントエンド

| カテゴリ | ライブラリ | バージョン | 選定理由 |
|---------|-----------|-----------|---------|
| ビルドツール | Vite | 5.0+ | 高速HMR、最新React対応 |
| UIフレームワーク | React | 19.0+ | コンポーネントエコシステム |
| デザインシステム | Serendie Design System | 最新 | konjoテーマ、製造業向け |
| ルーティング | React Router | v7 | 型安全、ネストルート |
| サーバー状態管理 | TanStack Query | v5 | キャッシュ・リフェッチ |
| クライアント状態管理 | Zustand | v4 | 軽量、SSE高頻度更新対応 |
| 仮想スクロール | @tanstack/react-virtual | v3 | 大量メッセージ対応 |
| グラフ描画 | Recharts | v2 | React向け、SVG出力、軽量、ResponsiveContainer対応 |
| 言語 | TypeScript | 5.0+ | 型安全、IDE補完 |

---

*本設計書は4チームの調査結果（Serendie UI・ライブラリ調査・バックエンドアーキテクチャ・フロントエンドアーキテクチャ）を統合したものです。*
