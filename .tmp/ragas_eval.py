"""
RAG Phantom - RAGAS評価スクリプト
通常モードと深掘りモードを比較評価する
"""
import asyncio
import json
import time
import httpx

API_BASE = "http://localhost:3000/rag-phantom/api"
USER_ID = "7108626b-33d5-45cb-acba-608280bbb484"
KB_ID = "ab4044cf-1970-4ec9-9b5e-ecce7b180071"  # 技術ブログ

# 10 evaluation questions with ground truth
EVAL_QUESTIONS = [
    {
        "question": "MQTTとはどのようなプロトコルですか？主な特徴を教えてください。",
        "ground_truth": "MQTTは軽量なメッセージングプロトコルで、IoTデバイス間の通信に使われる。Pub/Sub（発行/購読）モデルを採用し、ブローカーを介してメッセージを配信する。低帯域・低消費電力で動作する特徴がある。",
    },
    {
        "question": "Pub/Subモデルにおけるトピックの役割と構造について説明してください。",
        "ground_truth": "トピックはメッセージのルーティング先を指定する階層構造の文字列。PublisherがトピックにメッセージをPublishし、Subscriberが関心のあるトピックをSubscribeすることで、ブローカーが適切にメッセージを配信する。",
    },
    {
        "question": "Raspberry Piを使ったMQTTの設備監視システムの構成について教えてください。",
        "ground_truth": "Raspberry Piにセンサーを接続し、MQTTプロトコルでセンサーデータを収集・送信する。ブローカーを介して監視サーバーにデータを転送し、設備の状態をリアルタイムに監視する構成。",
    },
    {
        "question": "AWS Amplify Gen 2でのCognito認証の設定方法を教えてください。",
        "ground_truth": "defineAuthでCognito設定を定義し、React UIでログイン・サインアップ画面を実装する。Zustandで認証状態を管理し、React Routerで保護ルートを設定。ロールベースのアクセス制御やセッションタイムアウト機能も実装可能。",
    },
    {
        "question": "Lambda Function URLでのJWT検証の実装方法を教えてください。",
        "ground_truth": "Cognito発行のJWTトークンをLambda Function URL側で検証する。トークンのヘッダーからkidを取得し、CognitoのJWKS（JSON Web Key Set）と照合して署名を検証。有効期限やaudience等も確認する。",
    },
    {
        "question": "AWSサーバーレスチャットでリアルタイム通信にWebSocketを選んだ理由は？",
        "ground_truth": "Polling、SSE、WebSocketの3方式を比較検討し、双方向通信が可能でリアルタイム性が高く、API Gateway WebSocket APIとして管理できるWebSocketを選択。コスト面でも接続維持型の方が有利と判断。",
    },
    {
        "question": "DynamoDBのSingle Table Designについて、チャットデータの設計パターンを教えてください。",
        "ground_truth": "1つのDynamoDBテーブルでチャットの全エンティティ（ユーザー、ルーム、メッセージ、接続情報等）を管理する。PK/SKの命名規則で各エンティティを区別し、GSIを使って複数のアクセスパターンに対応する設計。",
    },
    {
        "question": "製造AI画像解析でLambdaストリーミングを使う理由は何ですか？",
        "ground_truth": "Lambda関数のタイムアウト（29秒）を回避するため、レスポンスストリーミングを使用。画像解析はAI処理に時間がかかるため、部分的な結果を逐次返すことでユーザー体験を向上させる。",
    },
    {
        "question": "Bedrock RuntimeとBedrock Agents APIの違いは何ですか？",
        "ground_truth": "Bedrock Runtimeは直接的なモデル呼び出しAPI。Bedrock Agentsはツール使用やナレッジベース検索などのオーケストレーション機能を提供するAPIで、より高レベルな抽象化を行う。",
    },
    {
        "question": "AWSコスト最適化で54%削減を達成した方法について教えてください。",
        "ground_truth": "画像解析システムのAWSコストを54%削減した事例。具体的な手法として、リソースの最適化、キャッシュの活用、不要なAPI呼び出しの削減、適切なインスタンスサイズの選択などが挙げられる。",
    },
]


