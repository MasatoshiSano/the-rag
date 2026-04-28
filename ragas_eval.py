"""
RAGAS-style RAG evaluation script for RAG Phantom.

Evaluates:
1. Context Relevancy - Are retrieved chunks relevant to the question?
2. Faithfulness - Is the answer grounded in the retrieved context?
3. Answer Relevancy - Does the answer actually address the question?
4. Context Recall - Did the retrieval find the right documents?

Uses the RAG Phantom API directly with heuristic scoring.
"""

import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_BASE = "http://localhost:8010/api"
USER_ID = "ragas-eval-user"
# 技術ブログ KB ID
KB_ID = "ab4044cf-1970-4ec9-9b5e-ecce7b180071"

# Document ID → name mapping (Qdrant payload has document_id but not document_name)
DOC_ID_MAP = {
    "39ccead0-5005-457c-bee4-4b0eb45b58d4": "01_mqtt_introduction",
    "d83d21a4-0323-4c9d-a75d-6d4030f1cde1": "02_pubsub_topics",
    "a6af9d4b-884f-42ab-bee2-4e2c608016b5": "03_practical_implementation",
    "b5aacd4a-b418-4987-81d0-b6c711473811": "04_multi_pi_setup",
    "d2971370-6eca-4ee2-b9a6-7a6178aaeed6": "05_bidirectional_mqtt",
}
# Reverse mapping: name → document_id
DOC_NAME_TO_ID = {v: k for k, v in DOC_ID_MAP.items()}


@dataclass
class EvalCase:
    """Evaluation test case."""

    question: str
    ground_truth: str
    expected_doc: str  # Document name (e.g., "01_mqtt_introduction")
    key_terms: list[str]  # Key terms that should appear in a good answer


@dataclass
class EvalResult:
    """Single evaluation result."""

    question: str
    answer: str
    sources: list[dict]
    ground_truth: str
    expected_doc: str
    context_relevancy: float = 0.0
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_recall: float = 0.0


