---
title: "Claude Code Skillの作り方 — zipファイルからグローバルスキルを作成・配布する"
emoji: "🛠️"
type: "tech"
topics: ["Claude Code", "AI Agent", "Skill", "CLI", "Productivity"]
published: true
category: "HowTo"
date: "2026-04-28"
description: "Claude Codeのスキル機構を使って、技術ブログ執筆ワークフローをグローバルスキルとしてパッケージ化・全プロジェクトで共有する方法を実例付きで解説"
---

## はじめに

Claude Codeでプロジェクト作業をしていると、特定のドメイン知識や業務ワークフローを何度も手動で説明することになります。

「毎回、ブログ執筆の手順を書き直さなくちゃいけない」
「複数プロジェクトで同じツール操作を何度も説明している」

こうした課題を解決するのが**スキル（Skill）** です。

Claude Codeのスキル機構は、専門知識やワークフローをパッケージ化し、`~/.claude/skills/` に配置することで、全プロジェクトで再利用可能なコマンドに変身させます。

本記事では、技術ブログ執筆スキルを実例に、スキルの作成方法から配布まで、実装パターンを深掘りします。

## スキルとは何か

### スキルの役割

Claude Codeの**スキル**は、以下の2つを実現します：

1. **ドメイン知識のカプセル化**
   - 業務や技術領域の固有ロジックを1ファイルにまとめる
   - CLAUDE.md や個別プロジェクト設定に依存しない独立した定義

2. **グローバルコマンド化**
   - `~/.claude/skills/` に配置した時点で、全プロジェクトから `/skill-name` で呼び出し可能
   - セッション間でも永続化される

### スキルが活躍する場面

- **テンプレート・ワークフロー**: ブログ執筆、技術提案書作成、議事録フォーマット
- **ドメイン固有ツール**: AWS操作、データベース管理、テスト戦略
- **複数プロジェクト共有**: 組織全体のコーディング規約、設計パターン解説

## スキルの基本構造

### ディレクトリレイアウト

グローバルスキルは以下の構成を推奨します：

```
~/.claude/skills/
└── tech-blog/
    ├── SKILL.md              # スキル定義（必須）
    ├── references/           # 参照ドキュメント
    │   ├── seo-checklist.md
    │   ├── content-template.md
    │   └── keyword-research.md
    ├── scripts/              # 実行スクリプト
    │   ├── generate-frontmatter.js
    │   └── validate-metadata.js
    └── assets/               # テンプレート素材
        ├── frontmatter-template.yaml
        └── editorial-calendar.csv
```

### ファイルの役割

| ファイル | 用途 | ロード時期 |
|---------|------|---------|
| `SKILL.md` | スキルの定義・説明・実行ロジック | 常時（セッション開始時） |
| `references/` | 詳細な参考資料・チェックリスト | 必要に応じてClaudeが読む |
| `scripts/` | 自動化スクリプト・バリデータ | 実行時のみ |
| `assets/` | テンプレートファイル・マスターデータ | 参照時のみ |

## SKILL.md の書き方

### フロントマター

スキルメタデータはYAML形式で定義します：

```yaml
---
name: tech-blog
description: >
  技術的知見をブログ記事として投稿するスキル。

  使用タイミング：
  (1) /tech-blog コマンド実行時
  (2) ユーザーから「ブログ記事化して」と依頼された時
  (3) 技術ノートをブログポスト化する時

  サブコマンド：
  - /tech-blog：新規記事作成ウィザード
  - /tech-blog:seo：SEOメタデータ生成
  - /tech-blog:review：記事品質チェック
---
```

**重要**: `description` がスキルの**トリガー判定**に使われるため、ここに「いつ使うのか」「何ができるのか」を明確に記述する必要があります。CLAUDE.md に依存せず、スキル自体が自己完結していることが鉄則です。

### コンテンツ構成

SKILL.mdの本体は以下の3層を推奨します：

#### 第1層：概要（100行以内）

