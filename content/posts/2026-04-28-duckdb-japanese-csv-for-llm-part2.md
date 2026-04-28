---
title: "DuckDBで業務CSVをLLMに問い合わせ可能にする（第2回：Text-to-SQL + エージェント統合編）— query_csv_dataツールの設計"
emoji: "🗃️"
type: "tech"
topics: ["DuckDB", "LLM", "Text-to-SQL", "Python", "AI Agent"]
published: true
category: "Architecture"
date: "2026-04-28"
description: "DuckDBをLLMエージェントのツールとして統合し、describe→queryの2段階フローで自然言語からSQLを生成・実行する仕組みとセキュリティ対策を解説"
series: "DuckDBで業務CSVをLLMに問い合わせ可能にする"
seriesOrder: 2
---

> **このシリーズ: 全2回**
> 1. [第1回: エンコーディングとデータ準備編](/posts/duckdb-japanese-csv-for-llm-part1)
> 2. [第2回: Text-to-SQL + エージェント統合編](/posts/duckdb-japanese-csv-for-llm-part2) ← 今ここ

## はじめに

第1回では、日本語を含むCSVファイルのエンコーディング問題をDuckDBで解決する方法を紹介しました。今回は、そのデータをLLMエージェントから自然言語で問い合わせ可能にする仕組みを深掘りします。

特に以下のポイントを実装します：

- **Text-to-SQL**: 自然言語質問からSQLを自動生成
- **2段階フロー**: describe → query で確実性を向上
- **セッション管理**: 接続リソースの効率的な再利用
- **セキュリティ**: SQL インジェクション防止とデータ保護

この設計は、RAG Phantom などのエージェントシステムで実際に運用されているパターンです。

---

## 1. query_csv_data ツールの定義

LLM エージェントのツール定義は、以下のような構造で行います：

```python
_AGENTIC_QUERY_CSV_DATA_TOOL = {
    "name": "query_csv_data",
    "description": "データ型フォルダソース内のCSV/TSVに対してSQLクエリを実行。mode='describe'でテーブル一覧、mode='query'でSQL実行",
    "input_schema": {
        "type": "object",
        "properties": {
            "source_id": {
                "type": "string",
                "description": "データソースID（list_documentsで返されるID）"
            },
            "mode": {
                "type": "string",
                "enum": ["describe", "query"],
                "description": "describe: テーブル情報確認、query: SQL実行"
            },
            "sql_query": {
                "type": "string",
                "description": "SELECT/WITHのみ許可。INSERT/UPDATE/DELETEは禁止"
            }
        },
        "required": ["source_id", "mode", "sql_query"]
    }
}
```

ポイント：
- **mode の分離**: describe と query を明確に分ける
- **制限の明示**: スキーマから SELECT/WITH のみという制約を伝える
- **source_id**: list_documents で返されるID を直接指定

---

## 2. 2段階フロー：Describe → Query

自然言語から SQL を生成する際、LLM が「存在しないカラム名」でクエリを作成する問題が起こります。これを回避するため、**2段階フロー** を採用します：

### ステップ1：Describe（テーブル情報確認）

```python
# ユーザーの質問：「売上データで、月別の合計売上を教えて」
# LLM は まず以下を実行：
{
    "source_id": "datasource:sales_data",
    "mode": "describe",
    "sql_query": "SELECT * FROM information_schema.tables LIMIT 10"
}
```

レスポンス例：

```
テーブル一覧:
- data (Parquetモード: 全CSVを統合)

カラム情報:
- 日付 (DATE)
- 製品 (VARCHAR)
- 売上金額 (DECIMAL)
- 数量 (INTEGER)
- 営業所 (VARCHAR)

サンプルデータ:
| 日付       | 製品   | 売上金額 | 数量 | 営業所 |
|----------|--------|---------|------|--------|
| 2026-01-15 | 製品A | 150000  | 10   | 東京   |
| 2026-01-16 | 製品B | 200000  | 15   | 大阪   |
```

