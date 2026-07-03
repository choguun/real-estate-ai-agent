"use client";

import { useState, type FormEvent } from "react";

import { ApiError } from "@/lib/api";
import { sendReply } from "@/lib/messages";
import type { Message } from "@/lib/types";

interface ComposeBoxProps {
  leadId: string;
  onSent: (m: Message) => void;
}

export function ComposeBox({ leadId, onSent }: ComposeBoxProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    setError(null);
    setSending(true);
    try {
      const { message } = await sendReply(leadId, trimmed);
      setText("");
      onSent(message);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail || err.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="compose"
      className="space-y-2"
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="พิมพ์ข้อความตอบกลับ... (e.g. สวัสดีครับ สนใจคอนโดไหม?)"
        rows={3}
        data-testid="reply-text"
        className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring font-sans"
      />
      {error && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-sm text-destructive"
        >
          {error}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={sending || text.trim().length === 0}
          data-testid="send-reply"
          className="rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-white shadow hover:opacity-90 disabled:opacity-50"
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </form>
  );
}
