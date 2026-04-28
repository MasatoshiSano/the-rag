# RAG Phantom — タスク分解

> 作成日: 2026-03-19
> 対象システム: 製造工場向け RAG システム「RAG Phantom」

---

## 工数凡例

| 記号 | 目安時間 |
|------|---------|
| S | 1〜2 時間 |
| M | 2〜4 時間 |
| L | 4〜8 時間 |
| XL | 8 時間以上 |

---

## Phase 1: プロジェクト基盤構築

### Task 1.1: プロジェクト初期化

**説明**
モノレポ構成でプロジェクト全体のスケルトンを作成する。
- `docker-compose.yml` に frontend・backend・qdrant の 3 サービスを定義
- Backend: `app/main.py`・`app/routers/`・`app/services/`・`app/models/`・`app/infrastructure/config.py`・`app/infrastructure/db.py`・`app/infrastructure/bedrock_client.py`・`app/infrastructure/qdrant_client.py`・`app/infrastructure/master_cache.py` の骨格を生成
- Frontend: Vite + React + TypeScript でプロジェクトを初期化
- Serendie Design System (`@serendie/ui`, `@serendie/symbols`) をインストール・設定
- `SerendieProvider` でテーマ `konjo` を適用
- `requirements.txt` と `package.json` に全依存関係を記載
- Frontend 依存: `recharts` (グラフ描画ライブラリ)
- Backend テスト依存: `pytest`, `pytest-asyncio`, `ragas`, `moto` (AWS mock)
- Frontend テスト依存: `@playwright/test`

**依存タスク**: なし

**推定工数**: L

---

### Task 1.2: データベース基盤

**説明**
SQLite + SQLAlchemy によるデータ永続化層を構築する。
- 全テーブルの ORM モデルを定義する
  - `users`, `user_terms`, `user_behavior`, `sessions`, `messages`
  - `documents`, `document_tags`
  - `knowledge_bases` (id, name, description, color, created_by, created_at, updated_at)
  - `knowledge_base_favorites` (id, user_id, knowledge_base_id, created_at)
  - `oracle_query_templates`
  - `master_sites`, `master_lines`, `master_processes`
  - `chat_outputs` (id, message_id, output_type, table_data, chart_config, sql_executed, row_count, created_at)
- `documents` テーブルに `knowledge_base_id` 外部キーを追加する
- `documents` テーブルに `retry_count` INTEGER DEFAULT 0 カラムを追加する（エラーリトライ回数管理）
- `documents` テーブルに `deleted_at` TEXT NULL カラムを追加する（ソフトデリート用）
- `documents` テーブルの `status` enum に `permanent_failed`（リトライ上限到達）と `cancelled`（ユーザー中止）を追加する
- `sessions` テーブルに `knowledge_base_id` 外部キーを追加する
- Alembic でマイグレーション管理を設定する
- SQLite の WAL (Write-Ahead Logging) モードを有効化し、読み書き競合を抑制する
- DB 接続・セッション管理ユーティリティ (`get_db` 依存性注入) を実装する
- `messages_fts` FTS5 仮想テーブル（unicode61 トークナイザ）を作成し、`messages` テーブルとの INSERT/DELETE トリガーでインデックスを同期する

**依存タスク**: Task 1.1

**推定工数**: M

---

### Task 1.3: マスターデータ取り込み

**説明**
工場マスターデータをパースし、SQLite と Qdrant に格納する。
- `master-flat-with-place-aliases.md` (10,118 件) のパーサーを実装する
- SQLite の `master_sites`・`master_lines`・`master_processes` へ UPSERT する
- 起動時にオンメモリの `MasterDataCache` (`infrastructure/master_cache.py`) を構築して高速照合を実現する
- Cohere Embed (Bedrock 経由) でマスターデータの embedding を生成し Qdrant コレクション `master_data` へ格納する
- `routers/master.py` にマスターデータ参照 API を実装する:
  - `GET /api/master/sites`
  - `GET /api/master/lines`
  - `GET /api/master/processes`
  - `GET /api/master/search`

**依存タスク**: Task 1.1, Task 1.2, Task 1.4, Task 1.5

**推定工数**: L

---

### Task 1.4: Bedrock クライアント基盤

**説明**
AWS Bedrock との通信層を実装する。
- boto3 Bedrock Runtime クライアントを初期化し、リージョン・モデル ID を `infrastructure/config.py` で一元管理する
- Claude Sonnet 4.5 呼び出しラッパー (テキスト生成・ストリーミング両対応)
- Claude Vision 呼び出しラッパー (Base64 画像埋め込みによる画像解析)
- Cohere Embed 呼び出しラッパー (バッチ処理対応、最大 96 テキスト/コール)
- Cohere Rerank 呼び出しラッパー
- `tenacity` による指数バックオフで Rate Limit エラーを自動リトライする

**依存タスク**: Task 1.1

**推定工数**: M

---

### Task 1.5: Qdrant 基盤

**説明**
ベクトルデータベース Qdrant のクライアント層とコレクションを構築する。
- Qdrant クライアントを設定する (`qdrant-client` ライブラリ)
- コレクション `documents` と `master_data` を作成する
- Dense vector (1024 次元、Cosine 距離) と Sparse vector (ハイブリッド検索用) を設定する
- CRUD 操作ラッパー (upsert・search・delete・filter) を実装する

**依存タスク**: Task 1.1

**推定工数**: M

---

## Phase 2: ドキュメント処理パイプライン

### Task 2.1: converter.py — ファイル変換エンジン

**説明**
多様なファイル形式を Markdown に変換するエンジンを実装する。
- `FileType` enum と `ConversionResult` データクラスを定義する
- 対応形式ごとの変換ロジック:
  - MD / TXT: パススルー
  - PDF: `pdf2md` を統合
  - PPTX: `pptx2md` (`ConversionConfig`) を統合
  - XLSX: `excel2md（PyPIパッケージ名: xl2md）` を統合
  - DOCX: `python-docx` → Markdown 変換
  - CSV / JSON: 構造解析 → Markdown テーブル
  - HTML: `beautifulsoup4` + `markdownify`
  - PNG / JPEG: Bedrock Claude Vision → テキスト説明
