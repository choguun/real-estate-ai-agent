/**
 * Auth wrappers around `lib/api.ts`. Each function returns the auth
 * payload, persists the token, and surfaces error messages from
 * `ApiError.detail`.
 */

import { apiPost, apiGet, ApiError, AuthResponse, setAuthToken, User } from "./api";

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await apiPost<AuthResponse>("/api/auth/login", { email, password });
  setAuthToken(res.token);
  return res;
}

export async function signup(input: {
  email: string;
  full_name: string;
  password: string;
}): Promise<AuthResponse> {
  const res = await apiPost<AuthResponse>("/api/auth/signup", input);
  setAuthToken(res.token);
  return res;
}

export async function liffLogin(line_user_id: string, display_name?: string): Promise<AuthResponse> {
  const res = await apiPost<AuthResponse>("/api/auth/liff", {
    line_user_id,
    display_name,
  });
  setAuthToken(res.token);
  return res;
}

export async function fetchMe(): Promise<User> {
  return apiGet<User>("/api/auth/me");
}

export function describeAuthError(err: unknown): string {
  if (err instanceof ApiError) {
    return err.detail || err.message || "Authentication failed";
  }
  if (err instanceof Error) return err.message;
  return "Authentication failed";
}
