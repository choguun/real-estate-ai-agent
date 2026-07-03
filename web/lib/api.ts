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

/**
 * Read the JWT afresh from localStorage every call.
 *
 * Rationale: a module-level cache (`cachedToken`) sounded like an
 * obvious optimization but caused two real bugs —
 *   (a) StrictMode double-render in dev can drop a value mid-flight;
 *   (b) `clearAuthToken()` mutates a singleton shared by every
 *       component, so one clear can race another component's read.
 *
 * `localStorage.getItem` is ~10 µs and runs on every API call anyway;
 * the cache wasn't buying anything.
 */
function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getAuthToken(): string | null {
  return readToken();
}

export function clearAuthToken(): void {
  setAuthToken(null);
}

/**
 * Low-level fetch — pass the init object straight through, including a
 * pre-serialized body. For JSON helpers see `apiGet`/`apiPost`/`apiPatch`.
 * For multipart uploads use `apiUpload`.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const headers = new Headers(init.headers);
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

export async function apiGet<T>(
  path: string,
  options?: { signal?: AbortSignal },
): Promise<T> {
  return request<T>(path, { method: "GET", signal: options?.signal });
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  options?: { signal?: AbortSignal },
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export async function apiPatch<T>(
  path: string,
  body: unknown,
  options?: { signal?: AbortSignal },
): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export async function apiPostNoBody<T>(path: string): Promise<T> {
  return request<T>(path, { method: "POST" });
}

/** Multipart upload — FormData is sent as-is; browser sets the boundary header. */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: formData });
}

export async function checkBackendHealth(): Promise<{ status: string }> {
  return apiGet<{ status: string }>("/health");
}
