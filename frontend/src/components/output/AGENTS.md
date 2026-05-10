<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# output

## Purpose
構造化出力（テーブル・チャート）の表示と CSV/画像ダウンロード。Oracle / DuckDB クエリ結果がチャットメッセージに紐づいて返るので、それを右ペインに描画する。

## Key Files
| File | Description |
|------|-------------|
| `OutputPanel.tsx` | 右ペインのコンテナ。テーブル/チャート切り替え、ダウンロードボタンを束ねる |
| `DataTable.tsx` | 行/列ベースのデータテーブル |
| `ChartView.tsx` | recharts ベースのチャート（バー/ライン/パイなどを `chart_config` で切替） |
| `DownloadButtons.tsx` | CSV ダウンロード / 画像（PNG）エクスポート |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- データソースは `useOutputStore`（バックエンドの `chat_outputs.table_data` / `chart_config` JSON を保持）。
- チャート画像化は `html-to-image`（`toPng`）を使用。フォントロード待ちが必要なケースがあるので `await document.fonts.ready` 等を挟む。

## Dependencies

### Internal
- `../../stores/outputStore`
- `../../api/output`
- `../../types/output`

### External
- `recharts`, `html-to-image`, `@serendie/ui`

<!-- MANUAL: -->