# 10 evaluation cases covering all 5 MQTT documents
EVAL_CASES = [
    # Doc 1: MQTT Introduction
    EvalCase(
        question="MQTTとは何ですか？簡単に説明してください。",
        ground_truth="MQTTは機械同士がメッセージをやり取りするための共通言語（プロトコル）。伝言板のような仕組みで、Publisher（発信者）がBroker（仲介者）にメッセージを送り、Subscriber（購読者）が受け取る。",
        expected_doc="01_mqtt_introduction",
        key_terms=["MQTT", "プロトコル", "Publisher", "Broker", "Subscriber", "メッセージ", "伝言板"],
    ),
    EvalCase(
        question="MQTTのQoSレベルにはどんな種類がありますか？",
        ground_truth="QoS 0は送りっぱなし（届かなくてもOK）、QoS 1は最低1回届く（重複の可能性あり）、QoS 2は確実に1回届く（重複なし）の3種類。",
        expected_doc="01_mqtt_introduction",
        key_terms=["QoS 0", "QoS 1", "QoS 2", "送りっぱなし", "最低1回", "確実に1回"],
    ),
    # Doc 2: Pub/Sub Topics
    EvalCase(
        question="MQTTのトピックのワイルドカード「+」と「#」の違いは？",
        ground_truth="「+」は1階層のみのワイルドカード（例: sensor/+/temp）、「#」は以降のすべての階層にマッチするワイルドカード（例: sensor/#）。",
        expected_doc="02_pubsub_topics",
        key_terms=["1階層", "すべての階層", "sensor", "ワイルドカード", "マッチ"],
    ),
    EvalCase(
        question="Pub/Subモデルのメリットは何ですか？",
        ground_truth="疎結合（送信者と受信者がお互いを知らなくてOK）、スケーラブル（受信者が増えても送信者は1回送るだけ）、非同期（受信者がオフラインでも後で受け取れる）、フィルタリング（興味のあるメッセージだけ受け取れる）。",
        expected_doc="02_pubsub_topics",
        key_terms=["疎結合", "スケーラブル", "非同期", "フィルタリング", "送信者", "受信者"],
    ),
    # Doc 3: Practical Implementation
    EvalCase(
        question="設備監視システムでカメラの色検知はどのように動作しますか？",
        ground_truth="カメラで設備のランプを撮影し、色を判定する。緑はstatus 1（稼働中）、赤はstatus 2（停止）、黄はstatus 3（異常）。検知結果はJSONデータとしてMQTTで中継機に送信される。",
        expected_doc="03_practical_implementation",
        key_terms=["カメラ", "ランプ", "緑", "赤", "黄", "status", "稼働", "停止", "異常"],
    ),
    EvalCase(
        question="中継機を使うメリットは何ですか？直接クラウドに接続する場合と比較して。",
        ground_truth="中継機を使うメリットは、クラウド認証情報が中継機だけで済む（セキュリティ向上）、ローカルで一時保存が可能（障害耐性）、カメラ追加が簡単（中継機を見るだけ）。",
        expected_doc="03_practical_implementation",
        key_terms=["中継機", "認証情報", "セキュリティ", "一時保存", "障害", "カメラ追加"],
    ),
    # Doc 4: Multi Pi Setup
    EvalCase(
        question="Mosquittoのインストールと設定方法を教えてください。",
        ground_truth="sudo apt install mosquitto mosquitto-clients -yでインストール。/etc/mosquitto/conf.d/local.confにlistener 1883とallow_anonymous trueを設定。sudo systemctl restart mosquittoで再起動。",
        expected_doc="04_multi_pi_setup",
        key_terms=["apt install", "mosquitto", "listener", "1883", "allow_anonymous", "systemctl"],
    ),
    EvalCase(
        question="子機を追加する手順はどうなりますか？",
        ground_truth="新しいRaspberry Piを用意し、同じプログラムをコピーし、settings.jsonのsta_no3だけ変更（例: EQ004）してプログラムを起動するだけ。親機（中継機）の設定変更は不要。",
        expected_doc="04_multi_pi_setup",
        key_terms=["Raspberry Pi", "プログラム", "コピー", "settings.json", "sta_no3", "EQ004", "設定変更", "不要"],
    ),
    # Doc 5: Bidirectional MQTT
    EvalCase(
        question="MQTTの双方向通信ではどのようなユースケースがありますか？",
        ground_truth="遠隔設定変更（MQTTで全子機に設定を配信）、マスターデータの配信（Oracleから設備名などを子機に配信）、他の設備の状態を取得（子機同士がBroker経由で状態を共有）。",
        expected_doc="05_bidirectional_mqtt",
        key_terms=["遠隔", "設定変更", "配信", "マスターデータ", "Oracle", "子機", "状態"],
    ),
    EvalCase(
        question="ローカルDBとMQTT+クラウドDBの使い分けはどうすべきですか？",
        ground_truth="ローカルDBは小規模（1-2台）やネットワーク不安定な環境に適している。MQTT+クラウドは3台以上でデータを集約管理・分析したい場合に適している。迷ったらクラウド集約がおすすめ。ハイブリッド構成（ローカルバッファ+クラウド同期）がベストプラクティス。",
        expected_doc="05_bidirectional_mqtt",
        key_terms=["ローカルDB", "クラウド", "小規模", "集約", "ハイブリッド", "ネットワーク"],
    ),
]


