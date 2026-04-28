import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../types/user";

interface UserState {
  userId: string | null;
  user: User | null;
  isLoading: boolean;

  // Actions
  setUserId: (id: string) => void;
  setUser: (user: User) => void;
  updateUserSettings: (settings: Partial<Pick<User, "rerank_enabled" | "hybrid_search_enabled" | "retrieval_count" | "response_mode" | "search_mode" | "agentic_max_iterations" | "nickname">>) => void;
  setIsLoading: (isLoading: boolean) => void;
  clearUser: () => void;
}

export const useUserStore = create<UserState>()(
  persist(
    (set) => ({
      userId: null,
      user: null,
      isLoading: false,

      setUserId: (id) => set({ userId: id }),

      setUser: (user) => set({ user, userId: user.id }),

      updateUserSettings: (settings) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...settings } : null,
        })),

      setIsLoading: (isLoading) => set({ isLoading }),

      clearUser: () => set({ userId: null, user: null }),
    }),
    {
      name: "the-rag-user",
      // Only persist userId - user data is fetched from the API
      partialize: (state) => ({ userId: state.userId }),
    }
  )
);
