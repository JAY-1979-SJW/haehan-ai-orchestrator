"use client";
/** 커뮤니티 레이더 — 자율 분석 리포트 (주간 자동 + 수동 전체 실행) */
import { useState, useEffect, useCallback } from "react";
import { type Report, authHeader } from "../communityShared";

type Batch = { generated_at?: string; reason?: string; site_count?: number; ok_count?: number; reports?: Report[] };

export function AutoReports({ siteCount, onError }: { siteCount: number; onError: (msg: string | null) => void }) {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [scheduleState, setScheduleState] = useState<{ last_run?: string | null } | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/proxy/api/v1/community/reports?limit=5", { headers: authHeader() });
      const d = await r.json();
      setBatches(d.reports || []);
      setScheduleState(d.state || null);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function runAll() {
    setRunning(true); onError(null);
    try {
      const r = await fetch("/api/proxy/api/v1/community/run-now", { method: "POST", headers: authHeader() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "실행 실패");
      await load();
    } catch (e) { onError(String(e)); } finally { setRunning(false); }
  }

  return (
    <div className="border border-[#E5E7EB] rounded-2xl bg-white p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <p className="text-sm font-bold text-[#111827]">자율 분석 리포트</p>
          <p className="text-[11px] text-[#9CA3AF]">
            등록 사이트를 주기(주 1회)마다 자동 수집·분석합니다.
            {scheduleState?.last_run ? ` 최근 실행: ${scheduleState.last_run}` : " 아직 실행 기록 없음"}
          </p>
        </div>
        <button onClick={runAll} disabled={running || siteCount === 0}
          className="px-3 py-1.5 rounded-lg bg-[#7C3AED] text-white text-xs font-semibold hover:bg-[#6D28D9] disabled:opacity-40">
          {running ? "전체 분석 중…" : "▶ 지금 전체 실행"}
        </button>
      </div>
      {batches.length === 0 && <p className="text-sm text-[#9CA3AF]">저장된 리포트가 없습니다. 사이트를 등록하고 실행하세요.</p>}
      {batches.map((batch, bi) => (
        <div key={bi} className="border border-[#F3F4F6] rounded-xl p-3 bg-[#FAFAFA]">
          <p className="text-xs text-[#6B7280] mb-1.5">{batch.generated_at} · {batch.reason === "scheduled" ? "자동" : "수동"} · {batch.ok_count}/{batch.site_count} 성공</p>
          <div className="space-y-1.5">
            {(batch.reports || []).map((r, ri) => (
              <div key={ri} className="text-sm">
                <span className="font-semibold text-[#111827]">{r.site}</span>
                {r.summary ? <span className="text-[#374151]"> — {r.summary}</span> : <span className="text-[#DC2626]"> — {r.error || "실패"}</span>}
                {!!r.opportunities?.length && (
                  <span className="text-xs text-[#16A34A]"> · 💰 {r.opportunities[0]?.idea}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
