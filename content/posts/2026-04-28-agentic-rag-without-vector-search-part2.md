---
title: "ベクトル検索を使わないRAG（第2回：検索エンジン編）— スライディングウィンドウAND検索とORフォールバック"
emoji: "🔍"
type: "tech"
topics: ["RAG", "Search", "Python", "NLP", "AI Agent"]
published: true
category: "Architecture"
date: "2026-04-28"
description: "ベクトルDBの代わりにスライディングウィンドウ方式のAND検索とORフォールバックを実装し、match_type:partialフラグでLLMに検索戦略の自己修正を促す設計を解説"
series: "ベクトル検索を使わないRAG"
seriesOrder: 2
---

> **このシリーズ: 全3回**
> 1. [第1回: エージェントループ設計編](/posts/agentic-rag-without-vector-search-part1)
> 2. [第2回: 検索エンジン編](/posts/agentic-rag-without-vector-search-part2) ← 今ここ
> 3. [第3回: リアルタイム進捗配信編](/posts/agentic-rag-without-vector-search-part3)

前回の記事では、ベクトルDBを使わずにLLMのエージェント機能でRAGを実現する全体設計を紹介しました。今回は、その心臓部ともいえる**キーワード検索エンジン**の実装に焦点を当てます。

## 問題設定: ベクトル検索がない環境での検索

ベクトルDB（Qdrant, Pinecone等）を使わない場合、残された選択肢は以下の3つです：

1. **全文検索**（Elasticsearch等）→ インフラ複雑化、本番化コスト
2. **キーワードマッチング**（AND/OR） → シンプルだが精度がやや低い
3. **LLMの自己修正ループ** → キーワード調整・同義語展開をLLMに任せる

私たちが採用したのは **2 + 3 の組み合わせ** です。検索結果に `match_type: "partial"` というフラグを付け、LLMに「全キーワードが近い距離で見つかりませんでした」と明示することで、LLMが自動的にキーワードを修正します。

## スライディングウィンドウAND検索の仕組み

### 設計思想

従来のOR検索では、検索キーワード「K298 エア圧力 規格値」で、「K298」と「規格値」が文書の離れた場所に出現しても1件として数えます。一方、**AND検索なら「K298」「エア圧力」「規格値」が近い距離（ウィンドウ内）に全て含まれる場所だけを返す** ので、ノイズが少なくなります。

### 実装の流れ

```
入力: テキスト, クエリ「K298 エア圧力 規格値」, ウィンドウサイズ=20行

ステップ1: キーワード分解
  keywords = ["k298", "エア圧力", "規格値"]

ステップ2: 行ごとのキーワード出現セットを事前計算
  line_kw_sets = [
    {0: {"k298"}},
    {1: {"k298", "エア圧力"}},
    {2: {"エア圧力"}},
    {3: {}},
    ...
    {21: {"規格値"}},
  ]

ステップ3: スライディングウィンドウでANDサーチ
  Window[0..19] → キーワードカバレッジ = 2/3 ✗ 不合格
  Window[1..20] → キーワードカバレッジ = 3/3 ✓ 合格 → 返す
```

### ASCII図解: スライディングウィンドウの動作

```
テキスト行番号:  0  1  2  3 ... 19 20 21 ...
キーワード分布:  k298
                    k298 エア圧力
                        エア圧力
                                           規格値

Window[0-19]範囲:
[===============================================] (19行)
k298    ✓
エア圧力  ✗ 位置20は範囲外
規格値    ✗ 位置21は範囲外
→ AND検索失敗（全3キーワード中2つだけ）

Window[1-20]範囲:
  [===============================================] (20行)
k298    ✓ (行1)
エア圧力  ✓ (行1-2)
規格値    ✗ 位置21は範囲外
→ AND検索失敗

Window[2-21]範囲:
    [===============================================] (20行)
k298    ✗ 行0-1は範囲外
エア圧力  ✓ (行2-3)
規格値    ✓ (行21)
→ AND検索失敗

Window[5-24]範囲:
         [===============================================] (20行)
k298    ✗ 範囲外
エア圧力  ✓
規格値    ✓
→ AND検索失敗

✗ AND検索 0件 → Phase 2: ORフォールバックへ
```

このように、ウィンドウを1行ずつスライドさせながら、ウィンドウ内に**全てのキーワード**が含まれている区間を探します。複数の長文ドキュメントでも高速に動作します。

## Pythonコード実装

### 完全な `_keyword_search_in_text` 関数

