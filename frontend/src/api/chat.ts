// Chat API: send messages and manage RAG responses
// TODO: Implement chat endpoints

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

/**
 * TODO: Send a user message and get the assistant response.
 * For streaming, use the SSE client instead.
 */
export async function sendMessage(
  _request: SendMessageRequest
): Promise<SendMessageResponse> {
  // TODO: implement
  return apiClient.post<SendMessageResponse>("/chat/messages", _request as unknown as Record<string, string>);
}

/**
 * TODO: Get all messages for a session.
 */
export async function getMessages(_sessionId: string): Promise<Message[]> {
  // TODO: implement
  return apiClient.get<Message[]>(`/chat/sessions/${_sessionId}/messages`);
}

/**
 * TODO: Rate a message (thumbs up/down).
 */
export async function rateMessage(
  _messageId: string,
  _rating: number
): Promise<void> {
  // TODO: implement
  return apiClient.put<void>(`/messages/${_messageId}/rating`, { rating: _rating });
}
