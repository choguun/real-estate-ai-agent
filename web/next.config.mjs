/**
 * Next.js config — cycle 6 T-605 (AC-WEB-01..05).
 *
 * Adds baseline security headers on every route:
 *   - Content-Security-Policy (CSP)
 *   - Strict-Transport-Security (HSTS)
 *   - X-Content-Type-Options
 *   - X-Frame-Options
 *   - Referrer-Policy
 *
 * The CSP uses 'unsafe-inline' for scripts because Next.js's bootstrap
 * script is inline today. This is the only unsafe directive; tighten
 * to nonce-based CSP in cycle 7+ if a CSP-violation-reporting channel
 * is added.
 */

/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV !== "production";

const securityHeaders = [
  // ── CSP ─────────────────────────────────────────────────────────────
  // default-src 'self' is the safe default.
  // script-src allows 'unsafe-inline' because Next.js bootstrap is inline.
  //   (Production nonces would tighten this — cycle 7+.)
  // style-src allows inline styles for the Tailwind / shadcn utilities.
  // img-src allows data: URIs (Next.js image placeholders) + https.
  // connect-src allows the API + Stripe.
  // frame-src allows Stripe Checkout (js.stripe.com hosts the iframe).
  // object-src 'none' blocks legacy plugin content.
  // base-uri 'self' prevents <base> tag injection attacks.
  // frame-ancestors 'none' prevents clickjacking via iframe embedding.
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // Dev allows 'unsafe-eval' for HMR (webpack hot-reload).
      isDev
        ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
        : "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      `connect-src 'self' ${isDev ? "ws: http://localhost:*" : ""} https://api.stripe.com`,
      "frame-src https://js.stripe.com",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      // Cycle 7 T-703: browsers POST violation reports here.
      // Same-origin so the standard browser fetch path works.
      isDev ? "" : "report-uri /api/csp-report",
    ]
      .filter(Boolean)
      .join("; "),
  },

  // ── HSTS ────────────────────────────────────────────────────────────
  // 2 years, includeSubDomains, preload-eligible.
  // (Note: enabling preload commits you to maintaining HTTPS forever.
  //  Remove `preload` until you're sure you can keep that promise.)
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },

  // ── Baseline ───────────────────────────────────────────────────────
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },

  // Permissions-Policy: disable unused browser features (defense in depth).
  {
    key: "Permissions-Policy",
    value: 'geolocation=(), microphone=(), camera=(), payment=(self "https://js.stripe.com")',
  },
];

const nextConfig = {
  reactStrictMode: true,
  async headers() {
    // AC-WEB-04: the matcher is '/(.*)' so the rules apply to every
    // route. Next.js doesn't allow wildcards in 'source' alone, but
    // the pattern '/(.*)' is the documented "everything" form.
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;