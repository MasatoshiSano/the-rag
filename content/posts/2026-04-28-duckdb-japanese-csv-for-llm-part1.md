---
title: "DuckDBで業務CSVをLLMに問い合わせ可能にする（第1回：エンコーディングとデータ準備編）— Shift-JIS対応とParquetキャッシュ"
emoji: "🦆"
type: "tech"
topics: ["DuckDB", "Python", "CSV", "Parquet", "Data"]
published: true
category: "HowTo"
date: "2026-04-28"
description: "日本の業務CSVでよくあるShift-JIS/CP932エンコーディングをDuckDBで扱う方法と、Parquetキャッシュによるパフォーマンス最適化を解説"
series: "DuckDBで業務CSVをLLMに問い合わせ可能にする"
seriesOrder: 1
---

> **このシリーズ: 全2回**
> 1. [第1回: エンコーディングとデータ準備編](/posts/2026-04-28-duckdb-japanese-csv-for-llm-part1) ← 今ここ
> 2. [第2回: Text-to-SQL + エージェント統合編](/posts/duckdb-japanese-csv-for-llm-part2)

## はじめに

こんにちは。RAG Phantomプロジェクトで、日本の工場ロギングシステムから出力されるShift-JIS/CP932エンコーディングのCSVをDuckDBで扱う必要が出てきました。

**やりたかったこと**は単純です：
- 工場のPLCロギングCSV（Shift-JIS/CP932、先頭にセクションマーカー行あり）をDuckDBで読み込む
- LLMから自然言語でSQL問い合わせできるようにする
- パフォーマンスを最適化する

しかし、DuckDBのデフォルト動作ではこれが実現できません。本記事では、このチャレンジをどのように解決したかを、実装レベルの詳細とともにお伝えします。

---

## 課題: DuckDBのエンコーディング制限

### 最初のアプローチ（失敗）

DuckDBのドキュメントを読むと、`read_csv`で直接CSVを読み込めます。素朴に試してみました：

```python
import duckdb

# これは失敗する
con = duckdb.connect()
result = con.execute("SELECT * FROM read_csv('factory_log.csv', encoding='cp932')").fetchall()
```

結果：

```
DuckDBException: Unsupported encoding 'cp932'
```

### 何が起きたか

DuckDBは、CSV読み込みのネイティブサポートで以下の3つのエンコーディングのみをサポートしています：

- UTF-8
- UTF-16
- Latin-1

日本の業務システムから出力されるCSVの大多数は**Shift-JIS（CP932）**です。工場のPLCロギング、ERP、在庫管理システムなど、レガシーシステムの産出物ばかり。つまり、**DuckDBはこの現実と対面している**のです。

### なぜこんなことに？

DuckDBは、SQL実行エンジンとして徹底的にパフォーマンスを優先する設計になっています。エンコーディング変換は重い処理なため、ネイティブサポートは限定的です。つまり、この制限は**設計の意思決定の結果**なのです。

---

## 解決策: 3レイヤーアプローチ

DuckDBの制限を迂回するため、以下の3つのレイヤーを構築しました：

### レイヤー1: エンコーディング自動検出

```python
from typing import Optional

_ENCODINGS = ["utf-8", "cp932", "shift_jis", "euc_jp"]

def _detect_encoding(file_path: str) -> str:
    """
    CSVファイルのエンコーディングを自動検出

    試行順序：UTF-8 → CP932 → Shift-JIS → EUC-JP
    """
    for encoding in _ENCODINGS:
        try:
            with open(file_path, encoding=encoding) as f:
                # 最初の4KBを読んで検証
                f.read(4096)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    # 全て失敗時はUTF-8をデフォルトに
    return "utf-8"
```

**ポイント：**
- 試行順序が重要。UTF-8を最初に試すことで、既に正しくエンコーディングされたファイルを高速に判定
- CP932を次に試す理由：日本のWindows環境からのファイル出力で最も多いパターン
- 4KBチャンク読み込みは、ファイル全体を読まずに判定できる最小単位

### レイヤー2: UTF-8一時ファイルへの変換

DuckDBがサポートするエンコーディングにファイルを変換します：

```python
import tempfile
from pathlib import Path

_DUCKDB_NATIVE_ENCODINGS = {"utf-8", "utf-16", "latin-1"}

def _ensure_utf8(file_path: str, encoding: str) -> str:
    """
    DuckDBネイティブエンコーディングに変換
    既にネイティブエンコーディングならそのまま返す
    """
    # 既にDuckDBがサポートしている場合
    if encoding.lower() in _DUCKDB_NATIVE_ENCODINGS:
        return file_path

    # UTF-8一時ファイルに変換
    suffix = Path(file_path).suffix  # .csv を保持
    tmp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=suffix,
        encoding="utf-8",
        delete=False
    )

    try:
        with open(file_path, encoding=encoding) as src:
            # チャンク単位で読み込み（大容量ファイル対応）
            for chunk in iter(lambda: src.read(65536), ""):
                tmp_file.write(chunk)
        tmp_file.close()
        return tmp_file.name
    except Exception:
        tmp_file.close()
        raise
```

