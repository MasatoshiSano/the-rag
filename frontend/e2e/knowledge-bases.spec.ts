import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * ナレッジベース管理テスト
 * KB の作成・編集・削除フローを検証します。
 * 注意: これらのテストはバックエンドが動作している状態で実行されます。
 * 各テストは独立して実行できるよう設計されています。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

test.describe('ナレッジベース一覧ページ', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');
  });

  test('ページが正しく表示される', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'ナレッジベース', level: 1 })).toBeVisible();
    await expect(page.getByRole('button', { name: '新しいナレッジベースを作成' })).toBeVisible();
  });

  test('「新規作成」ボタンをクリックするとフォームダイアログが開く', async ({ page }) => {
    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog', { name: 'ナレッジベースを作成' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'ナレッジベースを作成' })).toBeVisible();
  });
});

test.describe('ナレッジベースの作成', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');
  });

  test('KB名を入力して作成できる', async ({ page }) => {
    const kbName = `テストKB-${Date.now()}`;

    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // 名前フィールドに入力
    await dialog.getByLabel('名前').fill(kbName);

    // 説明フィールドに入力
    await dialog.getByLabel('説明').fill('テスト用の説明');

    // 送信
    await dialog.getByRole('button', { name: '作成' }).click();

    // ダイアログが閉じることを待機
    await expect(dialog).not.toBeVisible();

    // 作成されたKBカードが表示されることを確認
    await expect(page.getByRole('button', { name: `ナレッジベース: ${kbName}` })).toBeVisible();
  });

  test('名前なしでは作成できない（バリデーション）', async ({ page }) => {
    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // 名前フィールドを空のまま送信
    await dialog.getByRole('button', { name: '作成' }).click();

    // エラーメッセージが表示される
    await expect(dialog.getByRole('alert')).toBeVisible();
    await expect(dialog.getByText('名前を入力してください')).toBeVisible();

    // ダイアログは閉じない
    await expect(dialog).toBeVisible();
  });

  test('Escapeキーでダイアログを閉じられる', async ({ page }) => {
    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
  });

  test('「キャンセル」ボタンでダイアログを閉じられる', async ({ page }) => {
    await page.getByRole('button', { name: '新しいナレッジベースを作成' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    await dialog.getByRole('button', { name: 'キャンセル' }).click();
    await expect(dialog).not.toBeVisible();
  });
});

test.describe('ナレッジベースの編集', () => {
  /**
   * 編集テストでは、既存のKBが少なくとも1つ存在することを前提とします。
   * KBが存在しない場合はテストをスキップします。
   */
  test('KBが存在する場合、編集ボタンをクリックすると編集ダイアログが開く', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const editButtons = page.getByRole('button', { name: /を編集$/ });
    const count = await editButtons.count();

    if (count === 0) {
      test.skip();
      return;
    }

    await editButtons.first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('heading', { name: 'ナレッジベースを編集' })).toBeVisible();

    // 既存のKB名が入力されていることを確認
    const nameInput = dialog.getByLabel('名前');
    await expect(nameInput).not.toBeEmpty();

    // 「更新」ボタンが表示されている
    await expect(dialog.getByRole('button', { name: '更新' })).toBeVisible();
  });

  test('KBが存在する場合、説明を変更して保存できる', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const editButtons = page.getByRole('button', { name: /を編集$/ });
    const count = await editButtons.count();

    if (count === 0) {
      test.skip();
      return;
    }

    await editButtons.first().click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // 説明フィールドを更新
    const newDescription = `更新された説明 ${Date.now()}`;
    await dialog.getByLabel('説明').fill(newDescription);

    await dialog.getByRole('button', { name: '更新' }).click();

    // ダイアログが閉じることを確認
    await expect(dialog).not.toBeVisible();
  });
});

test.describe('ナレッジベースの削除', () => {
  test('削除ダイアログが表示され、キャンセルするとKBが残る', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const deleteButtons = page.getByRole('button', { name: /を削除$/ });
    const count = await deleteButtons.count();

    if (count === 0) {
      test.skip();
      return;
    }

    await deleteButtons.first().click();

    // 削除確認ダイアログが表示される
    const alertDialog = page.getByRole('alertdialog', { name: 'ナレッジベースを削除' });
    await expect(alertDialog).toBeVisible();
    await expect(alertDialog.getByText('関連するすべてのドキュメントとセッションも削除されます')).toBeVisible();

    // キャンセルをクリック
    await alertDialog.getByRole('button', { name: 'キャンセル' }).click();
    await expect(alertDialog).not.toBeVisible();

    // KBカードの数が変わっていないことを確認
    await expect(page.getByRole('button', { name: /を削除$/ })).toHaveCount(count);
  });
});
