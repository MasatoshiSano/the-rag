<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# maintenance

## Purpose
設備保全マニュアル系のサンプル投入データ。RAG の検索精度デモや RAGAS 評価に使う。

## Key Files
| File | Description |
|------|-------------|
| `motor_assy_43_maintenance.md` | モータ ASSY 43 の保全手順サンプル |

## For AI Agents

### Working In This Directory
- 実コードからは参照されない。手動アップロードで `documents` パイプライン（変換 → タグ → チャンク → ベクトル化）にかける。
- 新ファイルを追加するときは、`backend/data/master/master-flat-with-place-aliases.md` に存在するサイト/ライン/工程コードと整合させると、エイリアスマッチングで自動タグが効く。

## Dependencies

### Internal
- なし（投入用データのみ）

<!-- MANUAL: -->
