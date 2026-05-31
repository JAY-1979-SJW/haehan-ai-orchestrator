"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { API_BASE } from "@/lib/assistant/api";

// ── 빠른 버튼 ─────────────────────────────────────────────────────────────────
const QUICK_GROUPS = [
  {
    label: "계정·로그인",
    color: "#0891B2", bg: "#ECFEFF", border: "#A5F3FC",
    actions: [
      { label: "로그인 감지 시작", prompt: "공공데이터포털 로그인 감지를 시작해줘. 브라우저에서 로그인하면 마이페이지로 이동해줘." },
      { label: "마이페이지 열기",  prompt: "공공데이터포털 마이페이지를 열어줘." },
      { label: "로그인 상태 확인", prompt: "공공데이터포털 로그인 상태를 확인해줘." },
    ],
  },
  {
    label: "인증키 관리",
    color: "#F97316", bg: "#FFF7ED", border: "#FED7AA",
    actions: [
      { label: "인증키 목록 확인",  prompt: "공공데이터포털에서 내 인증키(API Key) 목록을 확인해줘." },
      { label: "인증키 발급 신청",  prompt: "공공데이터포털에서 새 API 인증키 발급을 신청해줘. 발급 절차를 안내해줘." },
      { label: "인증키 갱신",       prompt: "공공데이터포털에서 만료된 인증키를 갱신하는 방법을 안내해줘." },
    ],
  },
  {
    label: "데이터 신청",
    color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE",
    actions: [
      { label: "신청 현황 확인",    prompt: "공공데이터포털에서 내 데이터 신청 현황을 확인해줘." },
      { label: "활용신청 방법",     prompt: "공공데이터포털에서 원하는 데이터를 활용신청하는 방법을 단계별로 안내해줘." },
      { label: "승인 대기 확인",    prompt: "공공데이터포털에서 승인 대기 중인 데이터 신청이 있는지 확인해줘." },
    ],
  },
  {
    label: "데이터 검색",
    color: "#16A34A", bg: "#F0FDF4", border: "#BBF7D0",
    actions: [
      { label: "건설 관련 데이터",  prompt: "공공데이터포털에서 건설·공사 관련 공공 데이터를 검색해줘." },
      { label: "G2B 입찰 데이터",   prompt: "공공데이터포털에서 나라장터 입찰 관련 Open API를 찾아줘." },
      { label: "건설업 면허 데이터", prompt: "공공데이터포털에서 건설업 면허 조회 API를 찾아줘." },
    ],
  },
];

// ── 유용한 링크 ───────────────────────────────────────────────────────────────
const QUICK_LINKS = [
  { label: "마이페이지",    url: "https://www.data.go.kr/ugs/selectPublicDataPrlctcList.do" },
  { label: "인증키 관리",   url: "https://www.data.go.kr/ugs/selectPublicDataDetailView.do" },
  { label: "활용신청 현황", url: "https://www.data.go.kr/ugs/selectPublicDataUserApplicationList.do" },
  { label: "데이터 검색",   url: "https://www.data.go.kr/data/selectAll.do" },
  { label: "로그인",        url: "https://www.data.go.kr/login/loginForm.do" },
];

// ── 채팅 타입 ─────────────────────────────────────────────────────────────────
type ChatMsg = { role: "user" | "ai"; text: string };

