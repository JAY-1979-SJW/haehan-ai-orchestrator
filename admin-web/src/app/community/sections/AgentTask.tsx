"use client";
/** 커뮤니티 레이더 — AI 브라우저 작업 (링크+지시 → 로컬 로그인 브라우저가 수행) */
import { useState } from "react";
import { authHeader, J } from "../communityShared";

type Step = { action?: string; outcome?: string; result?: string; reason?: string; target?: string };
type AgentResult = { ok?: boolean; blocked?: boolean; result?: string; steps?: Step[]; url?: string };

export function AgentTask() {
  const [url, setUrl] = useState("");
  const [instruction, setInstruction] = useState("");
  const [running, setRunning] = useState(false);
  const [res, setRes] = useState<AgentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    if (!instruction.trim()) return;
    setRunning(true); setError(null); setRes(null);
    try {
      const r = await fetch("/api/proxy/api/v1/browser-agent/run", {
        method: "POST", headers: { ...J, ...authHeader() },
        body: JSON.stringify({ url: url.trim() || null, instruction: instruction.trim(), max_steps: 12 }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "실행 실패");
      setRes(d);
    } catch (e) { setError(String(e)); } finally { setRunning(false); }
  }

  return (
    <div className="border border-[#E9D5FF] bg-[#FAF5FF] rounded-2xl p-4 space-y-2">
      <p className="text-sm font-bold text-[#7C3AED]">🤖 AI 브라우저 작업 <span className="text-[10px] font-normal text-[#9CA3AF]">(베타 · 로컬 로그인 브라우저)</span></p>
      <div className="flex flex-wrap gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="시작 URL (선택, 비우면 현재 페이지)"
          className="flex-1 min-w-[220px] border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#7C3AED]" />
      </div>
      <div className="flex flex-wrap gap-2">
        <input value={instruction} onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          placeholder="할 일 (예: 이 카페에서 오늘 공지 제목 정리해줘)"
          className="flex-1 min-w-[260px] border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#7C3AED]" />
        <button onClick={run} disabled={running || !instruction.trim()}
          className="px-4 py-2 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-40">
          {running ? "수행 중…" : "▶ 실행"}
        </button>
      </div>
      <p className="text-[11px] text-[#9CA3AF]">내 PC의 로그인된 브라우저를 AI가 운전해 수행합니다(읽기·탐색·추출·검색). 결제·삭제·발송 같은 위험 동작은 자동 차단되어 직접 승인이 필요합니다.</p>

      {error && <p className="text-xs text-[#DC2626]">오류: {error}</p>}
      {running && <p className="text-xs text-[#6B7280]">브라우저를 운전하는 중… (10~40초)</p>}

      {res && (
        <div className="bg-white rounded-xl border border-[#E5E7EB] p-3 space-y-2">
          {res.blocked && (
            <p className="text-xs font-semibold text-[#C2410C]">⛔ 위험 동작 차단 — 직접 승인 후 진행하세요</p>
          )}
          <div>
            <p className="text-xs font-semibold text-[#6B7280] mb-1">결과</p>
            <p className="text-sm text-[#111827] whitespace-pre-wrap">{res.result}</p>
          </div>
          {!!res.steps?.length && (
            <details>
              <summary className="text-xs text-[#9CA3AF] cursor-pointer">수행 단계 {res.steps.length}개</summary>
              <ol className="mt-1 space-y-0.5">
                {res.steps.map((s, i) => (
                  <li key={i} className="text-[11px] text-[#6B7280]">
                    {i + 1}. <b>{s.action}</b> {s.outcome || s.reason || (s.result ? "(완료)" : "")}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
