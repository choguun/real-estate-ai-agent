import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { ApiError } from "@/lib/api";
import { describeAuthError, login, signup, liffLogin } from "@/lib/auth";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  if (typeof window !== "undefined") window.localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("auth wrappers", () => {
  it("login posts credentials and stores token", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        user: { id: "u1", email: "a@example.com", full_name: "A" },
        token: "jwt-token-abc",
      }),
    );

    const res = await login("a@example.com", "password123");

    expect(res.token).toBe("jwt-token-abc");
    expect(res.user.email).toBe("a@example.com");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const call = fetchMock.mock.calls[0];
    expect(call[0]).toContain("/api/auth/login");
    expect((call[1] as RequestInit).method).toBe("POST");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({
      email: "a@example.com",
      password: "password123",
    });
  });

  it("signup posts and stores token", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        user: { id: "u2", email: "b@example.com", full_name: "B" },
        token: "jwt-token-def",
      }),
    );

    await signup({ email: "b@example.com", full_name: "B", password: "password123" });

    expect(fetchMock.mock.calls[0][0]).toContain("/api/auth/signup");
  });

  it("liffLogin posts line_user_id and stores token", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        user: {
          id: "u3",
          email: "line_user@line.placeholder",
          full_name: "Y",
          line_user_id: "U9999",
        },
        token: "jwt-token-liff",
      }),
    );

    await liffLogin("U9999", "Y");

    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.line_user_id).toBe("U9999");
    expect(body.display_name).toBe("Y");
  });

  it("surfaces ApiError on 401", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: "Invalid email or password" }, 401),
    );

    await expect(login("a@example.com", "wrong")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("describeAuthError", () => {
  it("uses ApiError.detail when present", () => {
    expect(describeAuthError(new ApiError(401, "fallback", "Invalid email or password"))).toBe(
      "Invalid email or password",
    );
  });

  it("falls back to .message", () => {
    expect(describeAuthError(new Error("boom"))).toBe("boom");
  });

  it("falls back to the default message", () => {
    expect(describeAuthError("not an error")).toBe("Authentication failed");
  });
});
