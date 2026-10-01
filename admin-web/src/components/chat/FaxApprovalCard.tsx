"use client";

import { useCallback, useEffect, useState } from "react";
import { faxApi, type Authorization, type RunStatus } from "@/app/hanafax/api";

/**
 * AI 창 안의 팩스 발송 승인 카드. AI 가 승인 대기 초안을 만들고 "[[fax-approve:<id>]]" 를 답에 넣으면 나타난다.
 * 승인은 **사람이 이 버튼을 눌러야만** 된다(AI 는 승인·발송 API 를 쓸 수 없다). 미리보기는 선택 — 열지 않아도 승인할 수 있다.
 */
export function FaxApprovalCard({ authId }: { authId: string }) {
  const [auth, setAuth] = useState<Authorization | null>(null);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [live, setLive] = useState(true);
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [a, r] = await Promise.all([faxApi.get(authId), faxApi.runStatus(authId)]);
      setAuth(a);
      setRun(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [authId]);

  useEffect(() => {
    void refresh();
    const t = setInterval(() => void refresh(), 4000);
    return () => clearInterval(t);
  }, [refresh]);

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      await faxApi.approve(authId, live, true); // 승인 + 바로 발송
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function sendNow() {
    setBusy(true);
    setError(null);
    try {
      await faxApi.run(authId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  async function revoke() {
    setBusy(true);
    try {
      await faxApi.revoke(authId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      await refresh();
    }
  }

  if (!auth) return <div className="mt-2 text-[11px] text-gray-500">{error ?? "발송 승인 정보를 불러오는 중…"}</div>;

  const pending = !auth.approved && !auth.revoked;
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-[#FDBA74] bg-white p-2 text-[11px] text-[#111827]" data-testid="fax-approval-card">
      <div className="font-semibold">팩스 발송 승인 — {auth.name}</div>
      <div>
        제목: {auth.subject} · 수신 {auth.recipient_count}곳 · 첨부: {auth.document_name}
      </div>
      {auth.document_matches === false && <div className="text-red-600">첨부 파일이 바뀌었거나 없습니다 — 승인할 수 없습니다.</div>}
      <button className="text-[#2563EB] underline" onClick={() => setPreview((v) => !v)}>
        {preview ? "미리보기 접기" : "미리보기 보기 (선택)"}
      </button>
      {preview && (
        <ul className="max-h-32 list-disc overflow-auto pl-4">
          {auth.recipients?.map((r) => (
            <li key={r.fax}>
              {r.name || "(이름 없음)"} · {r.fax}
            </li>
          ))}
        </ul>
      )}
      {pending ? (
        <div className="space-y-1 border-t pt-1">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            실제로 전송 (해제하면 전송 없이 계획만 기록)
          </label>
          <div className="flex gap-2">
            <button
              className="rounded bg-[#F97316] px-3 py-1 text-white disabled:opacity-50"
              disabled={busy || auth.document_matches === false}
              onClick={approve}
            >
              승인하고 발송
            </button>
            <button className="rounded border px-3 py-1" disabled={busy} onClick={revoke}>
              취소
            </button>
          </div>
        </div>
      ) : (
        <div className="border-t pt-1">
          {auth.revoked ? "취소됨" : auth.live ? "승인됨 · 실전송" : "승인됨 · 드라이런"}
          {run?.running && " · 발송 중…"}
          {!auth.revoked && !run?.running && !run?.last && (
            <button
              className="ml-2 rounded bg-[#2563EB] px-2 py-0.5 text-white disabled:opacity-50"
              disabled={busy}
              onClick={sendNow}
            >
              지금 발송
            </button>
          )}
          {run?.last && <div>마지막 실행: {run.last.message}</div>}
        </div>
      )}
      {error && <div className="text-red-600">{error}</div>}
    </div>
  );
}
