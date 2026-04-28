// Users API: /users/me endpoints

import { apiClient } from "./client";
import type { User, UserBehavior, ProfileItem, UserMemoryItem } from "../types/user";

export interface UpdateSettingsPayload {
  nickname?: string;
  rerank_enabled?: boolean;
  hybrid_search_enabled?: boolean;
  retrieval_count?: number;
  response_mode?: "simple" | "detailed";
  search_mode?: "normal" | "agentic";
  agentic_max_iterations?: number;
}

export async function getMe(): Promise<User> {
  return apiClient.get<User>("/users/me");
}

export async function updateSettings(settings: UpdateSettingsPayload): Promise<User> {
  return apiClient.put<User>("/users/me/settings", settings as Record<string, unknown>);
}

export async function getBehavior(): Promise<UserBehavior> {
  return apiClient.get<UserBehavior>("/users/me/behavior");
}

// Profile items (custom key-value)
export async function getProfileItems(): Promise<ProfileItem[]> {
  return apiClient.get<ProfileItem[]>("/users/me/profile-items");
}

export async function createProfileItem(key: string, value: string): Promise<ProfileItem> {
  return apiClient.post<ProfileItem>("/users/me/profile-items", { key, value });
}

export async function updateProfileItem(id: number, data: { key?: string; value?: string }): Promise<ProfileItem> {
  return apiClient.put<ProfileItem>(`/users/me/profile-items/${id}`, data as Record<string, unknown>);
}

export async function deleteProfileItem(id: number): Promise<void> {
  return apiClient.delete<void>(`/users/me/profile-items/${id}`);
}

// User memories (flexible free-text)
export async function getMemories(): Promise<UserMemoryItem[]> {
  return apiClient.get<UserMemoryItem[]>("/users/me/memories");
}

export async function createMemory(content: string): Promise<UserMemoryItem> {
  return apiClient.post<UserMemoryItem>("/users/me/memories", { content });
}

export async function updateMemory(id: string, content: string): Promise<UserMemoryItem> {
  return apiClient.put<UserMemoryItem>(`/users/me/memories/${id}`, { content });
}

export async function deleteMemory(id: string): Promise<void> {
  return apiClient.delete<void>(`/users/me/memories/${id}`);
}
