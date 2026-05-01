// Chat API: メッセージ送信・履歴取得・評価

import { apiClient } from "./client";
import type { Message } from "../types/message";

export interface SendMessageRequest {
  sessionId: string;
  content: string;
  knowledgeBaseId: string;
  inputType: "text" | "voice";
}

export interface SendMessageResponse {
  messageId: string;
  sessionId: string;
}

/** ユーザーメッセージを送信し、生成された assistant メッセージの ID を返す（ストリーミング応答が必要な場合は SSE クライアントを利用する） */
export async function sendMessage(
  request: SendMessageRequest
): Promise<SendMessageResponse> {
  return apiClient.post<SendMessageResponse>("/chat/messages", { ...request });
}

/** 指定セッションに紐づくメッセージ履歴を時系列で取得する */
export async function getMessages(sessionId: string): Promise<Message[]> {
  return apiClient.get<Message[]>(`/chat/sessions/${sessionId}/messages`);
}

/** メッセージに評価値（thumbs up/down）を付与する */
export async function rateMessage(
  messageId: string,
  rating: number
): Promise<void> {
  return apiClient.put<void>(`/messages/${messageId}/rating`, { rating });
}