- 画像を `[[IMAGE:uuid]]` マーカー形式で埋め込む
- 部分的な変換失敗に対して `[変換失敗: {reason}]` プレースホルダを挿入する
- 変換結果テキストに対して Task 2.7 のテキスト正規化（NFKC）を適用する

**依存タスク**: Task 1.4

**推定工数**: XL

---

### Task 2.2: tagger.py — AI 自動タグ付与

**説明**
ドキュメント内容を Claude で解析し、マスターデータと照合してタグを自動付与する。
- `TagSuggestion` データクラスを定義する
- Claude へのプロンプトを設計する (先頭 2,000 文字 + 末尾 500 文字 + マスター候補 JSON)
- 3 段階のマスター照合を実装する:
  1. エイリアス完全一致
  2. SQLite LIKE 検索
  3. Qdrant セマンティック検索
- 付与するタグ種別: site・line・process・category・date・equipment・parts・persons・keywords
- 各タグに信頼度スコア (`confidence`) を付与する
- `temperature=0` で決定論的な結果を保証する

**依存タスク**: Task 1.3, Task 1.4

**推定工数**: L

---

### Task 2.3: chunker.py — チャンキングエンジン

**説明**
ドキュメントを意味的・構造的な単位に分割し、Parent-Child 関係を構築する。
- `ChunkingConfig` (max_tokens・overlap) と `Chunk` データクラス (`parent_chunk_id`, `children_ids` 含む) を定義する
- チャンク戦略の実装:
  - 構造的チャンク: ヘッダ階層に基づき、親=セクション・子=サブセクション
  - エージェンティックチャンク: Claude で意味的区切りを判定
  - 議事録特化チャンク: decisions / action_items / issues / countermeasures を分解
  - テーブルチャンク: 行グループ + セクション文脈
  - 画像チャンク: Vision 説明 + 前後テキスト
- チャンクごとに親ドキュメントのタグを継承しつつ細分化タグを付与する

**依存タスク**: Task 2.1, Task 2.2

**推定工数**: XL

---

### Task 2.4: embedder.py — ベクトル化・格納

**説明**
チャンクを embedding し Qdrant へ格納する。
- Cohere Embed でバッチ処理する (最大 96 テキスト/コール)
- Dense vector を生成・格納する
- Sparse vector を生成・格納する (ハイブリッド検索用)
- Qdrant payload にメタデータ・タグ・parent/child ID・`knowledge_base_id` を含める
- `is_latest` フラグでバージョン管理を実現する

**依存タスク**: Task 1.4, Task 1.5, Task 2.3

**推定工数**: M

---

### Task 2.5: ドキュメントアップロード API

**説明**
ドキュメントのアップロードと非同期パイプライン実行を担う API を実装する。
- `POST /api/documents/upload` エンドポイントを実装する
- ファイルバリデーション (拡張子・サイズ制限) を実装する
- FastAPI `BackgroundTasks` でパイプラインを非同期実行する
- ステータス遷移を管理する:
  - 正常系: `processing` → `converting` → `converted` → `tagging` → `tagged` → `chunking` → `chunked` → `indexing` → `indexed`
  - 異常系: `convert_failed` / `tag_failed` / `index_failed` / `permanent_failed`
  - 中止: `cancelled`（ユーザーによる処理中止）
- **バックグラウンド永続性**: FastAPI BackgroundTasks でサーバーサイド完結処理を実装する。ブラウザ閉じても処理継続。フロントエンド接続不要
- **エラーリトライ上限（3回）**: `retry_count` カラムで管理し、再試行ごとにインクリメント。`retry_count >= 3` で `permanent_failed` に遷移。`permanent_failed` は再試行不可・削除のみ
- `POST /api/documents/:id/reindex` で失敗箇所からの再試行を実装する（リトライ上限チェック付き）
- **キャンセル機構**: `POST /api/documents/:id/cancel` エンドポイントを実装する
  - インメモリ dict でキャンセルフラグを管理
  - 各ステージ開始前にフラグをチェックし、キャンセル検知時は status を "cancelled" に変更して停止
  - "cancelled" 状態のドキュメントは「再試行」（retry_count リセット）または「削除」が可能

**依存タスク**: Task 1.2, Task 2.1, Task 2.2, Task 2.3, Task 2.4

**推定工数**: L

---

### Task 2.6: ドキュメントバージョン管理

**説明**
同一ファイル名のドキュメントをバージョンとして管理する機能を実装する。
- アップロード時に同一ファイル名を検出し `parent_document_id` でリンクする
- バージョン番号を自動付与する
- 旧バージョンのチャンクは Qdrant で `is_latest=False` に更新する
- `GET /api/documents/:id/versions` でバージョン一覧を取得できるようにする

**依存タスク**: Task 2.5

**推定工数**: M

---

### Task 2.7: テキスト正規化（半角/全角カタカナ）

**説明**
テキスト正規化ユーティリティを実装し、全パイプラインに適用する。
- `unicodedata.normalize('NFKC', text)` による正規化関数を実装する
- 適用箇所: `rag.py`（検索クエリ）、`tagger.py`（マスター照合）、`embedder.py`（埋め込み前）、`user_profile.py`（用語辞書）、`oracle_query.py`（SQL 生成）、`master_cache.py`（キャッシュ構築）
- Oracle トラブルマスター（HF1SGM01）の半角カタカナ（ｻｲｸﾙﾀｲﾑｵｰﾊﾞｰ）とユーザー入力（サイクルタイムオーバー）のマッチングを保証する
- テストケース: 半角/全角カタカナ混在クエリでの検索ヒット確認

