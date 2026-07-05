/**
 * Client-side CSP violation reporter (cycle 7 T-703, AC-CSP-05).
 *
 * When the browser blocks a script per the page's CSP, the
 * browser's `SecurityPolicyViolationEvent` fires. This helper
 * extracts the relevant fields and forwards them to the backend
 * via `POST /api/csp-report` with the standard
 * `application/csp-report` content-type.
 *
 * Best-effort: fetch errors are silently swallowed (a CSP report
 * failure must never alert the user or break the page).
 *
 * Wired in `web/app/layout.tsx` via a `document.addEventListener`
 * for `securitypolicyviolation`.
 */

export interface CspReportBody {
  "csp-report": {
    "document-uri": string;
    "violated-directive": string;
    "blocked-uri": string;
    "original-policy"?: string;
  };
}

/**
 * Forward a CSP violation to the backend.
 *
 * Caller is responsible for debouncing (CSP events can fire many
 * times for the same violation); pass a debounced handler in the
 * layout, not this raw function.
 */
export async function reportCspViolation(
  event: SecurityPolicyViolationEvent,
): Promise<void> {
  const body: CspReportBody = {
    "csp-report": {
      "document-uri": event.documentURI || "unknown",
      "violated-directive": event.violatedDirective || "unknown",
      "blocked-uri": event.blockedURI || "unknown",
      "original-policy": event.originalPolicy,
    },
  };

  try {
    await fetch("/api/csp-report", {
      method: "POST",
      headers: { "Content-Type": "application/csp-report" },
      body: JSON.stringify(body),
      // CSP reports are best-effort; never block the page.
      keepalive: true,
    });
  } catch {
    // Swallow — the browser should never see a CSP-report failure
    // escalate into a console error or a page-level alert.
  }
}