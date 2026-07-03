import Link from "next/link";

import type { DashboardInboundMessage } from "@/lib/types";

interface RecentMessagesProps {
  messages: DashboardInboundMessage[];
}

export function RecentMessages({ messages }: RecentMessagesProps) {
  if (messages.length === 0) {
    return (
      <div
        data-testid="recent-messages-empty"
        className="rounded-lg border border-dashed p-8 text-center"
      >
        <p className="text-sm text-muted-foreground">
          ยังไม่มีข้อความเข้า — no inbound messages yet
        </p>
      </div>
    );
  }

  return (
    <ul data-testid="recent-messages" className="space-y-2">
      {messages.map((m) => (
        <li
          key={m.id}
          data-testid="recent-message"
          className="rounded-md border bg-card p-3"
        >
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm whitespace-pre-wrap break-words">
              {truncate(m.content ?? "(empty)", 80)}
            </p>
            <span className="shrink-0 text-xs text-muted-foreground">
              {timeAgo(m.created_at)}
            </span>
          </div>
          {m.lead?.id && (
            <Link
              href={`/leads/${m.lead.id}`}
              className="mt-1 inline-block text-xs text-emerald-600 hover:underline"
            >
              {m.lead.name ?? m.lead.line_user_id ?? "lead"} →
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, Math.floor((now - then) / 1000));
    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
  } catch {
    return "";
  }
}
