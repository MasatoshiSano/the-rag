# RAG Phantom 要件定義書

**プロジェクト名:** RAG Phantom
**作成日:** 2026-03-19
**バージョン:** 1.0.0
**ステータス:** 確定

---

## 目次

1. [システム概要](#1-システム概要)
2. [技術スタック](#2-技術スタック)
3. [ユーザーストーリー](#3-ユーザーストーリー)
4. [対応ファイル形式](#4-対応ファイル形式)
5. [チャンキング戦略](#5-チャンキング戦略)
6. [タグシステム](#6-タグシステム)
7. [検索フロー](#7-検索フロー)
8. [ユーザー管理](#8-ユーザー管理)
9. [マスターデータ](#9-マスターデータ)
10. [Oracle DB連携](#10-oracle-db連携)
11. [UI要件](#11-ui要件)
12. [非機能要件](#12-非機能要件)
13. [データモデル](#13-データモデル)
14. [APIエンドポイント](#14-apiエンドポイント)
15. [ディレクトリ構成](#15-ディレクトリ構成)
16. [テスト要件](#16-テスト要件)

---

## 1. システム概要

### 1.1 目的

製造工場における以下のドキュメント群を対象とした、チャットベースのRAG（Retrieval-Augmented Generation）検索システムを構築する。

- 保守マニュアル
- 会議議事録
- 技術文書
- マスターデータ（サイト・ライン・工程情報）

加えて、既存のOracle DBに格納された生産・品質データをSQL生成経由で統合し、自然言語による横断検索を実現する。

### 1.2 展開方式

オンプレミス環境でのDocker Composeによるデプロイ。社内ネットワーク内でデータを保持し、外部通信はAWS Bedrock APIへのリクエストのみに限定する。

### 1.3 対象ユーザー

工場現場の保守・品質・製造担当者（同時利用者数: 10〜50名）

---

## 2. 技術スタック

| 項目 | 採用技術 | 選定理由 |
|------|---------|---------|
| フロントエンド | Vite + React + TypeScript | 高速ビルド・型安全性 |
| UIコンポーネント | Serendie Design System (`@serendie/ui` + `@serendie/symbols`) | 社内標準デザインシステム |
| 状態管理 | Zustand | 軽量・シンプルなグローバル状態管理 |
| バックエンド | Python FastAPI | 非同期対応・高パフォーマンス・型ヒント |
| ベクトルDB | Qdrant (Docker) | オンプレミス対応・高速ANN検索 |
| メタデータ/セッション/ユーザー | SQLite (SQLAlchemy) | 軽量・オンプレミス・依存性なし |
| 生産・品質データ | Oracle DB（既存・読み取り専用） | 既存システム資産の活用 |
| LLM（生成） | AWS Bedrock Claude Sonnet 4.5 | 高品質生成・日本語対応 |
| Embedding | Cohere Embed（Bedrock経由） | 多言語対応・高精度 |
| Rerank | Cohere Rerank（Bedrock経由） | 検索精度向上・デフォルトOFF |
| グラフ表示 | Recharts | React向け・SVG出力可能・軽量 |
| 音声入力 | Web Speech API（ブラウザ標準） | 追加ライブラリ不要 |
| ファイル変換 | pdf2md / pptx2md / excel2md / python-docx / beautifulsoup4+markdownify | 各形式の安定した変換品質 |
| デプロイ | Docker Compose（オンプレミス） | 既存インフラとの親和性 |
| RAG品質評価 | RAGAS | RAGパイプラインの定量評価（Faithfulness, Relevancy等） |
| E2Eテスト | Playwright | クロスブラウザE2Eテスト・アクセシビリティ検証 |
| バックエンドテスト | pytest + pytest-asyncio | ユニットテスト・非同期テスト対応 |

---

## 3. ユーザーストーリー

### US-01: ドキュメントアップロードと自動インデックス

**概要:** ユーザーがドキュメントをアップロードすると、システムが自動的に変換・チャンキング・ベクトル化してインデックスに登録する。

**受け入れ基準:**
- 対応ファイル形式（セクション4参照）のファイルをドラッグ&ドロップまたはファイル選択でアップロード可能
- アップロード後、バックグラウンドで変換処理が非同期実行される
- **インデックス構築（変換→タグ付け→チャンキング→ベクトル化）はサーバーサイドで完全に実行される。ユーザーがブラウザを閉じても、画面をリロードしても、処理は継続する（FastAPI BackgroundTasksによるサーバーサイド処理）**
- **処理状況はフロントエンドがポーリング（GET /api/documents/:id）で取得する。画面を開き直した時、処理中のドキュメントがあれば自動的にポーリングを再開する**
- 処理状況（変換中/インデックス中/完了/エラー/中止）がUI上でリアルタイム確認可能
- **インデックス構築中のドキュメントに「中止」ボタンを表示する。中止すると現在実行中のステージが完了した後に処理を停止し、statusを "cancelled" に変更する**
- 処理完了後、チャット検索の対象に自動追加される
- タグ未確認（status: "tagged"）のファイルはインデックスされない（ユーザーによるタグ確認が必須）
- **エラー発生時（変換/タグ付け/インデックスの各ステージ）、ユーザーは「再試行」ボタンで再実行できる**
- **同じステージで3回失敗したら、「再試行」ボタンを無効化し、「このファイル形式は対応できない可能性があります。別の形式で再アップロードしてください。」と案内する**
- **再試行ごとに `retry_count` をインクリメントし、`retry_count >= 3` で status を "permanent_failed" に変更する**
- **"permanent_failed" 状態のドキュメントは再試行不可、削除のみ可能**
- **"cancelled" 状態のドキュメントは「再試行」または「削除」が可能**

---

### US-02: AIによる自動タグ付けとユーザー確認・編集

**概要:** ドキュメントのアップロード後、AIが自動的にタグを提案し、ユーザーが確認・編集して確定する。

**受け入れ基準:**
- AIがドキュメント内容を解析し、以下のタグを提案する:
  - サイト（site）、ライン（line）、工程（process）、カテゴリ（category）
  - 日付（date）、設備（equipment）、部品（parts）、担当者（persons）、キーワード（keywords）
- ユーザーはAI提案タグを確認し、追加・削除・修正が可能
- 確定したタグはドキュメント全体に適用される
- 確定前にプレビューで変換後Markdownを確認可能
- 複数ファイル一括アップロード時は、全ファイルのAI提案タグをテーブル形式で一覧表示するBatchTagEditorを使用する（単一ファイルの場合は従来のTagEditorを使用）
- タグ確認（status: "tagged"）のまま放置されたファイルは無期限に待機し、インデックスされない（自動確定なし・タイムアウトなし）
- ドキュメント一覧画面で未確認ファイルには「未確認」バッジを表示して目立たせる

---

### US-03: 自然言語によるチャット検索（ドキュメント + Oracle データ統合）

**概要:** 自然言語でチャット入力し、ドキュメントとOracle生産・品質データを統合した回答を得る。

**受け入れ基準:**
- 日本語自然言語でのクエリを受け付ける
- クエリの意図（ドキュメント検索/Oracle照会/ハイブリッド）をAIが自動判別
- ドキュメント検索結果とOracle SQLクエリ結果を統合して回答を生成
- SSEストリーミングでリアルタイムに回答を表示
- **ストリーミング中の入力制御:**
  - AI回答のストリーミング中はチャット入力欄を無効化（disabled）する
  - 送信ボタンもdisabledにする
  - 入力欄には「回答中...」のプレースホルダーテキストを表示する
  - キャンセル（停止ボタン）を押せば入力可能に戻る
  - 質問のキューイングは行わない（シンプルさ優先）
- Oracle DB未接続時はRAG検索のみで継続（グレースフルフォールバック）
- **キャンセル時の挙動:**
  - ストリーミング中にユーザーがキャンセル（停止ボタンクリック）した場合、途中までの回答テキストを保持して表示する
  - メッセージの末尾に「（回答が中断されました）」と表示する
  - messagesテーブルには途中のcontentを保存する（role="assistant"）
  - ソース参照は受信済みのものだけ表示する
  - 中断された回答には評価（星）を付けられない
  - 出力パネルのデータも受信済み分のみ表示する

---

### US-04: 音声入力による質問

**概要:** マイクボタンを押して話すと、音声がテキストに変換されてチャット入力欄に入力される。

**受け入れ基準:**
- ブラウザ標準Web Speech APIを使用（追加インストール不要）
- マイクボタン押下で録音開始、再押下または自動検出で終了
- 変換されたテキストはチャット入力欄に表示され、ユーザーが送信前に編集可能
- 音声入力で送信されたメッセージには`input_type: "voice"`が記録される

---

### US-05: 回答内のソース参照（クリック可能なプレビューモーダル）

**概要:** AI回答には引用元ドキュメントのリンクが表示され、クリックするとドキュメントの該当箇所がモーダルでプレビューされる。

**受け入れ基準:**
- 回答に引用元ドキュメント名・セクション名が表示される
- ソースリンクをクリックするとモーダルが開く
- モーダルには変換済みMarkdown内の該当セクションが表示される
- 複数ソースがある場合は一覧表示し、個別に参照可能

---

### US-06: AI回答のMarkdownコピー（ソース付き）

**概要:** AI回答をMarkdown形式でクリップボードにコピーできる。ソース参照情報も含まれる。

**受け入れ基準:**
- 回答欄にコピーボタンを設置
- コピー内容はMarkdown形式（回答本文 + ソース参照リスト）
- コピー成功時にトーストまたはボタンアニメーションでフィードバック

---

### US-07: セッション履歴の管理と過去セッションの継続

**概要:** 過去のチャットセッションが一覧表示され、選択して会話を継続できる。

**受け入れ基準:**
- サイドバーにセッション一覧が表示される（タイトル・日時）
- セッションタイトルはAIが最初の質問から自動生成
- 過去セッションを選択すると、そのセッションの会話履歴が表示される
- 新規セッション開始ボタンで新しいセッションを作成可能
- セッションの削除が可能
- セッションは常に1つのナレッジベースに紐付く（途中でKBを変更することはない）
- チャット中にサイドバーで別のナレッジベースを選択した場合、自動的に新規セッションが開始される（前のセッションは保持される）

---

### US-08: 5段階スター評価

**概要:** AI回答に対して1〜5段階のスター評価ができる。ホバーで点灯、クリックで確定する。

**受け入れ基準:**
- 各AI回答の下に☆☆☆☆☆の5つ星が表示される
- マウスホバーで対象の星まで点灯（ハイライト表示）
- クリックで評価が確定し、サーバーに保存される
- 確定後も評価の変更が可能
- 評価値（1〜5）はメッセージレコードに保存される

---

### US-09: ユーザーごとのRerank ON/OFF設定

**概要:** Cohere Rerankの使用をユーザーが個別に切り替えられる。設定は永続化される。

**受け入れ基準:**
- 設定ページにRerank ON/OFFのトグルを設置
- デフォルトはOFF
- 設定変更は即時反映され、次の検索から適用される
- ブラウザ/端末を変えても設定が維持される（ユーザーID紐付け）

---

### US-10: 個人用語辞書（ユーザー固有のスラング → マスターキー変換）

**概要:** ユーザーが使う独自の略語・スラングをマスターキーに変換するユーザー固有辞書を管理できる。

**受け入れ基準:**
- 設定ページで個人用語辞書の追加・編集・削除が可能
- 同じスラングでも、ユーザーによって異なるマスターキーへのマッピングが可能
- チャット入力時に辞書変換が自動適用されてからRAG検索が実行される
- マスターキーはマスターデータ（サイト/ライン/工程）と紐付け可能

---

### US-11: チャット内インライン用語検出と登録

**概要:** AIが回答生成中に未知の用語を検出した場合、候補を提示してユーザーが確認・辞書登録できる。

**受け入れ基準:**
- AI回答内で不明・曖昧な用語が検出されると、インラインでハイライト表示
- ハイライト用語をクリックするとマスター候補一覧がポップオーバー表示
- ユーザーが正しいマスターキーを選択すると個人用語辞書に自動登録
- 登録後は以降の検索で変換が自動適用される

---

### US-12: アップロードプレビュー（変換済みMarkdown）

**概要:** アップロード後、AIインデックス前に変換されたMarkdownをプレビュー確認できる。

**受け入れ基準:**
- 変換完了後、プレビューボタンまたは自動表示でMarkdownを確認可能
- Markdown形式でレンダリングされた表示と生テキスト表示の切り替え可能
- プレビュー確認後にタグ付け確認画面へ進む

---

### US-13: ドキュメントバージョン管理

**概要:** 同一ドキュメントが更新された場合、バージョンを管理し、検索では最新バージョンを優先する。

**受け入れ基準:**
- 同じファイル名またはユーザーが指定した親ドキュメントIDに紐付けて新バージョンを登録
- バージョン番号は自動採番（1, 2, 3...）
- ドキュメント一覧にはデフォルトで最新バージョンのみ表示
- バージョン履歴一覧から旧バージョンの参照・比較が可能
- 検索ヒット時は最新バージョンのチャンクが優先される

---

### US-14: 横断検索（ページをまたぐ・ドキュメントをまたぐ）

**概要:** 複数ドキュメントの複数ページにまたがる情報を統合して回答を生成できる。

**受け入れ基準:**
- 単一ドキュメントだけでなく、複数ドキュメントから関連チャンクを取得して統合
- 回答に複数のソース参照が付与される
- 関連度スコアに基づいて上位チャンクが選択される

---

### US-15: ユーザーごとのハイブリッド検索 ON/OFF設定

**概要:** ベクトル検索に加えてキーワード検索（BM25/スパースベクトル）を組み合わせるハイブリッド検索をユーザーが切り替えられる。

**受け入れ基準:**
- 設定ページにハイブリッド検索 ON/OFFのトグルを設置
- デフォルトはOFF（ベクトル検索のみ）
- ON時はQdrantのスパースベクトル/BM25と密ベクトルを組み合わせたRRFスコアリング
- 設定は永続化される

---

### US-16: シンプル/詳細回答モード切り替え

**概要:** チャット入力欄の近くにモード切り替えボタンを設置し、回答の詳細レベルを変更できる。

**受け入れ基準:**
- チャット入力欄近傍に「シンプル」/「詳細」切り替えボタンを設置
- シンプルモード: 簡潔な回答（3〜5文程度）
- 詳細モード: 詳細な説明・根拠・手順を含む回答
- モードはメッセージごとに選択可能
- メッセージレコードに`response_mode`として保存される

---

### US-17: ユーザープロファイル学習

**概要:** ユーザーの行動パターン（頻繁に参照するライン・カテゴリ・最近のコンテキスト）を学習し、回答生成のシステムプロンプトに反映する。

**受け入れ基準:**
- チャット・ドキュメント参照の行動履歴からプロファイルを自動更新
- 頻繁に参照するライン・カテゴリをランキング形式でプロファイルに保存
- 直近の検索コンテキストをセッションまたは期間で集約
- プロファイル情報はClaudeへのシステムプロンプトに暗黙的コンテキストとして付与
- 設定ページでプロファイル情報の確認・リセットが可能

---

### US-18: 出力パネル（Oracle取得データの可視化・ダウンロード）

**概要:** ユーザーとして、Oracleから取得したデータをチャット右側の出力パネルにテーブル・グラフで表示し、CSVや画像でダウンロードしたい。

**受け入れ基準:**
- Oracle DBから取得したデータがチャットエリア右側の出力パネルに表示される
- テーブル表示: ページネーション対応、カラムソート、CSVダウンロード、Markdownコピー
- グラフ表示: AIがデータと質問意図から最適なグラフ種別を自動選択
- PNG/SVGでグラフをダウンロード可能
- データ量に応じた表示制御（少量→チャット内埋め込み+出力パネル、中量→出力パネルテーブル、大量→ページネーション+CSVダウンロード）
- モバイル時はボトムシートまたはタブ切替で出力パネルを表示

---

### US-19: ナレッジベース管理

**概要:** ユーザーがナレッジベース（ドキュメントの論理的なグループ）を作成・管理し、ドキュメントをナレッジベース単位で整理・検索できる。

**受け入れ基準:**
- ナレッジベースの作成が可能（名前・説明・カラーの指定）
- ナレッジベースの名前・説明・カラーの編集が可能
- ナレッジベースの削除が可能（配下のドキュメント・ベクトルデータも連動削除）
- ナレッジベース一覧がカード形式で表示される（名前・説明・カラー・ドキュメント数）
- ドキュメントアップロード時にナレッジベースの指定が必須
- 各ドキュメントは必ず1つのナレッジベースに所属する
- チャットセッション作成時にナレッジベースの指定が必須
- ベクトル検索は指定されたナレッジベースのドキュメントのみをスコープとする

---

### US-20: ナレッジベースのお気に入り登録とチャット画面表示

**概要:** ユーザーがナレッジベースをお気に入りに登録し、チャット画面のサイドバーからお気に入りのナレッジベースを素早く選択してチャットを開始できる。

**受け入れ基準:**
- ナレッジベース一覧でお気に入り（スター/ブックマーク）の切り替えが可能
- チャット画面の左サイドバーにお気に入り登録済みナレッジベースのみが表示される
- お気に入りナレッジベースをクリックすると、そのナレッジベースをスコープとした新規チャットセッションが開始される
- チャット中に別のナレッジベースを選択した場合、現在のセッションを保持したまま新規セッションが自動的に開始される（KB切り替え = 新規セッション）
- お気に入りの登録・解除はユーザーごとに管理される
- お気に入りが未登録の場合、サイドバーにナレッジベース選択を促すメッセージを表示する

---

### US-21: ハルシネーション防止（厳格RAG制約）

**概要:** システムは一般知識による回答を一切行わず、選択されたナレッジベース内の検索結果のみに基づいて回答を生成する。

**受け入れ基準:**
- 検索されたドキュメントチャンクに該当する情報が含まれない場合、「選択されたナレッジベース内に該当する情報が見つかりませんでした。」と回答する
- 一般的な質問（例:「富士山の高さは？」）であっても、ナレッジベース内に情報がなければ回答を拒否する
- Claudeへのシステムプロンプトに「提供されたコンテキストのみを使用し、自身の学習知識は一切使用しない」旨を明示的に指示する
- 検索結果の関連度スコアが閾値（設定可能）を下回る場合、低信頼度であることをユーザーに明示するか、回答を拒否する
- 回答には必ずソース参照を含め、出典のない主張を含めない

---

### US-22: 半角/全角カタカナ正規化

**概要:** Oracleトラブルマスター（HF1SGM01）には半角カタカナ（例: ｻｲｸﾙﾀｲﾑｵｰﾊﾞｰ）が含まれるが、ユーザーは全角カタカナ（例: サイクルタイムオーバー）で検索する。検索時・タグ付け時にテキスト正規化を行い、表記ゆれを吸収する。

**受け入れ基準:**
- チャット検索時、ユーザー入力を正規化（全角→半角、半角→全角の両方向でマッチ）
- Qdrantベクトル検索前にクエリテキストを正規化する
- Oracle SQLテンプレートのWHERE句でも正規化を考慮
- タグ付け時（tagger.py）もマスター照合前に正規化
- 個人用語辞書のスラング登録時も正規化して格納
- Python標準ライブラリの `unicodedata.normalize('NFKC', text)` を使用
- 対象: カタカナ半角↔全角、英数字半角↔全角、記号の一部

---

### US-23: セッション横断キーワード検索

**概要:** サイドバーにセッション検索ボックスを設置し、全セッションのメッセージ本文（user/assistant両方）をキーワードで全文検索できるようにする。

**受け入れ基準:**
- サイドバーにセッション検索ボックスを設置
- キーワード入力で、全セッションのメッセージ本文（user/assistant両方）を全文検索
- 検索結果はセッション単位でグルーピングし、マッチしたメッセージのスニペットを表示
- 検索結果のセッションをクリックすると、該当セッションに遷移
- SQLiteのFTS5（Full-Text Search）を使用してパフォーマンス確保

---

### US-24: 複数ファイル一括アップロード

**概要:** DropZoneで複数ファイルを同時にドラッグ&ドロップまたは選択し、一括でアップロード・処理を行えるようにする。

**受け入れ基準:**
- DropZoneで複数ファイルを同時にドラッグ&ドロップまたは選択可能
- 各ファイルの処理状況を個別に表示（プログレスバー）
- 全ファイルに同一のナレッジベースを適用
- 1回のアップロードで最大20ファイルまで
- 合計ファイルサイズ上限: 200MB
- バックエンドは各ファイルを並行処理（最大3並行）
- 1ファイルの失敗が他ファイルの処理を停止しない
- ZIPファイルのアップロードにも対応（自動展開して個別処理）
- 全ファイルのAIタグ付けが完了後、BatchTagEditor（テーブル形式の一括タグ確認画面）を表示する
  - 各行 = 1ファイル、列 = ファイル名・サイト・ライン・工程・カテゴリ・キーワード・AI信頼度
  - 各セルはクリックで編集可能
  - 「全て確定」ボタンで全ファイルのタグを一括確定（`PATCH /api/documents/batch-tags`）
  - 個別ファイルの先行確定も可能
  - タグ付け未完了のファイルはスピナーを表示
  - 単一ファイルアップロード時は従来のTagEditorを表示

---

### US-25: ドキュメントのソフトデリートと復元

**概要:** ドキュメント削除時は即座に物理削除せず、ソフトデリート（論理削除）を行い、30日間はゴミ箱から復元可能にする。

**受け入れ基準:**
- ドキュメント削除時に確認ダイアログを表示する（「このドキュメントとそのインデックスデータを削除しますか？」）
- 削除は即座にQdrantからベクトルを消さない（ソフトデリート）
- `documents` テーブルの `deleted_at` カラムに削除日時をセットする
- `deleted_at` が設定されたドキュメントは一覧・検索から除外される（Qdrant検索時もフィルタリング）
- 30日後にバックグラウンドジョブで物理削除（Qdrantベクトル + SQLiteレコード + アップロードファイル）
- 30日以内なら「ゴミ箱」から復元可能（`deleted_at` をNULLにリセット）
- ドキュメント一覧画面に「ゴミ箱」タブまたはフィルターを設置し、ソフトデリート済みドキュメントを表示する
- ゴミ箱内の各ドキュメントに「復元」ボタンと「完全削除」ボタンを表示する

**API:**
- `DELETE /api/documents/{id}` → ソフトデリート（`deleted_at` をセット）
- `POST /api/documents/{id}/restore` → ゴミ箱から復元（`deleted_at` をNULLに）
- `GET /api/documents?deleted=true` → ゴミ箱一覧
- `DELETE /api/documents/{id}/permanent` → 物理削除（Qdrantベクトル + SQLiteレコード + アップロードファイルを完全削除）

---

## 4. 対応ファイル形式

| 拡張子 | 変換方式 | 使用ライブラリ |
|--------|---------|-------------|
| `.md` | そのまま使用 | — |
| `.txt` | そのまま使用 | — |
| `.pdf` | PDF → Markdown変換 | `pdf2md` (https://github.com/hama-jp/pdf2md) |
| `.pptx` | PPTX → Markdown変換 | `pptx2md` (https://github.com/ssine/pptx2md) |
| `.xlsx` | Excel → Markdown変換 | `excel2md` (https://github.com/elvezjp/excel2md) |
| `.docx` | Word → カスタム変換 | `python-docx` + カスタムMarkdown生成 |
| `.csv` | 構造解析 → Markdown変換 | カスタム実装 |
| `.json` | 構造解析 → Markdown変換 | カスタム実装 |
| `.png` `.jpeg` `.jpg` | 画像解析 → テキスト | AWS Bedrock Claude Vision |
| `.html` | HTML → Markdown変換 | `beautifulsoup4` + `markdownify` |

---

## 5. チャンキング戦略

### 5.1 構造化ドキュメント（md, html）

- ヘッダー階層（H1 > H2 > H3）に基づくセマンティックチャンキング
- 各チャンクにヘッダーパスをメタデータとして付与（例: `設備保守 > 3号機 > 点検手順`）

### 5.2 非構造化ドキュメント（txt等）

- Agenticチャンキング: BedrockのClaudeがセマンティック境界を判定
- 意味的に完結するブロック単位で分割

### 5.3 会議議事録

- 特殊チャンキング: 以下の要素に分解して個別チャンクとして管理
  - 決定事項（decisions）
  - アクションアイテム（action_items）
  - 課題（issues）
  - 対策（countermeasures）
- 各要素チャンクに会議メタ情報（日時・参加者・議題）を付与

### 5.4 テーブル（表）

- 行グループ単位でチャンク化
- 各チャンクにテーブルが属するセクションコンテキストを付与

### 5.5 画像

- Claude Visionによる画像説明テキストを生成
- 前後の文章コンテキストと結合して1チャンクとして登録

### 5.6 Parent-Child チャンキング

- **検索精度と文脈提供のバランスを取るため**、細粒度のchildチャンクでベクトル検索を実行
- 検索ヒットしたchildチャンクに対して、親チャンク（parentチャンク）に展開してLLMに渡す
- Qdrantのペイロードに`parent_chunk_id`を記録して紐付けを管理

---

## 6. タグシステム

### 6.1 ドキュメントレベルタグ（Two-Layer Tag System）

ドキュメント全体に付与するタグ。AIが自動提案し、ユーザーが確認・編集して確定する。

| タグキー | 説明 | 例 |
|---------|-----|---|
| `site` | サイト | `名古屋工場`, `大阪工場` |
| `line` | ライン | `A1ライン`, `B3ライン` |
| `process` | 工程 | `溶接`, `塗装`, `組立` |
| `category` | カテゴリ | `保守マニュアル`, `議事録`, `技術仕様` |
| `date` | 文書日付 | `2025-10-01` |
| `equipment` | 設備名 | `溶接ロボット3号機` |
| `parts` | 部品名 | `フランジボルト M10` |
| `persons` | 関連人物 | `山田太郎`, `鈴木花子` |
| `keywords` | キーワード | `[トルク管理, 締付トルク]` |

### 6.2 チャンクレベルタグ

チャンクごとにAIが自動付与。親ドキュメントのタグを継承しつつ、チャンク固有の追加タグを付与する。

- ドキュメントタグをすべて継承
- チャンク固有タグ: セクション名、ページ番号、チャンクタイプ（table/image/text/decision/action）

---

## 7. 検索フロー

```
ユーザーのクエリ入力
        │
        ▼
[Step 1] クエリ分析（Claude）
  - 意図分類: ドキュメント検索 / Oracle照会 / ハイブリッド
  - エンティティ抽出（設備名・ライン・日付等）
        │
        ▼
[Step 2] テキスト正規化（NFKC）
  - unicodedata.normalize('NFKC', text) によるクエリテキスト正規化
  - 半角カタカナ→全角カタカナ、全角英数字→半角英数字に統一
  - Oracle照会・ベクトル検索・タグ照合の全経路で適用
        │
        ▼
[Step 3] 個人用語辞書変換
  - ユーザー固有のスラング → マスターキーに変換
  - マスターデータ（SQLite/Qdrant）で正規化
        │
        ▼
[Step 4] ベクトル検索（Qdrant）
  - Cohere Embedでクエリをベクトル化
  - Qdrantでchildチャンクに対してANN検索（knowledge_base_idによるフィルタリング必須）
  - 検索スコープは選択されたナレッジベースのドキュメントのみに限定される
  - ユーザー設定によりハイブリッド検索（スパースベクトル/BM25）を併用（任意）
        │
        ▼
[Step 5] Parent-Child展開
  - ヒットしたchildチャンクをparentチャンクに展開
  - 文脈を保持したコンテキストをLLMへ渡す
        │
        ▼
[Step 6] Rerank（任意）
  - ユーザー設定でONの場合、Cohere Rerankで上位チャンクを再スコアリング
        │
        ▼
[Step 7] Oracle SQL生成・実行（必要な場合）
  - Claudeがクエリ意図に基づいてSELECT文を生成
  - oracle_query_templatesをリファレンスとして参照
  - 安全制約: SELECT専用・タイムアウト設定・取得行数上限
  - Oracle未接続時はRAG検索結果のみで継続（グレースフルフォールバック）
        │
        ▼
[Step 8] 回答生成（Claude Sonnet 4.5）
  - システムプロンプトにユーザープロファイルを付与
  - システムプロンプトに厳格RAG制約を明示（提供コンテキストのみ使用、一般知識の使用禁止）
  - ドキュメントチャンク + Oracle結果をコンテキストとして渡す
  - 関連度スコアが閾値未満の場合、回答拒否または低信頼度を明示
  - 該当情報がない場合、「選択されたナレッジベース内に該当する情報が見つかりませんでした。」と回答
  - シンプル/詳細モードに応じたプロンプト指示を適用
  - SSEストリーミングでフロントエンドへ配信
        │
        ▼
[Step 9] 回答表示
  - ストリーミング表示
  - ソース参照リンク付与
  - インライン用語検出・ハイライト
```

---

## 8. ユーザー管理

### 8.1 識別方式

アカウント登録不要。以下の方式でユーザーを一意に識別する。

- **ブラウザフィンガープリント** + **localStorageに保存したUUID**の組み合わせ
- 初回アクセス時にUUIDを発行し、ユーザーレコードを自動生成

### 8.2 任意プロファイル

- ニックネームの設定が可能（任意）
- 設定しない場合は「ゲスト」や自動生成名で表示

### 8.3 ユーザーごとの設定

| 設定項目 | デフォルト | 説明 |
|---------|---------|-----|
| `rerank_enabled` | `false` | Cohere Rerankの使用 |
| `hybrid_search_enabled` | `false` | ハイブリッド検索の使用 |
| `response_mode` | `"simple"` | シンプル/詳細モード |
| ニックネーム | 未設定 | 任意の表示名 |

### 8.4 個人用語辞書

- ユーザー固有のスラング → マスターキーのマッピングを管理
- 同一スラングでもユーザーによって異なるマスターキーへのマッピングが可能
  - 例: Aさんの「3号機」→ `LINE_A3`、Bさんの「3号機」→ `LINE_B3`
- マスターキーはマスターデータのsite/line/processコードと紐付け

### 8.5 行動履歴・プロファイル学習

- 頻繁に参照するライン・カテゴリをJSONで記録
- 直近の検索コンテキスト（直近N件のクエリ・参照ドキュメント）を保持
- Claude生成時のシステムプロンプトに暗黙的コンテキストとして付与

---

## 9. マスターデータ

### 9.1 規模

- 総レコード数: 10,118件（サイト・ライン・工程の階層構造）

### 9.2 二重保存戦略

| 保存先 | 用途 |
|-------|-----|
| SQLite | 構造化クエリ（コード検索・階層フィルタリング） |
| Qdrant | ベクトル検索（別名・スラングのファジーマッチング） |

### 9.3 データ構造

**サイト（master_sites）**
```
code (PK) | name | aliases (JSON配列)
```

**ライン（master_lines）**
```
code (PK) | site_code (FK) | name | aliases (JSON配列)
```

**工程（master_processes）**
```
code (PK) | line_code (FK) | name | tm_class | dt_class | station_no1 | station_no2 | station_no3
```

---

## 10. Oracle DB連携

### 10.1 接続方針

- 読み取り専用（SELECT専用）
- 既存のOracle DBには変更を加えない
- Oracle未接続時はRAG検索のみで継続

### 10.2 対象テーブル（5テーブル）

Oracle DBには以下の5テーブルが存在し、すべて読み取り専用でアクセスする。

#### HF1R6M01（生産トレーサビリティデータ）

| カラム名 | 型 | 説明 |
|---------|---|-----|
| `MK_DATE` | DATE | 製造日 |
| `STA_NO1` | VARCHAR | サイトコード |
| `STA_NO2` | VARCHAR | ラインコード |
| `STA_NO3` | VARCHAR | 工程コード |
| `M_SERIAL` | VARCHAR | メインシリアル番号 |
| `INSP_ITEMNAME` | VARCHAR | 検査項目名 |
| `MEASURE` | NUMBER | 計測値 |

#### HF1REM01（品質結果データ）— 約166,248件

品質判定結果テーブル。各製品の良品/不良品判定を記録し、不良率の算出に使用する。

> **重要**: `OPEFIN_RESULT` カラムが品質判定の核心であり、**1=良品(OK)、2=不良(NG)** を表す。不良率は `COUNT(OPEFIN_RESULT=2) / COUNT(*)` で算出する。

| カラム名 | 型 | 説明 |
|---------|---|-----|
| `MK_DATE` | VARCHAR | 作成日時（形式: "YYYYMMDDHHmmss"、例: "20260319083932"） |
| `STA_NO1` | VARCHAR | サイトコード（例: "SAND"） |
| `STA_NO2` | VARCHAR | ラインコード（例: "NHCFA010"） |
| `STA_NO3` | VARCHAR | 工程コード（例: "003010"） |
| `SUB_NO` | NUMBER | サブ番号 |
| `CORRECT_SEQ` | NUMBER | 修正シーケンス |
| `M_SERIAL` | VARCHAR | メインシリアル番号（タイムスタンプ形式、例: "20260319083929"）→ HF1R6M01と結合可能 |
| `MANAGEID` | VARCHAR | 管理ID |
| `PARTSNAME` | VARCHAR | 部品名（例: "3AC02B"） |
| **`OPEFIN_RESULT`** | **NUMBER** | **作業完了結果: 1=良品(OK), 2=不良(NG)** ← 不良率算出の核心カラム |
| `QTY` | NUMBER | 数量 |
| `SKIP_CHK_MODE` | VARCHAR | スキップチェックモード |
| `OPE_CODE` | VARCHAR | オペレーターコード |
| `EXCEPT_FLAG` | NUMBER | 例外フラグ（集計対象制御）: **0=通常データ（集計対象）, 1=通常データ（集計対象）, 2=除外データ（集計対象外）, 30代(30-39)=OKマスタ定義（集計対象外）, 40代(40-49)=NGマスタ定義（集計対象外）, 50代(50-59)=その他マスタ定義（集計対象外）**。集計クエリには必ず `WHERE EXCEPT_FLAG IN (0, 1)` を付与すること |
| `PLT_NO` | VARCHAR | パレット番号 |
| `NG_CODE` | VARCHAR | 不良コード → HF1SGM01.CODE_NO と結合して不良内容を解決。**注意: OPEFIN_RESULT=2（不良）でもNG_CODEがNULLの場合がある。LEFT JOINを使用し、NG_CODEがNULLの不良品は「未分類」として扱うこと** |
| `REWORK_CNT` | NUMBER | リワーク回数 |
| `RETRY_CNT` | NUMBER | リトライ回数 |
| `PENDING_FLAG` | VARCHAR | 保留フラグ |
| `S_SERIAL00` 〜 `S_SERIAL39` | VARCHAR | サブシリアル番号（40カラム）→ HF1SKM01.PARTS_NO で部品名を解決 |
| `T3_HANDSHAKE` | NUMBER | ハンドシェイクステータス |
| `RUNNING_NO` | VARCHAR | ランニング番号 |
| `UPCMPFLG` | NUMBER | アップロード完了フラグ |
| `ORDER_NO` | VARCHAR | オーダー番号 |
| `SOURCE_CAT` | VARCHAR | ソースカテゴリ |
| `CONTENTS` | VARCHAR | コンテンツ |

#### HF1SGM01（トラブルマスター）— 約11,821件

トラブルコードマスターテーブル。STA_NO1/2/3 + CODE_NO でトラブル名称を解決する。

| カラム名 | 型 | 説明 |
|---------|---|-----|
| `STA_NO1` | VARCHAR | サイトコード（例: "SAND"） |
| `STA_NO2` | VARCHAR | ラインコード（例: "KAHA02"） |
| `STA_NO3` | VARCHAR | 工程コード（例: "010010"） |
| `CODE_NO` | NUMBER | トラブルコード番号（1, 2, 3...） |
| `TROUBLE_NG_INFO` | VARCHAR | トラブル内容（例: "サイクルタイムオーバー", "抵抗値NG"） |
| `MK_DATE` | DATE | 作成日 |
| `UP_DATE` | DATE | 更新日 |
| `TROUBLE_NG_INFO_L` | VARCHAR | 詳細説明 |
| `TROUBLE_NG_INFO_EN` | VARCHAR | 英語説明 |
| `STA_NO4` | VARCHAR | 追加ステーション |
| `WITHOUT_FLAG` | VARCHAR | 除外フラグ |
| `MK_USER` | VARCHAR | 作成者 |
| `UP_USER` | VARCHAR | 更新者 |
| `MEMO` | VARCHAR | メモ |

#### HF1RFM01（トラブルデータ）

トラブル発生実績テーブル。STA_NO1/2/3 + CODE_NO でHF1SGM01と結合してトラブル名称を取得する。

| カラム名 | 型 | 説明 |
|---------|---|-----|
| `MK_DATE` | VARCHAR | 発生日時（形式: "20260319090353"） |
| `STA_NO1` | VARCHAR | サイトコード |
| `STA_NO2` | VARCHAR | ラインコード |
| `STA_NO3` | VARCHAR | 工程コード |
| `EXCEPT_FLAG` | VARCHAR | 例外フラグ（集計対象制御）: **0=通常データ（集計対象）, 1=通常データ（集計対象）, 2=除外データ（集計対象外）, 30代(30-39)=OKマスタ定義（集計対象外）, 40代(40-49)=NGマスタ定義（集計対象外）, 50代(50-59)=その他マスタ定義（集計対象外）**。集計クエリには必ず `WHERE EXCEPT_FLAG IN (0, 1)` を付与すること |
| `M_SERIAL` | VARCHAR | メインシリアル番号 |
| `T4_STATUS` | NUMBER | ステータスコード（※クエリでのフィルタ不要。無視してよい） |
| `CODE_NO` | NUMBER | トラブルコード → HF1SGM01と結合 |
| `T4_UPDATE_CHECK` | NUMBER | トラブルイベント種別: **4=ブザー鳴動（異常発生）時刻**, **5=ブザー停止（オペレーター対応）時刻**。※これは設備の異常停止時刻ではない。同じトラブルが4と5のペアで記録される。トラブル発生件数のカウントには `T4_UPDATE_CHECK=4` を使用する |
| `PARTSNAME` | VARCHAR | 部品名 |
| `OPE_CODE` | VARCHAR | オペレーターコード |
| `PLT_NO` | VARCHAR | パレット番号 |
| `T4_HANDSHAKE` | NUMBER | ハンドシェイクステータス |
| `UPCMPFLG` | NUMBER | アップロード完了フラグ |
| `ON_TIME` | VARCHAR | オンタイム |
| `REP_START_TIME` | VARCHAR | 修理開始時刻 |
| `RESTART_TIME` | VARCHAR | 復旧時刻 |
| `SOURCE_CAT` | VARCHAR | ソースカテゴリ |
| `MEMO` | VARCHAR | メモ |

#### HF1SKM01（シリアル/部品マスター）— 約958件

部品番号マスターテーブル。PARTS_NOから部品名称を解決する。HF1REM01のM_SERIAL・S_SERIALカラムの意味を説明する。

| カラム名 | 型 | 説明 |
|---------|---|-----|
| `STA_NO1` | VARCHAR | サイトコード |
| `STA_NO2` | VARCHAR | ラインコード |
| `STA_NO3` | VARCHAR | 工程コード |
| `PARTS_NO` | NUMBER | 部品番号 |
| `MAIN_PARTS_NAME` | VARCHAR | メイン部品名（例: "ワークID", "ホンダDA", "2Dcode"） |
| `SUB_PARTS_NAME` | VARCHAR | サブ部品名（例: "基盤ロット:親資材コード", "PCBオーディオ"） |
| `MAIN_LOT_START` | NUMBER | メインロット開始位置 |
| `MAIN_LOT_LENGTH` | NUMBER | メインロット長 |
| `SUB_LOT_START` | NUMBER | サブロット開始位置 |
| `SUB_LOT_LENGTH` | NUMBER | サブロット長 |
| `MEMO` | VARCHAR | メモ |
| `MK_DATE` | DATE | 作成日 |
| `UP_DATE` | DATE | 更新日 |
| `MAIN_PARTS_NAME_L` | VARCHAR | メイン部品名（詳細） |
| `SUB_PARTS_NAME_L` | VARCHAR | サブ部品名（詳細） |
| `MAIN_PARTS_NAME_EN` | VARCHAR | メイン部品名（英語） |
| `SUB_PARTS_NAME_EN` | VARCHAR | サブ部品名（英語） |
| `OYAKO_HANTEN` | VARCHAR | 親子反転フラグ |
| `NO_MANAGE` | VARCHAR | 管理対象外フラグ |
| `MK_USER` | VARCHAR | 作成者 |
| `UP_USER` | VARCHAR | 更新者 |
| `HINCODE` | VARCHAR | 品番コード |

### 10.3 テーブル間リレーション

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
```

- 全テーブルが `STA_NO1`（サイト）/ `STA_NO2`（ライン）/ `STA_NO3`（工程）でマスターデータと紐づく
- トラブル分析: `HF1RFM01` × `HF1SGM01` を `STA_NO1/2/3 + CODE_NO` で結合
- 品質×部品: `HF1REM01` × `HF1SKM01` を `STA_NO1/2/3 + PARTS_NO` で結合
- 不良内容解決: `HF1REM01.NG_CODE` → `HF1SGM01.CODE_NO` で不良名称を取得（**LEFT JOIN必須** — NG_CODEがNULLの不良品は「未分類」として扱う）
- **EXCEPT_FLAGフィルタ（必須）**: `HF1REM01` および `HF1RFM01` への集計クエリには必ず `WHERE EXCEPT_FLAG IN (0, 1)` を付与すること。このフィルタがないと、マスタ定義レコード（30代/40代/50代）や除外データ（2）が集計結果を汚染する
- **NG_CODEのNULL許容**: `OPEFIN_RESULT=2`（不良）でも `NG_CODE` がNULLの場合がある。`NG_CODE` での結合は `LEFT JOIN` を使用し、NULLの不良品は「未分類」として集計に含めること
- トレーサビリティ: `HF1REM01.M_SERIAL` → `HF1R6M01.M_SERIAL` で生産データと結合
- **トラブル時間算出（クロステーブル計算）**: `HF1RFM01`（T4_UPDATE_CHECK=4）の `MK_DATE` をトラブル開始とし、同一 `STA_NO1/2/3` で次に `HF1REM01` に品質結果が記録された `MK_DATE` をトラブル終了（生産復帰）とする。トラブル時間 = `HF1REM01.MK_DATE` - `HF1RFM01.MK_DATE`。これは設備停止時間ではなく、「トラブル発生から生産復帰（品質結果が出る）までの実影響時間」である

### 10.4 SQLクエリテンプレート例

以下はClaudeがSQL生成時に参照するテンプレートの例である。

**特定ラインのトラブル発生件数**
```sql
SELECT
    sgm.TROUBLE_NG_INFO AS トラブル内容,
    COUNT(*) AS 発生件数
FROM HF1RFM01 rfm
JOIN HF1SGM01 sgm
    ON rfm.STA_NO1 = sgm.STA_NO1
   AND rfm.STA_NO2 = sgm.STA_NO2
   AND rfm.STA_NO3 = sgm.STA_NO3
   AND rfm.CODE_NO = sgm.CODE_NO
WHERE rfm.T4_UPDATE_CHECK = 4  -- ブザー鳴動（異常発生）レコードのみカウント
  AND rfm.EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ（マスタ定義・除外データを排除）
  AND rfm.STA_NO2 = :line_code
  AND rfm.MK_DATE BETWEEN :start_date AND :end_date
GROUP BY sgm.TROUBLE_NG_INFO
ORDER BY 発生件数 DESC
FETCH FIRST 500 ROWS ONLY
```

**トラブル内容別の時系列推移**
```sql
SELECT
    SUBSTR(rfm.MK_DATE, 1, 8) AS 発生日,
    sgm.TROUBLE_NG_INFO AS トラブル内容,
    COUNT(*) AS 件数
FROM HF1RFM01 rfm
JOIN HF1SGM01 sgm
    ON rfm.STA_NO1 = sgm.STA_NO1
   AND rfm.STA_NO2 = sgm.STA_NO2
   AND rfm.STA_NO3 = sgm.STA_NO3
   AND rfm.CODE_NO = sgm.CODE_NO
WHERE rfm.T4_UPDATE_CHECK = 4  -- ブザー鳴動（異常発生）レコードのみカウント
  AND rfm.EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ
  AND rfm.STA_NO1 = :site_code
  AND rfm.MK_DATE >= :start_date
GROUP BY SUBSTR(rfm.MK_DATE, 1, 8), sgm.TROUBLE_NG_INFO
ORDER BY 発生日
FETCH FIRST 500 ROWS ONLY
```

**トラブル時間の算出（HF1RFM01 × HF1REM01 クロステーブル計算）**

トラブル時間 = トラブル発生（ブザー鳴動）から、同じ設備で生産が再開される（品質結果が記録される）までの実影響時間。ON_TIME/REP_START_TIME/RESTART_TIME カラムは存在するが、実際のビジネスルールではクロステーブル計算を使用する。

```sql
SELECT
    rf.STA_NO2 AS ライン,
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
WHERE rf.T4_UPDATE_CHECK = 4  -- ブザー鳴動（異常発生）レコードのみ
  AND rf.EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ
  AND rf.STA_NO1 = :site_code
  AND rf.STA_NO2 = :line_code
  AND rf.MK_DATE BETWEEN :start_date AND :end_date
ORDER BY rf.MK_DATE DESC
FETCH FIRST 500 ROWS ONLY
```

**部品名称の解決（品質結果×部品マスター）**
```sql
SELECT
    rem.MK_DATE,
    rem.M_SERIAL,
    skm.MAIN_PARTS_NAME AS 部品名,
    rem.PARTSNAME,
    rem.OPEFIN_RESULT
FROM HF1REM01 rem
JOIN HF1SKM01 skm
    ON rem.STA_NO1 = skm.STA_NO1
   AND rem.STA_NO2 = skm.STA_NO2
   AND rem.STA_NO3 = skm.STA_NO3
WHERE rem.EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ
  AND rem.STA_NO2 = :line_code
  AND rem.MK_DATE >= :start_date
FETCH FIRST 500 ROWS ONLY
```

**工程別不良率の算出（HF1REM01）**
```sql
SELECT
    STA_NO2 AS ライン,
    STA_NO3 AS 工程,
    COUNT(*) AS 総数,
    SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) AS 不良数,
    ROUND(SUM(CASE WHEN OPEFIN_RESULT = 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS 不良率
FROM HF1REM01
WHERE EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ（マスタ定義・除外データを排除）
  AND STA_NO1 = :site_code
  AND STA_NO2 = :line_code
  AND MK_DATE BETWEEN :start_date AND :end_date
GROUP BY STA_NO2, STA_NO3
```

**不良内容別の集計（HF1REM01 × HF1SGM01）**

> **注意**: `NG_CODE` は不良品（OPEFIN_RESULT=2）でもNULLの場合がある。LEFT JOINを使用し、NG_CODEがNULLの不良品は「未分類」として集計に含める。

```sql
SELECT
    r.STA_NO3 AS 工程,
    NVL(s.TROUBLE_NG_INFO, '未分類') AS 不良内容,
    COUNT(*) AS 件数
FROM HF1REM01 r
LEFT JOIN HF1SGM01 s
    ON r.STA_NO1 = s.STA_NO1
   AND r.STA_NO2 = s.STA_NO2
   AND r.STA_NO3 = s.STA_NO3
   AND r.NG_CODE = s.CODE_NO
WHERE r.OPEFIN_RESULT = 2
  AND r.EXCEPT_FLAG IN (0, 1)  -- 集計対象データのみ
  AND r.STA_NO1 = :site_code
  AND r.STA_NO2 = :line_code
GROUP BY r.STA_NO3, NVL(s.TROUBLE_NG_INFO, '未分類')
ORDER BY 件数 DESC
```

### 10.5 SQL生成安全制約

- **SELECT専用**: DML（INSERT/UPDATE/DELETE）は一切禁止
- **タイムアウト**: クエリタイムアウトを設定（例: 30秒）
- **行数上限**: 1クエリあたりの取得行数に上限を設定（例: 500行）
- **テンプレート参照**: `oracle_query_templates`テーブルのSQL雛形をリファレンスとしてClaudeに提供（5テーブル分のテンプレートを含む）
- **グレースフルフォールバック**: Oracle接続エラー時はエラーを回答に明示しつつRAG結果のみで応答

---

## 11. UI要件

### 11.1 基本方針

- デザインシステム: `@serendie/ui` + `@serendie/symbols`アイコン
- アクセシビリティ: WCAG 2.2 Level AA準拠
- レスポンシブ対応: モバイル（320px+）からデスクトップ

### 11.2 チャットページ（メイン画面）

**レイアウト:**

```
チャットページレイアウト:
┌──────────┬──────────────────┬──────────────────┐
│ セッション │  チャットエリア    │  出力パネル       │
│ 履歴     │                  │ (テーブル/グラフ)  │
│ サイドバー │  会話表示         │                  │
│          │                  │ ・テーブル表示     │
│          │  入力欄           │   (ページネーション)│
│          │                  │   (CSVダウンロード) │
│          │                  │ ・グラフ表示       │
│          │                  │   (PNG/SVGダウンロード)│
└──────────┴──────────────────┴──────────────────┘
```

- 左サイドバー: お気に入りナレッジベース + セッション履歴一覧
  - お気に入りナレッジベース一覧（クリックで新規チャット開始）
  - セッション一覧（タイトル・日時・対象ナレッジベース）
  - 新規セッション開始ボタン
  - セッション削除機能
- メインエリア: チャット表示と入力
- 右パネル: 出力パネル（Oracle取得データの可視化）

**チャット入力エリア機能:**
- テキスト入力欄
- 音声入力ボタン（マイクアイコン、Web Speech API）
- シンプル/詳細モード切り替えトグル（入力欄近傍）
- 送信ボタン

**AI回答表示機能:**
- SSEストリーミングによるリアルタイム表示
- Markdown形式のレンダリング
- ソース参照リスト（クリック → プレビューモーダル）
- コピーボタン（Markdown形式、ソース付き）
- 5段階スター評価（☆☆☆☆☆、ホバーハイライト・クリック確定）
- インライン用語ハイライト（クリック → マスター候補ポップオーバー）

**ソースプレビューモーダル:**
- 変換済みMarkdownの該当セクション表示
- Markdownレンダリング表示と生テキスト表示の切り替え

#### 出力パネル（Output Panel）

- チャットエリアの右側に配置
- Oracle DBから取得したデータの表示専用エリア
- テーブル表示機能:
  - ページネーション対応（1ページあたり20行、変更可能）
  - ソート機能（カラムクリック）
  - CSVダウンロードボタン
  - Markdownテーブルとしてコピー可能
- グラフ表示機能:
  - AIがデータとユーザーの質問意図を判断し、最適なグラフ種別を自動選択
    - 推移データ → 折れ線グラフ (line)
    - 比較データ → 棒グラフ (bar)
    - 構成比 → 円グラフ (pie)
    - 累積・推移 → 面グラフ (area)
    - 分布 → ヒストグラム (histogram)
  - PNG/SVGでダウンロード可能
- 表示の制御:
  - 少量データ（1〜5行）: チャット内に自然言語で埋め込み、出力パネルにもテーブル表示
  - 中量データ（5〜30行）: 出力パネルにテーブル表示
  - 大量データ（30行以上）: 出力パネルにテーブル（ページネーション）+ CSVダウンロード
  - 数値推移系の質問: テーブル + グラフを出力パネルに表示
- レスポンシブ:
  - デスクトップ: 3カラム（サイドバー + チャット + 出力パネル）
  - モバイル: 出力パネルはボトムシートまたはタブ切替

### 11.3 アップロードページ

- ドラッグ&ドロップエリア（対応形式の表示）
- ファイル選択ボタン
- アップロード後の処理状況表示（変換中/完了/エラー）
- 変換済みMarkdownプレビュー
- AIタグ提案表示・編集フォーム
  - 各タグの確認チェック
  - タグの追加・削除・修正
- タグ確定ボタン（インデックス登録開始）
- 同一ドキュメント更新時のバージョン管理UI

### 11.4 ドキュメント管理ページ

- ドキュメント一覧テーブル
  - ファイル名・カテゴリ・アップロード日・バージョン・ステータス表示
  - タグ未確認（status: "tagged"）のファイルには「未確認」バッジを表示
  - インデックス構築中のドキュメントには「中止」ボタンを表示
  - "cancelled" 状態のドキュメントには「再試行」ボタンと「削除」ボタンを表示
  - "permanent_failed" 状態のドキュメントには「削除」ボタンのみ表示し、リトライ上限メッセージを案内
- タグフィルター（サイト・ライン・工程・カテゴリ別）
- タグ再編集機能（一覧から直接タグ変更）
- バージョン履歴一覧（旧バージョンの参照）
- 再インデックス実行ボタン（リトライ回数を表示、3回失敗時は無効化）
- ドキュメント削除機能（確認ダイアログ表示、ソフトデリート）
- **「ゴミ箱」タブ/フィルター:**
  - ソフトデリート済みドキュメントの一覧表示
  - 各ドキュメントに「復元」ボタンと「完全削除」ボタンを表示
  - 削除日時と残り保持期間（30日からのカウントダウン）を表示

### 11.5 設定ページ

- **ユーザー基本情報**: ニックネーム設定
- **検索設定**:
  - Rerank ON/OFFトグル
  - ハイブリッド検索 ON/OFFトグル
- **個人用語辞書**:
  - 辞書エントリ一覧（スラング → マスターキー）
  - 追加・編集・削除
- **プロファイル情報**:
  - 頻繁に参照するライン・カテゴリの表示
  - プロファイルリセットボタン

---

## 12. 非機能要件

### 12.1 パフォーマンス

| 指標 | 目標値 |
|-----|-------|
| 同時接続ユーザー数 | 10〜50名 |
| チャット応答開始（TTFToken） | 3秒以内 |
| ドキュメント変換処理 | バックグラウンド非同期（UI非ブロッキング） |
| ベクトル検索レイテンシ | 500ms以内 |

### 12.2 スケーラビリティ

- Docker Compose構成でコンテナごとにスケールアップ可能
- Qdrantはデータ量に応じてディスク容量を増設
- SQLiteは50ユーザー程度の規模に適している（大規模化時はPostgreSQLへの移行を検討）

### 12.3 セキュリティ

- 社内ネットワーク内でのみ稼働（外部インターネットからのアクセスなし）
- AWS Bedrockへのアクセスのみが外部通信
- Oracle DBは読み取り専用接続
- SQLインジェクション対策（パラメータ化クエリ必須）
- ファイルアップロードのファイル形式・サイズバリデーション
- 一括アップロード制限: 最大20ファイル（`MAX_BATCH_UPLOAD_FILES`）、合計200MB（`MAX_BATCH_UPLOAD_SIZE`）
- ユーザー識別はブラウザフィンガープリント（強固な認証不要、社内利用のみのため）

### 12.4 可用性・運用

- Docker Composeによるコンテナ化でデプロイ・再起動が容易
- ログはコンテナ標準出力に出力（docker logs で確認）
- SQLiteデータベースはホストボリュームにマウントしてデータ永続化
- Qdrantデータは`qdrant_data/`ディレクトリにホストマウント

### 12.5 ハルシネーション防止ポリシー

| 項目 | 方針 |
|-----|------|
| 一般知識の使用 | 一切禁止。LLMの学習データに基づく回答を行わない |
| 回答根拠 | 必ず検索されたドキュメントチャンクに基づく |
| 情報不在時 | 「選択されたナレッジベース内に該当する情報が見つかりませんでした。」と回答 |
| 関連度閾値 | 検索結果のスコアが閾値（環境変数で設定可能、デフォルト: 0.3）未満の場合、回答拒否または低信頼度を明示 |
| システムプロンプト | 「提供されたコンテキスト情報のみを使用して回答してください。あなた自身の学習知識や一般知識は一切使用しないでください。」を明示的に含める |
| ソース参照 | すべての回答に必ずソース参照を含め、出典のない主張を含めない |

### 12.6 テキスト正規化ポリシー

| 項目 | 方針 |
|-----|------|
| 正規化方式 | `unicodedata.normalize('NFKC', text)` を使用 |
| 適用対象 | カタカナ半角↔全角、英数字半角↔全角、記号の一部 |
| 適用タイミング | チャット検索クエリ、ベクトル検索前、Oracle WHERE句生成、タグ付けマスター照合、個人用語辞書登録 |
| 具体例 | `ｻｲｸﾙﾀｲﾑｵｰﾊﾞｰ` → `サイクルタイムオーバー`、`Ａ３ライン` → `A3ライン` |
| 保存時 | 個人用語辞書の`user_term`は正規化後の値で格納 |
| ベクトル化前 | Cohere Embedに渡すテキストはNFKC正規化済みであること |

### 12.7 データ保持方針

- すべてのデータは社内ネットワーク内に保持
- AWS Bedrockには：クエリテキスト・ドキュメントチャンクが送信される
- Oracle DBのデータはSQL結果のみをBedrockに渡す（生テーブルデータは外部送信しない）

---

## 13. データモデル

### 13.1 SQLiteテーブル定義

#### users テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | ユーザー識別子（localStorageのUUID） |
| `nickname` | TEXT | NULL可 | 任意のニックネーム |
| `rerank_enabled` | INTEGER | DEFAULT 0 | Rerank設定（0=OFF, 1=ON） |
| `hybrid_search_enabled` | INTEGER | DEFAULT 0 | ハイブリッド検索設定（0=OFF, 1=ON） |
| `response_mode` | TEXT | DEFAULT 'simple' | 回答モード（'simple' / 'detailed'） |
| `created_at` | TEXT | NOT NULL | 作成日時（ISO 8601） |
| `updated_at` | TEXT | NOT NULL | 更新日時（ISO 8601） |

#### user_terms テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | INTEGER | PK, AUTOINCREMENT | — |
| `user_id` | TEXT | FK → users.id | ユーザーID |
| `user_term` | TEXT | NOT NULL | ユーザーのスラング・略語 |
| `master_key` | TEXT | NOT NULL | マスターデータのキー（コード） |
| `master_type` | TEXT | NOT NULL | マスター種別（'site' / 'line' / 'process'） |
| `created_at` | TEXT | NOT NULL | 作成日時（ISO 8601） |

**UNIQUE制約:** `(user_id, user_term)`

#### user_behavior テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | INTEGER | PK, AUTOINCREMENT | — |
| `user_id` | TEXT | FK → users.id, UNIQUE | ユーザーID |
| `frequent_lines` | TEXT (JSON) | NULL可 | 頻繁参照ラインのランキングJSON |
| `frequent_categories` | TEXT (JSON) | NULL可 | 頻繁参照カテゴリのランキングJSON |
| `recent_context` | TEXT | NULL可 | 直近検索コンテキスト（テキスト要約） |

#### knowledge_bases テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | ナレッジベースID |
| `name` | TEXT | NOT NULL | ナレッジベース名 |
| `description` | TEXT | NULL可 | ナレッジベースの説明 |
| `color` | TEXT | DEFAULT '#6366f1' | テーマカラー（HEXコード） |
| `created_by` | TEXT | FK → users.id | 作成者ユーザーID |
| `created_at` | TEXT | NOT NULL | 作成日時（ISO 8601） |
| `updated_at` | TEXT | NOT NULL | 更新日時（ISO 8601） |

#### knowledge_base_favorites テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | INTEGER | PK, AUTOINCREMENT | — |
| `user_id` | TEXT | FK → users.id | ユーザーID |
| `knowledge_base_id` | TEXT | FK → knowledge_bases.id | ナレッジベースID |
| `created_at` | TEXT | NOT NULL | 作成日時（ISO 8601） |

**UNIQUE制約:** `(user_id, knowledge_base_id)`

#### sessions テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | セッションID |
| `user_id` | TEXT | FK → users.id | ユーザーID |
| `knowledge_base_id` | TEXT | FK → knowledge_bases.id, NOT NULL | 対象ナレッジベースID |
| `title` | TEXT | NULL可 | セッションタイトル（AI自動生成） |
| `created_at` | TEXT | NOT NULL | 作成日時 |
| `updated_at` | TEXT | NOT NULL | 最終更新日時 |

#### messages テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | メッセージID |
| `session_id` | TEXT | FK → sessions.id | セッションID |
| `role` | TEXT | NOT NULL | 送信者（'user' / 'assistant'） |
| `content` | TEXT | NOT NULL | メッセージ本文 |
| `sources` | TEXT (JSON) | NULL可 | ソース参照情報のJSON |
| `rating` | INTEGER | NULL可, 1〜5 | スター評価値 |
| `input_type` | TEXT | DEFAULT 'text' | 入力方式（'text' / 'voice'） |
| `response_mode` | TEXT | NULL可 | 回答モード（'simple' / 'detailed'） |
| `created_at` | TEXT | NOT NULL | 作成日時 |

#### documents テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | ドキュメントID |
| `knowledge_base_id` | TEXT | FK → knowledge_bases.id, NOT NULL | 所属ナレッジベースID |
| `filename` | TEXT | NOT NULL | 元ファイル名 |
| `file_type` | TEXT | NOT NULL | 拡張子（例: 'pdf', 'docx'） |
| `original_path` | TEXT | NOT NULL | 保存パス |
| `converted_md` | TEXT | NULL可 | 変換済みMarkdown本文 |
| `version` | INTEGER | DEFAULT 1 | バージョン番号 |
| `parent_document_id` | TEXT | FK → documents.id, NULL可 | 旧バージョンの親ドキュメントID |
| `status` | TEXT | NOT NULL | 処理状態（'processing' / 'converting' / 'converted' / 'tagging' / 'tagged' / 'confirmed' / 'chunking' / 'chunked' / 'indexing' / 'indexed' / 'convert_failed' / 'tag_failed' / 'index_failed' / 'permanent_failed' / 'cancelled'） |
| `retry_count` | INTEGER | DEFAULT 0 | エラーリトライ回数（3回で permanent_failed に遷移） |
| `deleted_at` | TEXT | NULL可 | ソフトデリート日時（ISO 8601）。設定されたドキュメントは一覧・検索から除外される |
| `uploaded_by` | TEXT | FK → users.id | アップロードユーザーID |
| `uploaded_at` | TEXT | NOT NULL | アップロード日時 |

#### document_tags テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | INTEGER | PK, AUTOINCREMENT | — |
| `document_id` | TEXT | FK → documents.id | ドキュメントID |
| `tag_key` | TEXT | NOT NULL | タグキー（'site', 'line', 'process' 等） |
| `tag_value` | TEXT | NOT NULL | タグ値 |
| `ai_suggested` | INTEGER | DEFAULT 1 | AIによる提案フラグ（0=手動, 1=AI提案） |
| `confirmed` | INTEGER | DEFAULT 0 | ユーザー確認フラグ（0=未確認, 1=確認済） |

#### chat_outputs テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | TEXT (UUID) | PK | 出力データID |
| `message_id` | TEXT | FK → messages.id | 紐づくメッセージID |
| `output_type` | TEXT | NOT NULL | 出力種別（'table' / 'chart' / 'both'） |
| `table_data` | TEXT (JSON) | NULL可 | テーブルデータ（columns定義 + rows） |
| `chart_config` | TEXT (JSON) | NULL可 | グラフ設定（type, x_axis, y_axis, series等） |
| `sql_executed` | TEXT | NULL可 | 実行されたSQL文 |
| `row_count` | INTEGER | NOT NULL DEFAULT 0 | 取得行数 |
| `created_at` | TEXT | NOT NULL | 作成日時（ISO 8601） |

#### oracle_query_templates テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `id` | INTEGER | PK, AUTOINCREMENT | — |
| `name` | TEXT | NOT NULL, UNIQUE | テンプレート名 |
| `description` | TEXT | NOT NULL | テンプレートの説明 |
| `sql_template` | TEXT | NOT NULL | SQLテンプレート（プレースホルダー付き） |
| `parameters` | TEXT (JSON) | NOT NULL | パラメータ定義JSON |

#### master_sites テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `code` | TEXT | PK | サイトコード |
| `name` | TEXT | NOT NULL | サイト正式名称 |
| `aliases` | TEXT (JSON) | NOT NULL | 別名・略称のJSON配列 |

#### master_lines テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `code` | TEXT | PK | ラインコード |
| `site_code` | TEXT | FK → master_sites.code | 所属サイトコード |
| `name` | TEXT | NOT NULL | ライン正式名称 |
| `aliases` | TEXT (JSON) | NOT NULL | 別名・略称のJSON配列 |

#### master_processes テーブル

| カラム | 型 | 制約 | 説明 |
|-------|---|-----|-----|
| `code` | TEXT | PK | 工程コード |
| `line_code` | TEXT | FK → master_lines.code | 所属ラインコード |
| `name` | TEXT | NOT NULL | 工程正式名称 |
| `tm_class` | TEXT | NULL可 | TMクラス分類 |
| `dt_class` | TEXT | NULL可 | DTクラス分類 |
| `station_no1` | TEXT | NULL可 | ステーション番号1 |
| `station_no2` | TEXT | NULL可 | ステーション番号2 |
| `station_no3` | TEXT | NULL可 | ステーション番号3 |

#### messages_fts 仮想テーブル（FTS5）

セッション横断キーワード検索のためのFTS5仮想テーブル。

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
  content,
  content='messages',
  content_rowid='rowid'
);
```

| 項目 | 説明 |
|-----|------|
| 対象カラム | `content`（メッセージ本文） |
| 元テーブル | `messages` |
| 同期方式 | メッセージ挿入時にトリガーで自動同期 |
| 検索構文 | SQLite FTS5標準のMATCH構文 |

**同期トリガー:**
```sql
CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
```

---

## 14. APIエンドポイント

### 14.1 チャット系

#### `POST /api/chat`

SSEストリーミングでAI回答を返す。

**リクエスト:**
```json
{
  "session_id": "uuid または null（新規セッション）",
  "knowledge_base_id": "uuid（検索対象ナレッジベース、必須）",
  "message": "3号機の先週の品質不良件数を教えて",
  "response_mode": "simple"
}
```

**レスポンス（SSEストリーム）:**
```
data: {"type": "token", "content": "先週"}
data: {"type": "token", "content": "の3号機"}
data: {"type": "sources", "sources": [{"doc_id": "uuid", "title": "品質報告書", "section": "2.3 不良分析"}]}
data: {"type": "terms", "terms": [{"word": "3号機", "candidates": [{"master_key": "LINE_A3", "name": "A3ライン"}]}]}
data: {"type": "output", "output": {"output_type": "both", "table_data": {"columns": [...], "rows": [...]}, "chart_config": {"type": "line", "x_axis": "MK_DATE", "y_axis": "MEASURE", "series": [...]}}}
data: {"type": "done", "message_id": "uuid", "session_id": "uuid"}
```

**SSEイベント一覧:**

| イベント | ペイロード | 説明 |
|---------|-----------|------|
| `session` | `{session_id, knowledge_base_id}` | セッションID確立 |
| `status` | `{stage}` | 処理ステップ表示 (`"query_analysis"` / `"vector_search"` / `"oracle_query"` / `"generating"` / `"structuring_output"`) |
| `token` | `{text}` | 回答テキスト逐次送信 |
| `sources` | `[{file, section, page, chunk_id}]` | ソース参照情報 |
| `terms` | `[{unknown_term, candidates}]` | 未知用語候補 |
| `output` | `{output_type, table_data, chart_config}` | 出力パネルデータ |
| `complete` | `{message_id, oracle_used}` | 回答完了 |
| `error` | `{code, message, recoverable}` | エラー通知 |
| `done` | `{}` | ストリーム終端 |

---

#### `GET /api/chat/output/{message_id}`

メッセージに紐づく出力データ（テーブル/グラフ）を取得する。

**レスポンス:**
```json
{
  "id": "uuid",
  "message_id": "uuid",
  "output_type": "both",
  "table_data": {
    "columns": [{"key": "MK_DATE", "label": "製造日"}, {"key": "MEASURE", "label": "計測値"}],
    "rows": [{"MK_DATE": "2026-03-01", "MEASURE": 12.5}]
  },
  "chart_config": {
    "type": "line",
    "x_axis": "MK_DATE",
    "y_axis": "MEASURE",
    "series": [{"name": "計測値", "data_key": "MEASURE"}]
  },
  "sql_executed": "SELECT MK_DATE, MEASURE FROM ...",
  "row_count": 30
}
```

---

#### `GET /api/chat/output/{message_id}/csv`

出力データをCSV形式でダウンロードする。

**レスポンス:** `text/csv`（`Content-Disposition: attachment; filename="output_{message_id}.csv"`）

---

#### `GET /api/sessions`

ユーザーのセッション一覧を取得する。

**クエリパラメータ:**
- `knowledge_base_id`: ナレッジベースIDでフィルタリング（任意）

**レスポンス:**
```json
[
  {
    "id": "uuid",
    "knowledge_base_id": "uuid",
    "title": "3号機の品質確認",
    "created_at": "2026-03-19T10:00:00",
    "updated_at": "2026-03-19T10:30:00"
  }
]
```

---

#### `GET /api/sessions/{session_id}/messages`

指定セッションのメッセージ一覧を取得する。

**レスポンス:**
```json
[
  {
    "id": "uuid",
    "role": "user",
    "content": "3号機の先週の品質不良件数を教えて",
    "input_type": "text",
    "created_at": "2026-03-19T10:00:00"
  },
  {
    "id": "uuid",
    "role": "assistant",
    "content": "先週の3号機の品質不良件数は...",
    "sources": [...],
    "rating": null,
    "response_mode": "simple",
    "created_at": "2026-03-19T10:00:05"
  }
]
```

---

#### `DELETE /api/sessions/{session_id}`

指定セッションを削除する。

**レスポンス:** `204 No Content`

---

#### `GET /api/sessions/search`

全セッションのメッセージ本文をキーワードで横断検索する。

**クエリパラメータ:**
- `q`: 検索キーワード（必須）

**レスポンス:**
```json
[
  {
    "session_id": "uuid",
    "title": "3号機の品質確認",
    "knowledge_base_id": "uuid",
    "matches": [
      {
        "message_id": "uuid",
        "role": "assistant",
        "snippet": "...サイクルタイムオーバーの原因は...",
        "created_at": "2026-03-19T10:00:05"
      }
    ]
  }
]
```

---

#### `PUT /api/messages/{message_id}/rating`

AI回答へのスター評価を更新する。

**リクエスト:**
```json
{ "rating": 4 }
```

**レスポンス:**
```json
{ "id": "uuid", "rating": 4 }
```

---

### 14.2 ドキュメント系

#### `POST /api/documents/upload`

ドキュメントをアップロードし、バックグラウンド変換処理を開始する。複数ファイルの一括アップロードに対応。

**リクエスト:** `multipart/form-data`
- `files`: ファイルデータ（複数可、最大20ファイル、合計200MB以下）
- `knowledge_base_id`: 所属ナレッジベースID（必須）
- `parent_document_id`: 旧バージョンのドキュメントID（任意、単一ファイル時のみ）

**レスポンス:**
```json
{
  "results": [
    {
      "id": "uuid",
      "filename": "品質報告書_2026Q1.pdf",
      "status": "converting",
      "version": 1
    },
    {
      "id": "uuid",
      "filename": "議事録_20260315.docx",
      "status": "converting",
      "version": 1
    }
  ],
  "total": 2,
  "accepted": 2,
  "rejected": 0
}
```

**エラー時（一部失敗）:**
```json
{
  "results": [
    {"id": "uuid", "filename": "report.pdf", "status": "converting", "version": 1},
    {"filename": "invalid.exe", "status": "rejected", "error": "unsupported_file_type"}
  ],
  "total": 2,
  "accepted": 1,
  "rejected": 1
}
```

**制約:**
- 最大ファイル数: `MAX_BATCH_UPLOAD_FILES`（デフォルト: 20）
- 合計サイズ上限: `MAX_BATCH_UPLOAD_SIZE`（デフォルト: 200MB）
- ZIPファイルは自動展開して個別処理
- バックエンドは最大3ファイル並行処理

---

#### `GET /api/documents`

ドキュメント一覧を取得する（タグフィルタリング対応）。

**クエリパラメータ:**
- `site`, `line`, `process`, `category`: タグフィルター
- `latest_only`: `true`の場合、最新バージョンのみ返す（デフォルト: `true`）

**レスポンス:**
```json
[
  {
    "id": "uuid",
    "filename": "品質報告書_2026Q1.pdf",
    "file_type": "pdf",
    "version": 2,
    "status": "indexed",
    "uploaded_at": "2026-03-19T09:00:00",
    "tags": [
      {"tag_key": "site", "tag_value": "名古屋工場", "confirmed": true}
    ]
  }
]
```

---

#### `GET /api/documents/{document_id}`

ドキュメント詳細を取得する。

---

#### `GET /api/documents/{document_id}/preview`

変換済みMarkdownを取得する。

**レスポンス:**
```json
{ "converted_md": "# 品質報告書\n\n## 概要\n..." }
```

---

#### `PATCH /api/documents/{document_id}/tags`

ドキュメントタグを更新する（確認・編集後の確定）。

**リクエスト:**
```json
{
  "tags": [
    {"tag_key": "site", "tag_value": "名古屋工場", "confirmed": true},
    {"tag_key": "category", "tag_value": "品質報告", "confirmed": true}
  ]
}
```

---

#### `PATCH /api/documents/batch-tags`

複数ドキュメントのタグを一括確定する。

**リクエスト:**
```json
{
  "documents": [
    {
      "document_id": "uuid1",
      "tags": [
        {"tag_key": "site", "tag_value": "名古屋工場", "confirmed": true},
        {"tag_key": "category", "tag_value": "品質報告", "confirmed": true}
      ]
    },
    {
      "document_id": "uuid2",
      "tags": [
        {"tag_key": "site", "tag_value": "大阪工場", "confirmed": true}
      ]
    }
  ]
}
```

**レスポンス:**
```json
{ "confirmed": ["uuid1", "uuid2"] }
```

---

#### `POST /api/documents/{document_id}/reindex`

ドキュメントを再インデックスする。失敗箇所から再試行する。`retry_count` をインクリメントし、3回以上の場合は `permanent_failed` に遷移して `409 Conflict` を返す。

**レスポンス:**
```json
{ "status": "indexing", "retry_count": 1 }
```

**エラー（リトライ上限到達時）:**
```json
{ "error": "retry_limit_exceeded", "message": "このファイル形式は対応できない可能性があります。別の形式で再アップロードしてください。", "retry_count": 3 }
```

---

#### `POST /api/documents/{document_id}/cancel`

インデックス構築中のドキュメントの処理を中止する。現在実行中のステージが完了したら停止し、statusを "cancelled" に変更する。

**レスポンス:**
```json
{ "id": "uuid", "status": "cancelled" }
```

---

#### `DELETE /api/documents/{document_id}`

ドキュメントをソフトデリートする（`deleted_at` に現在日時をセット）。一覧・検索から除外されるが、30日間はゴミ箱から復元可能。

**レスポンス:** `204 No Content`

---

#### `POST /api/documents/{document_id}/restore`

ゴミ箱からドキュメントを復元する（`deleted_at` をNULLにリセット）。

**レスポンス:**
```json
{ "id": "uuid", "status": "indexed", "deleted_at": null }
```

---

#### `DELETE /api/documents/{document_id}/permanent`

ドキュメントを物理削除する。Qdrantベクトル、SQLiteレコード、アップロードファイルをすべて完全削除する。管理用エンドポイント。

**レスポンス:** `204 No Content`

---

#### `GET /api/documents/{document_id}/versions`

バージョン履歴一覧を取得する。

**レスポンス:**
```json
[
  {"id": "uuid", "version": 1, "uploaded_at": "2026-01-15T09:00:00"},
  {"id": "uuid", "version": 2, "uploaded_at": "2026-03-19T09:00:00"}
]
```

---

### 14.3 ナレッジベース系

#### `POST /api/knowledge-bases`

ナレッジベースを新規作成する。

**リクエスト:**
```json
{
  "name": "品質管理マニュアル",
  "description": "品質管理に関するドキュメント群",
  "color": "#6366f1"
}
```

**レスポンス:**
```json
{
  "id": "uuid",
  "name": "品質管理マニュアル",
  "description": "品質管理に関するドキュメント群",
  "color": "#6366f1",
  "created_by": "uuid",
  "created_at": "2026-03-19T10:00:00",
  "updated_at": "2026-03-19T10:00:00"
}
```

---

#### `GET /api/knowledge-bases`

ユーザーが参照可能なナレッジベース一覧を取得する。

**レスポンス:**
```json
[
  {
    "id": "uuid",
    "name": "品質管理マニュアル",
    "description": "品質管理に関するドキュメント群",
    "color": "#6366f1",
    "document_count": 15,
    "is_favorite": true,
    "created_at": "2026-03-19T10:00:00",
    "updated_at": "2026-03-19T10:00:00"
  }
]
```

---

#### `GET /api/knowledge-bases/favorites`

お気に入り登録済みのナレッジベース一覧のみを取得する。

**レスポンス:** `GET /api/knowledge-bases`と同一形式（お気に入りのみフィルタリング）

---

#### `PUT /api/knowledge-bases/{id}`

ナレッジベースの名前・説明・カラーを更新する。

**リクエスト:**
```json
{
  "name": "品質管理マニュアル（更新版）",
  "description": "品質管理に関するドキュメント群（2026年版）",
  "color": "#8b5cf6"
}
```

**レスポンス:** 更新後のナレッジベースオブジェクト

---

#### `DELETE /api/knowledge-bases/{id}`

ナレッジベースを削除する。配下のドキュメント・ベクトルデータも連動削除される。

**レスポンス:** `204 No Content`

---

#### `POST /api/knowledge-bases/{id}/favorite`

ナレッジベースをお気に入りに登録する。

**レスポンス:**
```json
{ "knowledge_base_id": "uuid", "favorited": true }
```

---

#### `DELETE /api/knowledge-bases/{id}/favorite`

ナレッジベースのお気に入りを解除する。

**レスポンス:** `204 No Content`

---

### 14.4 ユーザー系

#### `GET /api/users/me`

現在のユーザー情報を取得する。

**レスポンス:**
```json
{
  "id": "uuid",
  "nickname": "山田",
  "rerank_enabled": false,
  "hybrid_search_enabled": false,
  "response_mode": "simple",
  "created_at": "2026-01-01T00:00:00"
}
```

---

#### `PUT /api/users/me/settings`

ユーザー設定を更新する。

**リクエスト:**
```json
{
  "nickname": "山田",
  "rerank_enabled": true,
  "hybrid_search_enabled": false,
  "response_mode": "detailed"
}
```

---

#### `GET /api/users/me/terms`

個人用語辞書の一覧を取得する。

**レスポンス:**
```json
[
  {"id": 1, "user_term": "3号機", "master_key": "LINE_A3", "master_type": "line"},
  {"id": 2, "user_term": "品質部", "master_key": "DEPT_QA", "master_type": "process"}
]
```

---

#### `POST /api/users/me/terms`

個人用語辞書にエントリを追加する。

**リクエスト:**
```json
{
  "user_term": "3号機",
  "master_key": "LINE_A3",
  "master_type": "line"
}
```

---

#### `DELETE /api/users/me/terms/{term_id}`

個人用語辞書のエントリを削除する。

**レスポンス:** `204 No Content`

---

#### `GET /api/users/me/behavior`

ユーザー行動プロファイルを取得する。

**レスポンス:**
```json
{
  "frequent_lines": [
    {"code": "LINE_A3", "name": "A3ライン", "count": 42},
    {"code": "LINE_B1", "name": "B1ライン", "count": 28}
  ],
  "frequent_categories": [
    {"category": "保守マニュアル", "count": 35},
    {"category": "議事録", "count": 20}
  ],
  "recent_context": "A3ラインの溶接工程における品質不良調査"
}
```

---

### 14.5 マスターデータ系

#### `GET /api/master/sites`

サイト一覧を取得する。

#### `GET /api/master/lines`

ライン一覧を取得する（`?site_code=XXX`でフィルタリング可）。

#### `GET /api/master/processes`

工程一覧を取得する（`?line_code=XXX`でフィルタリング可）。

#### `GET /api/master/search`

マスターデータをファジー検索する（個人用語辞書登録時の候補取得用）。

**クエリパラメータ:**
- `q`: 検索クエリ（スラング・略語）
- `type`: 検索対象（`site` / `line` / `process` / 全て）

**レスポンス:**
```json
[
  {"code": "LINE_A3", "name": "A3ライン", "type": "line", "score": 0.95},
  {"code": "LINE_A31", "name": "A31ライン", "type": "line", "score": 0.82}
]
```

---

## 15. ディレクトリ構成

```
rag-phantom/
├── docker-compose.yml                    # 全サービス定義
├── .env.example                          # 環境変数テンプレート
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── app/                          # App.tsx, router.tsx, providers.tsx
│       ├── pages/                        # ChatPage（KB選択+チャット）, UploadPage, DocumentsPage, SettingsPage, KnowledgeBasesPage
│       ├── components/
│       │   ├── layout/                   # AppShell, Sidebar, Header, SessionSearchBox
│       │   ├── chat/                     # MessageList, MessageBubble, ChatInput, SourceList, StarRating, TermSuggestions, ResponseModeToggle
│       │   ├── output/                   # OutputPanel, DataTable, ChartView, DownloadButtons
│       │   ├── upload/                   # DropZone, ConversionPreview, TagEditor, BatchTagEditor, VersionConflictDialog
│       │   ├── documents/                # DocumentTable, TagFilter, VersionHistory, MarkdownPreview
│       │   ├── knowledge-base/            # KnowledgeBaseList, KnowledgeBaseCard, CreateKBDialog
│       │   ├── settings/                 # SettingsForm, TermDictionary, ProfileInfo
│       │   └── shared/                   # CopyButton, VoiceButton, SourcePreviewModal
│       ├── hooks/                        # useChat, useVoiceInput, useStarRating, useSessions, useSessionSearch, useDocuments, useUser, useKnowledgeBases, useOutput
│       ├── api/                          # client.ts, chat.ts, sessions.ts, documents.ts, users.ts, master.ts, sse.ts, knowledge-bases.ts, output.ts
│       ├── stores/
│       │   ├── chatStore.ts              # Zustandチャット状態
│       │   ├── userStore.ts              # Zustandユーザー状態
│       │   ├── kbStore.ts               # Zustandナレッジベース状態
│       │   ├── uiStore.ts               # Zustand UI状態
│       │   └── outputStore.ts              # 出力パネル状態 (Zustand)
│       ├── types/
│       │   ├── message.ts                # メッセージ関連型定義
│       │   ├── document.ts               # ドキュメント関連型定義
│       │   ├── user.ts                   # ユーザー関連型定義
│       │   ├── session.ts                # セッション関連型定義
│       │   ├── knowledge-base.ts        # ナレッジベース関連型定義
│       │   ├── master.ts                 # マスターデータ関連型定義
│       │   ├── tag.ts                    # タグ関連型定義
│       │   └── output.ts                # OutputData, TableData, ChartConfig 型
│       └── utils/                        # fingerprint.ts, markdown.ts, date.ts
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py                       # FastAPIアプリケーションエントリポイント
│       ├── routers/
│       │   ├── chat.py                   # チャット・セッションルーター
│       │   ├── documents.py              # ドキュメントルーター
│       │   ├── users.py                  # ユーザー・設定ルーター
│       │   ├── knowledge_bases.py        # ナレッジベースルーター
│       │   └── master.py                 # マスターデータルーター
│       ├── services/
│       │   ├── rag.py                    # RAGオーケストレーション
│       │   ├── chunker.py                # チャンキング戦略
│       │   ├── converter.py              # ファイル形式変換
│       │   ├── tagger.py                 # AIタグ付け
│       │   ├── normalizer.py             # テキスト正規化（NFKC）
│       │   ├── oracle_query.py           # Oracle SQL生成・実行
│       │   ├── user_profile.py           # ユーザープロファイル学習
│       │   └── embedder.py               # Cohere Embed（Bedrock経由）
│       ├── models/
│       │   ├── user.py                   # SQLAlchemyモデル（users, user_terms, user_behavior）
│       │   ├── session.py                # SQLAlchemyモデル（sessions, messages）
│       │   ├── document.py               # SQLAlchemyモデル（documents, document_tags）
│       │   ├── knowledge_base.py         # SQLAlchemyモデル（knowledge_bases, knowledge_base_favorites）
│       │   └── master.py                 # SQLAlchemyモデル（master_sites, master_lines, master_processes）
│       └── infrastructure/
│           ├── config.py                 # 設定・環境変数管理
│           ├── db.py                     # SQLAlchemyセットアップ
│           ├── bedrock_client.py         # AWS Bedrockクライアント
│           ├── qdrant_client.py          # Qdrantクライアント
│           └── master_cache.py           # マスターデータキャッシュ
│
└── data/
    ├── master.json                       # マスターデータ（初期投入用）
    ├── oracle_templates.json             # Oracle SQLテンプレート（初期投入用）
    ├── ragphantom.db                        # SQLiteデータベース（ボリュームマウント）
    └── uploads/                          # アップロードファイル保管（ボリュームマウント）

qdrant_data/                              # Qdrantデータ（ボリュームマウント）
```

---

## 16. テスト要件

### 16.1 RAGASによるRAG品質評価

RAGASフレームワークを使用してRAGパイプラインの品質を定量評価する。

#### 評価メトリクス

| メトリクス | 説明 | 合格基準 |
|-----------|-----|---------|
| Faithfulness（忠実度） | 回答が検索されたコンテキストに基づいているか | ≥ 0.8 |
| Answer Relevancy（回答関連性） | 回答がユーザーの質問に対して関連性があるか | ≥ 0.75 |
| Context Precision（コンテキスト精度） | 検索されたコンテキストが質問に対して精度高いか | ≥ 0.7 |
| Context Recall（コンテキスト再現率） | 必要なコンテキストが検索で取得できているか | ≥ 0.7 |

#### テストデータセット

- 工場ドメイン固有のQ&Aペアを作成（最低50件）
- 質問カテゴリ: 保全手順、品質トラブル、設備仕様、生産データ参照
- 各質問に期待される回答（ground truth）とソースドキュメントを紐づけ
- マスターデータのゆらぎを含む質問（俗称、別名）を含める

#### 定期実行

- チャンキング戦略やプロンプト変更時に自動実行
- 評価結果をログに保存し、品質の推移を追跡

---

### 16.2 PlaywrightによるE2Eテスト

Playwright を使用してフロントエンドのE2Eテストを実施する。

#### チャット機能

- テキスト入力で質問 → AI回答表示 → ソース参照クリック → プレビューモーダル表示
- 回答のコピーボタン → クリップボードにMarkdown形式でコピー
- ★5評価（ホバーで色変化、クリックで確定、APIに送信）
- セッション履歴: 新規セッション作成、過去セッション選択・復元
- シンプル/詳細モード切替 → 回答の長さが変化
- インライン用語確認: 候補チップ表示、選択、「この用語を覚える」登録

#### 出力パネル

- Oracleデータ取得時にテーブル表示
- テーブルのページネーション（ページ切替、表示行数変更）
- CSVダウンロード
- グラフ表示（種別自動選択）
- グラフのPNG/SVGダウンロード

#### アップロード機能

- ファイルドラッグ&ドロップ
- 各拡張子のアップロード（md, pdf, pptx, xlsx, docx等）
- 変換プレビュー表示
- AIタグ提案 → ユーザー確認・修正 → 確定
- バージョン管理（同一ファイル名アップロード時のダイアログ）

#### ドキュメント管理

- ドキュメント一覧表示
- タグフィルタリング
- タグ再編集
- バージョン履歴表示

#### 設定

- リランクON/OFF切替 → 設定永続化確認
- ハイブリッド検索ON/OFF切替
- 個人辞書の追加・削除

#### レスポンシブ

- デスクトップ表示（3カラム）
- モバイル表示（サイドバーオーバーレイ、出力パネルボトムシート）

#### アクセシビリティ

- キーボードナビゲーション（Tab, Enter, Escape, 矢印キー）
- スクリーンリーダー対応（ARIA属性検証）
- フォーカストラップ（モーダル）

#### エラーハンドリング

- Oracle接続失敗時のフォールバック表示
- アップロード失敗時のエラー表示とリトライ
- ネットワークエラー時の表示

---

### 16.3 バックエンドユニットテスト（pytest）

| テスト対象 | テスト内容 |
|-----------|----------|
| `converter.py` | 各ファイル形式の変換テスト |
| `tagger.py` | タグ付与の精度テスト（マスターデータ照合） |
| `chunker.py` | 各チャンキング戦略のテスト（構造的、エージェンティック、議事録、テーブル、Parent-Child） |
| `oracle_query.py` | SQL生成のバリデーション（SELECT以外をブロック）、タイムアウト、行数制限 |
| `user_profile.py` | 用語変換（最長一致）、未知用語検出 |
| `rag.py` | クエリ解析、検索フロー統合テスト |
| `embedder.py` | ベクトル化とQdrant格納テスト |

---

### 16.4 テスト技術スタック

| ツール | 用途 |
|-------|-----|
| RAGAS | RAG品質評価フレームワーク |
| Playwright | E2Eテスト |
| pytest | バックエンドユニットテスト |
| pytest-asyncio | 非同期テスト対応 |

---

## 付録: 主要な技術的決定事項

### A. ユーザー識別方式の選択理由

アカウント登録・ログイン機能を設けず、ブラウザフィンガープリント + localStorage UUIDを採用した理由:
- 社内利用限定のため強固な認証は不要
- ユーザーの利用摩擦を最小化
- ユーザーごとの設定・辞書・履歴は維持できる

### B. SQLite採用の根拠と限界

- 50ユーザー以下の同時利用であれば十分なパフォーマンス
- オンプレミスでの運用が容易（サーバープロセス不要）
- 大規模化（100ユーザー以上、高頻度書き込み）の場合はPostgreSQLへの移行を推奨

### C. Parent-Childチャンキングの設計意図

- 検索精度: 細粒度チャンク（child）でANN検索 → 高い再現率
- 文脈品質: 親チャンク（parent）をLLMに渡す → 文脈が切れない高品質な回答
- Qdrantペイロードの`parent_chunk_id`フィールドで管理

### D. Oracle接続のグレースフルフォールバック

生産環境でOracle DBが利用不可能な状況（メンテナンス・障害）でも、RAGドキュメント検索は継続して提供できるよう設計。Oracle不可の場合は回答に明示的に「生産データへのアクセスができませんでした」と付記する。
