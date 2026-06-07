"use client";
/** /agent — 원격 브라우저(AI 작업): 내 PC 로그인 브라우저를 AI가 운전 */
import { useState } from "react";

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const t = window.localStorage.getItem("haehan_ai_token");
  return t ? { Authorization: `Bearer ${t}` } : {};
}
const J = { "Content-Type": "application/json" };

type Step = { action?: string; outcome?: string; result?: string; reason?: string; target?: string };
type AgentResult = { ok?: boolean; blocked?: boolean; needs_login?: boolean; login_url?: string; result?: string; steps?: Step[]; url?: string };

const EXAMPLES = [
  "이 카페에서 오늘 올라온 공지 제목 정리해줘",
  "이 게시판 인기글 5개 제목과 요약 알려줘",
  "이 페이지에서 가격/스펙 표를 추출해줘",
];

export function AgentClient() {
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
    <div className="space-y-4 max-w-4xl">
      <div className="border border-[#E9D5FF] bg-[#FAF5FF] rounded-2xl p-4 space-y-3">
        <div>
          <p className="text-base font-bold text-[#7C3AED]">🤖 원격 브라우저 — AI가 내 브라우저를 운전</p>
          <p className="text-[12px] text-[#6B7280] mt-1">
            내 PC의 <b>로그인된 브라우저</b>를 AI가 직접 몰아 작업합니다(읽기·탐색·추출·검색).
            네이버·스토어처럼 로그인·봇보호된 사이트도 가능합니다. PC가 켜져 있어야 합니다.
          </p>
        </div>

        <input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="시작 URL (선택 — 비우면 현재 열린 페이지에서 시작)"
          className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#7C3AED]" />
        <div className="flex flex-wrap gap-2">
          <input value={instruction} onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") run(); }}
            placeholder="할 일을 자연어로 (예: 이 카페 오늘 공지 제목 정리해줘)"
            className="flex-1 min-w-[280px] border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm outline-none focus:border-[#7C3AED]" />
          <button onClick={run} disabled={running || !instruction.trim()}
            className="px-5 py-2 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-40">
            {running ? "수행 중…" : "▶ 실행"}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => setInstruction(ex)}
              className="text-[11px] text-[#7C3AED] bg-white border border-[#E9D5FF] rounded-full px-2.5 py-1 hover:bg-[#F3E8FF]">
              {ex}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-[#9CA3AF]">⚠️ 안전장치: 결제·구매·삭제·발송·제출 같은 위험 동작은 자동 차단되어 직접 승인이 필요합니다.</p>
      </div>

      {error && <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3 text-sm text-[#DC2626]">오류: {error}</div>}
      {running && <p className="text-sm text-[#6B7280]">브라우저를 운전하는 중… (10~40초)</p>}

      {res?.needs_login && (
        <div className="border border-[#FDE68A] bg-[#FFFBEB] rounded-2xl p-4 space-y-1">
          <p className="text-sm font-semibold text-[#B45309]">🔐 로그인이 필요합니다</p>
          <p className="text-xs text-[#92400E]">화면에 뜬 브라우저 창에서 해당 사이트에 로그인한 뒤, 다시 <b>[실행]</b>을 눌러주세요. (에이전트는 보안상 로그인을 대신할 수 없습니다)</p>
          {res.login_url && <p className="text-[11px] text-[#9CA3AF] truncate">{res.login_url}</p>}
        </div>
      )}

      {res && !res.needs_login && (
        <div className="bg-white rounded-2xl border border-[#E5E7EB] p-5 space-y-3">
          {res.blocked && (
            <p className="text-sm font-semibold text-[#C2410C]">⛔ 위험 동작 차단 — 직접 승인 후 진행하세요</p>
          )}
          <div>
            <p className="text-xs font-semibold text-[#6B7280] mb-1">결과</p>
            <p className="text-sm text-[#111827] whitespace-pre-wrap">{res.result}</p>
          </div>
          {!!res.steps?.length && (
            <details>
              <summary className="text-xs text-[#9CA3AF] cursor-pointer">수행 단계 {res.steps.length}개 보기</summary>
              <ol className="mt-1.5 space-y-0.5">
                {res.steps.map((s, i) => (
                  <li key={i} className="text-[11px] text-[#6B7280]">
                    {i + 1}. <b className="text-[#374151]">{s.action}</b> {s.outcome || s.reason || (s.result ? "(완료)" : "")}
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
