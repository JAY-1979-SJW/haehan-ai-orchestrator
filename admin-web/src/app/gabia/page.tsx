"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { PageShell } from "@/components/ui/PageShell";

// ── 빠른 버튼 (버튼 클릭 → AI 즉시 실행) ─────────────────────────────────────
const QUICK_ACTIONS = [
  {
    label: "업무 현황 조회",
    icon: "📋",
    prompt: "가비아 업무 현황을 보여줘",
    desc: "게이트 정책 + 가능 작업 목록",
    color: "#1D4ED8",
    bg: "#EFF6FF",
    border: "#BFDBFE",
  },
  {
    label: "로그인 감지 시작",
    icon: "🔐",
    prompt: "가비아 로그인 감지를 시작해줘",
    desc: "브라우저에서 로그인 후 DNS 화면 자동 이동",
    color: "#16A34A",
    bg: "#F0FDF4",
    border: "#BBF7D0",
  },
  {
    label: "DNS 화면 열기",
    icon: "🌐",
    prompt: "가비아 DNS 관리 화면을 열어줘",
    desc: "CDP 브라우저로 DNS 관리 화면 이동",
    color: "#7C3AED",
    bg: "#F5F3FF",
    border: "#DDD6FE",
  },
  {
    label: "업무 흐름 확인",
    icon: "📌",
    prompt: "DNS 작업 브라우저 단계별 흐름을 보여줘",
    desc: "8단계 자동화 계획 확인",
    color: "#374151",
    bg: "#F9FAFB",
    border: "#E5E7EB",
  },
  {
    label: "DNS 초안 작성",
    icon: "✏️",
    prompt: null, // 입력 모달 필요
    desc: "서브도메인 + IP 입력 → 초안 생성",
    color: "#F97316",
    bg: "#FFF7ED",
    border: "#FED7AA",
  },
];

const CHIPS = [
  { label: "업무 현황",       prompt: "가비아 업무 현황을 보여줘" },
  { label: "로그인 감지 시작", prompt: "가비아 로그인 감지를 시작해줘" },
  { label: "DNS 업무 목록",   prompt: "DNS 업무 레지스트리 목록을 보여줘" },
  { label: "업무 흐름",       prompt: "DNS 작업 브라우저 단계별 흐름을 보여줘" },
  { label: "DNS 초안 작성",   prompt: "autowork 서브도메인 A 레코드 초안을 작성해줘" },
  { label: "DNS 화면 열기",   prompt: "가비아 DNS 관리 화면을 열어줘" },
];

const TOOL_LABEL: Record<string, string> = {
  get_status:         "업무 현황 조회",
  start_login_watch:  "로그인 감지 시작",
  get_dns_tasks:      "DNS 업무 목록 조회",
  get_nav_plan:       "네비게이션 계획 조회",
  prepare_dns_record: "DNS 레코드 초안 작성",
  open_gabia_dns:     "DNS 관리 화면 열기",
};

type Msg =
  | { role: "user"; text: string }
  | { role: "ai"; blocks: AiBlock[] };

type AiBlock =
  | { type: "text"; text: string }
  | { type: "step"; tool: string; status: "running" | "ok" | "fail"; detail?: string }
  | { type: "done"; steps: number }
  | { type: "error"; message: string };

