/**
 * 네이버 메일함 API 호출 — 공용 프록시(/api/proxy)로 /api/v1/naver-mailbox/* 를 부른다.
 * 기준서: docs/specs/2026-10-01_naver_mailbox_tab.md
 */
const BASE = "/api/proxy/api/v1/naver-mailbox";

export interface Address {
  name: string;
  address: string;
}

export interface Account {
  account: string;
  ready: boolean;
}

export interface Folder {
  id: string;
  name: string;
  path: string;
  kind: string; // inbox | sent | drafts | junk | trash | user
  depth: number;
  total: number;
  unseen: number;
  selectable: boolean;
}

export interface MessageRow {
  uid: number;
  from: Address;
  to: Address[];
  subject: string;
  date: string;
  date_iso: string;
  size: number;
  seen: boolean;
  flagged: boolean;
  has_attachment: boolean;
}

export interface MessageList {
  page: number;
  per_page: number;
  total: number;
  truncated: boolean;
  messages: MessageRow[];
}

export interface AttachmentInfo {
  index: number;
  filename: string;
  size: number;
  content_type: string;
  previewable: boolean;
}

export interface MessageDetail {
  uid: number;
  folder: string;
  subject: string;
  from: Address;
  to: Address[];
  cc: Address[];
  date: string;
  date_iso: string;
  message_id: string;
  references: string;
  seen: boolean;
  text: string;
  html: string;
  /** 답장/전달 편집기에 넣는 인용문 — 서버가 정제한 HTML 만 들어온다 */
  quote_html: string;
  attachments: AttachmentInfo[];
}

export interface SendSummary {
  from: string;
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body_preview: string;
  rich: boolean;
  inline_images: number;
  attachments: { filename: string; size: number }[];
}

export interface PreparedSend {
  token: string;
  expires_in: number;
  summary: SendSummary;
}

export interface ForwardRef {
  folder: string;
  uid: number;
  indices: number[];
}

async function failure(res: Response): Promise<Error> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") detail = body.detail;
  } catch {
    /* 본문이 JSON 이 아니면 상태 코드만 보여 준다 */
  }
  return new Error(detail);
}

async function getJson<T>(path: string, params: Record<string, string | number | undefined>): Promise<T> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") qs.set(k, String(v));
  });
  const res = await fetch(`${BASE}/${path}?${qs.toString()}`, { cache: "no-store" });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as T;
}

export const mailboxApi = {
  accounts: () => getJson<{ accounts: Account[] }>("accounts", {}).then((r) => r.accounts),
  folders: (account: string) => getJson<{ folders: Folder[] }>("folders", { account }).then((r) => r.folders),
  messages: (account: string, folder: string, page: number, filter: string, q: string) =>
    getJson<MessageList>("messages", { account, folder, page, filter, q }),
  message: (account: string, folder: string, uid: number) =>
    getJson<MessageDetail>("message", { account, folder, uid }),
  setSeen: (account: string, folder: string, uids: number[], seen: boolean) =>
    postJson<{ ok: boolean }>("flags", { account, folder, uids, seen }),
  trash: (account: string, folder: string, uids: number[]) =>
    postJson<{ ok: boolean; count: number }>("trash", { account, folder, uids }),
  move: (account: string, folder: string, uids: number[], dest: string) =>
    postJson<{ ok: boolean; count: number }>("move", { account, folder, uids, dest }),
  /** 영구 삭제 — 휴지통·스팸에서만(서버도 강제). 호출 전에 화면에서 확인을 받는다. */
  purge: (account: string, folder: string, uids: number[]) =>
    postJson<{ ok: boolean; count: number }>("purge", { account, folder, uids }),
  emptyFolder: (account: string, folder: string) => postJson<{ ok: boolean; count: number }>("empty", { account, folder }),

  /** 첨부를 받아 Blob 으로 돌려준다(프록시가 Content-Disposition 을 전달하지 않아 파일명은 호출부가 정한다). */
  attachment: async (account: string, folder: string, uid: number, index: number, inline: boolean): Promise<Blob> => {
    const qs = new URLSearchParams({ account, folder, uid: String(uid), index: String(index), inline: inline ? "1" : "0" });
    const res = await fetch(`${BASE}/attachment?${qs.toString()}`, { cache: "no-store" });
    if (!res.ok) throw await failure(res);
    return res.blob();
  },

  prepareSend: async (form: {
    account: string;
    to: string;
    cc: string;
    bcc: string;
    subject: string;
    body: string;
    html: string;
    inReplyTo: string;
    references: string;
    forward: ForwardRef | null;
    files: File[];
  }): Promise<PreparedSend> => {
    const fd = new FormData();
    fd.set("account", form.account);
    fd.set("to", form.to);
    fd.set("cc", form.cc);
    fd.set("bcc", form.bcc);
    fd.set("subject", form.subject);
    fd.set("body", form.body);
    fd.set("html", form.html);
    fd.set("in_reply_to", form.inReplyTo);
    fd.set("references", form.references);
    if (form.forward) fd.set("forward", JSON.stringify(form.forward));
    form.files.forEach((f) => fd.append("files", f, f.name));
    const res = await fetch(`${BASE}/send/prepare`, { method: "POST", body: fd });
    if (!res.ok) throw await failure(res);
    return (await res.json()) as PreparedSend;
  },
  confirmSend: (token: string) => postJson<{ ok: boolean; recipients: string[] }>("send/confirm", { token }),
  cancelSend: (token: string) => postJson<{ ok: boolean }>("send/cancel", { token }),
};
