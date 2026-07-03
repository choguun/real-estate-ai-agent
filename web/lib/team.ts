/**
 * Typed team API client (cycle 3).
 */

import { apiGet, apiPost, apiPatch, apiDelete } from "./api";

export type TeamRole = "owner" | "admin" | "agent";

export interface Team {
  id: string;
  name: string;
  plan: string;
  owner_id: string;
  created_at: string;
  updated_at?: string;
  deleted_at?: string;
}

export interface TeamMember {
  id: string;
  team_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: TeamRole;
  joined_at: string;
  left_at?: string;
}

export interface Invitation {
  id: string;
  team_id: string;
  email: string;
  role: "admin" | "agent";
  token: string;
  invited_by: string;
  invited_at: string;
  expires_at: string;
  accepted_at?: string;
  accepted_by?: string;
  invite_url?: string;
}

export const teamApi = {
  me: () => apiGet<Team | null>("/api/teams/me"),
  create: (body: { name: string }) => apiPost<Team>("/api/teams", body),
  get: (teamId: string) => apiGet<Team>(`/api/teams/${teamId}`),
  members: (teamId: string) => apiGet<TeamMember[]>(`/api/teams/${teamId}/members`),
  invite: (teamId: string, body: { email: string; role: "admin" | "agent" }) =>
    apiPost<Invitation>(`/api/teams/${teamId}/invitations`, body),
  changeRole: (teamId: string, userId: string, role: TeamRole) =>
    apiPatch<TeamMember>(`/api/teams/${teamId}/members/${userId}`, { role }),
  remove: (teamId: string, userId: string) =>
    apiDelete<void>(`/api/teams/${teamId}/members/${userId}`),
  leave: (teamId: string) => apiPostNoBody<void>(`/api/teams/${teamId}/leave`),
};

// Re-import so the team page can also use apiPostNoBody via team module
import { apiPostNoBody } from "./api";
export { apiPostNoBody };