```python
def _keyword_search_in_text(
    content: str,
    query: str,
    max_results: int = 10,
    context_lines: int = 3,
    window_size: int = 20,
) -> list[dict]:
    """
    キーワード AND/OR 検索。AND で 0 件なら OR にフォールバック。

    Args:
        content: 検索対象のテキスト
        query: スペース区切りのキーワード（例: "K298 エア圧力 規格値"）
        max_results: 返す最大マッチ数
        context_lines: マッチ行の前後何行を含めるか
        window_size: AND検索のウィンドウサイズ（行数）

    Returns:
        [
          {
            "line_number": 42,
            "content": "...\n...エア圧力 規格値 K298...\n...",
            "match_type": "full",  # or "partial"
            "matched_keywords": ["k298", "エア圧力"]
          },
          ...
        ]
    """
    # キーワード正規化
    keywords = [kw.lower().strip() for kw in query.split() if kw.strip()]
    if not keywords:
        return []

    lines = content.split("\n")

    # ステップ1: 行ごとのキーワード出現セットを事前計算
    line_kw_sets = []
    for line in lines:
        line_lower = line.lower()
        matching_kws = {kw for kw in keywords if kw in line_lower}
        line_kw_sets.append(matching_kws)

    # ステップ2: スライディングウィンドウ AND 検索
    matches = []
    used_lines = set()

    for i in range(len(lines)):
        if i in used_lines:
            continue

        # ウィンドウ内の全キーワードをカバーしているか確認
        window_end = min(len(lines), i + window_size)
        window_keywords_union = set()

        for j in range(i, window_end):
            window_keywords_union |= line_kw_sets[j]

        # 全キーワードが揃っていない場合はスキップ
        if len(window_keywords_union) < len(keywords):
            continue

        # AND 検索成功：ウィンドウ内で最もキーワードを含む行をセンターに
        best_line_idx = max(
            range(i, window_end),
            key=lambda j: len(line_kw_sets[j])
        )

        # コンテキスト行を含める
        context_start = max(0, best_line_idx - context_lines)
        context_end = min(len(lines), best_line_idx + context_lines + 1)

        matches.append({
            "line_number": best_line_idx + 1,
            "content": "\n".join(lines[context_start:context_end]),
            "match_type": "full",
            "matched_keywords": list(line_kw_sets[best_line_idx]),
        })

        # 使用済み行をマーク（重複排除）
        for j in range(i, window_end):
            used_lines.add(j)

        if len(matches) >= max_results:
            break

    # AND検索で結果が出た場合はそれを返す
    if matches:
        return matches

    # ステップ3: フォールバック OR 検索
    # 各行がマッチしたキーワード数でスコア化
    or_candidates = []
    for line_idx, kw_set in enumerate(line_kw_sets):
        if kw_set:  # 1つ以上のキーワードを含む
            score = len(kw_set)
            or_candidates.append((score, line_idx, kw_set))

    # スコア降順でソート
    or_candidates.sort(reverse=True, key=lambda x: x[0])

    # 上位 max_results 件を返す
    for score, line_idx, kw_set in or_candidates[:max_results]:
        context_start = max(0, line_idx - context_lines)
        context_end = min(len(lines), line_idx + context_lines + 1)

        matches.append({
            "line_number": line_idx + 1,
            "content": "\n".join(lines[context_start:context_end]),
            "match_type": "partial",  # ← LLMの注目キーワード
            "matched_keywords": list(kw_set),
        })

    return matches
```

### 使用例

```python
content = """
K298 機械仕様書
- エア圧力: 0.5～0.8 MPa
- 規格値: ISO 1234

K300 フローチャート
- エア機械の流路図
- 規格値は別紙参照

K298 詳細スペック
- K298 エア圧力 規格値 = 0.6 MPa
"""

# AND 検索：全キーワードが近い場所を探す
results = _keyword_search_in_text(
    content,
    query="K298 エア圧力 規格値",
    max_results=5,
    context_lines=2,
    window_size=20
)

# 結果（AND検索で1件）:
# [
#   {
#     "line_number": 10,
#     "match_type": "full",
#     "matched_keywords": ["k298", "エア圧力", "規格値"],
#     "content": "K298 詳細スペック\n- K298 エア圧力 規格値 = 0.6 MPa\n"
#   }
# ]
```

## Phase 2: ORフォールバックと `match_type` フラグの威力

AND検索で0件の場合、OR検索にフォールバックします。重要なのは、検索結果に **`match_type: "partial"`** フラグを付けることです。このフラグは、LLMに「全キーワードが近い距離で揃っていない」という情報を与えます。

### システムプロンプトでの指示

LLMのシステムプロンプトに以下のような検索戦略を組み込みます：