**パフォーマンスの配慮：**
- チャンク読み込みで、大容量ファイル（GB単位）でもメモリに優しい
- 一時ファイルは`delete=False`で、後続処理から明示的に削除

### レイヤー3: PLC固有フォーマット対応

工場のPLCロギングCSVには、ユニークな構造があります：

```
[DEVICELIST]
時刻,データ型,値1,値2,値3
2026-04-28 10:00:00,INT,100,200,150
2026-04-28 10:00:01,INT,101,201,151
```

セクションマーカー`[DEVICELIST]`と、データ型定義行があり、実際のデータはこの後から始まります。DuckDBが読み込む時は、これらをスキップする必要があります：

```python
def _detect_skip_rows(file_path: str, encoding: str) -> int:
    """
    PLC CSVの先頭マーカー行をカウント

    [SECTION] で始まる行 + データ型定義行の計2行をスキップ
    """
    with open(file_path, encoding=encoding) as f:
        first_line = f.readline().strip()

    # セクションマーカーで始まっていればスキップ行数=2
    if first_line.startswith("["):
        return 2

    return 0
```

### これら3レイヤーを統合

```python
def prepare_csv_for_duckdb(file_path: str) -> tuple[str, int]:
    """
    CSVをDuckDB読み込み可能な形に準備

    戻り値: (DuckDB用ファイルパス, スキップ行数)
    """
    # ステップ1: エンコーディング検出
    encoding = _detect_encoding(file_path)

    # ステップ2: UTF-8変換（必要なら）
    utf8_path = _ensure_utf8(file_path, encoding)

    # ステップ3: スキップ行数を検出
    skip_rows = _detect_skip_rows(file_path, encoding)

    return utf8_path, skip_rows
```

使用例：

```python
csv_path, skip = prepare_csv_for_duckdb("factory_log.csv")

con = duckdb.connect()
result = con.execute(
    f"SELECT * FROM read_csv('{csv_path}', skip={skip})"
).fetchall()
```

---

## パフォーマンス最適化: Parquetキャッシュ層

ここまでで、DuckDBでCSVを読み込めるようになりました。ただし、毎回エンコーディング検出→UTF-8変換→DuckDB読み込みは、大容量ファイルでは重たいです。

特に、**LLMとの連携で複数回クエリを投げるシナリオ**では、この処理が何度も実行されます。

### キャッシュ戦略: CSV → Parquet変換

```python
import json
from pathlib import Path
import hashlib

class CsvDataSession:
    """CSVをParquetキャッシュで高速化"""

    def __init__(self, source_id: str, container_path: str):
        self.source_id = source_id
        self.container_path = Path(container_path)
        self.cache_dir = self.container_path / ".duckdb_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.manifest_path = self.cache_dir / "manifest.json"

    def _load_manifest(self) -> dict:
        """マニフェストから変換済みファイル情報を読み込む"""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: dict):
        """マニフェストを原子的に書き込み"""
        # 一時ファイルに書き込んでからリネーム（安全性確保）
        tmp_path = self.manifest_path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(manifest, f, indent=2)
        tmp_path.replace(self.manifest_path)

    def _get_file_hash(self, file_path: Path) -> str:
        """ファイルのハッシュ値を計算（変更検知用）"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def ensure_parquet_cache(self) -> str:
        """
        Parquetキャッシュが存在しなければ作成
        既に存在すれば、変更されたCSVのみを更新
        """
        # CSV一覧を取得
        csv_files = sorted(self.container_path.glob("*.csv"))
        current_filenames = {f.name for f in csv_files}

        # マニフェストから変換済みファイルを確認
        manifest = self._load_manifest()
        converted_set = set(manifest.get("converted_files", []))

        # 新規CSVのみを抽出
        new_filenames = current_filenames - converted_set

        # キャッシュヒット：変更なし
        if not new_filenames:
            return str(self.cache_dir / "data.parquet")

        # 新規ファイルをバッチで変換（最大50ファイルずつ）
        new_files = [self.container_path / name for name in new_filenames]
        self._convert_csv_batch_to_parquet(new_files)

        # マニフェストを更新
        manifest["converted_files"] = sorted(current_filenames)
        manifest["updated_at"] = str(Path.ctime(self.cache_dir))
        self._save_manifest(manifest)

        return str(self.cache_dir / "data.parquet")

    def _convert_csv_batch_to_parquet(self, csv_files: list[Path]):
        """複数のCSVを1つのParquetファイルに変換"""
        import duckdb
        from itertools import batched

        con = duckdb.connect()
        all_data = []

        # 最大50ファイルずつをParquetに変換
        for batch in batched(csv_files, 50):
            batch_data = []

            for csv_path in batch:
                # ステップ1-3を適用
                utf8_path, skip = prepare_csv_for_duckdb(str(csv_path))

                # DuckDBで読み込み
                df = con.execute(
                    f"SELECT * FROM read_csv('{utf8_path}', skip={skip})"
                ).df()

                # ソースファイル列を追加（どのCSVからきたデータか追跡可能に）
                df["_source_file"] = csv_path.name
                batch_data.append(df)

            # バッチをParquetに追記
            batch_df = pd.concat(batch_data, ignore_index=True)
            parquet_path = self.cache_dir / "data.parquet"

            if parquet_path.exists():
                # 既に存在：追記
                existing = pd.read_parquet(parquet_path)
                combined = pd.concat([existing, batch_df], ignore_index=True)
                combined.to_parquet(
                    parquet_path,
                    compression="zstd",
                    index=False
                )
            else:
                # 新規作成
                batch_df.to_parquet(
                    parquet_path,
                    compression="zstd",
                    index=False
                )
```

