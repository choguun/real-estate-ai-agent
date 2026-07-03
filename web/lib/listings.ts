/** Listing-generation + persistence API wrappers. */

import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
} from "./api";
import type {
  GeneratedContent,
  Platform,
  PropertySummaryForAi,
  SaveListingInput,
  SavedListing,
  UpdateListingInput,
} from "./types";

export interface GenerateListingRequest {
  property: PropertySummaryForAi;
  platforms?: Platform[];
  image_urls?: string[];
}

export async function generateListing(
  property: PropertySummaryForAi,
  platforms?: Platform[],
): Promise<GeneratedContent[]> {
  const body: GenerateListingRequest = { property, platforms, image_urls: undefined };
  return apiPost<GeneratedContent[]>("/api/generate-listing", body);
}

export async function listListingsForProperty(propertyId: string): Promise<SavedListing[]> {
  return apiGet<SavedListing[]>(
    `/api/listings?property_id=${encodeURIComponent(propertyId)}`,
  );
}

export async function saveListing(input: SaveListingInput): Promise<SavedListing> {
  return apiPost<SavedListing>("/api/listings", input);
}

export async function updateListing(
  id: string,
  patch: UpdateListingInput,
): Promise<SavedListing> {
  return apiPatch<SavedListing>(`/api/listings/${encodeURIComponent(id)}`, patch);
}

export async function deleteListing(id: string): Promise<void> {
  await apiDelete<void>(`/api/listings/${encodeURIComponent(id)}`);
}
