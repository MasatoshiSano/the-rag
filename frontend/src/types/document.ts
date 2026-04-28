export type DocumentStatus =
  | "processing"
  | "converting"
  | "converted"
  | "tagging"
  | "tagged"
  | "confirmed"
  | "chunking"
  | "chunked"
  | "indexing"
  | "indexed"
  | "convert_failed"
  | "tag_failed"
  | "index_failed"
  | "permanent_failed"
  | "cancelled";

export interface DocumentTag {
  id: number;
  tag_key: string;
  tag_value: string;
  confidence: number;
  ai_suggested: boolean;
  confirmed: boolean;
}

export interface Document {
  id: string;
  knowledge_base_id: string;
  filename: string;
  file_type: string;
  status: DocumentStatus;
  retry_count: number;
  version: number;
  parent_document_id: string | null;
  tags: DocumentTag[];
  deleted_at: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}