**キャッシュ戦略の利点：**

| 観点 | CSV直接読み込み | Parquetキャッシュ |
|------|----------|---------|
| 初回読み込み | 遅い（エンコーディング検出→変換） | 遅い（初回のみ同左） |
| 2回目以降 | 同じく遅い | **高速**（Parquet直接読み込み） |
| ストレージ | CSVサイズ | Parquetで約30-50%圧縮 |
| 変更検知 | 毎回全ファイル読み込み | マニフェスト＆ハッシュで高速判定 |
| バッチ処理 | N個ファイル→N回のエンコーディング検出 | 50ファイル単位でまとめて変換 |

---

## 実装上の工夫

### 一時ファイルの安全な管理

UTF-8変換で作成された一時ファイルは、確実にクリーンアップする必要があります：

```python
from contextlib import contextmanager

@contextmanager
def managed_utf8_file(file_path: str, encoding: str):
    """一時ファイルの自動クリーンアップを保証"""
    utf8_path, skip = prepare_csv_for_duckdb(file_path)

    try:
        yield utf8_path, skip
    finally:
        # オリジナルと異なる場合のみ削除（一時ファイル）
        if utf8_path != file_path:
            Path(utf8_path).unlink(missing_ok=True)

# 使用例
with managed_utf8_file("factory_log.csv", "cp932") as (utf8_path, skip):
    con = duckdb.connect()
    result = con.execute(
        f"SELECT * FROM read_csv('{utf8_path}', skip={skip})"
    ).fetchall()
    # ブロック終了時に一時ファイルは自動削除
```

### Parquetの圧縮設定

Parquetの圧縮コーデックはいくつか選択肢がありますが、ZSTD（Zstandard）をお勧めします：

| コーデック | 圧縮率 | 速度 | 互換性 | 用途 |
|----------|-------|------|------|------|
| Snappy | 低 | 高速 | 広い | I/O帯域幅が充分な環境 |
| Gzip | 高 | 遅い | 広い | ストレージ最小化重視 |
| **ZSTD** | **高** | **中速** | **広い** | **バランス重視（推奨）** |

```python
# ZSTD圧縮で保存（デフォルトより高圧縮率）
df.to_parquet(parquet_path, compression="zstd", index=False)
```

---

## まとめ

この第1回では、DuckDBで日本語CSVを扱うための3レイヤーアプローチと、Parquetキャッシュによるパフォーマンス最適化を解説しました。

**実装のポイント：**

1. **エンコーディング自動検出** - UTF-8優先で試行、CP932で大多数をキャッチ
2. **UTF-8一時ファイル変換** - DuckDBネイティブエンコーディングへの変換
3. **PLC固有フォーマット対応** - セクションマーカーとスキップ行の検出
4. **Parquetキャッシュ層** - マニフェスト＆差分検知で高速アクセス

これにより、大容量の日本語CSVをDuckDBで効率的に扱えるようになります。

---

次回: [第2回: Text-to-SQL + エージェント統合編](/posts/duckdb-japanese-csv-for-llm-part2) では、DuckDBをLLMエージェントのツールとして統合し、自然言語からSQLを生成・実行する仕組みを解説します。工場スタッフが「今日の生産数は？」と聞くだけで、複数のCSVから自動的にSQLを生成してデータを抽出し、結果を返す——そんな体験の実装方法を、実例コードとともにお届けします。
