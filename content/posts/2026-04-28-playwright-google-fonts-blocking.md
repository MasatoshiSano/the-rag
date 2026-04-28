---
title: "Playwright E2Eテストで外部フォントがページ読み込みを30秒ブロックする — route.abort()で解決"
emoji: "🎭"
type: "tech"
topics: ["Playwright", "E2E Testing", "Google Fonts", "Performance", "CI"]
published: true
category: "Debugging"
date: "2026-04-28"
description: "デザインシステムが読み込むGoogle FontsがCI/社内環境でタイムアウトし、PlaywrightのE2Eテストが30秒以上かかる問題をroute.abort()で解決する方法を解説"
---

# Playwright E2Eテストで外部フォントがページ読み込みを30秒ブロックする — route.abort()で解決

## やりたかったこと

Serendie Design System (`@serendie/ui`) を使ったReactアプリケーションのE2Eテストを、Playwrightで自動化する。テスト実行時間を最小化し、CIパイプラインを高速化したい。

## ❌ 最初にぶつかった問題

テストスイートを実行すると、**ページ読み込みが30秒以上かかる**。タイムアウトエラーで頻繁にテストが失敗する。

```
Error: Timeout 30000ms exceeded.
  waiting for locator.getByRole('button')
```

ローカルではテストが通るのに、**CI環境（GitLab Runner、社内プロキシ経由）では確実に失敗**する。

## 何が起きたか

原因を調査するため、Playwrightのネットワークリクエストログを確認しました。

```typescript
const requests = await page.context().tracing.trace('trace.zip');
```

結果、以下が判明しました：

1. `@serendie/ui` のCSSファイルが `@import url('https://fonts.googleapis.com/css2?family=...')` でGoogle Fontsを読み込んでいる
2. 社内プロキシまたはCI環境（インターネットアクセス制限あり）では、このリクエストが **タイムアウト** または **ブロック** されている
3. Google Fontsのリクエスト待機中、ブラウザの `load` イベントが発火しない
4. Playwrightが `waitUntil: 'load'` を指定していると、永遠に待機状態になる

## ✅ 解決策：route.abort()で外部リクエストをブロック

テストには外部フォントは不要です。以下のように **テスト内で外部フォントをブロック** します。

### 実装コード

テスト用のヘルパー関数 `gotoPage()` を作成：

```typescript
// tests/helpers/gotoPage.ts
export async function gotoPage(
  page: Page,
  url: string
): Promise<void> {
  // Google Fontsと関連リソースをブロック
  await page.route('**/*.googleapis.com/**', route => route.abort());
  await page.route('**/*.gstatic.com/**', route => route.abort());

  // DOM解析完了時点でnavigation終了とみなす
  await page.goto(url, { waitUntil: 'domcontentloaded' });

  // ネットワークが沈黙するまで待機（自動スクロール等の遅延読込に対応）
  await page.waitForLoadState('networkidle');
}
```

### 使い方

すべてのテストで `goto()` の代わりに `gotoPage()` を使用：

```typescript
// tests/pages/chat.spec.ts
import { test, expect } from '@playwright/test';
import { gotoPage } from '../helpers/gotoPage';

test('チャット画面が表示される', async ({ page }) => {
  await gotoPage(page, '/the-rag/chat');

  await expect(page.getByRole('heading', { name: /チャット/ })).toBeVisible();
});

test('メッセージ入力フォームが機能する', async ({ page }) => {
  await gotoPage(page, '/the-rag/chat');

  const input = page.getByRole('textbox', { name: /メッセージ/ });
  await input.fill('テストメッセージ');
  await input.press('Enter');

  await expect(page.getByText(/テストメッセージ/)).toBeVisible();
});
```

### 実行結果

```
✓ tests/pages/chat.spec.ts (2 tests)
  ✓ チャット画面が表示される (2.3s)
  ✓ メッセージ入力フォームが機能する (1.8s)

Total: 4.1s
```

**実行時間が30秒以上から4秒に短縮されました。**

## その他のPlaywright知見

このプロジェクトで遭遇した、Serendieデザインシステム使用時の落とし穴をまとめました。

### 1. RadioGroup は `.click()` を使う

Serendie の `RadioGroup` コンポーネントは特殊な構造をしており、`.check()` メソッドが機能しません。

```typescript
// ❌ 動作しない
await page.getByRole('radio', { name: 'オプションA' }).check();

// ✅ 正しい方法：ラベルテキストをクリック
await page.getByLabel('オプションA').click();
```

### 2. getByLabel()が複数の要素にマッチする場合

フォーム設計によっては、`getByLabel()` が複数の要素にマッチすることがあります。この場合は `getByRole()` で限定します。

```typescript
// ❌ 2つ以上のマッチが発生
await page.getByLabel('ニックネーム').fill('太郎');
// Error: Target element is not an input

// ✅ roleで絞り込む
await page.getByRole('textbox', { name: 'ニックネーム' }).fill('太郎');
```

### 3. AppShell構造の理解

アプリケーションのレイアウトが `AppShell` で統制されている場合、`<main>` タグは **AppShell側で定義されている** ため、各ページでは `<section>` を使用します。

```typescript
// ✅ ページコンポーネント
export function ChatPage() {
  return (
    <section>
      <h1>チャット</h1>
      {/* ページコンテンツ */}
    </section>
  );
}

// AppShell側でmainを持つ
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <main id="main-content">
      {children}
    </main>
  );
}
```

### 4. waitForLoadState()を正しく使う

Playwrightでは複数の `loadState` オプションがあります。フォント読込がブロックされた環境では、以下の組み合わせが有効です。

| オプション | 説明 | 用途 |
|-----------|------|------|
| `'domcontentloaded'` | DOMツリー構築完了 | 初期ナビゲーション完了 |
| `'load'` | すべてのリソース読込完了 | **外部フォント環境では避ける** |
| `'networkidle'` | 500msネットワーク沈黙 | 非同期リソース完全読込待機 |

```typescript
// ✅ 推奨：社内環境対応
await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForLoadState('networkidle');

// ❌ 避けるべき：CI環境でハング
await page.goto(url, { waitUntil: 'load' });
```

## まとめ

| 項目 | 内容 |
|------|------|
| **問題** | Google Fontsなど外部リソースがCI/プロキシ環境でタイムアウト、テストが30秒以上待機 |
| **原因** | `@serendie/ui` がGoogle Fontsをロード、ネットワーク制限環境で待機状態に |
| **解決策** | `page.route()` でテスト内から外部リクエストをブロック |
| **効果** | 実行時間を30秒以上から4秒以下に短縮 |
| **応用** | テスト環境では不要なリソース（分析スクリプト、広告等）もブロック可能 |

このパターンはデザインシステム採用時の標準的な解決策です。E2Eテストの高速化と安定化に、ぜひご活用ください。

---

## 関連リンク

- [Playwright - route.abort() documentation](https://playwright.dev/docs/api/class-route#route-abort)
- [Playwright - page.goto() waitUntil options](https://playwright.dev/docs/api/class-page#page-goto)
- [Serendie Design System - @serendie/ui](https://serendie.dev)

