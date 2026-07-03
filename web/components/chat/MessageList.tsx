import type { Message } from "@/lib/types";

interface MessageListProps {
  messages: Message[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div
        data-testid="empty-chat"
        className="rounded-lg border border-dashed p-10 text-center"
      >
        <p className="text-sm text-muted-foreground">
          No messages yet — try sending a reply below.
        </p>
      </div>
    );
  }

  return (
    <ul data-testid="message-list" className="space-y-3">
      {messages.map((m) => {
        const direction = m.direction ?? "inbound";
        const isInbound = direction === "inbound";
        return (
          <li
            key={m.id}
            data-testid="message"
            data-direction={direction}
            className={`flex ${isInbound ? "justify-start" : "justify-end"}`}
          >
            <article
              className={`max-w-[80%] rounded-lg px-4 py-2 text-sm shadow-sm ${
                isInbound
                  ? "bg-card border"
                  : "bg-emerald-500 text-white"
              }`}
            >
              <p className="whitespace-pre-wrap break-words">{m.content ?? "(empty)"}</p>
              <p
                className={`mt-1 text-xs ${
                  isInbound ? "text-muted-foreground" : "text-emerald-100"
                }`}
              >
                {direction === "outbound" ? "agent" : "lead"}
                {m.created_at ? ` · ${formatTime(m.created_at)}` : ""}
              </p>
            </article>
          </li>
        );
      })}
    </ul>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}
