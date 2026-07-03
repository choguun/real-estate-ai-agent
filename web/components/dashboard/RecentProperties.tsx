import Link from "next/link";

import { PropertyCard } from "@/components/properties/PropertyCard";
import type { Property } from "@/lib/types";

interface RecentPropertiesProps {
  properties: Property[];
}

export function RecentProperties({ properties }: RecentPropertiesProps) {
  if (properties.length === 0) {
    return (
      <div
        data-testid="recent-properties-empty"
        className="rounded-lg border border-dashed p-8 text-center"
      >
        <p className="text-sm text-muted-foreground">
          ยังไม่มีประกาศ — no properties yet.{" "}
          <Link href="/properties/new" className="text-emerald-600 hover:underline">
            เพิ่มประกาศแรก
          </Link>
        </p>
      </div>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {properties.map((p) => (
        <li key={p.id}>
          <PropertyCard property={p} />
        </li>
      ))}
    </ul>
  );
}