**依存タスク**: Task 1.1

**推定工数**: S

---

### Task 2.8: 複数ファイル一括アップロード

**説明**
DropZone とバックエンドを複数ファイル同時アップロードに対応させる。
- `POST /api/documents/upload` を複数ファイル対応に拡張する（multipart/form-data に `files[]`）
- `asyncio.Semaphore(3)` で最大 3 並行処理を制御する
- ZIP ファイル自動展開対応（`zipfile` モジュール）
- 最大 20 ファイル/回、合計 200MB 上限
- 1 ファイルの失敗が他に影響しない独立処理
- フロントエンド DropZone を複数ファイル対応に拡張する
- 各ファイルの個別プログレス表示
- Config に `MAX_BATCH_UPLOAD_FILES=20`, `MAX_BATCH_UPLOAD_SIZE=200MB` を追加する

**依存タスク**: Task 2.1（converter.py）

**推定工数**: M

---

### Task 2.8.1: 一括タグ確認画面（BatchTagEditor）

**説明**
複数ファイルアップロード時のタグ一括確認UIとAPIを実装する。

**フロントエンド:**
- `components/upload/BatchTagEditor.tsx` を新規作成する
  - テーブル形式: 各行 = 1ファイル、列 = ファイル名・サイト・ライン・工程・カテゴリ・キーワード・AI信頼度
  - 各セルはクリックでインライン編集可能
  - 「全て確定」ボタンで全ファイルのタグを一括確定
  - 個別ファイルの先行確定ボタン
  - タグ付け未完了のファイルはスピナーを表示
  - WCAG 2.2 Level AA 準拠（`role="grid"`, `aria-label` 等）
- DropZone のタグ確認表示を分岐: ファイル数 > 1 → BatchTagEditor、ファイル数 = 1 → 従来の TagEditor
- `api/documents.ts` に `batchConfirmTags()` API 関数を追加

**バックエンド:**
- `PATCH /api/documents/batch-tags` エンドポイントを `routers/documents.py` に追加する
  - リクエスト: `{ documents: [{ document_id, tags: [{tag_key, tag_value, confirmed}] }] }`
  - 各ドキュメントのタグを更新し status を "confirmed" に遷移
  - 確定後、バックグラウンドで chunk + index パイプラインを開始（最大3並行）
  - レスポンス: `{ confirmed: ["uuid1", "uuid2", ...] }`
- `BatchTagConfirmRequest` Pydantic モデルを定義する

**依存タスク**: Task 2.8, Task 2.5（tagger.py）

**推定工数**: M

---

## Phase 3: 検索・回答生成エンジン

### Task 3.1: rag.py — クエリ解析

**説明**
ユーザーの質問を解析し、検索戦略を決定する。
- `analyze_query`: Claude で意図を分類する (`DOC_SEARCH` / `ORACLE_QUERY` / `HYBRID`)
- フィルタ条件 (site・line・process) を抽出する
- Qdrant 検索時に `knowledge_base_id` でフィルタリングする
- `translate_query_terms`: ユーザー個人辞書を参照して俗称を正式名称に変換する (最長一致優先)
- `detect_unknown_terms`: 辞書未登録の用語を検出して TermSuggestions に渡す

**依存タスク**: Task 1.4, Task 4.2

**推定工数**: M

---

### Task 3.2: rag.py — ベクトル検索

**説明**
Qdrant を利用した検索処理を実装する。
- Qdrant 検索 (Dense vector + メタデータフィルタ + `is_latest=True`)
- ユーザー設定に応じてハイブリッド検索 (Dense + Sparse) を切り替える
- 子チャンクがヒットした場合は親チャンクを展開して文脈を補完する (Parent-Child 展開)
- ユーザー設定に応じて Cohere Rerank を適用する
- 検索結果からソース情報 (ドキュメント名・ページ・スコア) を構築する

**依存タスク**: Task 1.4, Task 1.5, Task 2.4, Task 3.1

**推定工数**: L

---

### Task 3.3: oracle_query.py — Oracle DB 連携

**説明**
自然言語から Oracle SQL を生成し、安全に実行する処理を実装する。対象は5つのOracleテーブル。
- SQL 生成プロンプトを設計する (5テーブルのスキーマ情報 + テンプレート参考情報付き)
  - 対象テーブル: HF1R6M01（生産トレサビ）、HF1REM01（品質結果）、HF1SGM01（トラブルマスタ）、HF1RFM01（トラブルデータ）、HF1SKM01（部品マスタ）
  - 結合ルール: 全テーブル STA_NO1/2/3 共通、トラブル分析は CODE_NO 結合、部品解決は PARTS_NO 結合、不良内容解決は NG_CODE = CODE_NO
  - HF1RFM01.MK_DATE が VARCHAR 型（"YYYYMMDDHHmmss" 形式）であることをプロンプトに明示
  - HF1REM01.MK_DATE も VARCHAR 型（"YYYYMMDDHHmmss" 形式）であることをプロンプトに明示
  - ビジネスルール: HF1REM01.OPEFIN_RESULT（1=良品, 2=不良）をプロンプトに明示し、不良率算出ロジック（`SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)`）を含める
  - ビジネスルール: HF1RFM01.T4_UPDATE_CHECK（4=ブザー鳴動/異常発生, 5=ブザー停止/オペレーター対応）をプロンプトに明示。トラブル発生件数カウントには必ず `T4_UPDATE_CHECK=4` を使用する。T4_STATUS はフィルタ不要
  - ビジネスルール: トラブル時間算出はクロステーブル計算（HF1RFM01.MK_DATE(T4_UPDATE_CHECK=4) → 同一STA_NO1/2/3の次のHF1REM01.MK_DATE）で行う。ON_TIME/REP_START_TIME/RESTART_TIME はトラブル時間算出には使用しない
  - ビジネスルール（EXCEPT_FLAG・必須）: HF1REM01およびHF1RFM01への**全ての集計クエリ**に `WHERE EXCEPT_FLAG IN (0, 1)` を必ず付与する。値の意味: 0,1=通常データ（集計対象）, 2=除外データ（集計対象外）, 30代=OKマスタ定義（集計対象外）, 40代=NGマスタ定義（集計対象外）, 50代=その他マスタ定義（集計対象外）。このフィルタがないとマスタ定義レコードや除外データが集計結果を汚染する。サブクエリ内のHF1REM01にも同様に付与すること
  - ビジネスルール（NG_CODE・NULL許容）: HF1REM01.NG_CODEはOPEFIN_RESULT=2（不良）でもNULLの場合がある。NG_CODEでHF1SGM01と結合する際は**LEFT JOIN**（INNER JOINではない）を使用し、NG_CODEがNULLの不良品は「未分類」として扱う（`NVL(s.TROUBLE_NG_INFO, '未分類')`）
