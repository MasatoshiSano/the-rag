// fingerprint.ts: generate and persist a UUID for anonymous user identification
// The UUID is stored in localStorage so it survives page reloads.

const STORAGE_KEY = "the-rag-user-id";

/**
 * Return the existing fingerprint UUID from localStorage, or generate and
 * persist a new one if none exists. This function is synchronous and
 * side-effect safe (idempotent for the same browser session).
 */
export function getOrCreateFingerprint(): string {
  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) return existing;

  const id = generateUuid();
  localStorage.setItem(STORAGE_KEY, id);
  return id;
}

/**
 * Generate a v4-compatible UUID using the Web Crypto API when available,
 * falling back to a Math.random-based implementation for environments
 * where crypto is unavailable.
 */
function generateUuid(): string {
  if (
    typeof globalThis.crypto !== "undefined" &&
    typeof globalThis.crypto.randomUUID === "function"
  ) {
    return globalThis.crypto.randomUUID();
  }

  // Fallback: RFC 4122 v4 UUID via Math.random
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const rand = (Math.random() * 16) | 0;
    const value = char === "x" ? rand : (rand & 0x3) | 0x8;
    return value.toString(16);
  });
}
