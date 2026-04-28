import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * 設定ページテスト
 * 検索設定・プロフィール・個人辞書・行動プロファイルセクションを検証します。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

test.describe('設定ページの表示', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/settings');
    await page.waitForLoadState('networkidle');
  });

  test('ページ見出しが表示される', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '設定', level: 1 })).toBeVisible();
  });

  test('「検索設定」セクションが表示される', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '検索設定', level: 2 })).toBeVisible();
  });

  test('「プロフィール」セクションが表示される', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'プロフィール', level: 2 })).toBeVisible();
  });

  test('全セクションが同一ページに存在する', async ({ page }) => {
    const headings = page.getByRole('heading', { level: 2 });
    const texts = await headings.allTextContents();
    expect(texts).toContain('検索設定');
    expect(texts).toContain('プロフィール');
  });
});

test.describe('検索設定セクション', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/settings');
    await page.waitForLoadState('networkidle');
  });

  test('リランクスイッチが表示される', async ({ page }) => {
    await expect(page.getByText('リランク')).toBeVisible();
  });

  test('ハイブリッド検索スイッチが表示される', async ({ page }) => {
    await expect(page.getByText('ハイブリッド検索')).toBeVisible();
  });

  test('応答モードラジオグループが表示される', async ({ page }) => {
    await expect(page.getByText('応答モード')).toBeVisible();
    await expect(page.getByRole('radio', { name: 'シンプル' })).toBeVisible();
    await expect(page.getByRole('radio', { name: '詳細' })).toBeVisible();
  });

  test('応答モード「詳細」を選択できる', async ({ page }) => {
    // Serendie RadioGroup はラベルテキストのクリックで切り替わる
    const radioGroup = page.getByRole('radiogroup');
    await radioGroup.getByText('詳細').click();
    await expect(page.getByRole('radio', { name: '詳細' })).toBeChecked();
  });

  test('応答モード「シンプル」を選択できる', async ({ page }) => {
    const radioGroup = page.getByRole('radiogroup');
    await radioGroup.getByText('詳細').click();
    await expect(page.getByRole('radio', { name: '詳細' })).toBeChecked();
    await radioGroup.getByText('シンプル').click();
    await expect(page.getByRole('radio', { name: 'シンプル' })).toBeChecked();
  });
});

test.describe('プロフィールセクション', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/settings');
    await page.waitForLoadState('networkidle');
  });

  test('ニックネームフィールドが表示される', async ({ page }) => {
    await expect(page.getByRole('textbox', { name: 'ニックネーム' })).toBeVisible();
  });

  test('ニックネームを入力すると保存ボタンが有効になる', async ({ page }) => {
    const nicknameInput = page.getByRole('textbox', { name: 'ニックネーム' });
    const saveButton = page.getByRole('button', { name: 'ニックネームを保存' });

    // 初期状態では保存ボタンは無効
    await expect(saveButton).toBeDisabled();

    // ニックネームを入力
    await nicknameInput.fill('テストユーザー');

    // 保存ボタンが有効になる
    await expect(saveButton).toBeEnabled();
  });

  test('ニックネームを保存できる', async ({ page }) => {
    const nicknameInput = page.getByRole('textbox', { name: 'ニックネーム' });
    const saveButton = page.getByRole('button', { name: 'ニックネームを保存' });

    await nicknameInput.fill('テストユーザー');
    await expect(saveButton).toBeEnabled();
    await saveButton.click();

    // 保存成功メッセージが表示される（3秒後に消える）
    await expect(page.getByRole('status').filter({ hasText: 'ニックネームを保存しました' })).toBeVisible();
  });
});

