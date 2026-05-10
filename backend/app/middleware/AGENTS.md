<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# middleware

## Purpose
FastAPI 依存関数として実装される認証・認可ヘルパ。現状は外部連携 API（`/api/external/*`）向けの API キー検証のみ。

## Key Files
| File | Description |
|------|-------------|
| `api_key.py` | `verify_api_key` 依存関数。`X-API-Key` ヘッダーを `config.API_KEYS` と照合し、不一致なら 403 |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- ここは Starlette `Middleware` ではなく FastAPI **依存関数** を置く場所。`Depends(verify_api_key)` でルーターに注入する使い方。
- API キーは `config.API_KEYS` のリスト一致なので、新しいキーの発行は環境変数 `API_KEYS` の更新で行う（`config.py` のデフォルトは `["the-rag-default-key"]`）。
- 内部 API のユーザー識別は `X-User-Id` ヘッダーで、こちらは認証ではなく単なる識別。各ルーターで `Header()` で取得する。

### Testing Requirements
- API キー認証付きエンドポイントは `tests/test_api_*` 内で `headers={"X-API-Key": "the-rag-default-key"}` を送信して検証する。

### Common Patterns
- 失敗時は `HTTPException(status_code=403, detail="...")` を raise（Bearer 認証ではないので 401 ではなく 403）。

## Dependencies

### Internal
- `app/infrastructure/config.py`

### External
- `fastapi`

<!-- MANUAL: -->
