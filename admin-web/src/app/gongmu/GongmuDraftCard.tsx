"use client";

import { useCallback, useEffect, useState } from "react";
import { gongmuApi, type Draft, type DraftStatus } from "./api";

const POLL_MS = 4000;

const STATUS_TEXT: Record<DraftStatus, { text: string; cls: string }> = {
  pending: { text: "승인 대기", cls: "bg-amber-100 text-amber-800" },
  confirmed: { text: "확정됨", cls: "bg-green-100 text-green-800" },
  cancelled: { text: "취소됨", cls: "bg-gray-200 text-gray-700" },
};

/**
 * AI 가 만든 공무 문서 초안의 승인 카드. AI 는 초안만 만들 수 있고, **확정·취소는 이 카드의 버튼(사람)** 으로만 된다.
 * 확정하면 연결된 업무의 메모 끝에 덧붙는다(업무 상태·서류 체크는 바뀌지 않는다).
 */
export function GongmuDraftCard({ draftId, onDecided }: { draftId: string; onDecided?: () => void }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDraft(await gongmuApi.draft(draftId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [draftId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!draft || draft.status !== "pending") return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [draft, refresh]);

  async function act(run: () => Promise<Draft>) {
    setBusy(true);
    setError(null);
    try {
      setDraft(await run());
      onDecided?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!draft) return <div className="mt-2 text-[11px] text-gray-500">{error ?? "공무 초안을 불러오는 중…"}</div>;

  const st = STATUS_TEXT[draft.status];
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-[#FDBA74] bg-white p-2 text-[11px] text-[#111827]" data-testid="gongmu-draft-card">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">공무 초안 확정 — {draft.title}</span>
        <span className={`shrink-0 rounded px-2 py-px ${st.cls}`}>{st.text}</span>
      </div>
      <div className="text-[#6B7280]">{draft.task_id ? "확정하면 연결된 업무의 메모 끝에 덧붙습니다." : "업무에 연결되지 않은 초안입니다(확정해도 기록만 남습니다)."}</div>
      <button type="button" className="text-[#C2410C] underline" onClick={() => setOpen((v) => !v)}>
        {open ? "내용 접기" : "내용 보기"}
      </button>
      {open && <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded bg-[#F9FAFB] p-2 text-[11px]">{draft.body}</pre>}
      {error && <div className="text-[#B91C1C]" role="alert">{error}</div>}
      {draft.status === "pending" && (
        <div className="flex gap-2">
          <button type="button" disabled={busy} onClick={() => void act(() => gongmuApi.confirmDraft(draft.id))} className="rounded-lg bg-[#F97316] px-3 py-1 font-semibold text-white hover:bg-[#EA580C] disabled:opacity-50">
            확정
          </button>
          <button type="button" disabled={busy} onClick={() => void act(() => gongmuApi.cancelDraft(draft.id))} className="rounded-lg border border-[#E5E7EB] px-3 py-1 text-[#374151] hover:bg-[#F9FAFB] disabled:opacity-50">
            취소
          </button>
        </div>
      )}
    </div>
  );
}
