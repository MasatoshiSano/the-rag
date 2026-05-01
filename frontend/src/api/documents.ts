// Documents API: upload, list, tag, reindex, cancel, delete, restore
import { apiClient } from "./client";
import type { Document, DocumentTag } from "../types/document";

export interface UploadResponse {
  documents: Document[];
  message: string;
}

export interface DocumentsListParams {
  knowledge_base_id: string;
  limit?: number;
  offset?: number;
  status?: string;
  tag?: string;
}

export interface DocumentDetail extends Document {
  converted_md?: string;
}

export interface PatchTagsRequest {
  tags: Array<{ tag_key: string; tag_value: string; confirmed: boolean }>;
}

export interface BatchTagsRequest {
  documents: Array<{
    document_id: string;
    tags: Array<{ tag_key: string; tag_value: string; confirmed: boolean }>;
  }>;
}

export async function uploadDocuments(
  knowledge_base_id: string,
  files: File[]
): Promise<UploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  return apiClient.post<UploadResponse>(
    `/documents/upload?knowledge_base_id=${encodeURIComponent(knowledge_base_id)}`,
    formData
  );
}

interface DocumentsListResponse {
  documents: Document[];
  total: number;
  limit: number;
  offset: number;
}

export async function getDocuments(
  params: DocumentsListParams
): Promise<Document[]> {
  const query = new URLSearchParams({
    knowledge_base_id: params.knowledge_base_id,
    limit: String(params.limit ?? 20),
    offset: String(params.offset ?? 0),
    ...(params.status ? { status: params.status } : {}),
    ...(params.tag ? { tag: params.tag } : {}),
  });
  const response = await apiClient.get<DocumentsListResponse>(`/documents/?${query}`);
  return response.documents;
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return apiClient.get<DocumentDetail>(`/documents/${id}`);
}

export async function patchDocumentTags(
  id: string,
  tags: PatchTagsRequest["tags"]
): Promise<Document> {
  return apiClient.patch<Document>(`/documents/${id}/tags`, { tags } as Record<string, unknown>);
}

export async function batchPatchTags(
  documents: BatchTagsRequest["documents"]
): Promise<Document[]> {
  return apiClient.patch<Document[]>(`/documents/batch-tags`, { documents } as Record<string, unknown>);
}

export async function reindexDocument(id: string): Promise<Document> {
  return apiClient.post<Document>(`/documents/${id}/reindex`);
}

export async function cancelDocument(id: string): Promise<Document> {
  return apiClient.post<Document>(`/documents/${id}/cancel`);
}

export async function softDeleteDocument(id: string): Promise<void> {
  return apiClient.delete<void>(`/documents/${id}`);
}

export async function restoreDocument(id: string): Promise<Document> {
  return apiClient.post<Document>(`/documents/${id}/restore`);
}

export async function permanentDeleteDocument(id: string): Promise<void> {
  return apiClient.delete<void>(`/documents/${id}/permanent`);
}

export async function getDocumentVersions(id: string): Promise<Document[]> {
  return apiClient.get<Document[]>(`/documents/${id}/versions`);
}

