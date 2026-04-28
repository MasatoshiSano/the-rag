import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * ナビゲーションテスト
 * 各ページへの遷移とサイドバーリンクの動作を検証します。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

test.describe('ページナビゲーション', () => {
  test('/ にアクセスすると /chat にリダイレクトされる', async ({ page }) => {
    await gotoPage(page, '/');
    await expect(page).toHaveURL(/\/chat/);
  });

  test('/upload ページが正しく表示される', async ({ page }) => {
    await gotoPage(page, '/upload');
    await expect(page.getByRole('heading', { name: 'ドキュメントアップロード', level: 1 })).toBeVisible();
  });

  test('/documents ページが正しく表示される', async ({ page }) => {
    await gotoPage(page, '/documents');
    await expect(page.getByRole('heading', { name: 'ドキュメント管理', level: 1 })).toBeVisible();
  });

  test('/knowledge-bases ページが正しく表示される', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await expect(page.getByRole('heading', { name: 'ナレッジベース', level: 1 })).toBeVisible();
  });

  test('/settings ページが正しく表示される', async ({ page }) => {
    await gotoPage(page, '/settings');
    await expect(page.getByRole('heading', { name: '設定', level: 1 })).toBeVisible();
  });

  test('/chat ページが正しく表示される', async ({ page }) => {
    await gotoPage(page, '/chat');
    // KB未選択時は「ナレッジベースを選択してください」が表示される
    await expect(page.getByRole('heading', { name: 'ナレッジベースを選択してください', level: 1 })).toBeVisible();
  });
});

test.describe('サイドバーナビゲーション', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
  });

  test('サイドバーに全ナビゲーションリンクが存在する', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await expect(nav).toBeVisible();

    await expect(nav.getByRole('link', { name: 'チャット' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'アップロード' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'ドキュメント' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'ナレッジベース' })).toBeVisible();
    await expect(nav.getByRole('link', { name: '設定' })).toBeVisible();
  });

  test('サイドバーの「アップロード」リンクをクリックするとアップロードページに遷移する', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await nav.getByRole('link', { name: 'アップロード' }).click();
    await expect(page).toHaveURL(/\/upload/);
    await expect(page.getByRole('heading', { name: 'ドキュメントアップロード', level: 1 })).toBeVisible();
  });

  test('サイドバーの「ドキュメント」リンクをクリックするとドキュメントページに遷移する', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await nav.getByRole('link', { name: 'ドキュメント' }).click();
    await expect(page).toHaveURL(/\/documents/);
    await expect(page.getByRole('heading', { name: 'ドキュメント管理', level: 1 })).toBeVisible();
  });

  test('サイドバーの「設定」リンクをクリックすると設定ページに遷移する', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await nav.getByRole('link', { name: '設定' }).click();
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.getByRole('heading', { name: '設定', level: 1 })).toBeVisible();
  });

  test('サイドバーの「チャット」リンクをクリックするとチャットページに遷移する', async ({ page }) => {
    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await nav.getByRole('link', { name: 'チャット' }).click();
    await expect(page).toHaveURL(/\/chat/);
  });
});