- `validate_sql`: `sqlparse` AST を検査し SELECT / WITH CTE のみ許可する
- `oracledb` 接続プールを設定する (min=2, max=10)
- `asyncio.to_thread()` で非同期実行する
- 30 秒タイムアウトと 500 行制限を適用する
- Oracle 接続不可時は `OracleUnavailableError` でフォールバックする

**依存タスク**: Task 1.4, Task 3.5

**推定工数**: L

---

### Task 3.4: rag.py — 回答生成 (SSE)

**説明**
Claude のストリーミング出力を SSE (Server-Sent Events) でクライアントへ送信する。
- Claude Sonnet 4.5 のストリーミング呼び出しを実装する
- ユーザープロファイルと応答モード (simple/detailed) を反映したシステムプロンプトを構築する
- SSE イベントの送信シーケンスを実装する:
  `session` → `status` → `token` (複数) → `sources` → `terms` → `output` → `complete` → `done`
  エラー時は `error` イベントを送信する
- `POST /api/chat` エンドポイント (SSE 応答) を実装する

**依存タスク**: Task 1.4, Task 3.1, Task 3.2, Task 3.3

**推定工数**: L

---

### Task 3.5: oracle_query_templates 初期データ

**説明**
Oracle SQL テンプレートの初期データを SQLite へ投入する。5つのOracleテーブルに対応するテンプレートを網羅する。
- トレーサビリティデータ検索テンプレート（HF1R6M01）を作成する
  - 使用カラム例: `MK_DATE`, `STA_NO1/2/3`, `M_SERIAL`, `INSP_ITEMNAME`, `MEASURE`
- 品質結果検索テンプレート（HF1REM01）を作成する
  - 工程別不良率の算出（OPEFIN_RESULT: 1=良品, 2=不良 を使用）
  - 不良内容別の集計（HF1REM01.NG_CODE × HF1SGM01.CODE_NO を結合）
- トラブル分析テンプレート（HF1RFM01 × HF1SGM01）を作成する
  - 特定ラインのトラブル発生件数集計（T4_UPDATE_CHECK=4 でカウント）
  - トラブル内容別の時系列推移（T4_UPDATE_CHECK=4 でカウント）
  - トラブル時間の算出（HF1RFM01 × HF1REM01 クロステーブル計算: T4_UPDATE_CHECK=4 の MK_DATE から同一設備の次の HF1REM01.MK_DATE までの実影響時間）
- 部品名称解決テンプレート（HF1REM01 × HF1SKM01）を作成する
  - 品質結果に部品名を結合して取得
- 初期データ投入スクリプトまたは Alembic データマイグレーションを実装する

**依存タスク**: Task 1.2

**推定工数**: S

---

### Task 3.6: 出力データ構造化

**説明**
Oracle クエリ結果をテーブル・グラフ用に構造化する機能を実装する。
- Claude がデータの性質とユーザーの質問意図を判断し、`chart_config` を生成する
  - 推移データ → 折れ線グラフ (line)
  - 比較データ → 棒グラフ (bar)
  - 構成比 → 円グラフ (pie)
  - 分布 → ヒストグラム (histogram)
- `table_data: {columns: [{key, label, type}], rows: [...]}` 形式でテーブルデータを構造化する
- SSE `output` イベントでフロントエンドに送信する
- `chat_outputs` テーブルへの保存を実装する
- API エンドポイントを実装する:
  - `GET /api/chat/output/:messageId` — 出力データ取得
  - `GET /api/chat/output/:messageId/csv` — CSV ダウンロード

**依存タスク**: Task 3.3 (Oracle DB 連携), Task 3.4 (回答生成 SSE)

**推定工数**: M

---

### Task 3.7: ハルシネーション防止機構

**説明**
RAG パイプラインにハルシネーション防止策を実装する。
- システムプロンプトに厳格な RAG 制約を追加する（参照文書のみで回答、一般知識の使用を禁止）
- 信頼度閾値 (`RELEVANCE_THRESHOLD=0.3`) の実装: 全チャンクのスコアが閾値未満の場合、「選択されたナレッジベース内に該当する情報が見つかりませんでした。」と回答する
- Qdrant 検索に `knowledge_base_id` フィルターを追加する
- テストケース: 一般常識質問（「富士山の高さは？」）で KB に情報がない場合の拒否テスト

**依存タスク**: Task 3.1 (RAG オーケストレーション)

**推定工数**: M

---

## Phase 4: ユーザー管理

### Task 4.1: ユーザー識別

**説明**
ブラウザ固有の ID でユーザーを識別する仕組みを実装する。
- Frontend: ブラウザフィンガープリント + `localStorage` UUID を生成する
- 全 API リクエストに `X-User-Id` ヘッダーを付与する (`axios` インターセプター)
- `GET /api/users/me`: ユーザーが存在しない場合は自動作成する
- `PUT /api/users/me/settings`: rerank・hybrid_search・response_mode・nickname の設定を保存する

