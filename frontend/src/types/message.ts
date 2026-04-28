export type StreamingStatus =
  | "idle"
  | "query_analysis"
  | "vector_search"
  | "oracle_query"
  | "structuring_output"
  | "generating";

export interface Source {
  documentId: string;
  documentName: string;
  sectionTitle: string;
  score: number;
  snippet: string;
}

export interface Message {
  id: string;
  sessionId: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  rating: number | null;
  inputType: "text" | "voice";
  isCancelled: boolean;
  createdAt: string;
}