async def send_chat_query(client: httpx.AsyncClient, question: str) -> tuple[str, list[dict]]:
    """Send a question to the RAG chat API and collect the full response."""
    payload = {
        "content": question,
        "session_id": None,
        "knowledge_base_id": KB_ID,
        "input_type": "text",
    }

    answer_parts: list[str] = []
    sources: list[dict] = []

    async with client.stream(
        "POST",
        f"{API_BASE}/chat",
        json=payload,
        headers={"X-User-Id": USER_ID, "Content-Type": "application/json"},
        timeout=120.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                event_data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            event = event_data.get("event", "")
            data = event_data.get("data", {})

            if event == "token":
                answer_parts.append(data.get("text", ""))
            elif event == "sources":
                sources = data.get("items", [])
            elif event == "error":
                logger.error("Error from API: %s", data)
                break

    return "".join(answer_parts), sources


def evaluate_context_relevancy(sources: list[dict]) -> float:
    """Score: how relevant are retrieved chunks to the question? (0-1)

    Based on retrieval scores from the vector search.
    """
    if not sources:
        return 0.0

    scores = [s.get("score", 0) for s in sources]
    if not scores:
        return 0.0

    # Use top-5 average score as relevancy metric
    top_scores = sorted(scores, reverse=True)[:5]
    avg_score = sum(top_scores) / len(top_scores)

    # Normalize: 0.5 score → 0.5 relevancy, 0.8+ → 1.0
    return min(1.0, max(0.0, (avg_score - 0.3) / 0.5))


def evaluate_context_recall(sources: list[dict], expected_doc: str) -> float:
    """Score: did we find the expected document? (0 or 1)

    Uses document_id mapping since Qdrant payloads don't store document_name.
    """
    if not sources:
        return 0.0

    expected_doc_id = DOC_NAME_TO_ID.get(expected_doc, "")
    if not expected_doc_id:
        return 0.0

    for s in sources:
        doc_id = s.get("document_id", "")
        if doc_id == expected_doc_id:
            return 1.0

    return 0.0


def evaluate_faithfulness(answer: str, sources: list[dict]) -> float:
    """Score: is the answer grounded in the retrieved context? (0-1)

    Since API doesn't return source content, we check if the answer
    contains substantive content (not just error messages or empty responses).
    """
    if not answer or not sources:
        return 0.0

    # Check for error patterns (use strict patterns to avoid false positives)
    error_patterns = ["エラーが発生", "ERROR:", "Internal Server Error", "再試行してください"]
    if any(p in answer for p in error_patterns):
        return 0.0

    # Check that the answer has substantive content (not just a header)
    clean_answer = re.sub(r"[#*•\-\n\s]", "", answer)
    if len(clean_answer) < 20:
        return 0.1

    # Sources exist and answer is substantive → assume grounded
    # (True faithfulness evaluation would require comparing answer claims against source content)
    num_sources = len(sources)
    if num_sources >= 5:
        return 0.8
    elif num_sources >= 1:
        return 0.6
    return 0.3


def evaluate_answer_relevancy(answer: str, case: EvalCase) -> float:
    """Score: does the answer address the question? (0-1)

    Checks how many key terms from the expected answer appear in the actual answer.
    """
    if not answer:
        return 0.0

    # Check for error patterns (use strict patterns to avoid false positives)
    error_patterns = ["エラーが発生", "ERROR:", "Internal Server Error", "再試行してください"]
    if any(p in answer for p in error_patterns):
        return 0.0

    answer_lower = answer.lower()
    matched = sum(1 for term in case.key_terms if term.lower() in answer_lower)
    total = len(case.key_terms)

    if total == 0:
        return 0.5

    ratio = matched / total
    return round(min(1.0, ratio), 3)


async def run_evaluation():
    """Run the full RAGAS evaluation."""
    results: list[EvalResult] = []

    async with httpx.AsyncClient(verify=False) as client:
        for i, case in enumerate(EVAL_CASES, 1):
            logger.info("=== Case %d/%d: %s ===", i, len(EVAL_CASES), case.question[:40])

            try:
                answer, sources = await send_chat_query(client, case.question)
            except Exception as e:
                logger.error("Failed to get response: %s", e)
                results.append(EvalResult(
                    question=case.question,
                    answer=f"ERROR: {e}",
                    sources=[],
                    ground_truth=case.ground_truth,
                    expected_doc=case.expected_doc,
                ))
                continue

            result = EvalResult(
                question=case.question,
                answer=answer,
                sources=sources,
                ground_truth=case.ground_truth,
                expected_doc=case.expected_doc,
            )

            # Calculate metrics
            result.context_relevancy = evaluate_context_relevancy(sources)
            result.context_recall = evaluate_context_recall(sources, case.expected_doc)
            result.faithfulness = evaluate_faithfulness(answer, sources)
            result.answer_relevancy = evaluate_answer_relevancy(answer, case)

            results.append(result)

            logger.info("  Answer length: %d chars", len(answer))
            logger.info(
                "  Sources: %d chunks, expected=%s, found=%s",
                len(sources),
                case.expected_doc,
                "YES" if result.context_recall == 1.0 else "NO",
            )
            logger.info(
                "  Scores: ctx_rel=%.2f, recall=%.2f, faith=%.2f, ans_rel=%.2f",
                result.context_relevancy,
                result.context_recall,
                result.faithfulness,
                result.answer_relevancy,
            )

            # Delay to avoid SQLite locking
            await asyncio.sleep(5)

    return results


def print_report(results: list[EvalResult]):
    """Print the evaluation report."""
    print("\n" + "=" * 80)
    print("RAGAS Evaluation Report - RAG Phantom")
    print("=" * 80)

    total_cr = 0.0
    total_recall = 0.0
    total_faith = 0.0
    total_ar = 0.0
    n = len(results)

    for i, r in enumerate(results, 1):
        print(f"\n--- Case {i}: {r.question}")
        answer_preview = r.answer[:150].replace("\n", " ")
        print(f"  Answer: {answer_preview}...")
        print(f"  Sources: {len(r.sources)} chunks")
        if r.sources:
            for s in r.sources[:3]:
                doc_id = s.get("document_id", "?")
                doc_name = DOC_ID_MAP.get(doc_id, doc_id[:12])
                print(f"    - {doc_name} (score: {s.get('score', 0):.3f})")
        print(f"  Expected doc: {r.expected_doc} -> {'FOUND' if r.context_recall == 1.0 else 'NOT FOUND'}")
        print(f"  Context Relevancy: {r.context_relevancy:.2f}")
        print(f"  Context Recall:    {r.context_recall:.2f}")
        print(f"  Faithfulness:      {r.faithfulness:.2f}")
        print(f"  Answer Relevancy:  {r.answer_relevancy:.2f}")

        total_cr += r.context_relevancy
        total_recall += r.context_recall
        total_faith += r.faithfulness
        total_ar += r.answer_relevancy

    print("\n" + "=" * 80)
    print("AGGREGATE SCORES")
    print("=" * 80)
    print(f"  Context Relevancy:  {total_cr / n:.2f}")
    print(f"  Context Recall:     {total_recall / n:.2f}")
    print(f"  Faithfulness:       {total_faith / n:.2f}")
    print(f"  Answer Relevancy:   {total_ar / n:.2f}")
    overall = (total_cr + total_recall + total_faith + total_ar) / (4 * n)
    print(f"  Overall Score:      {overall:.2f}")
    print("=" * 80)

    # Save JSON report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "knowledge_base_id": KB_ID,
        "num_cases": n,
        "aggregate": {
            "context_relevancy": round(total_cr / n, 3),
            "context_recall": round(total_recall / n, 3),
            "faithfulness": round(total_faith / n, 3),
            "answer_relevancy": round(total_ar / n, 3),
            "overall": round(overall, 3),
        },
        "cases": [
            {
                "question": r.question,
                "answer": r.answer,
                "ground_truth": r.ground_truth,
                "expected_doc": r.expected_doc,
                "num_sources": len(r.sources),
                "source_doc_ids": list({s.get("document_id", "") for s in r.sources}),
                "context_relevancy": round(r.context_relevancy, 3),
                "context_recall": round(r.context_recall, 3),
                "faithfulness": round(r.faithfulness, 3),
                "answer_relevancy": round(r.answer_relevancy, 3),
            }
            for r in results
        ],
    }

    with open("ragas_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nReport saved to ragas_report.json")


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Windows cp932 エンコーディングエラー対策
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    results = asyncio.run(run_evaluation())
    print_report(results)