**依存タスク**: Task 1.2

**推定工数**: M

---

### Task 4.2: 個人辞書

**説明**
ユーザーごとの俗称-正式名称マッピングを管理する機能を実装する。
- `POST /api/users/me/terms` (user_term・master_key・master_type を受け付ける)
- `GET /api/users/me/terms`
- `DELETE /api/users/me/terms/:id`
- `translate_query_terms`: 最長一致優先で俗称 → 正式名称へ変換する (ユーザーごとに独立)

**依存タスク**: Task 4.1

**推定工数**: M

---

### Task 4.3: プロファイル学習

**説明**
ユーザーの行動履歴からプロファイルを自動更新する。
- チャット履歴を集計し `user_behavior` テーブルの `frequent_lines`・`frequent_categories` を更新する
- 直近の会話テーマを `recent_context` として追跡する
- `GET /api/users/me/behavior` でプロファイルを取得できるようにする

**依存タスク**: Task 4.1, Task 3.4

**推定工数**: M

---

### Task 4.4: セッション管理

**説明**
チャットセッションの一覧・詳細・削除 API を実装する。
- `GET /api/sessions`: セッション一覧を日付グループ付きで返す
- `GET /api/sessions/:id`: セッションのメッセージ一覧を返す
- `DELETE /api/sessions/:id`: セッションを削除する
- 最初の質問からセッションタイトルを自動生成する

**依存タスク**: Task 1.2, Task 4.1

**推定工数**: M

---

### Task 4.5: 評価機能

**説明**
回答への 5 段階評価機能を実装する。
- `PUT /api/messages/:id/rating` で 1〜5 の評価を保存する
- `messages` テーブルに `rating` カラムを追加する
- 評価データを将来の品質改善に活用できるよう蓄積する

**依存タスク**: Task 4.4

**推定工数**: S

---

### Task 4.6: ナレッジベース CRUD API

**説明**
ナレッジベースの管理 API (`knowledge_bases.py` ルーター) を実装する。
- `POST /api/knowledge-bases` — ナレッジベース作成
- `GET /api/knowledge-bases` — ナレッジベース一覧取得
- `GET /api/knowledge-bases/favorites` — お気に入りナレッジベースのみ取得
- `PUT /api/knowledge-bases/{id}` — ナレッジベース更新
- `DELETE /api/knowledge-bases/{id}` — ナレッジベース削除（配下のドキュメント・ベクトルデータも連動削除（カスケード））
- `POST /api/knowledge-bases/{id}/favorite` — お気に入り登録
- `DELETE /api/knowledge-bases/{id}/favorite` — お気に入り解除

**依存タスク**: Task 1.2

**推定工数**: M

---

### Task 4.7: セッション横断キーワード検索

**説明**
セッション履歴の全文検索機能を実装する。
- SQLite FTS5 仮想テーブル `messages_fts` を利用する（Task 1.2 で作成済み、unicode61 トークナイザ）
- `GET /api/sessions/search?q=keyword&knowledge_base_id=xxx` API を実装する
- セッション単位でグルーピングし、スニペット付きレスポンスを返す
- `knowledge_base_id` でスコープを絞り込む

**依存タスク**: Task 1.2, Task 4.6（ナレッジベース CRUD）

**推定工数**: M

---

## Phase 5: フロントエンド実装

### Task 5.1: レイアウト基盤

**説明**
フロントエンド全体の骨格を構築する。
- `AppShell` (Sidebar + Header + `<Outlet>`) を実装する
- React Router v7 でルーティングを設定する
- Zustand stores を定義する: `chatStore`・`userStore`・`uiStore`・`outputStore`・`kbStore`
  - `outputStore`: `outputData`, `isOutputPanelOpen`, `setOutputData`, `clearOutput`, `toggleOutputPanel`
- TanStack Query の Provider を設定する
- API クライアントを実装する (`client.ts` + 各ドメインモジュール)
- `AppShell` のレイアウトを 3 カラム対応に更新する（サイドバー + チャット + 出力パネル）
- Sidebar にお気に入りナレッジベース一覧を表示する
- デスクトップ: サイドバー固定表示 / モバイル: オーバーレイドロワーでレスポンシブ対応する

**依存タスク**: Task 1.1, Task 4.1

**推定工数**: L

---

### Task 5.2: チャットページ

**説明**
メインのチャット UI を実装する。
- セッション履歴サイドバー (Drawer + List)
- `MessageList` (`role="log"` 属性付き、仮想スクロール対応)
- `MessageBubble` (user / assistant で表示を分ける)
- `ChatInput` (TextField + 送信 Button + VoiceButton)
  - **ストリーミング中の入力無効化**: `isStreaming=true` の間、TextField と送信ボタンを `disabled` にする
  - プレースホルダーを「回答中...」に変更
  - 送信ボタンを停止ボタンに切り替え表示
  - キャンセル（停止ボタン）押下で入力可能に復帰
  - 質問のキューイングは行わない（シンプルさ優先）
- SSE ストリーミング受信 (`fetch` + `ReadableStream`)
- ストリーミングキャンセル処理:
  - 停止ボタンクリックで `AbortController.abort()` を呼び出す
  - 途中までの回答テキストを保持し、末尾に「（回答が中断されました）」を表示
  - messagesテーブルに途中の content を保存（`is_cancelled=true`）
  - ソース参照・出力パネルデータは受信済み分のみ表示
  - 中断された回答には `StarRating` を非表示
- ソース表示 (`SourceList`・クリックで `SourcePreviewModal`)
- `CopyButton` (Markdown 形式でクリップボードコピー)
- `StarRating` (5 段階・ホバー色変化・クリック確定・`role="radiogroup"`)
- `TermSuggestions` (インライン用語確認チップ + 登録チェックボックス)
- `ResponseModeToggle` (シンプル / 詳細 切替)
- SSE `output` イベントの受信ハンドリング
- 出力パネルとの連携（`outputStore` 経由）

