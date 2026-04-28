// Output API: structured data and chart config for messages

import { apiClient } from "./client";
import type { OutputData } from "../types/output";

export async function getOutputData(messageId: string): Promise<OutputData> {
  return apiClient.get<OutputData>(`/chat/output/${messageId}`);
}

export async function downloadCsv(messageId: string): Promise<Blob> {
  const userId = localStorage.getItem("the-rag-user-id") ?? "";
  const response = await fetch(`/the-rag/api/chat/output/${messageId}/csv`, {
    headers: { "X-User-Id": userId },
  });
  if (!response.ok) {
    throw new Error(`CSV download failed: ${response.statusText}`);
  }
  return response.blob();
}
