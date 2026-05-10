<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# chat

## Purpose
チャット画面の構成パーツ。メッセージ送信入力、メッセージ吹き出し、参照ソース表示、コピー、評価（星）、音声入力ボタンを提供する。

## Key Files
| File | Description |
|------|-------------|
| `ChatInput.tsx` | メッセージ送信フォーム（テキスト + 音声ボタン） |
| `MessageList.tsx` | 仮想スクロール無しの素朴なメッセージリスト。新着で末尾にスクロール |
| `MessageBubble.tsx` | ロール別吹き出し。Markdown レンダリング・コピー・星評価・参照ソースリンクを内包 |
| `SourceList.tsx` | メッセージ末尾の参照ソース一覧（クリックで `SourcePanel` を開く） |
| `SourcePanel.tsx` | 右ペイン形式のソース詳細表示 |
| `CopyButton.tsx` | クリップボードコピーボタン |
| `StarRating.tsx` | 1〜5 星のメッセージ評価 UI |
| `VoiceButton.tsx` | Web Speech API で音声入力 |
| `index.ts` | barrel export |

## For AI Agents

### Working In This Directory
- ストリーミング状態は `useChatStore`（`stores/chatStore.ts`）の `streamingStatus` / `agenticSteps` から読み取り、`hooks/useStreamChat.ts` が更新する。
- ソースパネルの開閉は `useSourceStore`、出力パネルは `useOutputStore` を使い分ける（両方を並べることがある）。
- `VoiceButton` はブラウザ依存（`SpeechRecognition`）。サポート外環境ではボタンを無効化する。

### Common Patterns
- メッセージ Markdown レンダラはコードブロックの言語ハイライトを軽く行う程度。複雑なシンタックスハイライトは導入しない方針。

## Dependencies

### Internal
- `../../stores/{chat,source,output}Store`
- `../../api/chat`, `../../api/sse`
- `../../hooks/useStreamChat`

### External
- `@serendie/ui`

<!-- MANUAL: -->
