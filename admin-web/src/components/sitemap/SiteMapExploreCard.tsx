"use client";

import { useCallback, useEffect, useState } from "react";

const BASE = "/api/proxy/api/v1/site-map/explore/requests";
const POLL_MS = 3000;

type Status = "pending" | "running" | "done" | "failed" | "cancelled" | "interrupted";

interface ExploreRequest {
  id: string;
  host: string;
  start_url: string;
  depth: number;
  max_pages: number;
  reason: string;
  status: Status;
  decided_by: string;
  result: { pages?: number; form_pages?: number; tasks?: number; aborted_reason?: string; snapshot_errors?: number };
  error: string;
}

const STATUS_TEXT: Record<Status, { text: string; cls: string }> = {
  pending: { text: "승인 대기", cls: "bg-amber-100 text-amber-800" },
  running: { text: "탐색 중…", cls: "bg-blue-100 text-blue-800" },
  done: { text: "완료", cls: "bg-green-100 text-green-800" },
  failed: { text: "실패", cls: "bg-red-100 text-red-800" },
  cancelled: { text: "취소됨", cls: "bg-gray-200 text-gray-700" },
  interrupted: { text: "중단됨(서버 재시작)", cls: "bg-orange-100 text-orange-800" },
};
const LIVE: Status[] = ["pending", "running"];

async function call(path: string, method = "GET"): Promise<ExploreRequest> {
  const res = await fetch(`${BASE}/${path}`, { method, cache: "no-store" });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {
      /* 본문이 JSON 이 아니면 상태 코드만 */
    }
    throw new Error(detail);
  }
  return (await res.json()) as ExploreRequest;
}

/**
 * AI 가 만든 사이트 탐색 요청의 승인 카드. AI 는 요청만 만들 수 있고, **승인·취소는 이 카드의 버튼(사람)** 으로만 된다.
 * 승인하면 전용 작업 탭에서 주소 이동만으로 읽는다(클릭·입력·제출 없음). 로그인이 필요한 사이트는 먼저 브라우저에서 로그인해 두세요.
 */
export function SiteMapExploreCard({ requestId }: { requestId: string }) {
  const [req, setReq] = useState<ExploreRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setReq(await call(requestId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [requestId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!req || !LIVE.includes(req.status)) return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [req, refresh]);

  async function act(action: "approve" | "cancel") {
    setBusy(true);
    setError(null);
    try {
      setReq(await call(`${requestId}/${action}`, "POST"));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!req) return <div className="mt-2 text-[11px] text-gray-500">{error ?? "탐색 요청을 불러오는 중…"}</div>;

  const st = STATUS_TEXT[req.status];
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-[#FDBA74] bg-white p-2 text-[11px] text-[#111827]" data-testid="sitemap-explore-card">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">사이트 탐색 승인 — {req.host}</span>
        <span className={`shrink-0 rounded px-2 py-px ${st.cls}`}>{st.text}</span>
      </div>
      <dl className="space-y-[2px]">
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">시작 주소</dt><dd className="break-all">{req.start_url}</dd></div>
        <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">범위</dt><dd>깊이 {req.depth} · 최대 {req.max_pages}쪽 · 같은 사이트만</dd></div>
        {req.reason && <div className="flex gap-2"><dt className="w-14 shrink-0 text-[#9CA3AF]">이유</dt><dd>{req.reason}</dd></div>}
      </dl>
      <div className="text-[#6B7280]">읽기 전용(주소 이동만) · 로그아웃·삭제·제출 주소는 건너뜀 · 봇 차단이 보이면 즉시 중단 · 입력값과 표 데이터는 저장하지 않음</div>
      {req.status === "done" && (
        <div className="rounded bg-green-50 p-1 text-green-900">
          {req.result.pages ?? 0}쪽 방문 · 입력창 있는 화면 {req.result.form_pages ?? 0}개 · 지도 업무 {req.result.tasks ?? 0}개
          {req.result.aborted_reason ? ` · 중단 사유: ${req.result.aborted_reason}` : ""}
          {req.result.snapshot_errors ? ` · 읽기 실패 ${req.result.snapshot_errors}쪽` : ""}
        </div>
      )}
      {req.status === "failed" && <div className="rounded bg-red-50 p-1 text-red-800">{req.error}</div>}
      {error && <div className="text-[#B91C1C]" role="alert">{error}</div>}
      {req.status === "pending" && (
        <div className="flex gap-2">
          <button type="button" disabled={busy} onClick={() => void act("approve")} className="rounded-lg bg-[#F97316] px-3 py-1 font-semibold text-white hover:bg-[#EA580C] disabled:opacity-50">
            승인하고 탐색
          </button>
          <button type="button" disabled={busy} onClick={() => void act("cancel")} className="rounded-lg border border-[#E5E7EB] px-3 py-1 text-[#374151] hover:bg-[#F9FAFB] disabled:opacity-50">
            취소
          </button>
        </div>
      )}
    </div>
  );
}