### ステップ2：Query（SQL実行）

スキーマを把握した LLM は、正確な SQL を生成します：

```python
{
    "source_id": "datasource:sales_data",
    "mode": "query",
    "sql_query": "SELECT DATE_TRUNC('month', 日付) as 月, SUM(売上金額) as 合計売上 FROM data GROUP BY 1 ORDER BY 1 DESC LIMIT 100"
}
```

**なぜ有効か：**
- LLM は実際のカラム名・型を知った状態で SQL を作成
- ハルシネーション（存在しないカラム名）を防げる
- エラーリトライが必要なケースを大幅に削減

---

## 3. CsvDataSession：セッション管理とリソース再利用

DuckDB への接続はコストが高いため、**セッション単位での再利用** が重要です：

```python
class CsvDataSession:
    """CSV/TSVデータソースへの接続をセッション内で管理"""

    def __init__(self, container_path: str, source_id: str):
        self.source_id = source_id
        self.container_path = container_path
        self.conn = None
        self._init_connection()

    def _init_connection(self):
        """DuckDB接続を初期化"""
        import duckdb
        self.conn = duckdb.connect(':memory:')

        # Parquetモード試行（全CSVを統合）
        try:
            parquet_path = os.path.join(self.container_path, "*.parquet")
            self.conn.sql(f"CREATE TABLE data AS SELECT * FROM read_parquet('{parquet_path}')")
        except Exception:
            # フォールバック：個別CSV を VIEW として登録
            self._register_csv_views()

    def _register_csv_views(self):
        """CSVファイルを個別のVIEWとして登録"""
        for csv_file in os.listdir(self.container_path):
            if csv_file.endswith(('.csv', '.tsv')):
                view_name = os.path.splitext(csv_file)[0]
                file_path = os.path.join(self.container_path, csv_file)

                # UTF-8変換（CP932/Shift-JIS対応）
                df = self._read_csv_with_encoding(file_path)
                self.conn.register(view_name, df)

    def _read_csv_with_encoding(self, file_path: str):
        """複数エンコーディング対応でCSVを読み込み"""
        import pandas as pd
        for encoding in ['utf-8', 'cp932', 'shift-jis']:
            try:
                return pd.read_csv(file_path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"CSV読み込み失敗: {file_path}")

    def describe(self):
        """テーブル・カラム情報を取得"""
        tables = self.conn.sql("SELECT table_name FROM information_schema.tables").fetchall()
        info = []
        for table_name, in tables:
            columns = self.conn.sql(f"DESCRIBE {table_name}").fetchall()
            info.append(f"テーブル: {table_name}\n" +
                       "\n".join(f"  - {col[0]} ({col[1]})" for col in columns))

        # サンプルデータ
        sample = self.conn.sql("SELECT * FROM data LIMIT 5").fetch_arrow_table()
        info.append(f"\nサンプルデータ:\n{sample.to_pandas().to_markdown()}")
        return "\n".join(info)

    def query(self, sql: str, max_rows: int = 100, max_chars: int = 50000):
        """SQLを実行して結果をマークダウンテーブルで返す"""
        result = self.conn.sql(sql).fetch_arrow_table()
        df = result.to_pandas()

        # 行数制限
        if len(df) > max_rows:
            df = df.head(max_rows)
            warning = f"（表示: 最初の {max_rows} 行 / 全 {len(df)} 行）\n"
        else:
            warning = ""

        # 文字数制限
        markdown = df.to_markdown(index=False)
        if len(markdown) > max_chars:
            markdown = markdown[:max_chars] + "\n... (省略)"

        return warning + markdown

    def close(self):
        """接続を閉じる"""
        if self.conn:
            self.conn.close()
```

### グローバルセッション管理

ツール呼び出し時にセッションを再利用：

