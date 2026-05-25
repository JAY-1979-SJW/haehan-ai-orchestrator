import { API_BASE } from "./api";

export interface MailComposeRequest {
  to: string;
  cc?: string;
  subject?: string;
  body?: string;
  dry_run?: boolean;
}

export interface MailComposeResponse {
  ok: boolean;
  dry_run: boolean;
  to: string;
  cc?: string | null;
  subject: string;
  body_preview: string;
  detail: string;
  requires_send_approval: boolean;
}

export async function postNaverMailCompose(
  req: MailComposeRequest,
): Promise<MailComposeResponse> {
  const res = await fetch(`${API_BASE}/api/v1/naver-mail/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