```markdown
## スキル概要

このスキルは、技術的知見を**SEO最適化されたブログ記事**として構造化するワークフローを提供します。

### できること

- ブログ記事の新規作成（フロントマター自動生成）
- SEOメタデータの生成・最適化
- 記事品質のチェック（文体・構成・キーワード密度）
- 複数記事の一括メタデータ管理

### ワークフロー全体

```
[テーマ決定]
    ↓
[キーワードリサーチ] → references/keyword-research.md 参照
    ↓
[記事執筆] → content-template.md 使用
    ↓
[SEOチェック] → /tech-blog:seo コマンド実行
    ↓
[品質レビュー] → /tech-blog:review で検証
    ↓
[発行]
```
```

#### 第2層：ユースケース別ガイド（200～300行）

各ユースケースに対して、「何をするのか」「どのコマンドを使うのか」「参考資料はどこか」を記述：

```markdown
## ユースケース1：新規ブログ記事を作成する

### 手順

1. `/tech-blog` コマンドで新規記事ウィザードを起動
2. 以下の情報をインタラクティブに入力：
   - **記事タイトル** （80字以内推奨）
   - **記事テーマ** （技術, 業界動向, 学習記など）
   - **対象読者** （初心者, 中級者, 上級者）
   - **コアキーワード** （3～5個）

3. スキルが以下を自動生成：
   - Frontmatter（メタデータ）
   - SEO向けメタディスクリプション（複数案）
   - 目次テンプレート
   - ブログ配信プラン案

### 参考資料

- **コンテンツテンプレート**: `references/content-template.md` を参照
- **キーワード調査**: `references/keyword-research.md` で検索ボリューム判定
- **SEOチェックリスト**: `references/seo-checklist.md` で最終確認

### 出力例

```yaml
---
title: "Claude Code Skillの作り方 — グローバルスキルのパッケージ化と配布"
emoji: "🛠️"
type: "tech"
topics: ["Claude Code", "AI Agent", "Skill", "Productivity"]
published: true
category: "HowTo"
date: "2026-04-28"
description: "Claude Codeのスキルをパッケージ化し、全プロジェクトで共有する実装パターン"
---
```

## ユースケース2：既存記事をSEO最適化する

このスキルの `/tech-blog:seo` コマンドで、既存記事のメタデータを分析・改善できます。

詳細は `references/seo-checklist.md` を参照してください。
```

#### 第3層：詳細リファレンス（100～150行）

スキルの詳細な使い方やトラブルシューティング：

```markdown
## 詳細リファレンス

### コマンド一覧

| コマンド | 機能 | 出力 |
|---------|------|------|
| `/tech-blog` | 新規記事ウィザード | Frontmatter + メタデータ案 |
| `/tech-blog:seo` | SEO メタデータ生成 | メタディスクリプション複数案 |
| `/tech-blog:review` | 記事品質チェック | 指摘項目リスト |

### よくある質問

**Q: 記事を外部サイトに投稿する場合、メタデータは調整すべき？**

A: はい。プラットフォームごとに推奨フォーマットが異なります。`references/platform-guide.md` で各プラットフォームの仕様を確認してください。

**Q: キーワード密度はどれくらいが適切？**

A: 推奨値は 1～3%。ただしテーマによって異なるため、`references/keyword-research.md` の「密度別分析」セクションで競合記事と比較してください。

### トラブルシューティング

**問題: SEOチェックが古いメタデータを参照している**

解決策: キャッシュをクリアして再実行
```sh
rm -rf ~/.claude/skills/tech-blog/.cache
/tech-blog:seo
```
```

### SKILL.md の分量目安

- **推奨**: 500行以内
- **理由**: ロード時間を短縮し、Claudeの文脈ウィンドウを効率化するため

500行を超える場合は、詳細内容を `references/` に移行してください。

## Progressive Disclosure パターン

スキルは3段階のロード機構を採用することで、必要な情報だけを段階的に提供します：

### 段階1: SKILL.md（常時ロード）

スキル呼び出し時、SKILL.md は常にロードされます。500行以内に要点をまとめます。

### 段階2: references/（オンデマンドロード）

ユーザーが「詳細を見たい」と指示した時点で、Claudeが自動的に該当ファイルを読み込みます：

```markdown
詳細な手順は `references/content-template.md` を確認してください
→ ユーザー同意 → Claudeが自動読み込み
```