```python
# グローバル辞書：セッション保持
csv_sessions: dict[str, CsvDataSession] = {}

async def handle_query_csv_data(source_id: str, mode: str, sql_query: str):
    """query_csv_data ツールのハンドラ"""

    # source_id の正規化（LLMが "datasource:xxx" と返すことがある）
    clean_id = source_id.removeprefix("datasource:")

    # コンテナパスを取得
    container_path = get_datasource_container_path(clean_id)
    if not container_path:
        return f"エラー: データソースが見つかりません: {source_id}"

    try:
        # セッションを取得または作成
        if clean_id not in csv_sessions:
            csv_sessions[clean_id] = CsvDataSession(container_path, clean_id)

        session = csv_sessions[clean_id]

        # SQL 検証
        validation_error = validate_sql(sql_query)
        if validation_error:
            return f"エラー: {validation_error}"

        # Describe / Query 実行
        if mode == "describe":
            return session.describe()
        elif mode == "query":
            return session.query(sql_query)
        else:
            return f"エラー: 不明なmode: {mode}"

    except Exception as e:
        return f"エラー: {str(e)}"

    finally:
        # セッションはここでは閉じない（再利用のため）
        pass
```

---

## 4. セキュリティ：SQL インジェクション防止

### 4.1 SQL 検証ロジック

```python
import re

# 禁止キーワード
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|PRAGMA|ATTACH|DETACH)\b",
    re.IGNORECASE
)

# 許可される開始文
_ALLOWED_STARTERS = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

def validate_sql(sql: str) -> str | None:
    """SQLの安全性を検証。エラーメッセージがあれば返す"""

    # 空の確認
    if not sql or not sql.strip():
        return "SQLが空です"

    stripped = sql.strip()

    # 開始文を確認
    if not _ALLOWED_STARTERS.match(stripped):
        return "SELECT または WITH で始まるクエリのみ許可しています"

    # 禁止キーワード確認
    if _FORBIDDEN_KEYWORDS.search(stripped):
        return "INSERT/UPDATE/DELETE/DROP 等のキーワードは禁止しています"

    # コメント削除（--）での绕过防止
    if "--" in sql or "/*" in sql:
        return "コメント構文は禁止しています"

    return None  # 安全
```

### 4.2 インメモリ DuckDB の利点

```python
# セッション初期化で :memory: を使用
self.conn = duckdb.connect(':memory:')
```

**セキュリティ効果：**
- **データ永続化なし**: メモリ内のみなので、ファイル盗難のリスク ゼロ
- **セッション分離**: ユーザーごと・セッションごとに独立した DuckDB インスタンス
- **エスケープ不要**: SQL インジェクションの余地が極めて小さい

---

## 5. LLM システムプロンプト統合

エージェントのシステムプロンプトには、CSV データソース使用方法を明記します：

```markdown
## データソースの利用方法

list_documents で「[データ: CSVテーブル] 売上データ (xx件)」のような形式で表示される項目は、
SQL で問い合わせ可能なCSV/TSVデータソースです。

### 手順

1. **まずは describe**: ユーザーの質問に対して、データソースのテーブル構造を確認
   ```json
   {
     "source_id": "datasource:sales_data",
     "mode": "describe",
     "sql_query": "SELECT * FROM information_schema.tables"
   }
   ```

2. **テーブル構造を理解**: カラム名、データ型、サンプルデータを確認

3. **SQL を生成・実行**: describe の結果をもとに、正確な SQL を生成
   ```json
   {
     "source_id": "datasource:sales_data",
     "mode": "query",
     "sql_query": "SELECT DATE_TRUNC('month', 日付) as 月, SUM(売上金額) FROM data GROUP BY 1"
   }
   ```

### 重要な制約

- **SELECT / WITH のみ**: INSERT/UPDATE/DELETE は実行不可
- **LIMIT を付ける**: 大規模結果を避けるため、必ず `LIMIT 100` 等を指定
- **source_id**: list_documents で返された ID をそのまま使用（"datasource:" プレフィックス付き）

### 例：売上データの分析

ユーザー質問: 「先月の営業所別売上トップ3は？」

```
1. describe で sales_data のカラムを確認
   → 日付, 営業所, 売上金額 があることを確認