**依存タスク**: Task 5.1, Task 3.4, Task 4.4

**推定工数**: XL

---

### Task 5.3: 音声入力

**説明**
Web Speech API を用いた音声入力機能を実装する。
- `VoiceButton` コンポーネントを実装する
- `SpeechRecognition` API を使用する (`lang="ja-JP"`, `interimResults=true`)
- 状態遷移を管理する: `idle` → `listening` → `done` / `error`
- 非対応ブラウザではボタンをグレーアウトし、ツールチップで案内する

**依存タスク**: Task 5.2

**推定工数**: M

---

### Task 5.4: アップロードページ

**説明**
ドキュメントのアップロードとタグ確認・編集 UI を実装する。
- `DropZone`: HTML5 drag-drop + Serendie Design Tokens でスタイリングする
- ファイルバリデーション (拡張子チェック)
- アップロード進捗 (`ProgressIndicator`)
- 2 秒間隔のステータスポーリングを実装する
- `ConversionPreview`: 変換後 Markdown プレビュー
- `TagEditor`: AI 提案タグの確認・修正 UI
  - 各タグ: チップ表示 + 確認チェック / 削除 / 追加
  - 拠点・ライン・工程は Select コンポーネントで変更可能
- `VersionConflictDialog`: 同一ファイル名検出時に「新規登録」または「バージョン更新」を選択させる
- 「確定してインデックス構築」ボタン

**依存タスク**: Task 5.1, Task 2.5, Task 2.6

**推定工数**: XL

---

### Task 5.5: ドキュメント管理ページ

**説明**
登録済みドキュメントの一覧表示・管理 UI を実装する。
- `DocumentTable`: データテーブル (ソート・チェックボックス選択対応)
  - タグ未確認（status: "tagged"）のファイルには「未確認」バッジを表示する（Badge コンポーネント使用、目立つ配色）
  - インデックス構築中のドキュメントに「中止」ボタンを表示する（`POST /api/documents/:id/cancel` 呼び出し）
  - "cancelled" 状態には「再試行」ボタンと「削除」ボタンを表示
  - "permanent_failed" 状態には「削除」ボタンのみ表示し、リトライ上限メッセージを案内
  - 再試行ボタンにはリトライ回数を表示（例: 「再試行 (2/3)」）
- `TagFilter`: 拠点 / ライン / 工程 / 種別でフィルタリングする Select コンポーネント
- **ゴミ箱タブ/フィルター**: ソフトデリート済みドキュメントの一覧表示
  - 各ドキュメントに「復元」ボタン（`POST /api/documents/:id/restore`）と「完全削除」ボタン（`DELETE /api/documents/:id/permanent`）を表示
  - 削除日時と残り保持期間（30日からのカウントダウン）を表示
- **削除確認ダイアログ**: ドキュメント削除時に「このドキュメントとそのインデックスデータを削除しますか？」を表示
- ドキュメント詳細ドロワー:
  - タグの再編集
  - Markdown プレビュー
  - バージョン履歴一覧

**依存タスク**: Task 5.1, Task 2.5, Task 2.6

**推定工数**: L

---

### Task 5.6: 設定ページ

**説明**
ユーザー設定・個人辞書・プロファイル表示ページを実装する。
- リランク ON/OFF (Switch)
- ハイブリッド検索 ON/OFF (Switch)
- ニックネーム入力 (TextField)
- 個人辞書 (`TermDictionary`): 辞書エントリの一覧・追加・削除
- プロファイル情報 (`ProfileInfo`): 頻出ライン・カテゴリを読み取り専用で表示する

**依存タスク**: Task 5.1, Task 4.1, Task 4.2, Task 4.3

**推定工数**: M

---

### Task 5.7: 出力パネル実装

**説明**
チャット右側の出力パネルを実装する。
- `OutputPanel.tsx`: コンテナ（開閉制御、データがない時は非表示）
- `DataTable.tsx`: Serendie DataTable ベースのページネーション付きテーブル
  - ページネーション（10/20/50/100 行切替）
  - カラムソート
  - CSV ダウンロード（BOM 付き UTF-8）
  - Markdown コピー
- `ChartView.tsx`: Recharts によるグラフ表示
  - 対応: LineChart, BarChart, PieChart, AreaChart, Histogram
  - `ResponsiveContainer` でパネル幅に自動フィット
  - PNG/SVG ダウンロード
- `DownloadButtons.tsx`: ダウンロードボタン群
- SSE `output` イベント受信でパネル自動展開
- レスポンシブ:
  - Desktop (1280px+): 3 カラム（サイドバー + チャット + 出力パネル）
  - Desktop (1024-1279px): 出力パネルはオーバーレイ
  - Mobile: ボトムシートまたはタブ切替

**依存タスク**: Task 5.1 (レイアウト基盤), Task 5.2 (チャットページ)

**推定工数**: L

---

### Task 5.8: ナレッジベース UI

**説明**
フロントエンドにナレッジベース管理機能を実装する。
- `KnowledgeBaseList`: お気に入りフィルター付きナレッジベース一覧
- `KnowledgeBaseCard`: ナレッジベース表示カード（名前、色、ドキュメント数、お気に入りボタン）
- `CreateKBDialog`: ナレッジベース作成ダイアログ（名前、説明、色選択）
- `kbStore` (Zustand): 選択中のナレッジベース状態管理
  - `setSelectedKB` 内でKB切り替え時に新規セッションを自動作成するロジックを実装する
  - セッションは常に1つのKBに紐付く（途中でKBを変更しない）
- Sidebar をお気に入りナレッジベース表示に変更する
  - チャット中に別のKBを選択した場合、現在のセッションを保持したまま新規セッションが開始される
- `ChatPage`: 選択中のナレッジベースを表示し、未選択時はナレッジベース選択を促す
- `UploadPage`: ナレッジベース選択ドロップダウンを追加する

