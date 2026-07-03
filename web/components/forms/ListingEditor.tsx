"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { updateListing } from "@/lib/listings";
import type { Platform, SavedListing } from "@/lib/types";
import { PLATFORM_LABELS } from "@/lib/types";

interface ListingEditorProps {
  initial: SavedListing;
  /** Called after a successful save so the parent can refresh the list. */
  onSaved?: (updated: SavedListing) => void;
}

interface Snapshot {
  title: string;
  description: string;
  hashtags: string;
  seoKeywords: string;
}

function snapshotFromListing(l: SavedListing): Snapshot {
  return {
    title: l.title,
    description: l.description ?? "",
    hashtags: (l.hashtags ?? []).join(" "),
    seoKeywords: (l.seo_keywords ?? []).join(", "),
  };
}

export function ListingEditor({ initial, onSaved }: ListingEditorProps) {
  const [title, setTitle] = useState(initial.title);
  const [description, setDescription] = useState(initial.description ?? "");
  const [hashtags, setHashtags] = useState((initial.hashtags ?? []).join(" "));
  const [seoKeywords, setSeoKeywords] = useState(
    (initial.seo_keywords ?? []).join(", "),
  );
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Last snapshot we compare "dirty" against. Updated on save so a
  // second edit round trips correctly. (Previously compared against
  // `initial` which never changed → button stuck disabled after save.)
  const [lastSaved, setLastSaved] = useState<Snapshot>(() => snapshotFromListing(initial));

  // If the parent's `initial` changes (e.g. parent re-fetches), reset.
  useEffect(() => {
    setTitle(initial.title);
    setDescription(initial.description ?? "");
    setHashtags((initial.hashtags ?? []).join(" "));
    setSeoKeywords((initial.seo_keywords ?? []).join(", "));
    setSavedAt(null);
    setLastSaved(snapshotFromListing(initial));
  }, [initial]);

  const current: Snapshot = { title, description, hashtags, seoKeywords };
  const dirty =
    current.title !== lastSaved.title ||
    current.description !== lastSaved.description ||
    current.hashtags !== lastSaved.hashtags ||
    current.seoKeywords !== lastSaved.seoKeywords;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateListing(initial.id, {
        title: title.trim(),
        description,
        hashtags: hashtags
          .split(/\s+/)
          .map((t) => t.trim())
          .filter(Boolean),
        seo_keywords: seoKeywords
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      const now = new Date().toLocaleTimeString();
      setSavedAt(now);
      // Bump snapshot so the Save button disables correctly until next edit.
      setLastSaved({
        title: title.trim(),
        description,
        hashtags,
        seoKeywords,
      });
      onSaved?.(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail || err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <article
      data-testid="listing-editor"
      data-platform={initial.platform}
      className="rounded-lg border bg-card p-5 shadow-sm"
    >
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-medium">{PLATFORM_LABELS[initial.platform]}</h2>
          <p className="text-xs text-muted-foreground">
            model: <code>{initial.ai_model ?? "—"}</code>
          </p>
        </div>
        {savedAt && (
          <span className="text-xs text-emerald-600" data-testid="saved-at">
            Saved at {savedAt}
          </span>
        )}
      </header>

      <div className="space-y-3">
        <div className="space-y-1">
          <label htmlFor={`title-${initial.platform}`} className="text-xs uppercase tracking-wide text-muted-foreground">
            Title
          </label>
          <input
            id={`title-${initial.platform}`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor={`desc-${initial.platform}`} className="text-xs uppercase tracking-wide text-muted-foreground">
            Description
          </label>
          <textarea
            id={`desc-${initial.platform}`}
            rows={6}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring font-sans"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor={`tags-${initial.platform}`} className="text-xs uppercase tracking-wide text-muted-foreground">
              Hashtags (space-separated)
            </label>
            <input
              id={`tags-${initial.platform}`}
              value={hashtags}
              onChange={(e) => setHashtags(e.target.value)}
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor={`seo-${initial.platform}`} className="text-xs uppercase tracking-wide text-muted-foreground">
              SEO keywords (comma-separated)
            </label>
            <input
              id={`seo-${initial.platform}`}
              value={seoKeywords}
              onChange={(e) => setSeoKeywords(e.target.value)}
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          {error}
        </p>
      )}

      <footer className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving || !dirty}
          data-testid="save-listing"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90 disabled:opacity-50"
        >
          {saving ? "Saving…" : savedAt ? "Re-save" : "Save"}
        </button>
      </footer>
    </article>
  );
}
