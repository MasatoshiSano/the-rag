// Knowledge Bases API: CRUD + favorites management

import { apiClient } from "./client";
import type { KnowledgeBase, CreateKBRequest } from "../types/knowledge-base";

/** 全ナレッジベースを取得する */
export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  return apiClient.get<KnowledgeBase[]>("/knowledge-bases");
}

/** お気に入りナレッジベースを取得する */
export async function getFavoriteKnowledgeBases(): Promise<KnowledgeBase[]> {
  return apiClient.get<KnowledgeBase[]>("/knowledge-bases/favorites");
}

/** 指定IDのナレッジベースを取得する */
export async function getKnowledgeBase(id: string): Promise<KnowledgeBase> {
  return apiClient.get<KnowledgeBase>(`/knowledge-bases/${id}`);
}

/** ナレッジベースを新規作成する */
export async function createKnowledgeBase(
  request: CreateKBRequest
): Promise<KnowledgeBase> {
  return apiClient.post<KnowledgeBase>(
    "/knowledge-bases",
    request as unknown as Record<string, unknown>
  );
}

/** ナレッジベースを更新する */
export async function updateKnowledgeBase(
  id: string,
  request: Partial<CreateKBRequest>
): Promise<KnowledgeBase> {
  return apiClient.put<KnowledgeBase>(
    `/knowledge-bases/${id}`,
    request as unknown as Record<string, unknown>
  );
}

/** ナレッジベースを削除する（カスケード削除） */
export async function deleteKnowledgeBase(id: string): Promise<void> {
  return apiClient.delete<void>(`/knowledge-bases/${id}`);
}

/** ナレッジベースをお気に入りに追加する */
export async function addFavorite(id: string): Promise<void> {
  return apiClient.post(`/knowledge-bases/${id}/favorite`);
}

/** ナレッジベースのお気に入りを解除する */
export async function removeFavorite(id: string): Promise<void> {
  return apiClient.delete<void>(`/knowledge-bases/${id}/favorite`);
}