export async function downloadDocument(id: string, filename: string): Promise<void> {
  const userId = localStorage.getItem("the-rag-user-id") ?? "";
  const response = await fetch(`/the-rag/api/documents/${id}/download`, {
    headers: { "X-User-Id": userId },
  });
  if (!response.ok) {
    throw new Error(`Download failed: ${response.statusText}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// GitHub sources (sync history) API
export interface GitHubSourceResponse {
  id: string;
  knowledge_base_id: string;
  repository_url: string;
  path: string;
  branch: string;
  synced_by: string | null;
  last_synced_at: string;
  created_at: string;
}

export async function getGitHubSources(
  knowledgeBaseId: string
): Promise<GitHubSourceResponse[]> {
  return apiClient.get<GitHubSourceResponse[]>(
    `/documents/github-sources?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
  );
}

export async function deleteGitHubSource(id: string): Promise<void> {
  return apiClient.delete<void>(`/documents/github-sources/${id}`);
}

// GitHub sync API
export interface GitHubSyncRequest {
  repository_url: string;
  path: string;
  branch: string;
  knowledge_base_id: string;
}

export interface GitHubSyncFileResult {
  filename: string;
  document_id: string;
  status: string;
}

export interface GitHubSyncResponse {
  synced_files: GitHubSyncFileResult[];
  total: number;
  message: string;
}

export async function syncGitHub(
  params: GitHubSyncRequest
): Promise<GitHubSyncResponse> {
  // 内部用の /api/documents/github-sync エンドポイントを使用する
  // (X-User-Id 認証ベース。外部 API キーはフロントへ露出させない。)
  return apiClient.post<GitHubSyncResponse>(
    `/documents/github-sync`,
    params as unknown as Record<string, unknown>
  );
}

// Gitea sources (sync history) API
export interface GiteaSourceResponse {
  id: string;
  knowledge_base_id: string;
  repository_url: string;
  path: string;
  branch: string;
  synced_by: string | null;
  last_synced_at: string;
  created_at: string;
}

export async function getGiteaSources(
  knowledgeBaseId: string
): Promise<GiteaSourceResponse[]> {
  return apiClient.get<GiteaSourceResponse[]>(
    `/documents/gitea-sources?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
  );
}

export async function deleteGiteaSource(id: string): Promise<void> {
  return apiClient.delete<void>(`/documents/gitea-sources/${id}`);
}

// Gitea sync API
export interface GiteaSyncRequest {
  repository_url: string;
  path: string;
  branch: string;
  knowledge_base_id: string;
}

export interface GiteaSyncFileResult {
  filename: string;
  document_id: string;
  status: string;
}

export interface GiteaSyncResponse {
  synced_files: GiteaSyncFileResult[];
  total: number;
  message: string;
}

export async function syncGitea(
  params: GiteaSyncRequest
): Promise<GiteaSyncResponse> {
  // 内部用の /api/documents/gitea-sync エンドポイントを使用する
  // (X-User-Id 認証ベース。外部 API キーはフロントへ露出させない。)
  return apiClient.post<GiteaSyncResponse>(
    `/documents/gitea-sync`,
    params as unknown as Record<string, unknown>
  );
}

// ---------------------------------------------------------------------------
// Folder sources API
// ---------------------------------------------------------------------------

export interface FolderSourceResponse {
  id: string;
  knowledge_base_id: string;
  folder_path: string;
  container_path: string;
  label: string | null;
  source_type: "document" | "data";
  file_count: number;
  has_more: boolean;
  registered_by: string | null;
  created_at: string;
}

export interface FolderSourceValidateResponse {
  valid: boolean;
  container_path: string;
  file_count: number;
  has_more: boolean;
  error: string;
}

export async function validateFolderPath(
  folderPath: string
): Promise<FolderSourceValidateResponse> {
  return apiClient.post<FolderSourceValidateResponse>(
    "/documents/folder-sources/validate",
    { folder_path: folderPath } as Record<string, unknown>
  );
}

export async function createFolderSource(params: {
  folder_path: string;
  knowledge_base_id: string;
  label?: string;
  source_type?: "document" | "data";
}): Promise<FolderSourceResponse> {
  return apiClient.post<FolderSourceResponse>(
    "/documents/folder-sources",
    params as Record<string, unknown>
  );
}

export async function getFolderSources(
  knowledgeBaseId: string
): Promise<FolderSourceResponse[]> {
  return apiClient.get<FolderSourceResponse[]>(
    `/documents/folder-sources?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
  );
}

export async function deleteFolderSource(id: string): Promise<void> {
  return apiClient.delete<void>(`/documents/folder-sources/${id}`);
}

// Re-export DocumentTag for convenience
export type { DocumentTag };
