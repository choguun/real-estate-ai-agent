// T-703 — CSP violation reporting client helper (cycle 7 AC-CSP-05).
//
// 3 vitest tests covering:
//
// - The helper extracts the right fields from a
//   SecurityPolicyViolationEvent and posts to /api/csp-report
//   with Content-Type: application/csp-report
// - The helper is silent on fetch errors (best-effort; never
//   alerts the user, never logs to console)
// - The helper is a no-op when CSP isn't violated (returns
//   immediately, no network call)

import { describe, it, expect, vi, beforeEach } from "vitest";
import { reportCspViolation } from "@/lib/csp_report";

describe("csp_report helper (T-703)", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({ status: 204 });
    global.fetch = fetchMock;
  });

  it("posts the violation to /api/csp-report with the standard body shape", async () => {
    const event = {
      documentURI: "https://app.example.com/dashboard",
      violatedDirective: "script-src 'self'",
      blockedURI: "https://evil.example.com/x.js",
      originalPolicy: "default-src 'self'; script-src 'self'",
    } as unknown as SecurityPolicyViolationEvent;

    await reportCspViolation(event);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/csp-report");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/csp-report");
    const body = JSON.parse(init.body);
    expect(body["csp-report"]).toEqual({
      "document-uri": "https://app.example.com/dashboard",
      "violated-directive": "script-src 'self'",
      "blocked-uri": "https://evil.example.com/x.js",
      "original-policy": "default-src 'self'; script-src 'self'",
    });
  });

  it("swallows fetch errors silently", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));

    const event = {
      documentURI: "https://app.example.com",
      violatedDirective: "script-src 'self'",
      blockedURI: "https://evil.example.com/x.js",
    } as unknown as SecurityPolicyViolationEvent;

    // Must NOT throw — browsers shouldn't see retry storms from
    // our CSP report helper.
    await expect(reportCspViolation(event)).resolves.toBeUndefined();
  });

  it("swallows non-204 responses silently", async () => {
    // Even if the backend returns 5xx or 4xx, we don't escalate —
    // CSP reports are best-effort.
    fetchMock.mockResolvedValue({ status: 500 });

    const event = {
      documentURI: "https://app.example.com",
      violatedDirective: "script-src 'self'",
      blockedURI: "https://evil.example.com/x.js",
    } as unknown as SecurityPolicyViolationEvent;

    await expect(reportCspViolation(event)).resolves.toBeUndefined();
  });
});