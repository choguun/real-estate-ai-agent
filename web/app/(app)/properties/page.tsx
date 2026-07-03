"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, getAuthToken } from "@/lib/api";
import { listProperties } from "@/lib/properties";
import type { Property } from "@/lib/types";
import { PropertyCard } from "@/components/properties/PropertyCard";

export default function PropertiesPage() {
  const router = useRouter();
  const [items, setItems] = useState<Property[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login");
      return;
    }
    listProperties()
      .then(setItems)
      .catch((err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          router.replace("/login");
          return;
        }
        setError(err.detail || err.message || "Failed to load properties");
      });
  }, [router]);

  if (items === null && error === null) {
    return (
      <main>
        <div data-testid="loading" className="text-sm text-muted-foreground">
          Loading properties…
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main>
        <div
          role="alert"
          data-testid="error"
          className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {error}
        </div>
      </main>
    );
  }

  const list = items ?? [];

  return (
    <main>
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Properties</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your listings, sorted by most-recently updated.
          </p>
        </div>
        <Link
          href="/properties/new"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90"
        >
          New property
        </Link>
      </header>

      {list.length === 0 ? (
        <div
          data-testid="empty"
          className="mt-10 rounded-lg border border-dashed p-10 text-center"
        >
          <h2 className="font-medium">No properties yet</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Create your first listing and the AI will draft copy for DDProperty,
            Livinginsider, Facebook, and a general version.
          </p>
          <Link
            href="/properties/new"
            className="mt-4 inline-block rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent"
          >
            Add a property
          </Link>
        </div>
      ) : (
        <ul
          data-testid="property-list"
          className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {list.map((property) => (
            <li key={property.id}>
              <PropertyCard property={property} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
