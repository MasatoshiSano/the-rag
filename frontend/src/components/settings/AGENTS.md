<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# settings

## Purpose
設定画面のセクションコンポーネント。`/users/me` 系 API の値を編集する。

## Key Files
| File | Description |
|------|-------------|
| `ProfileInfo.tsx` | ニックネーム・行動プロファイル・ユーザーメモリの表示と編集 |
| `SearchSettings.tsx` | rerank・ハイブリッド検索・取得件数・応答モード・検索モード（normal/agentic）・エージェント最大反復回数の設定 |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- バックエンドの `User` モデルのカラム追加 → 型 (`types/user.ts`) → API (`api/users.ts`) → このコンポーネントへ反映、の順で同期する。
- 検索モードを `agentic` にすると `agentic_max_iterations` が有効になる。UI 側でモードに応じたフィールド表示制御を行う。

## Dependencies

### Internal
- `../../api/users`
- `../../types/user`
- `../../stores/userStore`

### External
- `@serendie/ui`

<!-- MANUAL: -->
