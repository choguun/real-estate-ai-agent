/** Dashboard API wrapper. */

import { apiGet } from "./api";
import type { DashboardData } from "./types";

export async function getDashboard(): Promise<DashboardData> {
  return apiGet<DashboardData>("/api/dashboard");
}
