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

/** Thai-locale UI labels for the agent's lead workflow. */
export type LeadStatus =
  | "new"
  | "contacted"
  | "qualified"
  | "viewing"
  | "negotiation"
  | "closed"
  | "lost";

export const LEAD_STATUS_LABELS_TH: Record<LeadStatus, string> = {
  new: "ใหม่",
  contacted: "ติดต่อแล้ว",
  qualified: "มีศักยภาพ",
  viewing: "นัดชม",
  negotiation: "เจรจา",
  closed: "ปิดดีล",
  lost: "หลุด",
};

export interface Lead {
  id: string;
  user_id: string;
  team_id: string | null;
  name: string | null;
  phone: string | null;
  email: string | null;
  line_user_id: string | null;
  source: string | null;
  status: LeadStatus | string | null;
  interest_type: string | null;
  budget_min: number | null;
  budget_max: number | null;
  preferred_areas: string[] | null;
  notes: string | null;
  last_contacted_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Message {
  id: string;
  lead_id: string | null;
  user_id: string;
  direction: "inbound" | "outbound" | string | null;
  message_type: string | null;
  content: string | null;
  is_ai_generated: boolean | null;
  created_at: string | null;
}

export interface LeadWithMessages extends Lead {
  messages: Message[];
}

export interface Property {
  id: string;
  user_id: string;
  team_id: string | null;
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
  property_type?: string | null;
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

/** Aggregated dashboard payload returned by /api/dashboard. */
export interface DashboardLeadPreview {
  id: string;
  name: string | null;
  line_user_id: string | null;
}

export interface DashboardInboundMessage extends Message {
  lead: DashboardLeadPreview | null;
}

export interface DashboardData {
  new_leads_count: number;
  recent_inbound: DashboardInboundMessage[];
  recent_properties: Property[];
}

/** Persisted version of a generated listing (one row per (property, platform)). */
export interface SavedListing extends GeneratedContent {
  id: string;
  property_id: string;
  user_id: string;
  is_published: boolean;
  raw_response: unknown | null;
  created_at: string | null;
}

/** Payload for POST /api/listings — used by PropertyForm auto-save. */
export interface SaveListingInput {
  property_id: string;
  platform: Platform;
  title: string;
  description: string;
  hashtags?: string[];
  seo_keywords?: string[];
  ai_model?: string | null;
  prompt_used?: string | null;
}

/** Payload for PATCH /api/listings/{id}. */
export interface UpdateListingInput {
  title?: string;
  description?: string;
  hashtags?: string[];
  seo_keywords?: string[];
  is_published?: boolean;
}


export interface PropertyCreateInput {
  title?: string | null;
  description?: string | null;
  property_type?: string | null;
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
