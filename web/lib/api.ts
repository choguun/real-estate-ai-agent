/**
 * Typed fetch client for the FastAPI backend.
 *
 * - Reads NEXT_PUBLIC_API_URL (default http://localhost:8000).
 * - Attaches Authorization: Bearer <token> when `setAuthToken` was called.
 * - Throws `ApiError` on non-2xx so callers can use try/catch.
 */

export class ApiError extends Error {
  public readonly status: number;
  public readonly detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.name = "ApiError";
  }
}

export interface User {
  id: string;
  email: string | null;
  full_name: string;
  phone?: string | null;
  role?: string | null;
  line_user_id?: string | null;
}

export interface AuthResponse {
  user: User;
  token: string;
}

const TOKEN_KEY = "auth_token";

let cachedToken: string | null = null;

function readToken(): string | null {
  if (cachedToken) return cachedToken;
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(TOKEN_KEY);
  cachedToken = stored;
  return stored;
}

export function setAuthToken(token: string | null): void {
  cachedToken = token;
  if (typeof window !== "undefined") {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }
}

export function getAuthToken(): string | null {
  return readToken();
}

export function clearAuthToken(): void {
  setAuthToken(null);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* swallow */
    }
    throw new ApiError(res.status, detail || res.statusText, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  return apiGet<{ status: string }>("/health");
}
