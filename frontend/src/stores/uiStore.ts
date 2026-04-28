import { create } from "zustand";

type ModalId = "createKnowledgeBase" | "deleteDocument" | "deleteSession" | "confirmCancel";

interface UiState {
  isSidebarOpen: boolean;
  openModals: Set<ModalId>;
  activeModal: ModalId | null;
  modalPayload: Record<string, string | number | boolean> | undefined;

  // Actions
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  openModal: (id: ModalId, payload?: Record<string, string | number | boolean>) => void;
  closeModal: (id: ModalId) => void;
  closeAllModals: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  isSidebarOpen: window.innerWidth >= 768,
  openModals: new Set<ModalId>(),
  activeModal: null,
  modalPayload: undefined,

  setSidebarOpen: (open) => set({ isSidebarOpen: open }),

  toggleSidebar: () =>
    set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),

  openModal: (id, payload) =>
    set((state) => ({
      openModals: new Set([...state.openModals, id]),
      activeModal: id,
      modalPayload: payload,
    })),

  closeModal: (id) =>
    set((state) => {
      const next = new Set(state.openModals);
      next.delete(id);
      return {
        openModals: next,
        activeModal: next.size > 0 ? ([...next].pop() ?? null) : null,
        modalPayload: next.size === 0 ? undefined : state.modalPayload,
      };
    }),

  closeAllModals: () =>
    set({ openModals: new Set<ModalId>(), activeModal: null, modalPayload: undefined }),
}));
