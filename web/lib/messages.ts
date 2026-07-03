/** Messages API wrappers (outbound only — inbound is via LINE webhook). */

import { apiPost } from "./api";
import type { Message } from "./types";

export async function sendReply(
  leadId: string,
  text: string,
): Promise<{ message: Message; line_reply: { id: string; line_user_id: string; sent_at: string } }> {
  return apiPost(`/api/leads/${encodeURIComponent(leadId)}/messages`, { text });
}