**依存タスク**: Task 4.6 (ナレッジベース CRUD API), Task 5.1 (レイアウト基盤)

**推定工数**: L

---

### Task 5.9: セッション検索 UI

**説明**
サイドバーにセッション検索機能を実装する。
- `SessionSearch` コンポーネント（サイドバー上部に検索ボックス）を実装する
- 検索結果をドロップダウン表示する（セッション名、マッチスニペット）
- 検索結果のセッションクリックでセッション遷移する
- デバウンス付きリアルタイム検索（300ms）を実装する

**依存タスク**: Task 4.7（セッション横断キーワード検索 API）, Task 5.1

**推定工数**: S

---

### Task 5.10: ドキュメントソフトデリート・ゴミ箱 API

**説明**
ドキュメントのソフトデリート、復元、物理削除、バックグラウンド物理削除ジョブを実装する。
- `documents` テーブルに `deleted_at` TEXT NULL カラムと `retry_count` INTEGER DEFAULT 0 カラムを追加する（Alembic マイグレーション）
- `DELETE /api/documents/{id}` → ソフトデリート（`deleted_at` に現在日時をセット）
- `POST /api/documents/{id}/restore` → ゴミ箱から復元（`deleted_at` を NULL にリセット）
- `GET /api/documents?deleted=true` → ゴミ箱一覧（`deleted_at IS NOT NULL` のドキュメント取得）
- `DELETE /api/documents/{id}/permanent` → 物理削除（Qdrant ベクトル + SQLite レコード + アップロードファイル）
- 既存の `GET /api/documents` を修正し、`deleted_at IS NULL` のドキュメントのみ返すようにフィルタリング
- Qdrant 検索時にソフトデリート済み document_id を除外するフィルタを追加
- バックグラウンド物理削除ジョブ: FastAPI startup イベントで定期実行（1日1回）をスケジューリング
  - `deleted_at` が 30 日以上前のドキュメントを自動的に物理削除
  - Qdrant ベクトル削除 + SQLite レコード削除 + ファイル削除

**依存タスク**: Task 1.2, Task 1.5, Task 2.5

**推定工数**: L

---

## Phase 6: テスト・品質保証・Docker

### Task 6.1: Docker Compose 統合

**説明**
本番相当の Docker 構成を完成させる。
- Frontend の `Dockerfile` (multi-stage: ビルドステージ + nginx 配信ステージ)
- Backend の `Dockerfile` (Python + 依存ライブラリ)
- `docker-compose.yml` に frontend・backend・qdrant と永続ボリュームを定義する
- `nginx.conf` に SPA ルーティング (try_files) と `/api` へのリバースプロキシを設定する

**依存タスク**: Task 1.1, Task 5.1 (全 Phase 5 完了後)

**推定工数**: M

---

### Task 6.2: バックエンドユニットテスト (pytest)

**説明**
各サービスモジュールのユニットテストを実装する。
- `converter.py`: 各ファイル形式（md, pdf, pptx, xlsx, docx, csv, json, html, png, jpeg）の変換テスト
- `tagger.py`: AI 自動タグ付与のテスト（マスターデータ 3 段階照合）
- `chunker.py`: 4 つのチャンキング戦略テスト（構造的、エージェンティック、議事録分解、テーブル）+ Parent-Child 関係構築
- `oracle_query.py`: SQL 生成バリデーション（SELECT 以外ブロック、セミコロン複文ブロック）、タイムアウト、500 行制限、5テーブル（HF1R6M01, HF1REM01, HF1SGM01, HF1RFM01, HF1SKM01）のスキーマ参照テスト
- `user_profile.py`: 用語変換（最長一致優先）、未知用語検出、ユーザーごと独立マッピング
- `rag.py`: クエリ解析（意図分類）、検索フロー統合
- `embedder.py`: ベクトル化と Qdrant 格納
- Bedrock モック: `boto3` のモックを使用して API コールなしでテスト可能にする

**依存タスク**: Phase 2, Phase 3 の各サービス実装完了

**推定工数**: L

---

### Task 6.3: RAGAS — RAG 品質評価

**説明**
RAGAS フレームワークを使用して RAG パイプラインの品質を定量評価する。
- 評価メトリクス: Faithfulness, Answer Relevancy, Context Precision, Context Recall
- 工場ドメイン固有の Q&A テストデータセット作成（最低 50 件）
  - 質問カテゴリ: 保全手順、品質トラブル、設備仕様、生産データ参照
  - マスターデータのゆらぎ含む質問（俗称、別名）
  - 各質問に ground truth（期待回答）とソースドキュメントを紐づけ
- 合格基準:
  - Faithfulness ≥ 0.8
  - Answer Relevancy ≥ 0.75
  - Context Precision ≥ 0.7
  - Context Recall ≥ 0.7
- 評価スクリプト: チャンキング戦略やプロンプト変更時に再実行可能
- 評価結果をログに保存し品質推移を追跡する

**依存タスク**: Task 6.5 (サンプルデータ投入), Phase 3 完了

**推定工数**: L

---

### Task 6.4: Playwright — E2E テスト

**説明**
Playwright を使用したフロントエンド E2E テストを実装する。
- チャット機能:
  - テキスト入力 → AI 回答 → ソース参照クリック → プレビューモーダル
  - コピーボタン → クリップボード
  - ★5 評価（ホバー色変化、クリック確定）
  - セッション履歴（新規/復元）
  - シンプル/詳細モード切替
  - インライン用語確認・登録
- 出力パネル:
  - テーブル表示、ページネーション
  - CSV ダウンロード
  - グラフ表示、PNG/SVG ダウンロード
- アップロード:
  - ドラッグ&ドロップ
  - 変換プレビュー
  - タグ確認・修正・確定
  - バージョン管理ダイアログ
