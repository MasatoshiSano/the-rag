<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# hooks

## Purpose
カスタム React フック。現状はチャットストリーミング制御の 1 つだけ。

## Key Files
| File | Description |
|------|-------------|
| `useStreamChat.ts` | `api/sse.ts:streamChatResponse` をラップし、SSE イベントごとに `chatStore` / `outputStore` を更新するフック。`SseStatus/Token/Complete/Error/Session/AgenticStep` 各イベントを `switch` で処理 |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- 新しい SSE イベントを追加する場合は `api/sse.ts` の型 → このフックの switch 分岐 → 必要ならストアの slice の順に更新する。
- 中断（cancel）は `AbortController` でフェッチを切る。`isStreaming` フラグの解除を忘れると UI が固まる。

## Dependencies

### Internal
- `../api/sse`, `../api/chat`
- `../stores/{chat,kb,user,output}Store`
- `../types/{message,output}`

### External
- `react`, `react-router-dom`

<!-- MANUAL: -->
