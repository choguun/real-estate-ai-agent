/** Leads API wrappers. */

import { apiGet, apiPatch } from "./api";
import type { Lead, LeadWithMessages, LeadStatus } from "./types";

export interface ListLeadsOptions {
  status?: LeadStatus | string;
}

export async function listLeads(opts: ListLeadsOptions = {}): Promise<Lead[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  const qs = params.toString();
  return apiGet<Lead[]>(`/api/leads${qs ? `?${qs}` : ""}`);
}

export async function getLead(id: string): Promise<LeadWithMessages> {
  return apiGet<LeadWithMessages>(`/api/leads/${encodeURIComponent(id)}`);
}

export async function updateLead(id: string, patch: Partial<Lead>): Promise<Lead> {
  return apiPatch<Lead>(`/api/leads/${encodeURIComponent(id)}`, patch);
}
