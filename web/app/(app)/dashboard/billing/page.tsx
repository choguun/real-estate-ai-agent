"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";

import { billingApi, BillingStatusOut, PlanTier, PLAN_PRICING } from "@/lib/billing";
import { getAuthToken } from "@/lib/api";

export default function BillingPage() {
  const [status, setStatus] = useState<BillingStatusOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [upgrading, setUpgrading] = useState<PlanTier | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const searchParams = useSearchParams();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await billingApi.status();
      setStatus(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    // Show success toast on return from Stripe
    if (searchParams.get("upgrade") === "success") {
      setToast("🎉 Upgrade successful! Welcome to your new plan.");
      // Reload to pick up the new plan state from the webhook
      void load();
    } else if (searchParams.get("upgrade") === "canceled") {
      setToast("Upgrade canceled — no changes made.");
    }
  }, [searchParams, load]);

  async function onUpgrade(plan: PlanTier) {
    if (!getAuthToken()) {
      setError("Not authenticated");
      return;
    }
    setUpgrading(plan);
    setError(null);
    try {
      const { url } = await billingApi.checkout(plan);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setUpgrading(null);
    }
  }

  async function onManageBilling() {
    try {
      const { url } = await billingApi.portal();
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Portal failed");
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <p>Loading billing…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Billing</h1>
          {status && (
            <p className="text-sm text-muted-foreground">
              Current plan: <strong>{status.plan}</strong>
              {status.is_paid ? ` · $${PLAN_PRICING[status.plan as Exclude<PlanTier, "starter">]?.price ?? "?"}/mo` : " · Free"}
            </p>
          )}
        </div>
        {status?.is_paid && (
          <button
            type="button"
            onClick={onManageBilling}
            className="rounded border px-4 py-2 text-sm hover:bg-muted"
          >
            Manage billing
          </button>
        )}
      </header>

      {toast && (
        <div
          role="status"
          className="mb-4 rounded border border-green-300 bg-green-50 px-4 py-2 text-sm text-green-800"
        >
          {toast}
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="mb-4 rounded border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {status && (
        <section className="mb-8 rounded-lg border p-4">
          <h2 className="mb-3 text-sm font-medium uppercase text-muted-foreground">
            Usage
          </h2>
          <ul className="space-y-1 text-sm">
            <li>
              Seats: {status.seats_used} / {status.seats_limit}
            </li>
            <li>
              Properties: {status.properties_used} / {status.properties_limit}
            </li>
            <li>
              AI listings (this month): {status.ai_listings_used_month} /{" "}
              {status.ai_listings_limit_month}
            </li>
            {status.current_period_end && (
              <li>
                Current period ends:{" "}
                {new Date(status.current_period_end).toLocaleDateString()}
              </li>
            )}
          </ul>
        </section>
      )}

      <h2 className="mb-3 text-sm font-medium uppercase text-muted-foreground">
        Plans
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {(["starter", "growth", "team"] as const).map((plan) => {
          const isCurrent = status?.plan === plan;
          const cfg = plan === "starter"
            ? { name: "Starter", price: 0, seats: 1, properties: 5, ai: 20 }
            : PLAN_PRICING[plan];
          return (
            <article
              key={plan}
              className={`rounded-lg border p-4 ${
                isCurrent ? "border-primary ring-2 ring-primary/20" : ""
              }`}
            >
              <header className="mb-2">
                <h3 className="text-lg font-semibold">
                  {cfg.name}
                  {isCurrent && (
                    <span className="ml-2 rounded bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                      Current
                    </span>
                  )}
                </h3>
                <p className="text-2xl font-bold">
                  {cfg.price === 0 ? "Free" : `$${cfg.price}`}
                  {cfg.price > 0 && (
                    <span className="text-sm font-normal text-muted-foreground">
                      /mo
                    </span>
                  )}
                </p>
              </header>
              <ul className="mb-3 space-y-1 text-sm text-muted-foreground">
                <li>{cfg.seats} member{cfg.seats > 1 ? "s" : ""}</li>
                <li>{cfg.properties} properties</li>
                <li>{cfg.ai} AI listings/month</li>
              </ul>
              <button
                type="button"
                onClick={() => onUpgrade(plan)}
                disabled={plan === "starter" || isCurrent || upgrading !== null}
                className="w-full rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
              >
                {isCurrent
                  ? "Current plan"
                  : plan === "starter"
                    ? "Free"
                    : upgrading === plan
                      ? "Opening Stripe…"
                      : `Upgrade to ${cfg.name}`}
              </button>
            </article>
          );
        })}
      </div>
    </main>
  );
}
