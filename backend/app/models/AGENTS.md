<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# models

## Purpose
SQLAlchemy 2.0 declarative ORM モデルの定義。`Base.metadata.create_all` で参照されるため、新規モデル追加時は必ずこのモジュールに集約する。datetime は ISO 8601 文字列、JSON は文字列として TEXT 型カラムに格納するのが本リポジトリの規約。

## Key Files
| File | Description |
|------|-------------|
| `database.py` | 全 ORM テーブル: `User`, `UserBehavior`, `UserMemory`, `KnowledgeBase`, `KnowledgeBaseFavorite`, `Session`, `Message`, `Document`, `DocumentTag`, `ChatOutput`, `OracleQueryTemplate`, `MasterSite`, `MasterLine`, `MasterProcess`, `GitHubSource`, `GiteaSource`, `FolderSource` |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- カラム型は `Text` / `Integer` / `REAL` のみ使う（SQLite 互換のため）。`DateTime` 型は使わず ISO 8601 文字列を `Text` で保持する。
- リレーションは双方向の `relationship(... back_populates=...)` を必ず張る。`cascade="all, delete-orphan"` は `KnowledgeBase` 配下の子テーブルなど依存関係に従う。
- 新カラム追加時は (1) `Mapped[...]` 宣言を追加 (2) `db.py:init_db` の `ALTER TABLE` フォールバックリストに `ADD COLUMN` を追加（既存 DB がある環境でも起動できるように）。
- `Document.status` は約 14 種の状態（`processing/converting/converted/tagging/tagged/confirmed/chunking/chunked/indexing/indexed/convert_failed/tag_failed/index_failed/permanent_failed/cancelled`）。コメントを最新に保つ。
- ID 型は基本 UUID 文字列（`Text`）。`User.id` はフロントの localStorage UUID をそのまま使う。

### Testing Requirements
- `tests/conftest.py:db_session` がインメモリ SQLite に対し `Base.metadata.create_all` で全テーブルを作成する。新規モデルは追加と同時にテスト実行で検証可能になる。

### Common Patterns
- `__table_args__ = (UniqueConstraint(...),)` で複合ユニーク制約を表現。
- `__repr__` は短く識別可能な形（id + 主要フィールド 1〜2 個）に統一。

## Dependencies

### Internal
- `app/infrastructure/db.py:Base`

### External
- `sqlalchemy.orm` (Mapped/mapped_column/relationship/DeclarativeBase)

<!-- MANUAL: -->
