import { useState, useRef, useCallback, useEffect } from "react";
import { SerendieSymbolMic, SerendieSymbolMicMuted } from "@serendie/symbols";

// Web Speech API の型定義 (標準 TypeScript 型定義に含まれないため手動定義)
interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message: string;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  readonly transcript: string;
  readonly confidence: number;
}

interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

// ブラウザの SpeechRecognition 対応確認
function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

type VoiceState = "idle" | "listening";

export interface VoiceButtonProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

/**
 * 音声入力ボタンコンポーネント
 *
 * Usage:
 *   <VoiceButton onTranscript={(text) => setInput((prev) => prev + text)} />
 */
export function VoiceButton({ onTranscript, disabled = false }: VoiceButtonProps) {
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const SpeechRecognitionCtor = getSpeechRecognitionConstructor();
  const isSupported = SpeechRecognitionCtor !== null;
  const isListening = voiceState === "listening";

  // コンポーネントアンマウント時に認識を停止する
  useEffect(() => {
    return () => {
      recognitionRef.current?.abort();
    };
  }, []);

  const startListening = useCallback(() => {
    if (!SpeechRecognitionCtor) return;

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "ja-JP";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => {
      setVoiceState("listening");
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      // 最終結果のみを transcript として返す
      let finalTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript.length > 0) {
        onTranscript(finalTranscript);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // "no-speech" はユーザー操作なしで終了するため無視
      if (event.error !== "no-speech") {
        console.error("音声認識エラー:", event.error, event.message);
      }
      setVoiceState("idle");
      recognitionRef.current = null;
    };

    recognition.onend = () => {
      setVoiceState("idle");
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [SpeechRecognitionCtor, onTranscript]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setVoiceState("idle");
  }, []);

  const handleClick = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  const isButtonDisabled = disabled || !isSupported;

  const ariaLabel = isListening ? "音声入力を停止" : "音声入力を開始";
  const title = !isSupported
    ? "このブラウザは音声入力に対応していません。Google Chrome をお試しください。"
    : ariaLabel;

  return (
    <button
      type="button"
      role="button"
      aria-label={ariaLabel}
      aria-pressed={isListening}
      title={title}
      disabled={isButtonDisabled}
      onClick={handleClick}
      style={{
        flexShrink: 0,
        width: 36,
        height: 36,
        borderRadius: "50%",
        border: isListening
          ? "2px solid var(--sds-color-primary-default)"
          : "1px solid var(--sds-color-outline-default)",
        backgroundColor: isListening
          ? "var(--sds-color-primary-container)"
          : "transparent",
        cursor: isButtonDisabled ? "not-allowed" : "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: isListening
          ? "var(--sds-color-primary-default)"
          : isButtonDisabled
            ? "var(--sds-color-on-surface-disabled)"
            : "var(--sds-color-on-surface-low)",
        transition: "background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease",
        outline: "none",
        // listening 中は点滅アニメーションを当てる
        animation: isListening ? "voice-pulse 1.2s ease-in-out infinite" : "none",
      }}
      onFocus={(e) => {
        if (!isButtonDisabled) {
          (e.currentTarget as HTMLButtonElement).style.boxShadow =
            "0 0 0 2px var(--sds-color-primary-default)";
        }
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLButtonElement).style.boxShadow = "none";
      }}
      onMouseEnter={(e) => {
        if (!isButtonDisabled && !isListening) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "var(--sds-color-surface-container-high)";
        }
      }}
      onMouseLeave={(e) => {
        if (!isListening) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = "transparent";
        }
      }}
    >
      {/* listening 中はマイクミュートアイコンで「停止可能」を示す */}
      {isListening ? (
        <SerendieSymbolMicMuted
          aria-hidden="true"
          width={18}
          height={18}
          style={{ display: "block" }}
        />
      ) : (
        <SerendieSymbolMic
          aria-hidden="true"
          width={18}
          height={18}
          style={{ display: "block" }}
        />
      )}

      {/* listening 中のグローバルアニメーション定義 (SSRセーフ) */}
      {isListening && (
        <style>{`
          @keyframes voice-pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
          }
        `}</style>
      )}
    </button>
  );
}
