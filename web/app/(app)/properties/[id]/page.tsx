"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { ApiError, getAuthToken } from "@/lib/api";
import {
  generateListing,
  listListingsForProperty,
  saveListing,
} from "@/lib/listings";
import { getProperty } from "@/lib/properties";
import type {
  GeneratedContent,
  Property,
  SavedListing,
} from "@/lib/types";
import { formatTHB, propertyTypeLabel } from "@/lib/types";
import { ListingEditor } from "@/components/forms/ListingEditor";

export default function PropertyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id ?? "";
  const [property, setProperty] = useState<Property | null>(null);
  const [listings, setListings] = useState<SavedListing[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    Promise.all([getProperty(id), listListingsForProperty(id)])
      .then(([p, l]) => {
        setProperty(p);
        setListings(l);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setError("Property not found");
          return;
        }
        setError(err.detail || err.message || "Failed to load property");
      });
  }, [id, router]);

  async function refreshListings() {
    setListings(await listListingsForProperty(id));
  }

  async function handleGenerateFromDetail() {
    if (!property) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const summary = {
        title: property.title,
        property_type: property.property_type,
        price: property.price,
        size_sqm: property.size_sqm,
        bedrooms: property.bedrooms,
        bathrooms: property.bathrooms,
        floor: property.floor,
        address: property.address,
        district: property.district,
        province: property.province,
        near_bts_mrt: property.near_bts_mrt,
        foreign_quota: property.foreign_quota,
      };
      // Save each generated variant
      const generated: GeneratedContent[] = await generateListing(summary);
      for (const g of generated) {
        await saveListing({
          property_id: property.id,
          platform: g.platform,
          title: g.title,
          description: g.description,
          hashtags: g.hashtags,
          seo_keywords: g.seo_keywords,
          ai_model: g.ai_model,
          prompt_used: g.prompt_used ?? null,
        });
      }
      await refreshListings();
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.detail || err.message : "Generation failed",
      );
    } finally {
      setGenerating(false);
    }
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
        <Link href="/properties" className="mt-4 inline-block text-sm text-muted-foreground hover:text-foreground">
          ← All properties
        </Link>
      </main>
    );
  }

  if (!property || listings === null) {
    return (
      <main>
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  return (
    <main className="space-y-8">
      <Link href="/properties" className="text-sm text-muted-foreground hover:text-foreground">
        ← All properties
      </Link>

      {/* ── Property header ── */}
      <header className="rounded-lg border bg-card p-6" data-testid="property-header">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">
              {property.title ?? "Untitled"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {propertyTypeLabel(property.property_type)} ·{" "}
              {property.district ?? "—"}{property.province ? `, ${property.province}` : ""}
            </p>
          </div>
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium">
            {property.status ?? "draft"}
          </span>
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Price</dt>
            <dd className="font-medium">{formatTHB(property.price)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Size</dt>
            <dd className="font-medium">
              {property.size_sqm != null ? `${property.size_sqm} ตร.ม.` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Bed / Bath</dt>
            <dd className="font-medium">
              {property.bedrooms ?? "?"} / {property.bathrooms ?? "?"}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Floor</dt>
            <dd className="font-medium">{property.floor ?? "—"}</dd>
          </div>
        </dl>

        {property.images && property.images.length > 0 && (
          <div className="mt-4 flex gap-2 overflow-x-auto" data-testid="property-images">
            {property.images.map((url, i) => (
              <div key={i} className="h-24 w-24 shrink-0 overflow-hidden rounded-md border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={url} alt={`Photo ${i + 1}`} className="h-full w-full object-cover" />
              </div>
            ))}
          </div>
        )}
      </header>

      {/* ── Listings section ── */}
      <section>
        <header className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Generated listings</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              One variant per platform. Edit and save in place.
            </p>
          </div>
          <button
            type="button"
            onClick={handleGenerateFromDetail}
            disabled={generating}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90 disabled:opacity-50"
          >
            {generating
              ? "Generating…"
              : listings.length > 0
                ? "🔄 Regenerate"
                : "✨ Generate"}
          </button>
        </header>

        {generateError && (
          <p
            role="alert"
            className="mb-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          >
            {generateError}
          </p>
        )}

        {listings.length === 0 ? (
          <div
            data-testid="no-listings"
            className="rounded-lg border border-dashed p-10 text-center"
          >
            <p className="font-medium">No listings yet</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Click &quot;✨ Generate&quot; above to draft copy for all 4 platforms.
            </p>
          </div>
        ) : (
          <ul className="grid gap-4 lg:grid-cols-2" data-testid="listing-list">
            {listings.map((l) => (
              <li key={l.id}>
                <ListingEditor initial={l} onSaved={refreshListings} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
