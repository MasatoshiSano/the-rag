import { create } from "zustand";
import type { OutputData } from "../types/output";

interface OutputState {
  isOutputPanelOpen: boolean;
  outputData: OutputData | null;
  selectedMessageId: string | null;

  // Actions
  openOutputPanel: (data: OutputData) => void;
  closeOutputPanel: () => void;
  setOutputData: (data: OutputData | null) => void;
  setSelectedMessageId: (id: string | null) => void;
  clearOutput: () => void;
}

export const useOutputStore = create<OutputState>((set) => ({
  isOutputPanelOpen: false,
  outputData: null,
  selectedMessageId: null,

  openOutputPanel: (data) =>
    set({ isOutputPanelOpen: true, outputData: data, selectedMessageId: data.messageId }),

  closeOutputPanel: () =>
    set({ isOutputPanelOpen: false }),

  setOutputData: (data) => set({ outputData: data }),

  setSelectedMessageId: (id) => set({ selectedMessageId: id }),

  clearOutput: () =>
    set({ isOutputPanelOpen: false, outputData: null, selectedMessageId: null }),
}));
