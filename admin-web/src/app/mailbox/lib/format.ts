import type { Address, MessageDetail } from "./api";

export { formatSize } from "@/components/chat/formatSize";

const KST_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** 시각을 한국 시간(KST)의 연·월·일·시·분 문자열로 나눈다 — 보는 PC 의 시간대와 무관하다. */
function kstParts(d: Date): { y: string; mo: string; d: string; h: string; mi: string } {
  const p = Object.fromEntries(KST_PARTS.formatToParts(d).map((x) => [x.type, x.value]));
  return { y: p.year, mo: p.month, d: p.day, h: p.hour, mi: p.minute };
}

/** 네이버 목록처럼(한국 시간 기준): 오늘이면 시:분, 올해면 월.일, 그 외 연.월.일 */
export function formatListDate(iso: string, fallback: string): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  const t = kstParts(d);
  const n = kstParts(new Date());
  if (t.y === n.y && t.mo === n.mo && t.d === n.d) return `${t.h}:${t.mi}`;
  if (t.y === n.y) return `${t.mo}.${t.d}`;
  return `${t.y}.${t.mo}.${t.d}`;
}

export function formatFullDate(iso: string, fallback: string): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  const t = kstParts(d);
  return `${t.y}.${t.mo}.${t.d} ${t.h}:${t.mi}`;
}

export function displayAddress(a: Address): string {
  return a.name ? `${a.name} <${a.address}>` : a.address;
}

export function senderName(a: Address): string {
  return a.name || a.address;
}

export type ComposeMode = "new" | "reply" | "replyAll" | "forward";

export interface ComposeDraft {
  mode: ComposeMode;
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  /** 편집기에 넣을 HTML (이미 서버에서 정제된 인용문만 포함) */
  html: string;
  inReplyTo: string;
  references: string;
  /** 전달할 때 원본 메일 참조(원본 첨부를 서버가 가져온다) */
  source: { folder: string; uid: number; attachments: MessageDetail["attachments"] } | null;
}

export const EMPTY_DRAFT: ComposeDraft = {
  mode: "new",
  to: "",
  cc: "",
  bcc: "",
  subject: "",
  html: "",
  inReplyTo: "",
  references: "",
  source: null,
};

function withPrefix(subject: string, prefix: string): string {
  const re = new RegExp(`^\\s*(${prefix.replace(":", "")}|${prefix === "Re:" ? "회신" : "전달"})\\s*:`, "i");
  return re.test(subject) ? subject : `${prefix} ${subject}`;
}

function esc(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 편집기에 넣을 인용 HTML — 머리말은 직접 이스케이프하고, 본문은 서버가 정제한 quote_html 만 쓴다. */
function quoteBlock(m: MessageDetail): string {
  const head = [
    "-------- 원본 메시지 --------",
    `보낸 사람: ${displayAddress(m.from)}`,
    `받는 사람: ${m.to.map(displayAddress).join(", ")}`,
    `날짜: ${formatFullDate(m.date_iso, m.date)}`,
    `제목: ${m.subject}`,
  ]
    .map(esc)
    .join("<br>");
  return `<p><br></p><div style="color: #6b7280; font-size: 12px">${head}</div><blockquote style="margin-left: 0; padding-left: 12px; border-left: 3px solid #e5e7eb">${m.quote_html}</blockquote>`;
}

/** 답장/전체답장/전달 초안 — `myAddress` 는 전체답장에서 내 주소를 빼기 위해 쓴다. */
export function buildDraft(mode: Exclude<ComposeMode, "new">, m: MessageDetail, myAddress: string): ComposeDraft {
  const base: ComposeDraft = { ...EMPTY_DRAFT, mode, html: quoteBlock(m) };
  if (mode === "forward") {
    return { ...base, subject: withPrefix(m.subject, "Fwd:"), source: { folder: m.folder, uid: m.uid, attachments: m.attachments } };
  }
  const refs = [m.references, m.message_id].filter(Boolean).join(" ").trim();
  const draft = { ...base, subject: withPrefix(m.subject, "Re:"), to: m.from.address, inReplyTo: m.message_id, references: refs };
  if (mode === "replyAll") {
    const others = [...m.to, ...m.cc].map((a) => a.address).filter((a) => a && a !== myAddress && a !== m.from.address);
    return { ...draft, cc: Array.from(new Set(others)).join(", ") };
  }
  return draft;
}