2. query で SQL を実行
   SELECT 営業所, SUM(売上金額) as 合計
   FROM data
   WHERE YEAR(日付) = 2026 AND MONTH(日付) = 3
   GROUP BY 営業所
   ORDER BY 合計 DESC
   LIMIT 3
```

結果をユーザーに自然言語で説明してください。
```

---

## 6. 実装上の注意点

### 6.1 source_id の正規化

LLM が返す source_id に `datasource:` プレフィックスが付くことがあります：

```python
clean_id = source_id.removeprefix("datasource:")
```

### 6.2 エンコーディング対応（第1回の応用）

```python
def _read_csv_with_encoding(self, file_path: str):
    """日本語CSVを複数エンコーディング試行で読み込み"""
    import pandas as pd
    for encoding in ['utf-8', 'cp932', 'shift-jis', 'iso-2022-jp']:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(f"サポートされていないエンコーディング: {file_path}")
```

### 6.3 セッションクリーンアップ

セッション終了時（ユーザーが会話を終了したとき）にメモリを解放：

```python
def cleanup_csv_sessions(user_id: str):
    """ユーザーのセッションをすべてクリア"""
    for session in csv_sessions.values():
        session.close()
    csv_sessions.clear()
```

---

## 7. パフォーマンス最適化

### 7.1 Parquet 統合モード

複数の CSV がある場合、事前に Parquet に変換して統合することで、クエリが高速化します：

```python
# CSV → Parquet 変換（一度だけ）
import duckdb
duckdb.sql("""
    COPY (
        SELECT * FROM read_csv('data/*.csv')
    ) TO 'data.parquet'
""")

# 以後、セッションで使用
self.conn.sql("CREATE TABLE data AS SELECT * FROM read_parquet('data.parquet')")
```

### 7.2 大規模データ対応

1 千万行を超えるデータの場合は、インメモリ限度に達するため、以下を検討：

- **パーティション**: month/year で分割したファイル
- **キャッシング**: 月別・営業所別の集計を事前計算
- **プーリング**: 複数 LLM リクエストで同じセッションを再利用

---

## 8. トラブルシューティング

### Q. LLM が「カラムが見つかりません」というエラーを返す

**A.** describe モードを実行して、実際のカラム名を確認してください。よくある原因：
- 全角スペースが含まれている
- 前後にダブルクオーテーション `"` が必要
- 日本語カラム名で正確な漢字/カナが異なる

### Q. SQL クエリが遅い

**A.** 以下を確認：
- `LIMIT` が付いているか → 大規模結果を避ける
- Parquet 統合モードか → CSV 個別読み込みは遅い
- インデックスが必要か → DuckDB では `CREATE INDEX` で対応可能

### Q. セッションがメモリを消費し続ける

**A.** セッションクリーンアップが実行されているか確認：
```python
# セッション終了時に必ず実行
finally:
    cleanup_csv_sessions(user_id)
```

---

## まとめ

DuckDB と LLM エージェントの統合により、以下が実現できます：

| 要件 | 実装方法 |
|-----|---------|
| **自然言語でデータ問い合わせ** | Text-to-SQL (describe → query フロー) |
| **日本語CSV対応** | UTF-8 変換 +複数エンコーディング試行 |
| **セキュリティ** | SQL 検証 + インメモリ DuckDB |
| **パフォーマンス** | セッション再利用 + Parquet 統合 |
| **運用性** | エラーハンドリング + ログ記録 |

これで「DuckDB で業務 CSV を LLM に問い合わせ可能にする」シリーズは完結です。第1回のエンコーディング対応と合わせて、日本の業務データを LLM で活用する実践的なパターンをカバーしました。

ぜひプロジェクトに組み込んでみてください。質問や改善案があれば、コメント欄までお願いします！