- ドキュメント管理:
  - 一覧表示、タグフィルタ、タグ再編集、バージョン履歴
- 設定:
  - リランク/ハイブリッド検索トグル永続化
  - 個人辞書 CRUD
- レスポンシブ:
  - デスクトップ 3 カラム表示
  - モバイル表示（サイドバーオーバーレイ、出力パネルボトムシート）
- アクセシビリティ:
  - キーボードナビゲーション
  - ARIA 属性検証
  - フォーカストラップ（モーダル）
- ナレッジベース管理:
  - KB作成・編集・削除、お気に入り登録/解除、KB選択後のチャット開始、KB未選択時のチャット入力無効化
- ハルシネーション防止:
  - KB内に情報がない質問→拒否メッセージの表示確認
- エラーハンドリング:
  - Oracle 接続失敗フォールバック
  - アップロード失敗リトライ

**依存タスク**: Phase 5 完了, Task 6.1 (Docker 統合)

**推定工数**: XL

---

### Task 6.5: サンプルデータ投入

**説明**
動作確認用のサンプルデータをシステムへ投入する。
- `maintenance/` 配下のメンテナンス履歴ドキュメントをアップロードする
- `meeting_minutes/` 配下の議事録ドキュメントをアップロードする
- `sample/` 配下のガイド文書をアップロードする
- `master-flat-with-place-aliases.md` の取り込みと Qdrant 格納を確認する

**依存タスク**: Task 6.1

**推定工数**: M

---

### Task 6.6: 統合テスト

**説明**
主要フローの End-to-End テストを実装・実行する。
- アップロード → 変換 → タグ付与 → チャンク → インデックス E2E フロー
- チャット → 検索 → 回答生成 E2E フロー
- Oracle 接続 → SQL 生成 → 実行フロー
- Oracle 不可時のフォールバック動作確認
- ユーザー辞書 → クエリ変換フロー
- バージョン管理フロー (同一ファイル名の上書き・旧バージョン参照)

**依存タスク**: 全 Phase 1〜5 のタスク完了後, Task 6.5

**推定工数**: XL

---

## タスク依存関係サマリー

```
Phase 1 (基盤)
  1.1 → 1.2, 1.4, 1.5
  1.2 → 1.3, 3.5, 4.1, 4.4, 4.6
  1.4 → 1.3, 2.1, 2.2, 3.1, 3.2, 3.3, 3.4
  1.5 → 1.3, 3.2, 2.4

Phase 2 (パイプライン)
  1.1 → 2.7 (テキスト正規化)
  2.1 → 2.3, 2.8 (複数ファイル一括アップロード)
  2.8 + 2.5 → 2.8.1 (一括タグ確認画面 BatchTagEditor)
  2.2 → 2.3
  2.3 → 2.4
  2.4 → 2.5
  2.5 → 2.6

Phase 3 (検索・生成)
  3.5 → 3.3
  3.1 → 3.2, 3.4, 3.7
  3.2 → 3.4
  3.3 → 3.4, 3.6
  3.4 → 3.6

Phase 4 (ユーザー管理)
  4.1 → 4.2, 4.3, 4.4
  4.2 → 3.1 (クエリ変換)
  4.4 → 4.5
  4.6 → 4.7 (セッション横断キーワード検索), 5.8 (ナレッジベース UI)
  1.2, 4.6 → 4.7

Phase 5 (フロントエンド)
  5.1 → 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
  5.2 → 5.3, 5.7
  4.7, 5.1 → 5.9 (セッション検索 UI)
  1.2, 1.5, 2.5 → 5.10 (ソフトデリート・ゴミ箱 API)

Phase 6 (テスト・品質保証)
  Phase 2,3 完了 → 6.2 (pytest)
  6.5 (サンプルデータ) + Phase 3 完了 → 6.3 (RAGAS)
  Phase 5 完了 + 6.1 → 6.4 (Playwright E2E)
  6.1 → 6.5 (サンプルデータ)
  全完了 + 6.5 → 6.6 (統合テスト)
```

### クリティカルパス（出力パネル関連）

```
Task 1.1 → Task 1.4 → Task 3.3 → Task 3.4 (回答生成 SSE) → Task 3.6 (出力データ構造化) → Task 5.7 (出力パネル)
```

### クリティカルパス（ナレッジベース関連）

```
Task 1.1 → Task 1.2 → Task 4.6 (ナレッジベース CRUD API) → Task 5.8 (ナレッジベース UI)
```

### クリティカルパス（ハルシネーション防止関連）

```
Task 1.4 → Task 3.1 (RAG オーケストレーション) → Task 3.7 (ハルシネーション防止機構)
```

### クリティカルパス（セッション検索関連）

```
Task 1.1 → Task 1.2 (messages_fts) → Task 4.6 → Task 4.7 (セッション横断キーワード検索) → Task 5.9 (セッション検索 UI)
```

### クリティカルパス（テスト関連）

```
Phase 5 完了 → Task 6.4 (Playwright E2E)
Phase 3 完了 → Task 6.2 (pytest) → Task 6.3 (RAGAS)
```

---

## 工数サマリー

| Phase | タスク数 | 合計工数目安 |
|-------|---------|------------|
| Phase 1: 基盤構築 | 5 | L×3 + M×2 = 約 24〜40h |
| Phase 2: ドキュメント処理 | 8 | XL×2 + L×2 + M×3 + S×1 = 約 35〜62h |
| Phase 3: 検索・生成 | 7 | L×3 + M×3 + S×1 = 約 22〜38h |
| Phase 4: ユーザー管理 | 7 | M×6 + S×1 = 約 13〜26h |
| Phase 5: フロントエンド | 10 | XL×2 + L×5 + M×2 + S×1 = 約 45〜82h |
| Phase 6: テスト・品質保証 | 6 | XL×2 + L×2 + M×1 = 約 28〜48h |
| **合計** | **43** | **約 167〜296h** |
