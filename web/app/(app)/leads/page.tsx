"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, getAuthToken } from "@/lib/api";
import { listLeads } from "@/lib/leads";
import type { Lead } from "@/lib/types";
import { LEAD_STATUS_LABELS_TH } from "@/lib/types";

const STATUS_FILTERS: { label: string; value?: string }[] = [
  { label: "ทั้งหมด", value: undefined },
  { label: "ใหม่", value: "new" },
  { label: "ติดต่อแล้ว", value: "contacted" },
  { label: "มีศักยภาพ", value: "qualified" },
  { label: "นัดชม", value: "viewing" },
  { label: "เจรจา", value: "negotiation" },
  { label: "ปิดดีล", value: "closed" },
  { label: "หลุด", value: "lost" },
];

export default function LeadsPage() {
  const router = useRouter();
  const [leads, setLeads] = useState<Lead[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    listLeads(filter ? { status: filter } : {})
      .then(setLeads)
      .catch((err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          router.replace("/login");
          return;
        }
        setError(err.detail || err.message || "Failed to load leads");
      });
  }, [router, filter]);

  if (leads === null && error === null) {
    return (
      <main>
        <p className="text-sm text-muted-foreground">Loading leads…</p>
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

  const list = leads ?? [];

  return (
    <main>
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Leads</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Inbound LINE conversations, organized by status.
          </p>
        </div>
      </header>

      <div role="tablist" className="mb-6 flex flex-wrap gap-2 border-b pb-2">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s.label}
            type="button"
            role="tab"
            aria-selected={filter === s.value}
            data-testid={`filter-${s.value ?? "all"}`}
            onClick={() => setFilter(s.value)}
            className={`rounded-full px-3 py-1 text-xs transition ${
              filter === s.value
                ? "bg-primary text-primary-foreground"
                : "border bg-card hover:bg-accent"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {list.length === 0 ? (
        <div
          data-testid="empty-leads"
          className="rounded-lg border border-dashed p-10 text-center"
        >
          <h2 className="font-medium">No leads yet</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            When someone messages your LINE OA, they&apos;ll show up here.
            Try sending a test event to <code>/webhook/line</code> to see one.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3" data-testid="leads-list">
          {list.map((lead) => (
            <li key={lead.id}>
              <Link
                href={`/leads/${lead.id}`}
                data-testid="lead-row"
                className="flex items-center justify-between rounded-lg border bg-card p-4 shadow-sm transition hover:shadow-md"
              >
                <div className="space-y-1">
                  <p className="font-medium">
                    {lead.name ?? `LINE user ${lead.line_user_id ?? lead.id.slice(0, 6)}`}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {lead.line_user_id ?? "—"} · last contact{" "}
                    {lead.last_contacted_at
                      ? new Date(lead.last_contacted_at).toLocaleString()
                      : "never"}
                  </p>
                </div>
                <span
                  data-status={lead.status ?? "new"}
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                    lead.status === "qualified" || lead.status === "negotiation"
                      ? "bg-emerald-500/10 text-emerald-700"
                      : lead.status === "lost"
                        ? "bg-muted text-muted-foreground"
                        : lead.status === "closed"
                          ? "bg-blue-500/10 text-blue-700"
                          : "bg-amber-500/10 text-amber-700"
                  }`}
                >
                  {LEAD_STATUS_LABELS_TH[(lead.status ?? "new") as keyof typeof LEAD_STATUS_LABELS_TH] ??
                    lead.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
