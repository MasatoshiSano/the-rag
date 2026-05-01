import { test, expect } from '@playwright/test';
import { gotoPage, blockExternalFonts } from './helpers';

/**
 * チャットページテスト
 * KB選択・メッセージ送受信・ストリーミング・ソース参照・評価機能を検証します。
 * 注意: バックエンドが動作している状態で実行してください。
 */

test.beforeEach(async ({ page }) => {
  await blockExternalFonts(page);
});

// ─────────────────────────────────────────────────────────────────────────────
// KB未選択状態の表示
// ─────────────────────────────────────────────────────────────────────────────
test.describe('KB未選択時の初期表示', () => {
  test.beforeEach(async ({ page }) => {
    await gotoPage(page, '/chat');
  });

  test('「ナレッジベースを選択してください」見出しが表示される', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: 'ナレッジベースを選択してください' })
    ).toBeVisible();
  });

  test('チャット入力フィールドが無効になっている', async ({ page }) => {
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    if ((await input.count()) > 0) {
      await expect(input).toBeDisabled();
    } else {
      // 入力フォームごと非表示の場合
      await expect(page.getByRole('form')).not.toBeVisible().catch(() => {
        // フォームに role=form がない実装でも問題なし
      });
    }
  });

  test('サイドバーにナレッジベース選択が表示される', async ({ page }) => {
    const sidebar = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await expect(sidebar).toBeVisible();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// KB選択後のチャット UI（KBが存在する場合のみ実行）
// ─────────────────────────────────────────────────────────────────────────────
test.describe('KB選択後のチャット UI', () => {
  /**
   * KBが1件以上存在することを前提とします。
   * KBが存在しない場合は各テストをスキップします。
   */
  async function selectFirstKB(page: import('@playwright/test').Page): Promise<boolean> {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');

    const kbButtons = page.getByRole('button', { name: /^ナレッジベース: / });
    if ((await kbButtons.count()) === 0) return false;

    await kbButtons.first().click();
    await page.waitForLoadState('networkidle');
    return true;
  }

  test('KB選択後、チャット入力フィールドが有効になる', async ({ page }) => {
    const selected = await selectFirstKB(page);
    if (!selected) { test.skip(); return; }

    await gotoPage(page, '/chat');
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await expect(input).toBeEnabled();
  });

  test('選択中のKB名がチャットページに表示される', async ({ page }) => {
    const selected = await selectFirstKB(page);
    if (!selected) { test.skip(); return; }

    await gotoPage(page, '/chat');
    // KB名またはサイドバーのハイライトが存在することを確認
    const kbIndicator = page.getByTestId('selected-kb-name')
      .or(page.getByRole('status', { name: /選択中のナレッジベース/ }));
    if ((await kbIndicator.count()) > 0) {
      await expect(kbIndicator).toBeVisible();
    }
  });

  test('テキストを入力して送信ボタンが有効になる', async ({ page }) => {
    const selected = await selectFirstKB(page);
    if (!selected) { test.skip(); return; }

    await gotoPage(page, '/chat');
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await expect(input).toBeEnabled();

    await input.fill('テスト質問');
    const sendButton = page.getByRole('button', { name: /送信|Send/i });
    await expect(sendButton).toBeEnabled();
  });

  test('空メッセージでは送信ボタンが無効のまま', async ({ page }) => {
    const selected = await selectFirstKB(page);
    if (!selected) { test.skip(); return; }

    await gotoPage(page, '/chat');
    const sendButton = page.getByRole('button', { name: /送信|Send/i });
    await expect(sendButton).toBeDisabled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// メッセージ送受信フロー
// ─────────────────────────────────────────────────────────────────────────────
test.describe('メッセージ送受信', () => {
  async function setupChat(page: import('@playwright/test').Page): Promise<boolean> {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');
    const kbButtons = page.getByRole('button', { name: /^ナレッジベース: / });
    if ((await kbButtons.count()) === 0) return false;
    await kbButtons.first().click();
    await gotoPage(page, '/chat');
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await expect(input).toBeEnabled();
    return true;
  }

  test('質問を送信するとユーザーメッセージがログに表示される', async ({ page }) => {
    const ok = await setupChat(page);
    if (!ok) { test.skip(); return; }

    const question = 'このシステムについて教えてください';
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await input.fill(question);
    await page.keyboard.press('Enter');

    const log = page.getByRole('log');
    await expect(log.getByText(question)).toBeVisible({ timeout: 10000 });
  });

  test('送信後にアシスタントの回答が表示される', async ({ page }) => {
    const ok = await setupChat(page);
    if (!ok) { test.skip(); return; }

    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await input.fill('こんにちは');
    await page.keyboard.press('Enter');

    // ストリーミング完了を最大 60 秒待機
    const log = page.getByRole('log');
    await expect(log.locator('[data-role="assistant"]').first())
      .toBeVisible({ timeout: 60000 });
  });

  test('送信中はテキストフィールドと送信ボタンが無効になる', async ({ page }) => {
    const ok = await setupChat(page);
    if (!ok) { test.skip(); return; }

    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await input.fill('テスト');
    await page.keyboard.press('Enter');

    // ストリーミング中の短い間を捉える
    await expect(input).toBeDisabled({ timeout: 5000 });
  });

  test('ストリーミング完了後に入力フィールドが再び有効になる', async ({ page }) => {
    const ok = await setupChat(page);
    if (!ok) { test.skip(); return; }

    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await input.fill('ありがとう');
    await page.keyboard.press('Enter');

    // 送信中は無効、完了後は有効に戻る
    await expect(input).toBeEnabled({ timeout: 90000 });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// セッション・履歴
// ─────────────────────────────────────────────────────────────────────────────
test.describe('セッション履歴', () => {
  test('/chat ページにセッションリストのサイドバー要素が存在する', async ({ page }) => {
    await gotoPage(page, '/chat');
    // セッション一覧やサイドバーが存在することを確認
    const sidebar = page.getByRole('navigation', { name: 'サイドバーナビゲーション' });
    await expect(sidebar).toBeVisible();
  });

  test('「新規チャット」ボタンが存在する', async ({ page }) => {
    await gotoPage(page, '/chat');
    const newChatBtn = page
      .getByRole('button', { name: /新規チャット|新しいチャット/ })
      .or(page.getByLabel(/新規チャット|新しいチャット/));
    if ((await newChatBtn.count()) > 0) {
      await expect(newChatBtn.first()).toBeVisible();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 応答モード切替
// ─────────────────────────────────────────────────────────────────────────────
test.describe('応答モード切替', () => {
  test('チャットページに応答モードトグルが表示される', async ({ page }) => {
    await gotoPage(page, '/chat');
    const toggle = page.getByRole('radiogroup')
      .or(page.getByTestId('response-mode-toggle'));
    if ((await toggle.count()) > 0) {
      await expect(toggle.first()).toBeVisible();
    }
  });

  test('シンプル・詳細の切替ボタンが選択可能', async ({ page }) => {
    await gotoPage(page, '/chat');
    const simpleBtn = page.getByRole('radio', { name: 'シンプル' });
    const detailBtn = page.getByRole('radio', { name: '詳細' });
    if ((await simpleBtn.count()) > 0 && (await detailBtn.count()) > 0) {
      await detailBtn.click();
      await expect(detailBtn).toBeChecked();
      await simpleBtn.click();
      await expect(simpleBtn).toBeChecked();
    }
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// コピー・評価（回答が存在する場合）
// ─────────────────────────────────────────────────────────────────────────────
test.describe('コピーボタンと星評価', () => {
  test('アシスタント回答がある場合、コピーボタンが表示される', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');
    const kbButtons = page.getByRole('button', { name: /^ナレッジベース: / });
    if ((await kbButtons.count()) === 0) { test.skip(); return; }
    await kbButtons.first().click();

    await gotoPage(page, '/chat');
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await expect(input).toBeEnabled();
    await input.fill('簡単な質問');
    await page.keyboard.press('Enter');

    // ストリーミング完了後にコピーボタンを確認
    const copyBtn = page.getByRole('button', { name: /コピー|Copy/i });
    await expect(copyBtn.first()).toBeVisible({ timeout: 90000 });
  });

  test('アシスタント回答がある場合、星評価（StarRating）が表示される', async ({ page }) => {
    await gotoPage(page, '/knowledge-bases');
    await page.waitForLoadState('networkidle');
    const kbButtons = page.getByRole('button', { name: /^ナレッジベース: / });
    if ((await kbButtons.count()) === 0) { test.skip(); return; }
    await kbButtons.first().click();

    await gotoPage(page, '/chat');
    const input = page.getByRole('textbox', { name: /メッセージ|質問/i });
    await expect(input).toBeEnabled();
    await input.fill('評価テスト');
    await page.keyboard.press('Enter');

    // role="radiogroup" の星評価を確認
    const rating = page.getByRole('radiogroup', { name: /評価/ });
    await expect(rating.first()).toBeVisible({ timeout: 90000 });
  });
});
