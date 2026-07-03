import type { Property } from "@/lib/types";
import { formatTHB, propertyTypeLabel } from "@/lib/types";

interface PropertyCardProps {
  property: Property;
}

export function PropertyCard({ property }: PropertyCardProps) {
  return (
    <article
      data-testid="property-card"
      data-property-id={property.id}
      className="rounded-lg border bg-card p-5 shadow-sm transition hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-1">
          <h2 className="text-base font-medium leading-tight">
            {property.title ?? "Untitled listing"}
          </h2>
          <p className="text-sm text-muted-foreground">
            {property.district ?? "—"}
            {property.province ? `, ${property.province}` : ""}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
            property.status === "active"
              ? "bg-emerald-500/10 text-emerald-700"
              : property.status === "archived"
                ? "bg-muted text-muted-foreground"
                : "bg-amber-500/10 text-amber-700"
          }`}
        >
          {property.status ?? "draft"}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Type</dt>
          <dd className="font-medium">{propertyTypeLabel(property.property_type)}</dd>
        </div>
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
      </dl>

      {(property.bedrooms || property.bathrooms || property.near_bts_mrt) && (
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
          {property.bedrooms != null && <span>🛏️ {property.bedrooms} ห้องนอน</span>}
          {property.bathrooms != null && <span>🚿 {property.bathrooms} ห้องน้ำ</span>}
          {property.near_bts_mrt && <span>🚆 {property.near_bts_mrt}</span>}
        </div>
      )}
    </article>
  );
}
