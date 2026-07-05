// Cycle 6 T-605 — Front-end security headers (AC-WEB-01..05).
//
// Asserts the headers config exported by next.config.mjs sets the
// baseline security headers on every route:
//   - Content-Security-Policy
//   - Strict-Transport-Security (HSTS)
//   - X-Content-Type-Options
//   - X-Frame-Options
//   - Referrer-Policy
//
// We import the config directly (rather than spinning up `next dev`)
// because (a) faster — no Next.js server needed, (b) the headers()
// function is a pure function that takes a list of routes and returns
// the final headers; testing the export is the right level.

import { describe, it, expect } from "vitest";
// @ts-expect-error — next.config.mjs has no .d.ts; we only access
// the `headers` runtime field via a typed accessor below.
import nextConfig from "../next.config.mjs";

describe("security headers (T-605)", () => {
  // The NextConfig export is an object. The headers function may be
  // attached as `nextConfig.headers`. Some Next.js shapes use a
  // function vs an object — handle both.
  const headersFn = (nextConfig as any).headers as
    | undefined
    | (() => Promise<Array<{ source: string; headers: Array<{ key: string; value: string }> }>>);

  async function fetchHeaders() {
    if (typeof headersFn !== "function") {
      throw new Error(
        "next.config.mjs must export a `headers()` function returning an array of route rules"
      );
    }
    return await headersFn();
  }

  it("AC-WEB-01: Content-Security-Policy header is set on every route", async () => {
    const rules = await fetchHeaders();
    const allRoute = rules.find((r) => r.source === "/(.*)");
    expect(allRoute, "missing route matcher for /(.*)").toBeDefined();
    const csp = allRoute!.headers.find((h) => h.key === "Content-Security-Policy");
    expect(csp, "Content-Security-Policy header missing").toBeDefined();
    expect(csp!.value).toContain("default-src 'self'");
    // Stripe needs to be allowed in frame-src + connect-src for Checkout
    expect(csp!.value).toContain("https://js.stripe.com");
    // AC-CSP-04: cycle 7 T-703 adds report-uri to the production CSP.
    // In tests NODE_ENV is "test" so isDev=true and report-uri
    // is gated off. The production path is verified by the
    // dedicated AC-CSP-04 test below.
  });

  it("AC-CSP-04: report-uri is wired when NODE_ENV !== 'development'", async () => {
    // The config module reads NODE_ENV at module-load time, so
    // we can't easily flip it in a vitest test. Instead, read
    // the source file and assert the directive plumbing is in
    // place (the production CSP includes report-uri when isDev
    // is false). This is a contract test on the source code, not
    // on the runtime value.
    const fs = await import("node:fs/promises");
    const src = await fs.readFile("./next.config.mjs", "utf-8");
    expect(src).toMatch(/report-uri \/api\/csp-report/);
    // The directive must be gated by isDev so dev mode doesn't
    // POST to the (potentially-non-existent) backend.
    expect(src).toMatch(/isDev \? "" : "report-uri/);
  });

  it("AC-WEB-02: Strict-Transport-Security header is set", async () => {
    const rules = await fetchHeaders();
    const allRoute = rules.find((r) => r.source === "/(.*)");
    const hsts = allRoute!.headers.find((h) => h.key === "Strict-Transport-Security");
    expect(hsts, "HSTS header missing").toBeDefined();
    // 2 years (industry standard for HSTS preload eligibility)
    expect(hsts!.value).toMatch(/max-age=63072000/);
    expect(hsts!.value).toContain("includeSubDomains");
    expect(hsts!.value).toContain("preload");
  });

  it("AC-WEB-03: baseline headers (X-CTO, X-Frame-Options, Referrer-Policy)", async () => {
    const rules = await fetchHeaders();
    const allRoute = rules.find((r) => r.source === "/(.*)");
    const headerMap = new Map(allRoute!.headers.map((h) => [h.key, h.value]));

    expect(headerMap.get("X-Content-Type-Options")).toBe("nosniff");
    expect(headerMap.get("X-Frame-Options")).toBe("DENY");
    expect(headerMap.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
  });

  it("AC-WEB-04: matcher covers all routes (source: '/(.*)')", async () => {
    const rules = await fetchHeaders();
    const allRoute = rules.find((r) => r.source === "/(.*)");
    expect(allRoute).toBeDefined();
  });
});