export default function GabiaPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // DNS 초안 작성 모달
  const [dnsModal, setDnsModal] = useState(false);
  const [dnsSubdomain, setDnsSubdomain] = useState("");
  const [dnsIp, setDnsIp] = useState("");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || running) return;
    const userMsg: Msg = { role: "user", text };
    setMessages((p) => [...p, userMsg]);
    setInput("");
    setRunning(true);

    const history = [...messages, userMsg]
      .map((m) => ({
        role: m.role === "user" ? "user" : "assistant",
        content: m.role === "user" ? m.text : (m as { role: "ai"; blocks: AiBlock[] }).blocks
          .filter((b) => b.type === "text")
          .map((b) => (b as { type: "text"; text: string }).text)
          .join(""),
      }))
      .filter((m) => m.content);

    const aiIdx = messages.length + 1;
    setMessages((p) => [...p, { role: "ai", blocks: [] }]);

    try {
      const res = await fetch("/api/gabia/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          const lines = part.split("\n");
          const eventLine = lines.find((l) => l.startsWith("event:"));
          const dataLine  = lines.find((l) => l.startsWith("data:"));
          if (!eventLine || !dataLine) continue;
          const event = eventLine.slice(6).trim();
          const data  = JSON.parse(dataLine.slice(5).trim());

          setMessages((prev) => {
            const next = [...prev];
            const ai = { ...(next[aiIdx] as { role: "ai"; blocks: AiBlock[] }) };
            const blocks = [...ai.blocks];

            if (event === "text") {
              const last = blocks[blocks.length - 1];
              if (last?.type === "text") {
                blocks[blocks.length - 1] = { type: "text", text: last.text + data.text };
              } else {
                blocks.push({ type: "text", text: data.text });
              }
            } else if (event === "step") {
              const idx = blocks.findIndex(
                (b) => b.type === "step" && (b as { type: "step"; tool: string; status: string }).tool === data.tool && (b as { type: "step"; tool: string; status: string }).status === "running",
              );
              const block: AiBlock = { type: "step", tool: data.tool, status: data.status, detail: data.detail };
              if (idx >= 0) blocks[idx] = block;
              else blocks.push(block);
            } else if (event === "done") {
              blocks.push({ type: "done", steps: data.steps });
            } else if (event === "error") {
              blocks.push({ type: "error", message: data.message });
            }

            ai.blocks = blocks;
            next[aiIdx] = ai;
            return next;
          });
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        const ai = next[aiIdx] as { role: "ai"; blocks: AiBlock[] };
        ai.blocks = [...ai.blocks, { type: "error", message: String(e) }];
        return next;
      });
    } finally {
      setRunning(false);
    }
  }, [messages, running]);

  return (
    <PageShell title="가비아" description="도메인·DNS·호스팅 AI 자동화" chatDomain="gabia">
      <div className="flex flex-col h-full w-full" style={{ minHeight: "calc(100vh - 120px)" }}>

        {/* 안내 배너 */}
        <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-xl px-4 py-3 mb-4 text-xs text-[#1D4ED8]">
          <p className="font-semibold mb-1">가비아 AI 에이전트 운영 원칙</p>
          <p>로그인(OTP/2FA)은 사용자가 직접 수행 · DNS 최종 저장은 사용자 승인 필수 · 결제/청구는 직접 처리</p>
        </div>

        {/* 빠른 버튼 패널 */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-4">
          {QUICK_ACTIONS.map((a) => (
            <button
              key={a.label}
              disabled={running}
              onClick={() => {
                if (a.prompt) {
                  send(a.prompt);
                } else {
                  setDnsModal(true);
                }
              }}
              className="flex flex-col items-start gap-1 p-3 rounded-xl border text-left hover:shadow-sm transition-all disabled:opacity-40"
              style={{ background: a.bg, borderColor: a.border }}
            >
              <div className="flex items-center gap-1.5">
                <span className="text-base">{a.icon}</span>
                <span className="text-xs font-bold" style={{ color: a.color }}>{a.label}</span>
              </div>
              <span className="text-[10px] text-[#9CA3AF] leading-tight">{a.desc}</span>
            </button>
          ))}
        </div>

        {/* DNS 초안 작성 모달 */}
        {dnsModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
            <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
              <h3 className="text-sm font-bold text-[#111827] mb-4">DNS 레코드 초안 작성</h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-[#374151] mb-1">서브도메인</label>
                  <input
                    value={dnsSubdomain}
                    onChange={(e) => setDnsSubdomain(e.target.value)}
                    placeholder="예: autowork, app, api"
                    className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]"
                  />
                  <p className="text-[10px] text-[#9CA3AF] mt-1">{dnsSubdomain ? `→ ${dnsSubdomain}.haehan-ai.kr` : ""}</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#374151] mb-1">서버 IP (A 레코드)</label>
                  <input
                    value={dnsIp}
                    onChange={(e) => setDnsIp(e.target.value)}
                    placeholder="예: 1.201.176.236"
                    className="w-full border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#F97316]"
                  />
                </div>
              </div>
              <div className="flex gap-2 mt-5">
                <button onClick={() => { setDnsModal(false); setDnsSubdomain(""); setDnsIp(""); }}
                  className="flex-1 py-2 rounded-xl border border-[#E5E7EB] text-sm text-[#6B7280] hover:border-[#374151]">
                  취소
                </button>
                <button
                  disabled={!dnsSubdomain.trim() || !dnsIp.trim()}
                  onClick={() => {
                    const prompt = `${dnsSubdomain}.haehan-ai.kr A 레코드 초안을 작성해줘. IP는 ${dnsIp}야.`;
                    setDnsModal(false);
                    setDnsSubdomain("");
                    setDnsIp("");
                    send(prompt);
                  }}
                  className="flex-1 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-40">
                  초안 작성
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 대화 영역 */}
        <div className="flex-1 overflow-y-auto space-y-4 pb-4">
          {messages.length === 0 && (
            <div className="text-center py-12 text-[#9CA3AF]">
              <p className="text-2xl mb-2">🏢</p>
              <p className="text-sm font-medium text-[#6B7280]">가비아 AI 에이전트</p>
              <p className="text-xs mt-1">도메인·DNS·호스팅 업무를 자연어로 지시하세요</p>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "user" ? (
                <div className="max-w-[70%] bg-[#1D4ED8] text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
                  {m.text}
                </div>
              ) : (
                <div className="max-w-[80%] space-y-2">
                  {(m as { role: "ai"; blocks: AiBlock[] }).blocks.map((b, j) => (
                    <div key={j}>
                      {b.type === "text" && b.text && (
                        <div className="bg-white border border-[#E5E7EB] rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm text-[#111827] whitespace-pre-wrap">
                          {b.text}
                        </div>
                      )}
                      {b.type === "step" && (
                        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${
                          b.status === "running" ? "bg-[#FFF7ED] text-[#F97316] border-[#FED7AA]" :
                          b.status === "ok"      ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]" :
                                                    "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]"
                        }`}>
                          <span>{b.status === "running" ? "⟳" : b.status === "ok" ? "✓" : "✗"}</span>
                          <span>{TOOL_LABEL[b.tool] ?? b.tool}</span>
                        </div>
                      )}
                      {b.type === "done" && (
                        <div className="text-xs text-[#9CA3AF]">완료 ({b.steps}단계)</div>
                      )}
                      {b.type === "error" && (
                        <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl px-3 py-2 text-xs text-[#DC2626]">
                          {b.message}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* 예시 칩 */}
        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {CHIPS.map((c) => (
              <button key={c.label} onClick={() => send(c.prompt)} disabled={running}
                className="px-3 py-1.5 rounded-full border border-[#E5E7EB] text-xs text-[#374151] bg-white hover:border-[#1D4ED8] hover:text-[#1D4ED8] transition-colors disabled:opacity-40">
                {c.label}
              </button>
            ))}
          </div>
        )}

        {/* 입력창 */}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            placeholder="가비아 업무를 지시하세요 (예: autowork DNS A 레코드 추가해줘)"
            disabled={running}
            className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#1D4ED8] focus:border-transparent disabled:opacity-50"
          />
          <button onClick={() => send(input)} disabled={running || !input.trim()}
            className="px-5 py-2.5 rounded-xl bg-[#1D4ED8] text-white text-sm font-semibold hover:bg-[#1E40AF] disabled:opacity-40 transition-colors">
            {running ? "실행 중" : "전송"}
          </button>
        </div>
      </div>
    </PageShell>
  );
}
