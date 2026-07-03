/**
 * Typed fetch client for the FastAPI backend.
 *
 * - Reads NEXT_PUBLIC_API_URL (default http://localhost:8000).
 * - Attaches Authorization: Bearer <token> when `setAuthToken` was called.
 * - Throws `ApiError` on non-2xx so callers can use try/catch.
 */

export class ApiError extends Error {
  public readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

let cachedToken: string | null = null;

export function setAuthToken(token: string | null): void {
  cachedToken = token;
  if (typeof window !== "undefined") {
    if (token) localStorage.setItem("auth_token", token);
    else localStorage.removeItem("auth_token");
  }
}

function readToken(): string | null {
  if (cachedToken) return cachedToken;
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem("auth_token");
  cachedToken = stored;
  return stored;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url =
    (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + path;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}