export default function DataPortalPage() {
  const [msgs, setMsgs]       = useState<ChatMsg[]>([]);
  const [input, setInput]     = useState("");
  const [running, setRunning] = useState(false);
  const [sessionStatus, setSessionStatus] = useState<"unknown" | "logged_in" | "logged_out">("unknown");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  // 세션 상태 조회
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/sessions/status`, { headers: {} })
      .then((r) => r.json())
      .then((d) => {
        const site = d.sites?.find((s: { key: string; status: string }) => s.key === "dataportal");
        if (site?.status === "LOGGED_IN") setSessionStatus("logged_in");
        else if (site?.status !== "UNKNOWN") setSessionStatus("logged_out");
      })
      .catch(() => {});
  }, []);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || running) return;
    setMsgs((p) => [...p, { role: "user", text }]);
    setInput("");
    setRunning(true);

    // 로그인 감지 요청이면 실제 스크립트 실행
    if (text.includes("로그인 감지")) {
      try {
        await fetch(`${API_BASE}/api/v1/sessions/refresh`, { method: "POST", headers: {} });
      } catch { /* ignore */ }
    }

    // Google chat API 재사용 (공공데이터포털 컨텍스트 주입)
    try {
      const r = await fetch(`${API_BASE}/api/v1/google/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: `[공공데이터포털 data.go.kr] ${text}\n\n운영 원칙:\n- 로그인은 사용자가 브라우저에서 직접 수행\n- 인증키(API Key) 값은 출력하지 않음\n- 신청/발급 절차 안내는 단계별로 명확하게\n- 실제 CDP 이동이 필요하면 URL을 알려줌`
        }),
      });
      const d = await r.json();
      setMsgs((p) => [...p, { role: "ai", text: d.reply ?? "처리 완료" }]);
    } catch {
      setMsgs((p) => [...p, { role: "ai", text: "서버 연결 오류" }]);
    } finally {
      setRunning(false);
    }
  }, [running]);

  return (
    <PageShell title="공공데이터포털" description="data.go.kr · API 키 발급·관리·신청" chatDomain="dataportal">
      <div className="flex flex-col gap-4 w-full" style={{ minHeight: "calc(100vh - 120px)" }}>

        {/* 헤더 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#0891B2] flex items-center justify-center text-white text-xs font-bold shrink-0">공</div>
              <div>
                <p className="text-sm font-bold text-[#111827]">공공데이터포털</p>
                <a href="https://www.data.go.kr" target="_blank" rel="noopener noreferrer"
                  className="text-xs text-[#0891B2] hover:underline">data.go.kr</a>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {/* 세션 상태 */}
              <span className={`text-xs font-semibold px-3 py-1.5 rounded-full border ${
                sessionStatus === "logged_in"  ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]" :
                sessionStatus === "logged_out" ? "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]" :
                "bg-[#F9FAFB] text-[#9CA3AF] border-[#E5E7EB]"
              }`}>
                {sessionStatus === "logged_in" ? "● 로그인됨" :
                 sessionStatus === "logged_out" ? "○ 미로그인" : "○ 상태 미확인"}
              </span>
              {/* 빠른 링크 */}
              {QUICK_LINKS.map((l) => (
                <a key={l.label} href={l.url} target="_blank" rel="noopener noreferrer"
                  className="text-xs px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-[#374151] hover:border-[#0891B2] hover:text-[#0891B2] transition-colors whitespace-nowrap">
                  {l.label}
                </a>
              ))}
            </div>
          </div>

          {/* 안내 */}
          <div className="mt-3 px-3 py-2 rounded-xl bg-[#ECFEFF] border border-[#A5F3FC] text-xs text-[#0891B2]">
            로그인은 브라우저에서 직접 수행 · 인증키 값은 화면에 표시하지 않음 · 신청/발급 절차는 단계별 안내
          </div>
        </div>

        {/* 빠른 버튼 패널 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-4 space-y-3">
          <p className="text-xs font-bold text-[#374151]">⚡ 빠른 작업</p>
          <div className="space-y-3">
            {QUICK_GROUPS.map((g) => (
              <div key={g.label}>
                <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5"
                  style={{ color: g.color }}>{g.label}</p>
                <div className="flex flex-wrap gap-2">
                  {g.actions.map((a) => (
                    <button key={a.label} disabled={running}
                      onClick={() => send(a.prompt)}
                      className="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors hover:shadow-sm disabled:opacity-40"
                      style={{ background: g.bg, borderColor: g.border, color: g.color }}>
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 채팅창 */}
        <div className="flex-1 flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden min-h-0" style={{ minHeight: 300 }}>
          <div className="shrink-0 px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB] flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-[#0891B2] flex items-center justify-center text-white text-[10px] font-bold">AI</div>
            <p className="text-sm font-bold text-[#111827]">공공데이터포털 AI 에이전트</p>
            {running && <span className="ml-auto text-xs text-[#0891B2] font-semibold animate-pulse">처리 중...</span>}
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {msgs.length === 0 && (
              <div className="flex items-center justify-center h-full text-center">
                <div>
                  <p className="text-3xl mb-2">🏛️</p>
                  <p className="text-sm font-medium text-[#6B7280]">공공데이터포털 AI 에이전트</p>
                  <p className="text-xs text-[#9CA3AF] mt-1">위 버튼을 클릭하거나 직접 질문하세요</p>
                  <div className="mt-3 space-y-1 text-xs text-[#9CA3AF]">
                    <p>예: "G2B 입찰 API 신청 방법 알려줘"</p>
                    <p>예: "내 인증키 만료일 확인해줘"</p>
                    <p>예: "건설업 면허 조회 API 찾아줘"</p>
                  </div>
                </div>
              </div>
            )}

            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "user" ? (
                  <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm text-white bg-[#0891B2]">
                    {m.text}
                  </div>
                ) : (
                  <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm text-[#111827] bg-[#F9FAFB] border border-[#E5E7EB] whitespace-pre-wrap leading-relaxed">
                    {m.text}
                  </div>
                )}
              </div>
            ))}

            {running && (
              <div className="flex justify-start">
                <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-[#F9FAFB] border border-[#E5E7EB]">
                  <span className="flex gap-1">
                    {[0, 150, 300].map((d) => (
                      <span key={d} className="w-1.5 h-1.5 rounded-full bg-[#0891B2] animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="shrink-0 px-4 py-3 border-t border-[#E5E7EB] flex gap-2">
            <input value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
              placeholder="공공데이터포털 업무를 지시하세요 (예: G2B API 신청 방법)"
              disabled={running}
              className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0891B2] disabled:opacity-50"
            />
            <button onClick={() => send(input)} disabled={running || !input.trim()}
              className="px-5 py-2.5 rounded-xl bg-[#0891B2] text-white text-sm font-semibold hover:bg-[#0E7490] disabled:opacity-40 transition-colors">
              {running ? "···" : "전송"}
            </button>
          </div>
        </div>

      </div>
    </PageShell>
  );
}
