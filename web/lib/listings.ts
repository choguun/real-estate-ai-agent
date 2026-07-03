/** Listing-generation API wrapper. */

import { apiPost } from "./api";
import type {
  GeneratedContent,
  Platform,
  PropertySummaryForAi,
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
