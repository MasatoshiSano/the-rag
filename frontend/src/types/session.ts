export interface Session {
  id: string;
  knowledge_base_id: string;
  title: string | null;
  message_count: number;
  last_message_preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionSearchMatch {
  message_id: string;
  snippet: string;
  role: string;
  created_at: string;
}

export interface SessionSearchResult {
  session_id: string;
  session_title: string | null;
  matches: SessionSearchMatch[];
}