### 段階3: scripts/（実行時のみ）

バリデーションやデータ処理が必要な場合、実行時にスクリプトを呼び出します：

```bash
node ~/.claude/skills/tech-blog/scripts/validate-metadata.js article.md
```

このパターンにより、初回起動は軽量に、詳細が必要なら段階的にロードできます。

## 実装例：tech-blog スキル

### SKILL.md（完全版）

```markdown
---
name: tech-blog
description: >
  技術的知見をSEO最適化されたブログ記事として構造化するスキル。
  テーマ選定からSEOチェックまで、執筆ワークフロー全体をサポートします。
---

## tech-blogスキル

### 概要

このスキルは以下をサポートします：

1. **新規記事作成**: 対話的なウィザードでメタデータを自動生成
2. **SEO最適化**: キーワード密度・メタディスクリプション・タイトルタグをチェック
3. **品質レビュー**: 文体・構成・完成度を自動評価
4. **複数記事管理**: メタデータの一括チェック

### クイックスタート

```bash
/tech-blog
```

対話形式で以下を入力：
- 記事タイトル（案）
- テーマ（技術/業界動向/学習記など）
- 対象読者レベル
- コアキーワード

スキルが Frontmatter と SEO メタデータ案を生成します。

### ワークフロー

```
[1] テーマ決定 → /tech-blog で新規記事を初期化
    ↓
[2] キーワードリサーチ → references/keyword-research.md で検索ボリューム確認
    ↓
[3] 記事執筆 → references/content-template.md で構成フォローアップ
    ↓
[4] SEOチェック → /tech-blog:seo でメタデータを検証
    ↓
[5] 品質レビュー → /tech-blog:review で最終チェック
    ↓
[6] 発行準備 → メタデータを確定、ブログプラットフォームに投稿
```

### サブコマンド

#### /tech-blog
新規ブログ記事を作成（対話的ウィザード）

**入力**: なし
**出力**: Frontmatter + SEO メタディスクリプション複数案

#### /tech-blog:seo
既存記事のSEOメタデータを検証・最適化

**入力**: 記事ファイルパス
**出力**: メタデータチェック結果 + 改善提案

#### /tech-blog:review
記事の品質をレビュー

**入力**: 記事ファイルパス
**出力**: 構成・文体・キーワード密度レポート

### 参考資料

詳細は以下を参照：

- **SEO チェックリスト** → `references/seo-checklist.md`
- **コンテンツテンプレート** → `references/content-template.md`
- **キーワード調査法** → `references/keyword-research.md`
- **プラットフォーム別ガイド** → `references/platform-guide.md`

### よくある質問

**Q: 既存プロジェクトの CLAUDE.md に依存するスキルは作れる？**

A: 可能ですが非推奨。スキルは独立している方が、複数プロジェクトで再利用しやすくなります。プロジェクト固有の設定が必要なら、CLAUDE.md ではなく、スキルの `assets/config.yaml` で管理してください。

**Q: スキルのバージョン管理は？**

A: スキルディレクトリに `.version` ファイルを配置し、メジャー・マイナーバージョンを管理できます。更新配布時は、既存スキルをバックアップしてから新しい zip を展開してください。

**Q: 複数プロジェクト間でスキルが共有されないことがある**

A: `~/.claude/skills/` が正しい位置にあるか、ファイル権限が適切か確認してください。セッション再開後も認識されない場合は、キャッシュをクリア：

```bash
rm -rf ~/.claude/skills/.cache
```

### トラブルシューティング

**スキルが呼び出されない**

→ `~/.claude/skills/tech-blog/SKILL.md` が存在するか確認
→ セッションを再開
→ `/tech-blog` で直接呼び出し

**スキル内の references が読み込まれない**

→ ファイルパスが相対パスになっているか確認
→ ファイル存在確認: `ls ~/.claude/skills/tech-blog/references/`
```

### references/ ディレクトリ

#### references/seo-checklist.md

