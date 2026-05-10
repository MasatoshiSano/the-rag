// Chat API: メッセージ評価。
// チャット送受信は SSE クライアント（api/sse.ts）、履歴取得は api/sessions.ts を使う。

import { apiClient } from "./client";

interface RatingResponse {
  message_id: string;
  rating: number;
}

/** メッセージに 1〜5 の評価を付ける（PUT /api/messages/{id}/rating）。 */
export async function rateMessage(messageId: string, rating: number): Promise<void> {
  await apiClient.put<RatingResponse>(`/messages/${messageId}/rating`, { rating });
}
