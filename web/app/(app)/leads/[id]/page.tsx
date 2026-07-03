"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError, getAuthToken } from "@/lib/api";
import { getLead } from "@/lib/leads";
import type { LeadWithMessages, Message } from "@/lib/types";
import { LEAD_STATUS_LABELS_TH } from "@/lib/types";
import { MessageList } from "@/components/chat/MessageList";
import { ComposeBox } from "@/components/chat/ComposeBox";

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const leadId = params?.id ?? "";

  const [lead, setLead] = useState<LeadWithMessages | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    if (!leadId) return;
    getLead(leadId)
      .then(setLead)
      .catch((err) => {
        if (err instanceof ApiError) {
          if (err.status === 401 || err.status === 403) {
            router.replace("/login");
            return;
          }
          if (err.status === 404) {
            setError("Lead not found");
            return;
          }
        }
        setError(err.detail || err.message || "Failed to load lead");
      });
  }, [leadId, router]);

  function handleSent(m: Message) {
    setLead((prev) => (prev ? { ...prev, messages: [...prev.messages, m] } : prev));
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
        <Link href="/leads" className="mt-4 inline-block text-sm text-muted-foreground hover:text-foreground">
          ← All leads
        </Link>
      </main>
    );
  }

  if (!lead) {
    return (
      <main>
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  const statusLabel =
    LEAD_STATUS_LABELS_TH[(lead.status ?? "new") as keyof typeof LEAD_STATUS_LABELS_TH] ??
    lead.status;

  return (
    <main className="space-y-6">
      <Link href="/leads" className="text-sm text-muted-foreground hover:text-foreground">
        ← All leads
      </Link>

      <header className="rounded-lg border bg-card p-5" data-testid="lead-header">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">
              {lead.name ?? `LINE user ${lead.line_user_id ?? lead.id.slice(0, 6)}`}
            </h1>
            <p className="text-sm text-muted-foreground">
              {lead.line_user_id ?? "—"}
              {lead.phone ? ` · ${lead.phone}` : ""}
            </p>
          </div>
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium">
            {statusLabel}
          </span>
        </div>

        {(lead.budget_min || lead.budget_max || lead.interest_type || lead.notes) && (
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            {lead.interest_type && (
              <div>
                <dt className="text-muted-foreground">Interest</dt>
                <dd className="font-medium">{lead.interest_type}</dd>
              </div>
            )}
            {(lead.budget_min || lead.budget_max) && (
              <div>
                <dt className="text-muted-foreground">Budget</dt>
                <dd className="font-medium">
                  {lead.budget_min ? `฿${lead.budget_min.toLocaleString()}` : ""}
                  {lead.budget_min && lead.budget_max ? " – " : ""}
                  {lead.budget_max ? `฿${lead.budget_max.toLocaleString()}` : ""}
                </dd>
              </div>
            )}
            {lead.notes && (
              <div className="col-span-2 sm:col-span-2">
                <dt className="text-muted-foreground">Notes</dt>
                <dd className="font-medium">{lead.notes}</dd>
              </div>
            )}
          </dl>
        )}
      </header>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">
          Conversation ({lead.messages.length})
        </h2>
        <MessageList messages={lead.messages} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight">Reply</h2>
        <ComposeBox leadId={lead.id} onSent={handleSent} />
      </section>
    </main>
  );
}
