// KBFormDialog: KB作成・編集ダイアログ（モーダル）
// WCAG 2.1.1: キーボードトラップ対応、Escape で閉じる
// WCAG 1.4.3: コントラスト比確保

import { useState, useEffect, useRef, useId } from "react";
import type { KnowledgeBase, CreateKBRequest } from "../../types/knowledge-base";

const PRESET_COLORS = [
  "#4F81BD", // ブルー
  "#2E75B6", // ダークブルー
  "#70AD47", // グリーン
  "#ED7D31", // オレンジ
  "#A9D18E", // ライトグリーン
  "#FF0000", // レッド
  "#7030A0", // パープル
  "#00B0F0", // スカイブルー
  "#FF00FF", // マゼンタ
  "#FFC000", // ゴールド
  "#333333", // ダークグレー
  "#808080", // グレー
];

interface KBFormDialogProps {
  isOpen: boolean;
  editingKb: KnowledgeBase | null;
  onClose: () => void;
  onSubmit: (data: CreateKBRequest) => Promise<void>;
  isSubmitting: boolean;
}

export function KBFormDialog({
  isOpen,
  editingKb,
  onClose,
  onSubmit,
  isSubmitting,
}: KBFormDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFocusRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const nameErrorId = useId();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(PRESET_COLORS[0]);
  const [nameError, setNameError] = useState("");

  // 編集時は既存値をセット
  useEffect(() => {
    if (editingKb) {
      setName(editingKb.name);
      setDescription(editingKb.description ?? "");
      setColor(editingKb.color);
    } else {
      setName("");
      setDescription("");
      setColor(PRESET_COLORS[0]);
    }
    setNameError("");
  }, [editingKb, isOpen]);

  // ダイアログを開いたら最初のフォームフィールドにフォーカス
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => firstFocusRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Escapeキーで閉じる
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const validate = (): boolean => {
    if (!name.trim()) {
      setNameError("名前を入力してください");
      firstFocusRef.current?.focus();
      return false;
    }
    if (name.length > 100) {
      setNameError("名前は100文字以内で入力してください");
      firstFocusRef.current?.focus();
      return false;
    }
    setNameError("");
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    await onSubmit({ name: name.trim(), description: description.trim(), color });
  };

  if (!isOpen) return null;

  return (
    /* オーバーレイ */
    <div
      role="presentation"
      aria-hidden="false"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.5)",
        zIndex: 500,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      {/* ダイアログ本体 */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          backgroundColor: "var(--sds-color-surface-default)",
          borderRadius: 8,
          padding: 24,
          width: "100%",
          maxWidth: 480,
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
      >
        <h2
          id={titleId}
          style={{
            margin: "0 0 20px",
            fontSize: 18,
            fontWeight: 600,
            color: "var(--sds-color-on-surface-default)",
          }}
        >
          {editingKb ? "ナレッジベースを編集" : "ナレッジベースを作成"}
        </h2>

        <form onSubmit={handleSubmit} noValidate>
          {/* 名前フィールド */}
          <div style={{ marginBottom: 16 }}>
            <label
              htmlFor={`${titleId}-name`}
              style={{
                display: "block",
                fontSize: 14,
                fontWeight: 500,
                color: "var(--sds-color-on-surface-default)",
                marginBottom: 6,
              }}
            >
              名前 <span aria-hidden="true" style={{ color: "var(--sds-color-error-default, #B00020)" }}>*</span>
              <span className="sr-only">（必須）</span>
            </label>
            <input
              ref={firstFocusRef}
              id={`${titleId}-name`}
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (nameError) setNameError("");
              }}
              aria-required="true"
              aria-invalid={!!nameError}
              aria-describedby={nameError ? nameErrorId : undefined}
              maxLength={100}
              placeholder="例: 社内規程ドキュメント"
              style={{
                width: "100%",
                padding: "8px 12px",
                border: `1px solid ${nameError ? "var(--sds-color-error-default, #B00020)" : "var(--sds-color-outline-default)"}`,
                borderRadius: 4,
                backgroundColor: "var(--sds-color-surface-default)",
                color: "var(--sds-color-on-surface-default)",
                fontSize: 14,
                boxSizing: "border-box",
                outline: "none",
              }}
            />
            {nameError && (
              <p
                id={nameErrorId}
                role="alert"
                style={{
                  margin: "4px 0 0",
                  fontSize: 12,
                  color: "var(--sds-color-error-default, #B00020)",
                }}
              >
                {nameError}
              </p>
            )}
          </div>

          {/* 説明フィールド */}
          <div style={{ marginBottom: 16 }}>
            <label
              htmlFor={`${titleId}-description`}
              style={{
                display: "block",
                fontSize: 14,
                fontWeight: 500,
                color: "var(--sds-color-on-surface-default)",
                marginBottom: 6,
              }}
            >
              説明
            </label>
            <textarea
              id={`${titleId}-description`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="このナレッジベースの説明を入力..."
              rows={3}
              maxLength={500}
              style={{
                width: "100%",
                padding: "8px 12px",
                border: "1px solid var(--sds-color-outline-default)",
                borderRadius: 4,
                backgroundColor: "var(--sds-color-surface-default)",
                color: "var(--sds-color-on-surface-default)",
                fontSize: 14,
                resize: "vertical",
                boxSizing: "border-box",
                outline: "none",
                fontFamily: "inherit",
              }}
            />
          </div>

          {/* カラーピッカー */}
          <div style={{ marginBottom: 24 }}>
            <p
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: "var(--sds-color-on-surface-default)",
                margin: "0 0 8px",
              }}
            >
              カラー
            </p>
            <div
              role="radiogroup"
              aria-label="ナレッジベースのカラーを選択"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {PRESET_COLORS.map((c) => (
                <label
                  key={c}
                  aria-label={`カラー ${c}`}
                  style={{ cursor: "pointer" }}
                >
                  <input
                    type="radio"
                    name="kb-color"
                    value={c}
                    checked={color === c}
                    onChange={() => setColor(c)}
                    style={{ position: "absolute", opacity: 0, width: 1, height: 1 }}
                  />
                  <span
                    aria-hidden="true"
                    style={{
                      display: "block",
                      width: 28,
                      height: 28,
                      borderRadius: "50%",
                      backgroundColor: c,
                      border: color === c
                        ? "3px solid var(--sds-color-on-surface-default)"
                        : "2px solid rgba(0,0,0,0.15)",
                      boxSizing: "border-box",
                    }}
                  />
                </label>
              ))}
            </div>
          </div>

          {/* アクションボタン */}
          <div
            style={{
              display: "flex",
              gap: 12,
              justifyContent: "flex-end",
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              style={{
                padding: "8px 20px",
                border: "1px solid var(--sds-color-outline-default)",
                borderRadius: 6,
                backgroundColor: "transparent",
                color: "var(--sds-color-on-surface-default)",
                fontSize: 14,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                fontWeight: 500,
              }}
            >
              キャンセル
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              aria-busy={isSubmitting}
              style={{
                padding: "8px 20px",
                border: "none",
                borderRadius: 6,
                backgroundColor: "var(--sds-color-impression-primary)",
                color: "#fff",
                fontSize: 14,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                fontWeight: 500,
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting ? "保存中..." : (editingKb ? "更新" : "作成")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
