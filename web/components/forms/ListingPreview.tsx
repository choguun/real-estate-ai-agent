"use client";

import { useState } from "react";

import type { GeneratedContent, Platform } from "@/lib/types";
import { PLATFORM_LABELS } from "@/lib/types";

interface ListingPreviewProps {
  contents: GeneratedContent[];
  /** Optional pre-selected platform. Defaults to first in list. */
  initialPlatform?: Platform;
}

export function ListingPreview({ contents, initialPlatform }: ListingPreviewProps) {
  const [active, setActive] = useState<Platform>(
    initialPlatform ?? contents[0]?.platform ?? "general",
  );
  const [copied, setCopied] = useState(false);

  if (contents.length === 0) return null;

  const current = contents.find((c) => c.platform === active) ?? contents[0]!;
  const fullText = `${current.title}\n\n${current.description}${
    current.hashtags.length > 0 ? "\n\n" + current.hashtags.join(" ") : ""
  }`;

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <section
      className="rounded-lg border bg-card p-5"
      data-testid="listing-preview"
      data-platform={current.platform}
    >
      <header className="mb-4 flex items-center justify-between">
        <h2 className="font-medium">AI-generated listings</h2>
        <span className="text-xs text-muted-foreground">
          model: <code>{current.ai_model}</code>
        </span>
      </header>

      <div role="tablist" className="mb-3 flex gap-2 border-b">
        {contents.map((c) => (
          <button
            key={c.platform}
            type="button"
            role="tab"
            aria-selected={c.platform === active}
            data-testid={`tab-${c.platform}`}
            onClick={() => setActive(c.platform)}
            className={`border-b-2 px-3 py-1.5 text-sm transition ${
              c.platform === active
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {PLATFORM_LABELS[c.platform]}
          </button>
        ))}
      </div>

      <article
        key={current.platform}
        data-testid="listing-content"
        className="space-y-3"
      >
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Title</p>
          <p className="text-base font-medium leading-tight">{current.title}</p>
        </div>

        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Description</p>
          <pre className="whitespace-pre-wrap rounded-md bg-muted/30 p-3 text-sm font-sans">
{current.description}
          </pre>
        </div>

        {current.hashtags.length > 0 && (
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Hashtags</p>
            <p className="text-sm">{current.hashtags.join(" ")}</p>
          </div>
        )}

        {current.seo_keywords.length > 0 && (
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">SEO</p>
            <p className="text-sm">{current.seo_keywords.join(", ")}</p>
          </div>
        )}
      </article>

      <footer className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-accent"
        >
          {copied ? "Copied!" : "Copy to clipboard"}
        </button>
      </footer>
    </section>
  );
}
