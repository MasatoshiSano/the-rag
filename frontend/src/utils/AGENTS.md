<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# utils

## Purpose
横断的なユーティリティ関数。現状は匿名ユーザー識別の fingerprint 生成のみ。

## Key Files
| File | Description |
|------|-------------|
| `fingerprint.ts` | `getOrCreateFingerprint()` — `localStorage` キー `the-rag-user-id` から UUID を取得、無ければ `crypto.randomUUID()` で生成して保存 |
| `index.ts` | barrel export（一部 TODO の export を計画中） |

## For AI Agents

### Working In This Directory
- `localStorage` キー `the-rag-user-id` は `api/client.ts` と `api/sse.ts` でも参照されている定数。変更時は 3 箇所同時に直す。
- 同期 API として実装されている（再代入安全 / 副作用のみ `localStorage`）。テストでは `vi.spyOn(window, "localStorage")` でモックすると安全。

## Dependencies

### External
- `crypto.randomUUID()`（ブラウザ Web Crypto API）

<!-- MANUAL: -->
