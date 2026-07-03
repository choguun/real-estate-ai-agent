"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { clearAuthToken, getAuthToken } from "@/lib/api";
import { fetchMe } from "@/lib/auth";
import type { User } from "@/lib/api";

/**
 * T-003 placeholder. Real dashboard (counter + recent messages + recent
 * properties) lands in T-011.
 */
export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    fetchMe()
      .then(setUser)
      .catch((err) => setError(String(err)));
  }, [router]);

  function handleLogout() {
    clearAuthToken();
    router.replace("/login");
  }

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-20">
      <h1 className="text-3xl font-bold tracking-tight">Welcome, {user.full_name}</h1>
      <p className="mt-2 text-muted-foreground">
        Signed in as {user.email ?? `${user.line_user_id} (LINE)`}
      </p>

      <div className="mt-10 rounded-lg border bg-card p-6">
        <h2 className="font-medium">Coming in T-011</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          This page will show: inbound message counter, latest 5 properties,
          new-leads count. Today&apos;s auth is wired up — try /login or /signup again
          after signing out to confirm round-trip.
        </p>
        <div className="mt-6 flex gap-3">
          <Link href="/" className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent">
            Home
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
          >
            Sign out
          </button>
        </div>
      </div>
    </main>
  );
}