```
## 検索フロー

1. まず `list_documents` でドキュメント一覧を確認
2. `search_in_document` でキーワード検索し関連箇所を特定
3. `read_document_section` で詳しく読み込む
4. 情報不足なら別キーワードで再検索

## 検索のコツと戦略

- 複合キーワード検索で0件 or `match_type: "partial"` が返された
  → キーワードを減らして再検索するべき信号

例: 「K298 エア圧力 規格値」で partial → 「エア圧力 規格値」に分割して再検索
例: 「制御系統 ポンプ 動作原理」で 0件 → 「ポンプ 動作」に絞る

- 同義語で再検索
  「エア圧」で0件 → 「空気圧」「圧力」を試す
  「規格値」で partial → 「仕様」「スペック」を試す

- `match_type: "partial"` = 部分一致
  → 複数キーワード中いくつかが見つかったが全部揃っていない
  → キーワードを絞ったり、同義語に変えたりして再検索が有効

## 判断基準

検索結果の質評価:
- `match_type: "full"` + 複数行: 高精度、この情報で十分な可能性が高い
- `match_type: "partial"` + 1キーワードのみ: 低精度、別キーワードで再検索推奨
- 複数の異なるキーワード組み合わせで同じ情報が出現 → 確度高い
```

### LLMの自己修正メカニズム

```
ユーザー質問: 「K298のエア圧力の規格値は？」
↓
エージェント: search_in_document("K298 エア圧力 規格値")
↓
結果: match_type="partial", matched_keywords=["k298", "エア圧力"]
      → 「規格値」が見つからなかった
↓
エージェント思考: 「partial フラグなので、キーワードを絞ろう」
↓
エージェント: search_in_document("K298 規格値")
↓
結果: match_type="full", matched_keywords=["k298", "規格値"]
      → 成功！詳細を read_document_section で取得
```

このように、LLMが`match_type`フラグを見て自動的に検索戦略を調整します。

## パフォーマンス最適化

### 1. 事前計算によるメモリ効率化

`line_kw_sets` を事前計算することで、ウィンドウスライド中に何度も `line.lower()` や `if kw in line` を繰り返しません。大型ドキュメント（数十MB）でも高速です。

### 2. 使用済み行トラッキング

AND検索で見つけた区間を `used_lines` に記録し、重複するマッチを排除します。結果として max_results で指定した件数を効率よく返せます。

### 3. 短いウィンドウサイズの選択

`window_size=20` はデフォルトですが、以下のように調整可能：
- ドキュメント内のキーワード密度が高い → window_size=10
- キーワード間の距離が遠い可能性 → window_size=50

```python
# 例：JSON配列のようにキーワード密度が高い場合
_keyword_search_in_text(content, query, window_size=10)

# 例：マニュアルのような分散した記述の場合
_keyword_search_in_text(content, query, window_size=50)
```

## よくある失敗パターンと対策

| パターン | 原因 | 対策 |
|---------|------|------|
| キーワードの大文字小文字が不一致 | 日本語は OK、英数字は要正規化 | `query.lower()` で統一 |
| 記号や空白が含まれて検索漏れ | 「K-298」vs「K298」 | システムプロンプトで同義語リスト提示 |
| ウィンドウサイズが小さすぎる | キーワード間隔が20行以上 | 「partial」フラグを見てLLMが拡大再検索 |
| 大量マッチで遅い | max_results デフォルト10件で十分？ | 必要に応じて max_results=5 に縮小 |

## システムプロンプトでの実装例（FastAPI）

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class SearchRequest(BaseModel):
    document_id: str
    query: str

@app.post("/search_in_document")
async def search_in_document(req: SearchRequest):
    """
    エージェントが呼び出す検索エンドポイント
    """
    doc = get_document(req.document_id)  # DB取得

    results = _keyword_search_in_text(
        content=doc.content,
        query=req.query,
        max_results=10,
        context_lines=3,
        window_size=20
    )

    return {
        "query": req.query,
        "total_matches": len(results),
        "matches": results,
        "hint": "partial が多い場合、キーワードを絞ってください"
    }
```

## まとめ: なぜベクトルDBを捨てたのか

| 観点 | ベクトルDB | キーワード AND/OR + LLM自己修正 |
|-----|----------|----------------------------------|
| **導入コスト** | インフラ構築・維持（高） | Python 関数だけ（低） |
| **精度** | 埋め込みモデルに依存 | LLMが動的調整（中～高） |
| **デバッグ性** | なぜそのスコアか不明 | 検索キーワードと一致度が明確 |
| **対応言語** | 埋め込みモデルの対応言語限定 | 言語非依存、キーワードマッチ |
| **計算量** | O(1) 埋め込みベクトル検索 | O(n × window_size) テキスト走査 |
| **スケーラビリティ** | 大規模向け | 中規模（1000ドキュメント等）向け |

ベクトルDBはスケーラビリティで勝りますが、**デバッグしやすさ**と**シンプルさ**ではキーワード検索が優れています。特に、LLMに検索戦略の自己修正を任せることで、複雑なクエリ拡張やリランキングロジックを書かなくて済みます。

---

**次回予告**

次回（第3回）では、エージェントの各ステップをSSEでフロントエンドにリアルタイム配信する実装を解説します。「思考中 → 検索中 → 3件発見 → 読み込み中 → 回答生成中」という進捗表示により、ユーザーが待たされている感覚を軽減できます。

[第3回: リアルタイム進捗配信編](/posts/agentic-rag-without-vector-search-part3)へ続く...
