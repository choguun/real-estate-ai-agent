"use client";

import { useState, type FormEvent } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (email: string, role: "admin" | "agent") => Promise<void>;
}

export function InviteMemberModal({ open, onClose, onSubmit }: Props) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "agent">("agent");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function onSubmitForm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!email.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(email.trim(), role);
      setEmail("");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invite failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <form
        onSubmit={onSubmitForm}
        className="flex w-full max-w-md flex-col gap-4 rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 className="text-lg font-semibold">Invite a teammate</h2>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border px-3 py-2"
            placeholder="alice@example.com"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Role</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as "admin" | "agent")}
            className="rounded border px-3 py-2"
          >
            <option value="agent">Agent</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border px-4 py-2 text-sm hover:bg-muted"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !email.trim()}
            className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send invite"}
          </button>
        </div>
      </form>
    </div>
  );
}
