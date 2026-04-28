// Sessions API: セッションの一覧・詳細・削除・検索

import { apiClient } from "./client";
import type { Session, SessionSearchResult } from "../types/session";

export interface SessionListParams {
  limit?: number;
  offset?: number;
  knowledge_base_id?: string;
}

export interface SessionMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SessionSource[] | null;
  rating: number | null;
  input_type: string;
  response_mode: string | null;
  is_cancelled: boolean;
  created_at: string;
  has_output: boolean;
}

export interface SessionSource {
  document_id: string;
  document_name?: string;
  file_name?: string;
  section_title?: string;
  chunk_index?: number;
  score: number;
  snippet?: string;
}

export interface SessionWithMessages extends Session {
  messages: SessionMessage[];
}

interface SessionListResponse {
  sessions: Session[];
  total: number;
}

/** セッション一覧を取得する（ページネーション・KB絞り込み対応） */
export async function getSessions(
  params: SessionListParams = {}
): Promise<Session[]> {
  const { limit = 20, offset = 0, knowledge_base_id } = params;
  const query = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (knowledge_base_id) {
    query.set("knowledge_base_id", knowledge_base_id);
  }
  const response = await apiClient.get<SessionListResponse>(`/sessions?${query.toString()}`);
  return response.sessions;
}

/** 指定IDのセッション詳細（メッセージ付き）を取得する */
export async function getSession(session_id: string): Promise<SessionWithMessages> {
  return apiClient.get<SessionWithMessages>(`/sessions/${session_id}`);
}

/** 新しいセッションを作成する（チャット時に自動作成されるが、事前作成にも使用） */
export async function createSession(
  knowledge_base_id: string,
  title?: string
): Promise<Session> {
  return apiClient.post<Session>("/sessions", {
    knowledge_base_id,
    ...(title !== undefined ? { title } : {}),
  });
}

/** セッションを削除する */
export async function deleteSession(session_id: string): Promise<void> {
  return apiClient.delete<void>(`/sessions/${session_id}`);
}

interface SessionSearchResponse {
  query: string;
  results: SessionSearchResult[];
}

/** キーワードでセッションを全文検索する */
export async function searchSessions(
  query: string,
  knowledge_base_id?: string
): Promise<SessionSearchResult[]> {
  const params = new URLSearchParams({ q: query });
  if (knowledge_base_id) {
    params.set("knowledge_base_id", knowledge_base_id);
  }
  const response = await apiClient.get<SessionSearchResponse>(
    `/sessions/search?${params.toString()}`
  );
  return response.results;
}
