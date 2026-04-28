import { create } from "zustand";
import type { Source, StreamingStatus, Message } from "../types/message";

export interface AgenticStep {
  iteration: number;
  maxIterations: number;
  status: "thinking" | "searching" | "found";
  searchQuery?: string;
  resultCount?: number;
}

interface ChatState {
  messages: Message[];
  streamingText: string;
  streamingStatus: StreamingStatus;
  sources: Source[];
  isStreaming: boolean;
  abortController: AbortController | null;
  agenticSteps: AgenticStep[];

  // Actions
  setMessages: (messages: Message[]) => void;
  appendMessage: (message: Message) => void;
  updateStreamingText: (text: string) => void;
  appendStreamingText: (chunk: string) => void;
  setStreamingStatus: (status: StreamingStatus) => void;
  setSources: (sources: Source[]) => void;
  setIsStreaming: (isStreaming: boolean) => void;
  setAbortController: (controller: AbortController | null) => void;
  addAgenticStep: (step: AgenticStep) => void;
  cancelStreaming: () => void;
  resetStreamingState: () => void;
  clearMessages: () => void;
}

const initialStreamingState = {
  streamingText: "",
  streamingStatus: "idle" as StreamingStatus,
  sources: [],
  isStreaming: false,
  abortController: null,
  agenticSteps: [] as AgenticStep[],
};

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  ...initialStreamingState,

  setMessages: (messages) => set({ messages }),

  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateStreamingText: (text) => set({ streamingText: text }),

  appendStreamingText: (chunk) =>
    set((state) => ({ streamingText: state.streamingText + chunk })),

  setStreamingStatus: (status) => set({ streamingStatus: status }),

  setSources: (sources) => set({ sources }),

  setIsStreaming: (isStreaming) => set({ isStreaming }),

  setAbortController: (controller) => set({ abortController: controller }),

  addAgenticStep: (step) =>
    set((state) => ({ agenticSteps: [...state.agenticSteps, step] })),

  cancelStreaming: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
    }
    set({ ...initialStreamingState });
  },

  resetStreamingState: () => set({ ...initialStreamingState }),

  clearMessages: () => set({ messages: [], ...initialStreamingState }),
}));
