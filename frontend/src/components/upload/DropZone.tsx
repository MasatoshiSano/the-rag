// DropZone: HTML5 drag-and-drop file selector with WCAG 2.2 AA compliance
import { useRef, useState, useCallback } from "react";
import {
  SerendieSymbolUploadCloud,
  SerendieSymbolFile,
} from "@serendie/symbols";

const ACCEPTED_EXTENSIONS = [
  "md", "txt", "csv", "json", "pdf",
  "pptx", "xlsx", "docx", "png", "jpeg", "jpg", "html",
];

const ACCEPTED_MIME_TYPES = [
  "text/markdown",
  "text/plain",
  "text/csv",
  "application/json",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "image/png",
  "image/jpeg",
  "text/html",
];

const MAX_FILES = 20;

interface DropZoneProps {
  onFilesSelected: (files: File[]) => void;
  currentFileCount: number;
  disabled?: boolean;
}

function isAcceptedFile(file: File): boolean {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return ACCEPTED_EXTENSIONS.includes(ext) || ACCEPTED_MIME_TYPES.includes(file.type);
}

export function DropZone({ onFilesSelected, currentFileCount, disabled = false }: DropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = "dropzone-error";

  const processFiles = useCallback(
    (rawFiles: FileList | File[]) => {
      setErrorMessage(null);
      const fileArray = Array.from(rawFiles);
      const validFiles = fileArray.filter(isAcceptedFile);
      const invalidCount = fileArray.length - validFiles.length;

      if (invalidCount > 0) {
        setErrorMessage(
          `${invalidCount} 件のファイルは対応していない形式のため除外されました。`
        );
      }

      const remaining = MAX_FILES - currentFileCount;
      if (validFiles.length > remaining) {
        setErrorMessage(
          `最大 ${MAX_FILES} ファイルまでです。${remaining} 件のみ追加されました。`
        );
        onFilesSelected(validFiles.slice(0, remaining));
      } else {
        onFilesSelected(validFiles);
      }
    },
    [currentFileCount, onFilesSelected]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setIsDragOver(true);
  }, [disabled]);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);
      if (disabled) return;
      processFiles(e.dataTransfer.files);
    },
    [disabled, processFiles]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        processFiles(e.target.files);
        // Reset input so same file can be re-selected
        e.target.value = "";
      }
    },
    [processFiles]
  );

  const handleClick = useCallback(() => {
    if (!disabled) inputRef.current?.click();
  }, [disabled]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (!disabled) inputRef.current?.click();
      }
    },
    [disabled]
  );

  const canAddMore = currentFileCount < MAX_FILES && !disabled;

  return (
    <div>
      <div
        role="button"
        tabIndex={canAddMore ? 0 : -1}
        aria-label="ファイルをドラッグ＆ドロップまたはクリックして選択"
        aria-describedby={errorMessage ? errorId : undefined}
        aria-disabled={!canAddMore}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${
            isDragOver
              ? "var(--sds-color-impression-primary)"
              : "var(--sds-color-outline-default)"
          }`,
          borderRadius: "var(--sds-border-radius-medium, 12px)",
          padding: "40px 24px",
          textAlign: "center",
          cursor: canAddMore ? "pointer" : "not-allowed",
          backgroundColor: isDragOver
            ? "var(--sds-color-impression-primaryContainer)"
            : "var(--sds-color-surface-container)",
          transition: "border-color 0.15s ease, background-color 0.15s ease",
          outline: "none",
        }}
        onFocus={(e) => {
          if (canAddMore) {
            e.currentTarget.style.boxShadow =
              "0 0 0 3px var(--sds-color-impression-primary)";
          }
        }}
        onBlur={(e) => {
          e.currentTarget.style.boxShadow = "none";
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "12px",
            color: canAddMore
              ? "var(--sds-color-on-surface-default)"
              : "var(--sds-color-interaction-disabledOnSurface)",
          }}
        >
          <SerendieSymbolUploadCloud
            style={{
              width: 48,
              height: 48,
              color: isDragOver
                ? "var(--sds-color-impression-primary)"
                : "var(--sds-color-on-surface-variant)",
            }}
            aria-hidden="true"
          />
          <p
            style={{
              margin: 0,
              fontSize: "var(--sds-typography-body-medium-font-size, 14px)",
              fontWeight: 700,
            }}
          >
            {isDragOver
              ? "ここにドロップしてください"
              : "ファイルをドラッグ＆ドロップ、またはクリックして選択"}
          </p>
          <p
            style={{
              margin: 0,
              fontSize: "var(--sds-typography-body-small-font-size, 12px)",
              color: "var(--sds-color-on-surface-variant)",
            }}
          >
            最大 {MAX_FILES} ファイル（現在 {currentFileCount} / {MAX_FILES}）
          </p>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              flexWrap: "wrap",
              justifyContent: "center",
            }}
          >
            <SerendieSymbolFile
              style={{ width: 14, height: 14 }}
              aria-hidden="true"
            />
            <span
              style={{
                fontSize: "var(--sds-typography-body-small-font-size, 11px)",
                color: "var(--sds-color-on-surface-variant)",
              }}
            >
              対応形式: {ACCEPTED_EXTENSIONS.join(", ")}
            </span>
          </div>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(",")}
          onChange={handleInputChange}
          style={{ display: "none" }}
          tabIndex={-1}
          aria-hidden="true"
        />
      </div>

      {errorMessage && (
        <p
          id={errorId}
          role="alert"
          aria-live="polite"
          style={{
            marginTop: "8px",
            fontSize: "var(--sds-typography-body-small-font-size, 12px)",
            color: "var(--sds-color-negative-default, #d32f2f)",
          }}
        >
          {errorMessage}
        </p>
      )}
    </div>
  );
}