```markdown
# SEO チェックリスト

## タイトルタグ（Title Tag）

- [ ] 60字以内（推奨50～59字）
- [ ] コアキーワードを含む
- [ ] 数字・括弧を含むと CTR 向上傾向
- [ ] 重複なし

**例**: 「Claude Code Skillの作り方 — zipファイルからグローバルスキルを作成・配布する」（40字）

## メタディスクリプション

- [ ] 160字以内（推奨155～160字）
- [ ] コアキーワードを含む
- [ ] 行動喚起（CTA）を含む
- [ ] 疑問形・数字を含むと CTR 向上

## キーワード密度

| 密度 | 評価 | 備考 |
|-----|------|------|
| 0.5～1% | 推奨 | 自然で SEO フレンドリー |
| 1～3% | 許容 | テーマによって調整 |
| 3～5% | 要注意 | オーバー最適化の兆候 |
| 5%以上 | NG | キーワードスタッフィング |

## 内部リンク

- [ ] 関連記事へのリンク 3～5個
- [ ] アンカーテキストはキーワード含む
- [ ] リンク先は 200 語以上の充実コンテンツ

## 見出し構造

- [ ] H1 は 1個のみ
- [ ] H2 は 3～5個
- [ ] H3 で詳細を階層化
- [ ] キーワードを含める

## コンテンツの質

- [ ] 1000字以上の充実度
- [ ] データ・引用で信頼性向上
- [ ] ユーザー意図に応える
- [ ] 更新日時を明記
```

#### references/content-template.md

```markdown
# ブログ記事テンプレート

このテンプレートに従うと、SEO 最適化と読みやすさが両立します。

## 構成（推奨）

```
1. リード（50～100字）
   ↓
2. 目次
   ↓
3. 本文（セクション分割）
   - H2: 3～5個
   - 各 H2 下に H3: 2～3個
   ↓
4. まとめ
   ↓
5. CTA（行動喚起）
```

## 各セクションの書き方

### リード（導入部）

読者の痛点を 1～2 文で述べ、記事が解決することを明示：

```
❌ 「このスキル機構は便利です」

✓ 「複数プロジェクトで同じワークフローを何度も説明していませんか？
   Claude Code のスキル機構なら、これを 1 度だけ定義してすべてのプロジェクトで共有できます。」
```

### セクション（H2）

各セクションは 200～400 字が目安。以下の構成を推奨：

```
## セクションタイトル

[簡潔な説明（1～2文）]

[具体例・コード例]

[重要ポイント（3 項目以内）]
```

### まとめ

記事の要点を 5 項目以内の箇条書きでまとめ、次のアクション（CTA）に導く。
```

### scripts/validate-metadata.js

```javascript
#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

/**
 * Frontmatter のメタデータを検証し、SEO 品質スコアを出力
 */

const filePath = process.argv[2];

if (!filePath) {
  console.error('Usage: node validate-metadata.js <article.md>');
  process.exit(1);
}

const content = fs.readFileSync(filePath, 'utf-8');
const match = content.match(/^---\n([\s\S]*?)\n---/);

if (!match) {
  console.error('Frontmatter not found');
  process.exit(1);
}

const frontmatter = match[1];
const titleMatch = frontmatter.match(/title:\s*"([^"]*)"/);
const descMatch = frontmatter.match(/description:\s*"([^"]*)"/);

const title = titleMatch ? titleMatch[1] : '';
const description = descMatch ? descMatch[1] : '';

let score = 100;
const issues = [];

// Title check
if (title.length < 30) {
  issues.push(`⚠️  タイトルが短い（${title.length}字）→ 50～60字推奨`);
  score -= 10;
}
if (title.length > 70) {
  issues.push(`⚠️  タイトルが長い（${title.length}字）→ 60字以内推奨`);
  score -= 10;
}

// Description check
if (description.length < 120) {
  issues.push(`⚠️  メタディスクリプションが短い（${description.length}字）→ 155～160字推奨`);
  score -= 15;
}
if (description.length > 165) {
  issues.push(`⚠️  メタディスクリプションが長い（${description.length}字）→ 160字以内推奨`);
  score -= 10;
}

console.log(`\n=== SEO メタデータ検証 ===\n`);
console.log(`📄 タイトル（${title.length}字）:\n   "${title}"\n`);
console.log(`📝 メタディスクリプション（${description.length}字）:\n   "${description}"\n`);

if (issues.length > 0) {
  console.log(`⚠️  指摘事項:\n`);
  issues.forEach(issue => console.log(`   ${issue}`));
} else {
  console.log(`✓ メタデータは最適化されています`);
}

console.log(`\n🎯 SEO スコア: ${score}/100\n`);
```

