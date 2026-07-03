/** Domain types — mirror backend DTOs. Keep these in sync with `app/domain/*.py`. */

export type PropertyType = "condo" | "house" | "townhouse" | "land" | "commercial";

export type PropertyStatus =
  | "draft"
  | "active"
  | "sold"
  | "rented"
  | "archived";

export const PROPERTY_TYPE_LABELS_EN: Record<PropertyType, string> = {
  condo: "Condo",
  house: "House",
  townhouse: "Townhouse",
  land: "Land",
  commercial: "Commercial",
};

export const PROPERTY_TYPE_LABELS_TH: Record<PropertyType, string> = {
  condo: "คอนโด",
  house: "บ้านเดี่ยว",
  townhouse: "ทาวน์เฮาส์",
  land: "ที่ดิน",
  commercial: "อาคารพาณิชย์",
};

export interface Property {
  id: string;
  user_id: string;
  title: string | null;
  description: string | null;
  property_type: PropertyType | string | null;
  price: number | null;
  size_sqm: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  floor: number | null;
  address: string | null;
  district: string | null;
  province: string | null;
  near_bts_mrt: string | null;
  foreign_quota: boolean | null;
  status: PropertyStatus | string | null;
  images: string[] | null;
  created_at: string | null;
  updated_at: string | null;
}

/** Subset of Property fields the AI generator accepts in its request. */
export interface PropertySummaryForAi {
  title?: string | null;
  property_type?: PropertyType | null;
  price?: number | null;
  size_sqm?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  floor?: number | null;
  address?: string | null;
  district?: string | null;
  province?: string | null;
  near_bts_mrt?: string | null;
  foreign_quota?: boolean | null;
}

export type Platform = "ddproperty" | "livinginsider" | "facebook" | "general";

export const PLATFORM_LABELS: Record<Platform, string> = {
  ddproperty: "DDProperty",
  livinginsider: "Livinginsider",
  facebook: "Facebook",
  general: "General",
};

export interface GeneratedContent {
  platform: Platform;
  title: string;
  description: string;
  hashtags: string[];
  seo_keywords: string[];
  ai_model: string;
  prompt_used?: string | null;
}

export interface PropertyCreateInput {
  title?: string | null;
  description?: string | null;
  property_type?: PropertyType | null;
  price?: number | null;
  size_sqm?: number | null;
  bedrooms?: number | null;
  bathrooms?: number | null;
  floor?: number | null;
  address?: string | null;
  district?: string | null;
  province?: string | null;
  near_bts_mrt?: string | null;
  foreign_quota?: boolean | null;
  images?: string[] | null;
}

export interface PropertyUpdateInput extends PropertyCreateInput {
  status?: PropertyStatus | null;
}

/** Format a THB amount as `฿1,234,567`. */
export function formatTHB(value: number | null | undefined): string {
  if (value == null) return "—";
  return `฿${new Intl.NumberFormat("en-US").format(value)}`;
}

/** Translate a property type to Thai. Falls back to English, then raw. */
export function propertyTypeLabel(value: PropertyType | string | null | undefined, locale: "en" | "th" = "th"): string {
  if (!value) return "—";
  const map = locale === "th" ? PROPERTY_TYPE_LABELS_TH : PROPERTY_TYPE_LABELS_EN;
  return map[value as PropertyType] ?? String(value);
}
