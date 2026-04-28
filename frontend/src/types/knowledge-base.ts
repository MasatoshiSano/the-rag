export interface KnowledgeBase {
  id: string;
  name: string;
  description: string | null;
  color: string;
  created_by: string | null;
  document_count: number;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateKBRequest {
  name: string;
  description: string;
  color: string;
}
