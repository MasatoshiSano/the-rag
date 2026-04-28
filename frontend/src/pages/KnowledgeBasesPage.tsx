// KnowledgeBasesPage: ナレッジベース管理ページ
// WCAG 2.2 AA準拠: ランドマーク・aria属性・キーボード操作

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  getKnowledgeBases,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase,
  addFavorite,
  removeFavorite,
} from "../api/knowledge-bases";
import {
  KnowledgeBaseCard,
  KBFormDialog,
  DeleteKBDialog,
} from "../components/knowledge-base";
import { useKbStore } from "../stores/kbStore";
import type { KnowledgeBase, CreateKBRequest } from "../types/knowledge-base";

export function KnowledgeBasesPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const setSelectedKbId = useKbStore((s) => s.setSelectedKbId);

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBase | null>(null);
  const [deletingKb, setDeletingKb] = useState<KnowledgeBase | null>(null);

  // KBリスト取得
  const {
    data: knowledgeBases = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["knowledge-bases"],
    queryFn: getKnowledgeBases,
  });

  // 作成・更新ミューテーション
  const createMutation = useMutation({
    mutationFn: createKnowledgeBase,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      setIsFormOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreateKBRequest> }) =>
      updateKnowledgeBase(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      setEditingKb(null);
      setIsFormOpen(false);
    },
  });

  // 削除ミューテーション
  const deleteMutation = useMutation({
    mutationFn: deleteKnowledgeBase,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      setDeletingKb(null);
    },
  });

  // お気に入りトグルミューテーション（楽観的更新）
  const favoriteMutation = useMutation({
    mutationFn: ({ id, is_favorite }: { id: string; is_favorite: boolean }) =>
      is_favorite ? removeFavorite(id) : addFavorite(id),
    onMutate: async ({ id, is_favorite }) => {
      await queryClient.cancelQueries({ queryKey: ["knowledge-bases"] });
      const previous = queryClient.getQueryData<KnowledgeBase[]>(["knowledge-bases"]);
      queryClient.setQueryData<KnowledgeBase[]>(["knowledge-bases"], (old) =>
        old?.map((kb) =>
          kb.id === id ? { ...kb, is_favorite: !is_favorite } : kb
        )
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["knowledge-bases"], context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
      void queryClient.invalidateQueries({ queryKey: ["knowledge-bases", "favorites"] });
    },
  });

  const handleFormSubmit = useCallback(
    async (data: CreateKBRequest): Promise<void> => {
      if (editingKb) {
        await updateMutation.mutateAsync({ id: editingKb.id, data });
      } else {
        await createMutation.mutateAsync(data);
      }
    },
    [editingKb, createMutation, updateMutation]
  );

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      await deleteMutation.mutateAsync(id);
    },
    [deleteMutation]
  );

  const handleKbClick = useCallback(
    (kb: KnowledgeBase) => {
      setSelectedKbId(kb.id);
      navigate("/chat");
    },
    [setSelectedKbId, navigate]
  );

  const handleEdit = useCallback((kb: KnowledgeBase) => {
    setEditingKb(kb);
    setIsFormOpen(true);
  }, []);

  const handleCreateNew = () => {
    setEditingKb(null);
    setIsFormOpen(true);
  };

  const handleFormClose = () => {
    setIsFormOpen(false);
    setEditingKb(null);
  };

  const isSubmitting = createMutation.isPending || updateMutation.isPending;

  return (
    <>
      <section
        aria-label="ナレッジベース管理"
        style={{
          padding: "16px",
          maxWidth: 1200,
          margin: "0 auto",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {/* ページヘッダー */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 24,
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <h1
            style={{
              margin: 0,
              fontSize: 24,
              fontWeight: 700,
              color: "var(--sds-color-on-surface-default)",
            }}
          >
            ナレッジベース
          </h1>
          <button
            type="button"
            onClick={handleCreateNew}
            aria-label="新しいナレッジベースを作成"
            style={{
              padding: "8px 20px",
              border: "none",
              borderRadius: 6,
              backgroundColor: "var(--sds-color-impression-primary)",
              color: "#fff",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span aria-hidden="true">＋</span>
            新規作成
          </button>
        </div>

        {/* エラー表示 */}
        {isError && (
          <div
            role="alert"
            aria-live="assertive"
            style={{
              padding: "12px 16px",
              backgroundColor: "var(--sds-color-error-container, #FDECEA)",
              border: "1px solid var(--sds-color-error-default, #B00020)",
              borderRadius: 6,
              color: "var(--sds-color-error-default, #B00020)",
              marginBottom: 24,
              fontSize: 14,
            }}
          >
            データの読み込みに失敗しました: {(error as Error).message}
          </div>
        )}

        {/* ローディング状態 */}
        {isLoading && (
          <div
            aria-live="polite"
            aria-busy="true"
            aria-label="ナレッジベースを読み込み中"
            style={{
              display: "flex",
              justifyContent: "center",
              padding: 64,
              color: "var(--sds-color-on-surface-variant)",
            }}
          >
            読み込み中...
          </div>
        )}

        {/* 空状態 */}
        {!isLoading && !isError && knowledgeBases.length === 0 && (
          <div
            role="status"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "64px 24px",
              textAlign: "center",
            }}
          >
            <p
              style={{
                fontSize: 16,
                color: "var(--sds-color-on-surface-variant)",
                margin: "0 0 16px",
              }}
            >
              ナレッジベースがまだありません
            </p>
            <button
              type="button"
              onClick={handleCreateNew}
              style={{
                padding: "10px 24px",
                border: "none",
                borderRadius: 6,
                backgroundColor: "var(--sds-color-impression-primary)",
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              最初のナレッジベースを作成
            </button>
          </div>
        )}

        {/* KBカードグリッド */}
        {!isLoading && knowledgeBases.length > 0 && (
          <section aria-label="ナレッジベース一覧">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(min(280px, 100%), 1fr))",
                gap: 16,
              }}
            >
              {knowledgeBases.map((kb) => (
                <KnowledgeBaseCard
                  key={kb.id}
                  kb={kb}
                  onFavoriteToggle={(id, is_favorite) =>
                    favoriteMutation.mutate({ id, is_favorite })
                  }
                  onEdit={handleEdit}
                  onDelete={(target) => setDeletingKb(target)}
                  onClick={handleKbClick}
                />
              ))}
            </div>
          </section>
        )}
      </section>

      {/* KB作成・編集ダイアログ */}
      <KBFormDialog
        isOpen={isFormOpen}
        editingKb={editingKb}
        onClose={handleFormClose}
        onSubmit={handleFormSubmit}
        isSubmitting={isSubmitting}
      />

      {/* KB削除確認ダイアログ */}
      <DeleteKBDialog
        kb={deletingKb}
        onClose={() => setDeletingKb(null)}
        onConfirm={handleDelete}
        isDeleting={deleteMutation.isPending}
      />
    </>
  );
}
