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
 * domcontentloaded で遷移し、networkidle でSPAレンダリング完了を待つ。
 */
export async function gotoPage(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
}
