import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * アップロードページテスト
 * KBセレクターとドロップゾーンの動作を検証します。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

test.describe('アップロードページの表示', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/upload');
    await page.waitForLoadState('networkidle');
  });

  test('ページ見出しが表示される', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'ドキュメントアップロード', level: 1 })).toBeVisible();
  });

  test('ナレッジベースセレクターが表示される', async ({ page }) => {
    await expect(page.getByRole('combobox', { name: 'ナレッジベース' })).toBeVisible();
  });

  test('「ファイルを選択」セクションが表示される', async ({ page }) => {
    // アップロード方法タブの「ファイル」トリガーが存在することを確認
    await expect(page.getByRole('tab', { name: 'ファイル' })).toBeVisible();
  });

  test('KB未選択時に注意メッセージが表示される', async ({ page }) => {
    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    await select.selectOption('');
    await expect(page.getByText('アップロード前にナレッジベースを選択してください。')).toBeVisible();
  });
});

test.describe('ナレッジベースセレクター', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/upload');
    await page.waitForLoadState('networkidle');
  });

  test('KBセレクターのデフォルト値がプレースホルダー', async ({ page }) => {
    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    const selectedValue = await select.inputValue();
    expect(selectedValue).toBe('');
  });

  test('KBが存在する場合はセレクターに選択肢が表示される', async ({ page }) => {
    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    const options = select.locator('option');
    await expect(options).not.toHaveCount(0);
    await expect(select.locator('option[value=""]')).toContainText('ナレッジベースを選択');
  });

  test('KBを選択するとセレクターの値が変わる', async ({ page }) => {
    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    const options = await select.locator('option').all();

    if (options.length <= 1) {
      test.skip();
      return;
    }

    const firstKbOption = options[1];
    const firstKbValue = await firstKbOption.getAttribute('value');
    if (!firstKbValue) {
      test.skip();
      return;
    }

    await select.selectOption(firstKbValue);
    await expect(select).toHaveValue(firstKbValue);

    await expect(page.getByText('アップロード前にナレッジベースを選択してください。')).not.toBeVisible();
  });
});

test.describe('ドロップゾーン', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/upload');
    await page.waitForLoadState('networkidle');
  });

  test('KB未選択時はドロップゾーンが aria-disabled="true" の状態', async ({ page }) => {
    // 「ファイル」タブをクリックしてDropZoneを表示
    await page.getByRole('tab', { name: 'ファイル' }).click();

    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    await select.selectOption('');

    const dropZone = page.getByRole('button', { name: 'ファイルをドラッグ＆ドロップまたはクリックして選択' });
    await expect(dropZone).toHaveAttribute('aria-disabled', 'true');
  });

  test('ドロップゾーンに対応ファイル形式のテキストが表示される', async ({ page }) => {
    await page.getByRole('tab', { name: 'ファイル' }).click();
    await expect(page.getByText(/対応形式:/)).toBeVisible();
    await expect(page.getByText(/pdf/)).toBeVisible();
  });

  test('ドロップゾーンにファイル数の上限が表示される', async ({ page }) => {
    await page.getByRole('tab', { name: 'ファイル' }).click();
    await expect(page.getByText(/最大 20 ファイル/)).toBeVisible();
  });
});
