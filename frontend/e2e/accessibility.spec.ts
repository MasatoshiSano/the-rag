import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * アクセシビリティテスト (WCAG 2.2 AA)
 * ランドマーク・スキップリンク・フォームラベル・キーボード操作を検証します。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

const PAGES = [
  { path: '/chat', name: 'チャット' },
  { path: '/upload', name: 'アップロード' },
  { path: '/documents', name: 'ドキュメント管理' },
  { path: '/knowledge-bases', name: 'ナレッジベース' },
  { path: '/settings', name: '設定' },
];

test.describe('スキップリンク', () => {
  for (const { path, name } of PAGES) {
    test(`${name}ページにスキップリンクが存在する`, async ({ page }) => {
      await gotoPage(page, path);
      const skipLink = page.getByRole('link', { name: 'メインコンテンツへスキップ' });
      await expect(skipLink).toBeAttached();
      await expect(skipLink).toHaveAttribute('href', '#main-content');
    });
  }

  test('スキップリンクにフォーカスすると表示される（AppShell）', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');

    await page.keyboard.press('Tab');

    const skipLink = page.getByRole('link', { name: 'メインコンテンツへスキップ' });
    await expect(skipLink).toBeFocused();
  });
});

test.describe('ランドマーク領域', () => {
  test('AppShell に banner ランドマークが存在する', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const banner = page.getByRole('banner');
    await expect(banner).toBeVisible();
  });

  test('AppShell に navigation ランドマークが存在する', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await expect(nav).toBeVisible();
  });

  test('各ページに main ランドマークが存在する', async ({ page }) => {
    for (const { path } of PAGES) {
      await gotoPage(page, path);
      await page.waitForLoadState('networkidle');

      const main = page.getByRole('main');
      await expect(main).toBeVisible();
    }
  });

  test('ドキュメント管理ページの main に id="main-content" がある', async ({ page }) => {
    await gotoPage(page, '/documents');
    await expect(page.locator('#main-content')).toBeAttached();
  });
});

test.describe('フォームのアクセシビリティ', () => {
  test('アップロードページのナレッジベースセレクターにラベルが紐付いている', async ({ page }) => {
    await gotoPage(page, '/upload');
    await page.waitForLoadState('networkidle');

    const select = page.getByRole('combobox', { name: 'ナレッジベース' });
    await expect(select).toBeVisible();
    await expect(select).toHaveAttribute('id', 'kb-select');

    const label = page.locator('label[for="kb-select"]');
    await expect(label).toBeAttached();
  });

  test('ドキュメントページのナレッジベースセレクターにラベルが紐付いている', async ({ page }) => {
    await gotoPage(page, '/documents');
    await page.waitForLoadState('networkidle');

    const select = page.locator('#docs-kb-select');
    await expect(select).toBeAttached();

    const label = page.locator('label[for="docs-kb-select"]');
    await expect(label).toBeAttached();
  });

  test('KBフォームダイアログで名前フィールドにラベルが紐付いている', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    const nameInput = dialog.getByLabel('名前');
    await expect(nameInput).toHaveAttribute('aria-required', 'true');
  });

  test('設定ページのニックネームフィールドにラベルが紐付いている', async ({ page }) => {
    await gotoPage(page, '/settings');
    await page.waitForLoadState('networkidle');

    const nicknameInput = page.getByRole('textbox', { name: 'ニックネーム' });
    await expect(nicknameInput).toBeVisible();
  });

  test('個人辞書の個人用語フィールドにラベルが紐付いている', async ({ page }) => {
    await gotoPage(page, '/settings');
    await page.waitForLoadState('networkidle');

    await expect(page.getByLabel('個人用語')).toBeVisible();
    await expect(page.getByLabel('マスターキー')).toBeVisible();
  });
});

test.describe('キーボード操作のアクセシビリティ', () => {
  test('サイドバーのナビゲーションリンクがキーボードでフォーカス可能', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const nav = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    const links = nav.getByRole('link');
    const count = await links.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const link = links.nth(i);
      const tabIndex = await link.getAttribute('tabindex');
      expect(tabIndex === null || parseInt(tabIndex, 10) >= 0).toBe(true);
    }
  });

  test('KBフォームダイアログを Escape キーで閉じられる', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
  });

  test('KB削除確認ダイアログを Escape キーで閉じられる', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const deleteButtons = page.getByRole('button', { name: /を削除$/ });
    const count = await deleteButtons.count();

    if (count === 0) {
      test.skip();
      return;
    }

    await deleteButtons.first().click();
    const alertDialog = page.getByRole('alertdialog');
    await expect(alertDialog).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(alertDialog).not.toBeVisible();
  });

  test('ドロップゾーンがキーボード操作に対応している', async ({ page }) => {
    await gotoPage(page, '/upload');
    await page.waitForLoadState('networkidle');

    const dropZone = page.getByRole('button', { name: 'ファイルをドラッグ＆ドロップまたはクリックして選択' });
    await expect(dropZone).toBeVisible();

    const tabIndex = await dropZone.getAttribute('tabindex');
    expect(['-1', '0']).toContain(tabIndex);
  });

  test('KBカードがキーボードでフォーカスおよびクリック可能', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const cards = page.getByRole('button', { name: /^ナレッジベース: / });
    const count = await cards.count();

    if (count === 0) {
      test.skip();
      return;
    }

    const firstCard = cards.first();
    await expect(firstCard).toHaveAttribute('tabindex', '0');
  });
});

test.describe('ARIA ライブリージョン', () => {
  test('チャットページのローディング状態に aria-live 属性が設定されている', async ({ page }) => {
    await gotoPage(page, '/chat');
    const statusEl = page.locator('[role="status"][aria-live="polite"]').first();
    await expect(statusEl).toBeAttached();
  });

  test('ナレッジベースページにステータス表示用の領域が存在する', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    // ローディング中は aria-label="ナレッジベースを読み込み中" が表示される
    // 読み込み完了後は aria-label="ナレッジベース一覧" region が表示される
    const region = page.getByRole('region', { name: /ナレッジベース/ });
    await expect(region.first()).toBeAttached();
  });
});

test.describe('ダイアログのアクセシビリティ', () => {
  test('KB作成ダイアログに aria-modal="true" が設定されている', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  test('KB作成ダイアログが開いたとき名前フィールドにフォーカスが移る', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await page.waitForTimeout(100);
    const nameInput = dialog.getByLabel('名前');
    await expect(nameInput).toBeFocused();
  });
});
