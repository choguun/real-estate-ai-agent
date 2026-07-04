/**
 * Typed billing API client (cycle 4).
 */

import { apiGet, apiPost, apiPostNoBody, apiDelete } from "./api";

export type PlanTier = "starter" | "growth" | "team";
export type BillingStatus =
  | "trialing"
  | "active"
  | "past_due"
  | "canceled"
  | "incomplete";

export interface BillingStatusOut {
  plan: PlanTier;
  status: BillingStatus;
  seats_used: number;
  seats_limit: number;
  properties_used: number;
  properties_limit: number;
  ai_listings_used_month: number;
  ai_listings_limit_month: number;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  trial_ends_at?: string | null;
  is_paid: boolean;
  is_within_plan_limits: boolean;
}

export interface CheckoutResponse {
  url: string;
  session_id: string;
}

export const PLAN_PRICING: Record<
  Exclude<PlanTier, "starter">,
  { name: string; price: number; seats: number; properties: number; ai: number }
> = {
  growth: { name: "Growth", price: 29, seats: 3, properties: 25, ai: 200 },
  team: { name: "Team", price: 99, seats: 10, properties: 100, ai: 1000 },
};

export const billingApi = {
  status: () => apiGet<BillingStatusOut>("/api/billing/status"),
  checkout: (plan: PlanTier) =>
    apiPost<CheckoutResponse>("/api/billing/checkout", { plan }),
  portal: () => apiPost<CheckoutResponse>("/api/billing/portal", {}),
  cancel: (subscriptionId: string) =>
    apiDelete<void>(`/api/billing/subscriptions/${subscriptionId}`),
  keepAlive: () => apiPostNoBody<void>("/api/billing/heartbeat"),
};
