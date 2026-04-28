export interface User {
  id: string;
  nickname: string;
  rerank_enabled: boolean;
  hybrid_search_enabled: boolean;
  retrieval_count: number;
  response_mode: "simple" | "detailed";
  search_mode: "normal" | "agentic";
  agentic_max_iterations: number;
  created_at: string;
}

export interface UserBehavior {
  user_id: string;
  frequent_lines: string[];
  frequent_categories: string[];
  recent_context: string | null;
  total_sessions: number;
  total_messages: number;
}

export interface ProfileItem {
  id: number;
  key: string;
  value: string;
  created_at: string;
  updated_at: string;
}

export interface UserMemoryItem {
  id: string;
  content: string;
  source: "manual" | "auto";
  created_at: string;
  updated_at: string;
}
