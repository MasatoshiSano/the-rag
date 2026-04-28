import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useChatStore } from "../stores/chatStore";
import { useKbStore } from "../stores/kbStore";
import { useUserStore } from "../stores/userStore";
import { useOutputStore } from "../stores/outputStore";
import { streamChatResponse } from "../api/sse";
import type { SseEvent, SseStatusEvent, SseTokenEvent, SseCompleteEvent, SseErrorEvent, SseSessionEvent, SseAgenticStepEvent } from "../api/sse";
import type { StreamingStatus, Source } from "../types/message";
import type { OutputData } from "../types/output";

interface UseStreamChatReturn {
  sendMessage: (content: string, sessionId?: string) => Promise<void>;
}

const STATUS_MAP: Record<string, StreamingStatus> = {
  query_analysis: "query_analysis",
  vector_search: "vector_search",
  oracle_query: "oracle_query",
  structuring_output: "structuring_output",
  generating: "generating",
};

export function useStreamChat(): UseStreamChatReturn {
  const navigate = useNavigate();
  const {
    appendMessage,
    setStreamingStatus,
    appendStreamingText,
    setSources,
    setIsStreaming,
    setAbortController,
    addAgenticStep,
    resetStreamingState,
  } = useChatStore();
  const { selectedKbId } = useKbStore();
  const { openOutputPanel } = useOutputStore();

  const sendMessage = useCallback(
    async (content: string, sessionId?: string) => {
      if (!selectedKbId) return;

      const responseMode = useUserStore.getState().user?.response_mode ?? "detailed";
      const searchMode = (localStorage.getItem("the-rag-search-mode") as "normal" | "agentic" | null)
        ?? useUserStore.getState().user?.search_mode
        ?? "agentic";

      // Add user message to local state immediately
      const tempUserMsgId = `user-${Date.now()}`;
      appendMessage({
        id: tempUserMsgId,
        sessionId: sessionId ?? "",
        role: "user",
        content,
        sources: [],
        rating: null,
        inputType: "text",
        isCancelled: false,
        createdAt: new Date().toISOString(),
      });

      // session_id が未指定の場合は null を渡してバックエンドに新規作成を委譲
      const activeSessionId = sessionId ?? null;

      // Setup AbortController
      const controller = new AbortController();
      setAbortController(controller);
      setIsStreaming(true);
      setStreamingStatus("query_analysis");

      let finalMessageId = "";
      let wasCancelled = false;

      try {
        await streamChatResponse({
          sessionId: activeSessionId,
          content,
          knowledgeBaseId: selectedKbId,
          responseMode: responseMode,
          searchMode: searchMode,
          signal: controller.signal,
          onEvent: (event: SseEvent) => {
            if (event.type === "session") {
              const sessionEvent = event as SseSessionEvent;
              navigate(`/chat/${sessionEvent.session_id}`, { replace: true });
            } else if (event.type === "status") {
              const statusEvent = event as SseStatusEvent;
              const mapped = STATUS_MAP[statusEvent.status] ?? "generating";
              setStreamingStatus(mapped);
            } else if (event.type === "token") {
              const tokenEvent = event as SseTokenEvent;
              appendStreamingText(tokenEvent.token);
            } else if (event.type === "complete") {
              const completeEvent = event as SseCompleteEvent;
              finalMessageId = completeEvent.message_id;
            } else if (event.type === "error") {
              const errEvent = event as SseErrorEvent;
              console.error("SSE error event:", errEvent.message);
            } else if (event.type === "agentic_step") {
              const stepEvent = event as SseAgenticStepEvent;
              addAgenticStep({
                iteration: stepEvent.iteration,
                maxIterations: stepEvent.maxIterations,
                status: stepEvent.status,
                searchQuery: stepEvent.searchQuery,
                resultCount: stepEvent.resultCount,
              });
            }

            // Handle sources/output events
            if (event.type === "sources" && "sources" in event) {
              const mapped: Source[] = event.sources.map((s) => ({
                documentId: s.document_id,
                documentName: s.document_name,
                sectionTitle: s.section_title,
                score: s.score,
                snippet: s.snippet,
              }));
              setSources(mapped);
            }
            if (event.type === "output" && "output_data" in event) {
              const od = event.output_data;
              // type: "none" の場合はパネルを開かない
              if (od && od.type !== "none") {
                openOutputPanel(od as unknown as OutputData);
              }
            }
          },
          onError: (error: Error) => {
            if (error.name === "AbortError") {
              wasCancelled = true;
            } else {
              console.error("Stream error:", error);
            }
          },
          onDone: () => {
            // Finalize: capture current streaming state
            const currentStreamingText = useChatStore.getState().streamingText;
            const currentSources = useChatStore.getState().sources;
            const finalContent = wasCancelled
              ? currentStreamingText + "（回答が中断されました）"
              : currentStreamingText;

            appendMessage({
              id: finalMessageId || `assistant-${Date.now()}`,
              sessionId: activeSessionId ?? "",
              role: "assistant",
              content: finalContent,
              sources: currentSources,
              rating: null,
              inputType: "text",
              isCancelled: wasCancelled,
              createdAt: new Date().toISOString(),
            });

            resetStreamingState();
          },
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          wasCancelled = true;
        }

        const currentStreamingText = useChatStore.getState().streamingText;
        const currentSources = useChatStore.getState().sources;
        const finalContent = wasCancelled
          ? currentStreamingText + "（回答が中断されました）"
          : currentStreamingText;

        appendMessage({
          id: finalMessageId || `assistant-${Date.now()}`,
          sessionId: activeSessionId ?? "",
          role: "assistant",
          content: finalContent,
          sources: currentSources,
          rating: null,
          inputType: "text",
          isCancelled: wasCancelled,
          createdAt: new Date().toISOString(),
        });

        resetStreamingState();
      }
    },
    [
      selectedKbId,
      navigate,
      appendMessage,
      setStreamingStatus,
      appendStreamingText,
      setSources,
      setIsStreaming,
      setAbortController,
      addAgenticStep,
      openOutputPanel,
      resetStreamingState,
    ]
  );

  return { sendMessage };
}
