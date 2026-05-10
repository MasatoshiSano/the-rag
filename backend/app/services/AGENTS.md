<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# services

## Purpose
RAG パイプライン本体とドキュメント処理パイプラインのドメインロジック層。`routers/` から呼び出され、`infrastructure/` を経由して外部 SaaS にアクセスする。

## Key Files
| File | Description |
|------|-------------|
| `rag.py` | RAG パイプライン本体: クエリ分析 → ベクトル/ハイブリッド検索 → リランク → Claude 生成。エージェンティックモードのループ制御も担当 |
| `chunker.py` | 見出し階層を保ちつつドキュメントをチャンク分割し、親子関係を構築 |
| `converter.py` | 多形式（PDF/PPTX/XLSX/DOCX/HTML/CSV/JSON/PNG/JPEG）→ Markdown 変換エンジン |
| `embedder.py` | チャンクを密ベクトル（Cohere Embed v3, 1024d）+ 疎ベクトル（TF ハッシング）に変換し Qdrant に upsert |
| `tagger.py` | 3 段階マッチング（マスタエイリアス完全一致 → SQLite LIKE → Qdrant セマンティック検索）+ Claude による自動タグ付与 |
| `text_normalizer.py` | NFKC 正規化（全角/半角統一など）。マスタ照合の前処理に使用 |
| `cleanup_job.py` | ソフトデリート済みドキュメントを保持期間（30 日）経過後に Qdrant・SQLite・ディスクから永続削除するスケジューラ |
| `folder_scanner.py` | Windows パス → コンテナ内パス（`/host_drives/...`）変換と再帰スキャン |
| `oracle_query.py` | Oracle 接続プール管理、LLM 生成 SQL の検証・実行（`SELECT/WITH` のみ許可） |
| `duckdb_query.py` | フォルダソース内 CSV を DuckDB（`:memory:`）で読み込み SQL 実行。`CsvDataSession` で UTF-8 変換キャッシュを共有 |
| `output_formatter.py` | クエリ結果 → 構造化出力（テーブル/チャート設定）変換 + ヒューリスティクス推定 + DB 保存 |
| `seed_templates.py` | `OracleQueryTemplate` テーブルへの初期データ投入 |
| `memory_extractor.py` | チャット会話から `UserMemory(source="auto")` を抽出 |
| `user_profile.py` | チャット履歴のキーワード頻度分析で `user_behaviors` を更新（LLM 不使用） |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- サービスは原則「DB セッションと値を受け取り値を返す」純粋関数。HTTP/Request 依存は `routers/` 側に置く。
- LLM 呼び出しは必ず `infrastructure/bedrock_client.py` のリトライ付きヘルパ経由。直接 boto3 を叩かない。
- DuckDB / Oracle クエリは LLM 生成 SQL を実行する箇所があるため、必ず `sqlparse` でパースし `SELECT`/`WITH` 以外を弾くガードを通す（`oracle_query.py` / `duckdb_query.py` の検証処理を参照）。
- エージェンティック RAG は最大反復数 `config.AGENTIC_MAX_ITERATIONS` とタイムアウト `config.AGENTIC_LOOP_TIMEOUT` で制御。ループ内で進捗を SSE イベントとして yield する設計。
- `cleanup_job.py:create_scheduler_task` は `main.py:lifespan` で起動・停止される。手動でタスク管理を増やさない。

### Testing Requirements
- サービス単位のテスト: `tests/test_<service>.py` パターン。`folder_scanner` / `cleanup_job` / `output_formatter` / `user_profile` は単体テスト済み。
- LLM 依存サービス（`rag` / `tagger` / `memory_extractor`）は Bedrock スタブのレスポンスを `bedrock_stub.generate_text.return_value = "..."` で差し替えてテストする。

### Common Patterns
- `dataclass` で結果型を定義（`Chunk`, `RerankResult` など）。
- リトライは Bedrock 呼び出し側に集約。サービス層では `try/except` を最小限に保つ。

## Dependencies

### Internal
- `app/infrastructure/*`
- `app/models/database.py`

### External
- `pymupdf4llm`, `pptx2md`, `xl2md`, `python-docx`, `beautifulsoup4`, `markdownify`
- `duckdb`, `oracledb`, `sqlparse`

<!-- MANUAL: -->