## グローバル配置方法

### ステップ1: スキルを zip 化

```bash
cd ~/.claude/skills/
zip -r tech-blog.zip tech-blog/
```

### ステップ2: 別環境で展開

```bash
# ダウンロードした tech-blog.zip をグローバルスキル ディレクトリに展開
unzip tech-blog.zip -d ~/.claude/skills/

# 確認
ls ~/.claude/skills/tech-blog/SKILL.md
```

### ステップ3: セッション再開

新規セッションを開始すると、`/tech-blog` コマンドが全プロジェクトで利用可能になります。

## スキル作成のベストプラクティス

### 1. 依存性を最小化する

**アンチパターン**：

```markdown
CLAUDE.md の以下の設定に依存します：
- `contentMarketingStyle`
- `blogPlatform`
```

**ベストプラクティス**：

```markdown
assets/config.yaml で設定可能：

blogPlatform: zenn
contentStyle: technical
```

スキル自体が独立していれば、どのプロジェクトでも使用できます。

### 2. ドメイン知識を徹底的に記述

```markdown
このスキルが前提とする知識：
- ブログ SEO の基本（タイトルタグ、メタディスクリプション、キーワード密度）
- Markdown フロントマター形式
- 日本語ブログプラットフォーム（Zenn, Qiita など）の特性
```

### 3. Progressive Disclosure の活用

```
SKILL.md（500行以内）
   ↓ ユーザー同意
references/seo-checklist.md（詳細項目）
   ↓ 実行要求
scripts/validate-metadata.js（自動化処理）
```

### 4. バージョン管理を考慮

```
tech-blog/
├── .version          # v1.2.0
├── CHANGELOG.md      # 更新履歴
└── SKILL.md
```

配布時は `.version` をインクリメントし、破壊的変更時はメジャーバージョンを上げます。

### 5. テストと検証

スキル公開前に複数プロジェクトで動作確認：

```bash
# プロジェクト A
cd ~/project-a
/tech-blog

# プロジェクト B
cd ~/project-b
/tech-blog

# プロジェクト C
cd ~/project-c
/tech-blog
```

## スキルの更新と配布

### 更新フロー

1. ローカルで `~/.claude/skills/tech-blog/` を修正
2. バージョンを `.version` に記録
3. `CHANGELOG.md` に変更内容を記述
4. zip 化: `zip -r tech-blog-v1.2.0.zip tech-blog/`
5. チームに配布

### 受信側のアップデート

```bash
# 既存スキルをバックアップ
cp -r ~/.claude/skills/tech-blog ~/.claude/skills/tech-blog-v1.1.0.bak

# 新しい zip を展開
unzip tech-blog-v1.2.0.zip -d ~/.claude/skills/

# 動作確認
/tech-blog
```

## おわりに

Claude Code のスキル機構は、単なる「コマンド化」ではなく、**ドメイン知識とワークフローの資産化**です。

本記事で紹介した tech-blog スキルの構造を参考に、あなたのプロジェクトで何度も出てくるワークフローをスキルとしてパッケージ化し、全体で共有することで、生産性が大きく向上します。

### ポイント整理

- **SKILL.md**: 500行以内で、スキルが自己完結する
- **Progressive Disclosure**: references → scripts の3段階ロード
- **依存性最小化**: CLAUDE.md ではなく、スキル内で設定完結
- **配布**: zip で簡単に共有可能

スキル作成は初期投資ですが、複数プロジェクトで何度も使われることを考えると、ROI は非常に高いです。

ぜひ、あなたのドメイン知識をスキルとして資産化してみてください。

---

## 関連リンク

- [Claude Code 公式ドキュメント](https://claude.ai/)
- [Skill フレームワーク](https://claude.ai/skills)
- [SEO ベストプラクティス](https://developers.google.com/search/docs)

