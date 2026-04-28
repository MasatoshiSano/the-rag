import { create } from "zustand";
import type { Source } from "../types/message";

interface SourceState {
  isSourcePanelOpen: boolean;
  panelSources: Source[];
  selectedSource: Source | null;

  openSourcePanel: (sources: Source[]) => void;
  closeSourcePanel: () => void;
  selectSource: (source: Source | null) => void;
}

export const useSourceStore = create<SourceState>((set) => ({
  isSourcePanelOpen: false,
  panelSources: [],
  selectedSource: null,

  openSourcePanel: (sources) =>
    set({ isSourcePanelOpen: true, panelSources: sources, selectedSource: null }),

  closeSourcePanel: () =>
    set({ isSourcePanelOpen: false, selectedSource: null }),

  selectSource: (source) =>
    set({ selectedSource: source }),
}));
