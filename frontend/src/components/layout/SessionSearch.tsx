// SessionSearch: セッション全文検索（デバウンス300ms・ドロップダウン）
// WCAG 2.4.3: フォーカス管理、aria-expanded、役割の明示

import { useState, useRef, useCallback, useEffect, useId } from "react";
import { useNavigate } from "react-router-dom";
import { searchSessions } from "../../api/sessions";
import type { SessionSearchResult } from "../../types/session";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function SessionSearch() {
  const navigate = useNavigate();
  const inputId = useId();
  const listboxId = useId();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SessionSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const debouncedQuery = useDebounce(query, 300);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 検索実行
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (!trimmed) {
      setResults([]);
      setIsOpen(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    searchSessions(trimmed)
      .then((data) => {
        if (!cancelled) {
          setResults(data);
          setIsOpen(data.length > 0);
          setActiveIndex(-1);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResults([]);
          setIsOpen(false);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  // コンテナ外クリックで閉じる
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = useCallback(
    (result: SessionSearchResult) => {
      setQuery("");
      setIsOpen(false);
      navigate(`/chat/${result.session_id}`);
    },
    [navigate]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, -1));
        break;
      case "Enter":
        e.preventDefault();
        if (activeIndex >= 0 && results[activeIndex]) {
          handleSelect(results[activeIndex]);
        }
        break;
      case "Escape":
        e.preventDefault();
        setIsOpen(false);
        setActiveIndex(-1);
        inputRef.current?.focus();
        break;
    }
  };

  const activeOptionId =
    activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined;

  return (
    <div
      ref={containerRef}
      role="search"
      aria-label="セッション検索"
      style={{ position: "relative", width: "100%" }}
    >
      <input
        ref={inputRef}
        id={inputId}
        type="search"
        role="combobox"
        aria-label="セッションを検索"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-activedescendant={activeOptionId}
        aria-autocomplete="list"
        autoComplete="off"
        placeholder="セッションを検索..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (results.length > 0) setIsOpen(true);
        }}
        style={{
          width: "100%",
          padding: "8px 36px 8px 12px",
          border: "1px solid var(--sds-color-outline-default)",
          borderRadius: 6,
          backgroundColor: "var(--sds-color-surface-default)",
          color: "var(--sds-color-on-surface-default)",
          fontSize: 14,
          outline: "none",
          boxSizing: "border-box",
        }}
      />

      {/* ローディングインジケータ */}
      {isLoading && (
        <span
          aria-live="polite"
          aria-label="検索中"
          style={{
            position: "absolute",
            right: 10,
            top: "50%",
            transform: "translateY(-50%)",
            width: 16,
            height: 16,
            border: "2px solid var(--sds-color-outline-default)",
            borderTopColor: "var(--sds-color-primary-default)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
            pointerEvents: "none",
          }}
        />
      )}

      {/* 検索結果ドロップダウン */}
      {isOpen && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="セッション検索結果"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            backgroundColor: "var(--sds-color-surface-default)",
            border: "1px solid var(--sds-color-outline-default)",
            borderRadius: 6,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            zIndex: 150,
            listStyle: "none",
            margin: 0,
            padding: "4px 0",
            maxHeight: 320,
            overflow: "auto",
          }}
        >
          {results.map((result, index) => (
            <li
              key={result.session_id}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(e) => {
                // mousedownで選択（blurより先に処理）
                e.preventDefault();
                handleSelect(result);
              }}
              onMouseEnter={() => setActiveIndex(index)}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                backgroundColor:
                  index === activeIndex
                    ? "var(--sds-color-impression-primaryContainer)"
                    : "transparent",
                borderRadius: 4,
                margin: "2px 4px",
              }}
            >
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: "var(--sds-color-on-surface-default)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {result.session_title || "無題のセッション"}
              </div>
              {result.matches.length > 0 && result.matches[0].snippet && (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--sds-color-on-surface-variant)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    marginTop: 2,
                  }}
                >
                  {result.matches[0].snippet}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* スピンアニメーション用スタイル */}
      <style>{`
        @keyframes spin {
          to { transform: translateY(-50%) rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
