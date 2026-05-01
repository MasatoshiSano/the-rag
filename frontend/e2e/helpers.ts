import { type Page } from '@playwright/test';

/**
 * Google Fonts が企業ネットワークでタイムアウトするため、
 * テスト開始前にフォントリクエストをブロックする。
 */
export async function blockExternalFonts(page: Page): Promise<void> {
  await page.route('**/*.googleapis.com/**', (route) => route.abort());
  await page.route('**/*.gstatic.com/**', (route) => route.abort());
}

/**
 * ページ遷移ヘルパー。
 * アプリは Vite base "/the-rag/" でビルドされているため、
 * path の先頭に "/the-rag" を自動的に付与する。
 * domcontentloaded で遷移し、networkidle でSPAレンダリング完了を待つ。
 */
export async function gotoPage(page: Page, path: string): Promise<void> {
  const normalizedPath = path === '/' ? '/the-rag/' : `/the-rag${path}`;
  await page.goto(normalizedPath, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
}
