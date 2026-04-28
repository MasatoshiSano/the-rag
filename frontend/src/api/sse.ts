// Server-Sent Events クライアント: fetch + ReadableStream でRAGレスポンスをストリーミング

const API_BASE_URL = "/the-rag/api";

function getUserId(): string {
  return localStorage.getItem("the-rag-user-id") ?? "";
}

// バックエンドが送信するSSEイベント種別
export type SseEventType =
  | "session"
  | "status"
  | "token"
  | "sources"
  | "output"
  | "complete"
  | "error"
  | "done"
  | "agentic_step";

export interface SseSessionEvent {
  type: "session";
  session_id: string;
  title: string;
}

export interface SseStatusEvent {
  type: "status";
  status: string;
  message?: string;
}

export interface SseTokenEvent {
  type: "token";
  token: string;
}

export interface SseSource {
  document_id: string;
  document_name: string;
  section_title: string;
  score: number;
  snippet: string;
}

export interface SseSourcesEvent {
  type: "sources";
  sources: SseSource[];
}

export interface SseOutputEvent {
  type: "output";
  output_data: Record<string, unknown>;
}

export interface SseCompleteEvent {
  type: "complete";
  message_id: string;
  content: string;
}

export interface SseErrorEvent {
  type: "error";
  message: string;
  code?: string;
}

export interface SseDoneEvent {
  type: "done";
}

export interface SseAgenticStepEvent {
  type: "agentic_step";
  iteration: number;
  maxIterations: number;
  status: "thinking" | "searching" | "found";
  searchQuery?: string;
  resultCount?: number;
}

export type SseEvent =
  | SseSessionEvent
  | SseStatusEvent
  | SseTokenEvent
  | SseSourcesEvent
  | SseOutputEvent
  | SseCompleteEvent
  | SseErrorEvent
  | SseDoneEvent
  | SseAgenticStepEvent;

export interface SseStreamOptions {
  sessionId: string | null;
  content: string;
  knowledgeBaseId: string;
  responseMode?: "simple" | "detailed";
  searchMode?: "normal" | "agentic";
  signal: AbortSignal;
  onEvent: (event: SseEvent) => void;
  onError: (error: Error) => void;
  onDone: () => void;
}

/**
 * チャットエンドポイントにPOSTしてSSEレスポンスをストリーミングする。
 * EventSourceは使用せず、カスタムヘッダー（X-User-Id）を送れるようfetchを使用する。
 */
/**
 * バックエンドSSEイベント形式を内部SseEvent形式に変換する。
 * Backend: {"event":"token","data":{"text":"hello"}}
 * Frontend: {"type":"token","token":"hello"}
 */
const STAGE_TO_STATUS: Record<string, string> = {
  analyzing: "query_analysis",
  searching: "vector_search",
  oracle: "oracle_query",
  generating: "generating",
  error: "error",
};

function convertBackendEvent(raw: Record<string, unknown>): SseEvent | null {
  // 既にフロントエンド形式（type フィールドあり）の場合はそのまま返す
  if ("type" in raw && !("event" in raw)) return raw as unknown as SseEvent;

  const eventType = raw.event as string;
  const data = (raw.data ?? {}) as Record<string, unknown>;

  switch (eventType) {
    case "token":
      return { type: "token", token: (data.text as string) ?? "" };
    case "session":
      return {
        type: "session",
        session_id: data.session_id as string,
        title: (data.title as string) ?? "",
      };
    case "status":
      return {
        type: "status",
        status: STAGE_TO_STATUS[data.stage as string] ?? "generating",
        message: data.message as string | undefined,
      };
    case "sources": {
      const rawItems = (data.items ?? []) as Record<string, unknown>[];
      const sources: SseSource[] = rawItems.map((item) => ({
        document_id: (item.document_id as string) ?? "",
        document_name: (item.document_name as string) ?? "",
        section_title: (item.section_title as string) ?? "",
        score: (item.score as number) ?? 0,
        snippet: (item.snippet as string) ?? "",
      }));
      return { type: "sources", sources };
    }
    case "output":
      return { type: "output", output_data: data };
    case "complete":
      return {
        type: "complete",
        message_id: (data.message_id as string) ?? "",
        content: (data.content as string) ?? "",
      };
    case "done":
      return { type: "done" };
    case "error":
      return { type: "error", message: (data.message as string) ?? "不明なエラー" };
    case "agentic_step":
      return {
        type: "agentic_step",
        iteration: (data.iteration as number) ?? 1,
        maxIterations: (data.max_iterations as number) ?? 5,
        status: (data.status as "thinking" | "searching" | "found") ?? "thinking",
        searchQuery: data.search_query as string | undefined,
        resultCount: data.result_count as number | undefined,
      };
    default:
      return null;
  }
}

export async function streamChatResponse(options: SseStreamOptions): Promise<void> {
  const { sessionId, content, knowledgeBaseId, responseMode, searchMode, signal, onEvent, onError, onDone } = options;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": getUserId(),
      },
      body: JSON.stringify({
        session_id: sessionId,
        content,
        knowledge_base_id: knowledgeBaseId,
        ...(responseMode ? { response_mode: responseMode } : {}),
        ...(searchMode ? { search_mode: searchMode } : {}),
      }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    onError(err instanceof Error ? err : new Error(String(err)));
    return;
  }

  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    onError(new Error(`HTTP ${response.status}: ${message}`));
    return;
  }

  if (!response.body) {
    onError(new Error("レスポンスボディがありません"));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");

      // 最後の不完全な行はバッファに残す
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;

        const jsonStr = trimmed.slice("data:".length).trim();
        if (!jsonStr || jsonStr === "[DONE]") continue;

        try {
          const raw = JSON.parse(jsonStr) as Record<string, unknown>;
          const event = convertBackendEvent(raw);
          if (!event) continue;
          onEvent(event);

          if (event.type === "done") {
            onDone();
            return;
          }
        } catch {
          // JSONパースエラーは無視して継続
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    onError(err instanceof Error ? err : new Error(String(err)));
    return;
  } finally {
    reader.releaseLock();
  }

  onDone();
}
