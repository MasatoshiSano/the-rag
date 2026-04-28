import { create } from "zustand";
import { persist } from "zustand/middleware";

interface KbState {
  selectedKbId: string | null;

  // Actions
  setSelectedKbId: (id: string | null) => void;
  clearSelectedKb: () => void;
}

export const useKbStore = create<KbState>()(
  persist(
    (set) => ({
      selectedKbId: null,

      setSelectedKbId: (id) => set({ selectedKbId: id }),

      clearSelectedKb: () => set({ selectedKbId: null }),
    }),
    {
      name: "the-rag-kb",
    }
  )
);
