// Base API client with X-User-Id header injection

const API_BASE_URL = "/the-rag/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getUserId(): string {
  // Import inline to avoid circular dependency
  // The fingerprint utility manages localStorage persistence
  const existing = localStorage.getItem("the-rag-user-id");
  if (existing) return existing;
  // Auto-create on first access
  const id = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  localStorage.setItem("the-rag-user-id", id);
  return id;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: Record<string, unknown> | FormData;
}

async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, headers: extraHeaders, ...rest } = options;

  const headers: Record<string, string> = {
    "X-User-Id": getUserId(),
    ...(extraHeaders as Record<string, string>),
  };

  let processedBody: BodyInit | undefined;

  if (body instanceof FormData) {
    processedBody = body;
    // Do NOT set Content-Type; browser sets it with boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    processedBody = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers,
    body: processedBody,
  });

  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, message);
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T>(path: string, options?: Omit<RequestOptions, "body" | "method">) =>
    request<T>(path, { ...options, method: "GET" }),

  post: <T>(path: string, body?: Record<string, unknown> | FormData, options?: Omit<RequestOptions, "body" | "method">) =>
    request<T>(path, { ...options, method: "POST", body }),

  put: <T>(path: string, body?: Record<string, unknown>, options?: Omit<RequestOptions, "body" | "method">) =>
    request<T>(path, { ...options, method: "PUT", body }),

  patch: <T>(path: string, body?: Record<string, unknown>, options?: Omit<RequestOptions, "body" | "method">) =>
    request<T>(path, { ...options, method: "PATCH", body }),

  delete: <T>(path: string, options?: Omit<RequestOptions, "body" | "method">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
