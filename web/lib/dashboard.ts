/** Dashboard API wrapper. */

import { apiGet } from "./api";
import type { DashboardData } from "./types";

export async function getDashboard(options?: { signal?: AbortSignal }): Promise<DashboardData> {
  return apiGet<DashboardData>("/api/dashboard", { signal: options?.signal });
}