def parse_sse_stream(raw_text: str) -> dict:
    """Parse SSE stream response and extract answer, sources, agentic steps."""
    answer_tokens: list[str] = []
    sources: list[dict] = []
    agentic_steps: list[dict] = []
    message_id = ""

    for line in raw_text.split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        evt_type = event.get("event", "")
        evt_data = event.get("data", {})

        if evt_type == "token":
            answer_tokens.append(evt_data.get("text", ""))
        elif evt_type == "sources":
            sources = evt_data.get("items", [])
        elif evt_type == "agentic_step":
            agentic_steps.append(evt_data)
        elif evt_type == "complete":
            message_id = evt_data.get("message_id", "")

    return {
        "answer": "".join(answer_tokens),
        "sources": sources,
        "agentic_steps": agentic_steps,
        "message_id": message_id,
    }


async def send_question(
    client: httpx.AsyncClient,
    question: str,
    search_mode: str,
) -> dict:
    """Send a question to the RAG API and return parsed response."""
    payload = {
        "session_id": None,
        "content": question,
        "knowledge_base_id": KB_ID,
        "response_mode": "detailed",
        "search_mode": search_mode,
    }
    headers = {
        "Content-Type": "application/json",
        "X-User-Id": USER_ID,
    }

    start = time.time()
    resp = await client.post(
        f"{API_BASE}/chat",
        json=payload,
        headers=headers,
        timeout=180.0,
    )
    elapsed = time.time() - start

    result = parse_sse_stream(resp.text)
    result["elapsed_sec"] = round(elapsed, 2)
    result["question"] = question
    result["search_mode"] = search_mode
    return result


def simple_ragas_scores(question: str, answer: str, ground_truth: str, sources: list[dict]) -> dict:
    """
    Compute simplified RAGAS-like metrics without requiring OpenAI API key.

    Metrics:
    - answer_length: 回答の文字数
    - source_count: 参照ソース数
    - keyword_coverage: ground_truthのキーワードが回答に含まれる割合
    - faithfulness_proxy: 回答が「情報が見つからない」系でないか (0 or 1)
    - answer_relevancy_proxy: 質問のキーワードが回答に含まれるか
    """
    import re

    # キーワード抽出 (2文字以上のカタカナ/英数字の連続)
    def extract_keywords(text: str) -> set:
        # Technical terms (English/katakana/kanji compounds)
        words = set()
        # カタカナ語
        words.update(re.findall(r'[ァ-ヶー]{2,}', text))
        # 英単語
        words.update(w.lower() for w in re.findall(r'[A-Za-z]{3,}', text))
        # 漢字2文字以上
        words.update(re.findall(r'[一-龥]{2,}', text))
        return words

    gt_keywords = extract_keywords(ground_truth)
    answer_keywords = extract_keywords(answer)
    question_keywords = extract_keywords(question)

    # keyword coverage: ground truthのキーワードが回答に出現する割合
    if gt_keywords:
        covered = sum(1 for kw in gt_keywords if kw in answer)
        keyword_coverage = round(covered / len(gt_keywords), 3)
    else:
        keyword_coverage = 0.0

    # answer relevancy: 質問キーワードが回答に出現する割合
    if question_keywords:
        q_covered = sum(1 for kw in question_keywords if kw in answer)
        answer_relevancy = round(q_covered / len(question_keywords), 3)
    else:
        answer_relevancy = 0.0

    # faithfulness proxy: 回答が実質的な内容を含むか
    no_info_phrases = ["情報が見つかりません", "該当する情報が", "ドキュメントが登録されていません", "お答えすることができません"]
    has_info = not any(phrase in answer for phrase in no_info_phrases)
    faithfulness = 1.0 if has_info else 0.0

    return {
        "answer_length": len(answer),
        "source_count": len(sources),
        "keyword_coverage": keyword_coverage,
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
    }


