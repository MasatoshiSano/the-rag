<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# docs

## Purpose
開発者・運用者向けドキュメント。MQTT を題材としたサンプルチュートリアル群と、API ガイド・外部連携セットアップガイド。

## Key Files
| File | Description |
|------|-------------|
| `01_mqtt_introduction.md` | MQTT プロトコル入門 |
| `02_pubsub_topics.md` | Pub/Sub とトピック設計 |
| `03_practical_implementation.md` | 実装例（Python / mosquitto） |
| `04_multi_pi_setup.md` | 複数 Raspberry Pi 構成 |
| `05_bidirectional_mqtt.md` | 双方向通信パターン |
| `api-guide.md` | RAG Phantom API の利用ガイド（外部連携 `/api/external/*` を含む） |
| `external-setup-guide.md` | Bedrock / Oracle / Qdrant 等の外部システム接続準備手順 |

## For AI Agents

### Working In This Directory
- ここのドキュメントは社内デモやサンプルデータ投入のソースとしても使われる（`uploads/` のサンプルや RAGAS 評価対象になることがある）。
- API 仕様の変更があれば `api-guide.md` を最新に保つ。OpenAPI スキーマは FastAPI の `/docs` から自動生成されるため二重管理しない。

### Common Patterns
- 日本語、Markdown、コードブロックには言語識別子を付ける（`bash`, `python`, `yaml`）。

## Dependencies

### Internal
- なし（純粋なドキュメント）

<!-- MANUAL: -->
