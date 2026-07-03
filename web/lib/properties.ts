/** Property API wrappers — uses the typed `lib/api.ts` client. */

import {
  apiGet,
  apiPatch,
  apiPost,
  apiPostNoBody,
} from "./api";
import type {
  Property,
  PropertyCreateInput,
  PropertyUpdateInput,
} from "./types";

export interface ListPropertiesOptions {
  status?: string;
  includeArchived?: boolean;
}

export async function listProperties(opts: ListPropertiesOptions = {}): Promise<Property[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  if (opts.includeArchived) params.set("include_archived", "true");
  const qs = params.toString();
  return apiGet<Property[]>(`/api/properties${qs ? `?${qs}` : ""}`);
}

export async function getProperty(id: string): Promise<Property> {
  return apiGet<Property>(`/api/properties/${encodeURIComponent(id)}`);
}

export async function createProperty(input: PropertyCreateInput): Promise<Property> {
  return apiPost<Property>("/api/properties", input);
}

export async function updateProperty(
  id: string,
  patch: PropertyUpdateInput,
): Promise<Property> {
  return apiPatch<Property>(`/api/properties/${encodeURIComponent(id)}`, patch);
}

export async function archiveProperty(id: string): Promise<Property> {
  return apiPostNoBody<Property>(`/api/properties/${encodeURIComponent(id)}/archive`);
}