async def run_evaluation():
    print("=" * 80)
    print("RAG Phantom - RAGAS評価")
    print(f"KB: 技術ブログ ({KB_ID})")
    print(f"質問数: {len(EVAL_QUESTIONS)}")
    print("=" * 80)

    results = {"normal": [], "agentic": []}

    async with httpx.AsyncClient() as client:
        for i, q in enumerate(EVAL_QUESTIONS):
            print(f"\n--- Q{i+1}: {q['question'][:40]}... ---")

            for mode in ["normal", "agentic"]:
                print(f"  [{mode}] sending...", end=" ", flush=True)
                try:
                    result = await send_question(client, q["question"], mode)
                    scores = simple_ragas_scores(
                        q["question"], result["answer"], q["ground_truth"], result["sources"]
                    )
                    result["scores"] = scores
                    results[mode].append(result)
                    print(
                        f"done ({result['elapsed_sec']}s, "
                        f"{scores['answer_length']}chars, "
                        f"sources={scores['source_count']}, "
                        f"kw_cov={scores['keyword_coverage']}, "
                        f"faith={scores['faithfulness']}, "
                        f"rel={scores['answer_relevancy']})"
                    )
                except Exception as e:
                    print(f"ERROR: {e}")
                    results[mode].append({
                        "question": q["question"],
                        "search_mode": mode,
                        "answer": "",
                        "sources": [],
                        "agentic_steps": [],
                        "elapsed_sec": 0,
                        "scores": {
                            "answer_length": 0,
                            "source_count": 0,
                            "keyword_coverage": 0,
                            "faithfulness": 0,
                            "answer_relevancy": 0,
                        },
                    })

    # Summary
    print("\n" + "=" * 80)
    print("評価結果サマリー")
    print("=" * 80)

    for mode in ["normal", "agentic"]:
        mode_label = "通常" if mode == "normal" else "深掘り"
        mode_results = results[mode]
        n = len(mode_results)

        avg_time = sum(r["elapsed_sec"] for r in mode_results) / n
        avg_length = sum(r["scores"]["answer_length"] for r in mode_results) / n
        avg_sources = sum(r["scores"]["source_count"] for r in mode_results) / n
        avg_kw_cov = sum(r["scores"]["keyword_coverage"] for r in mode_results) / n
        avg_faith = sum(r["scores"]["faithfulness"] for r in mode_results) / n
        avg_rel = sum(r["scores"]["answer_relevancy"] for r in mode_results) / n

        print(f"\n【{mode_label}モード】")
        print(f"  平均応答時間:     {avg_time:.1f}秒")
        print(f"  平均回答文字数:   {avg_length:.0f}文字")
        print(f"  平均ソース数:     {avg_sources:.1f}")
        print(f"  キーワード網羅率: {avg_kw_cov:.3f}")
        print(f"  Faithfulness:     {avg_faith:.3f}")
        print(f"  回答関連性:       {avg_rel:.3f}")

    # Detail table
    print("\n" + "=" * 80)
    print("個別結果詳細")
    print("=" * 80)
    print(f"{'Q#':<4} {'モード':<8} {'時間(s)':<8} {'文字数':<8} {'ソース':<8} {'KW網羅':<8} {'忠実性':<8} {'関連性':<8}")
    print("-" * 68)

    for i in range(len(EVAL_QUESTIONS)):
        for mode in ["normal", "agentic"]:
            r = results[mode][i]
            s = r["scores"]
            mode_label = "通常" if mode == "normal" else "深掘り"
            print(
                f"Q{i+1:<3} {mode_label:<8} {r['elapsed_sec']:<8} {s['answer_length']:<8} "
                f"{s['source_count']:<8} {s['keyword_coverage']:<8.3f} {s['faithfulness']:<8.1f} "
                f"{s['answer_relevancy']:<8.3f}"
            )

    # Save detailed results
    output_path = r"C:\Users\tadsysp616\Apps\rag-phantom\.tmp\ragas_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n詳細結果を {output_path} に保存しました")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
