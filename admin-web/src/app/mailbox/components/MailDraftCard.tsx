"use client";

import { useCallback, useEffect, useState } from "react";
import { draftApi, type Draft, type DraftStatus } from "../lib/draftApi";
import { formatSize } from "../lib/format";

const POLL_MS = 4000;
const LIVE: DraftStatus[] = ["pending", "sending"]; // 아직 바뀔 수 있는 상태만 주기적으로 다시 읽는다

const STATUS_TEXT: Record<DraftStatus, { text: string; cls: string }> = {
  pending: { text: "승인 대기", cls: "bg-amber-100 text-amber-800" },
  sending: { text: "전송 중…", cls: "bg-blue-100 text-blue-800" },
  sent: { text: "보냄", cls: "bg-green-100 text-green-800" },
  failed: { text: "전송 실패 (다시 시도 가능)", cls: "bg-red-100 text-red-800" },
  unknown: { text: "결과 확인 필요", cls: "bg-orange-100 text-orange-800" },
  cancelled: { text: "취소됨", cls: "bg-gray-200 text-gray-700" },
  expired: { text: "만료됨", cls: "bg-gray-200 text-gray-700" },
};

/**
 * AI 가 만든 메일 초안의 승인 카드. AI 는 초안만 만들 수 있고, **보내기는 이 카드의 버튼(사람)** 으로만 된다.
 * 결과가 불확실하면(unknown) 자동으로 다시 보내지 않는다 — 보낸편지함을 확인한 뒤 필요하면 새 초안을 만든다.
 */
export function MailDraftCard({ draftId }: { draftId: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDraft(await draftApi.get(draftId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [draftId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!draft || !LIVE.includes(draft.status)) return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [draft, refresh]);

  async function act(run: () => Promise<Draft>) {
    setBusy(true);
    setError(null);
    try {
      setDraft(await run());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!draft) return <div className="mt-2 text-[11px] text-gray-500">{error ?? "메일 초안을 불러오는 중…"}</div>;

  const st = STATUS_TEXT[draft.status];
  const canSend = draft.status === "pending" || draft.status === "failed";
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-[#FDBA74] bg-white p-2 text-[11px] text-[#111827]" data-testid="mail-draft-card">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">메일 발송 승인 — {draft.subject}</span>
        <span className={`shrink-0 rounded px-2 py-px ${st.cls}`}>{st.text}</span>
      </div>
      <dl className="space-y-[2px]">
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">보내는 사람</dt><dd>{draft.account}@naver.com</dd></div>
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">받는 사람</dt><dd className="break-words">{draft.to.join(", ")}</dd></div>
        {draft.cc.length > 0 && <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">참조</dt><dd className="break-words">{draft.cc.join(", ")}</dd></div>}
        {draft.bcc.length > 0 && <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">숨은참조</dt><dd className="break-words">{draft.bcc.join(", ")}</dd></div>}
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-[#9CA3AF]">첨부</dt>
          <dd>{draft.attachments.length === 0 ? "없음" : draft.attachments.map((a) => `${a.name} (${formatSize(a.size)})`).join(", ")}</dd>
        </div>
      </dl>
      <button type="button" className="text-[#2563EB] underline" onClick={() => setOpen((v) => !v)}>
        {open ? "본문 접기" : "본문 보기"}
      </button>
      {open && <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-[#F9FAFB] p-2 font-sans">{draft.body_preview}</pre>}

      {canSend && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-1">
          <button type="button" className="rounded bg-[#F97316] px-3 py-1 text-white disabled:opacity-50" disabled={busy} onClick={() => void act(() => draftApi.send(draft.id))}>
            승인하고 보내기
          </button>
          <button type="button" className="rounded border px-3 py-1 disabled:opacity-50" disabled={busy} onClick={() => void act(() => draftApi.cancel(draft.id))}>
            취소
          </button>
          <span className="text-[#9CA3AF]">고치려면 AI 창에 “제목을 …로 바꿔 다시 만들어줘”라고 하세요.</span>
        </div>
      )}
      {draft.status === "sent" && <div className="border-t pt-1 text-green-700">보냈습니다{draft.sent_at ? ` · ${draft.sent_at.replace("T", " ").slice(0, 16)}` : ""}{draft.result.refused_count ? ` · 일부 주소는 거부됨(${draft.result.refused_count})` : ""}</div>}
      {draft.status === "unknown" && (
        <div className="border-t pt-1 text-orange-700">
          전송 결과를 확인하지 못했습니다(자동으로 다시 보내지 않습니다). <b>보낸메일함</b>에서 확인한 뒤 필요하면 새 초안을 만드세요. {draft.result.message}
        </div>
      )}
      {draft.status === "failed" && <div className="border-t pt-1 text-red-700">{draft.result.message || "전송에 실패했습니다."}</div>}
      {error && <div className="text-red-600">{error}</div>}
    </div>
  );
}
