"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, clearAuthToken, getAuthToken } from "@/lib/api";
import type { User } from "@/lib/api";
import { getDashboard } from "@/lib/dashboard";
import type { DashboardData } from "@/lib/types";
import { fetchMe } from "@/lib/auth";
import { NewLeadsCounter } from "@/components/dashboard/NewLeadsCounter";
import { RecentMessages } from "@/components/dashboard/RecentMessages";
import { RecentProperties } from "@/components/dashboard/RecentProperties";

const POLL_INTERVAL_MS = 5_000;

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    // AbortController per poll cycle — guards against overlapping
    // fetches when the backend is slower than POLL_INTERVAL_MS.
    let inflight: AbortController | null = null;

    async function load() {
      inflight?.abort();
      const ctl = new AbortController();
      inflight = ctl;
      try {
        const [me, d] = await Promise.all([
          fetchMe({ signal: ctl.signal }),
          getDashboard({ signal: ctl.signal }),
        ]);
        if (cancelled || ctl.signal.aborted) return;
        setUser(me);
        setData(d);
        setError(null);
      } catch (err) {
        if (cancelled || ctl.signal.aborted) return;
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          router.replace("/login");
          return;
        }
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(
          err instanceof ApiError
            ? err.detail || err.message
            : "Failed to load dashboard",
        );
      }
    }

    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      inflight?.abort();
      clearInterval(interval);
    };
  }, [router]);

  function handleLogout() {
    clearAuthToken();
    router.replace("/login");
  }

  if (data === null && error === null) {
    return (
      <main>
        <p className="text-sm text-muted-foreground">Loading dashboard…</p>
      </main>
    );
  }

  if (error) {
    return (
      <main>
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {error}
        </div>
      </main>
    );
  }

  const d = data ?? { new_leads_count: 0, recent_inbound: [], recent_properties: [] };

  return (
    <main className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" data-testid="greeting">
            สวัสดี, {user?.full_name ?? "agent"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            ภาพรวมของ inbox และ listings — auto-refreshes every 5s
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent"
        >
          Sign out
        </button>
      </header>

      <section data-testid="dashboard">
        <NewLeadsCounter count={d.new_leads_count} />

        <h2 className="mt-8 mb-3 text-lg font-semibold tracking-tight">
          Recent inbox
        </h2>
        <RecentMessages messages={d.recent_inbound} />

        <h2 className="mt-8 mb-3 text-lg font-semibold tracking-tight">
          Recent properties
        </h2>
        <RecentProperties properties={d.recent_properties} />
      </section>
    </main>
  );
}
