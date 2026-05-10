<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# e2e

## Purpose
Playwright による E2E テストスイート。`docker compose up` 済みの環境（`http://localhost:3000`）に対して Chromium で実行する。

## Key Files
| File | Description |
|------|-------------|
| `helpers.ts` | テスト共通ヘルパ（ログイン代替の fingerprint 注入、API リクエスト待機など） |
| `accessibility.spec.ts` | アクセシビリティ（aria 属性、コントラストなど）の検証 |
| `knowledge-bases.spec.ts` | KB の作成・編集・削除フロー |
| `navigation.spec.ts` | サイドバーから各画面へのナビゲーション |
| `settings.spec.ts` | 設定変更とその永続化 |
| `upload.spec.ts` | ファイルアップロードとステータス遷移の確認 |

## For AI Agents

### Working In This Directory
- `playwright.config.ts`: `baseURL=http://localhost:3000`, `locale=ja-JP`, タイムアウト 90s（global）/ 15s（expect） / 45s（navigation） / 15s（action）。Chromium のみ。
- 実行: `cd frontend && npx playwright test`。Docker Compose スタックを事前起動する。
- 新規 spec を追加するときは既存の `helpers.ts` のフィクスチャ/ヘルパを使い、API リクエストの完了を `page.waitForResponse` で同期させる（タイミング起因の flaky を避ける）。
- バックエンドの DB は永続なので、テスト間の状態クリーンアップが必要なら API 経由で削除するか、テスト用 KB を毎回作成する。

### Common Patterns
- `test.describe('機能名', () => { ... })` で機能単位にまとめる。
- セレクタはアクセシブルロール優先（`getByRole('button', { name: '保存' })`）。

## Dependencies

### Internal
- `../src/*`（実装が変わるとテストも調整が必要）

### External
- `@playwright/test`

<!-- MANUAL: -->
