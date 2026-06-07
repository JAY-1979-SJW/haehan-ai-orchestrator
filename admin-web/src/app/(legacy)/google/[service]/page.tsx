"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { PageShell } from "@/components/ui/PageShell";

// ── 앱별 설정 ─────────────────────────────────────────────────────────────────
import { SERVICE_CONFIG, getConfig, type ChatMsg } from "./serviceConfig";
export default function GoogleServicePage() {
  const params  = useParams();
  const router  = useRouter();
  const service = typeof params?.service === "string" ? params.service : "";
  const cfg     = getConfig(service);

  const [msgs, setMsgs]         = useState<ChatMsg[]>([]);
  const [input, setInput]       = useState("");
  const [running, setRunning]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || running) return;
    setMsgs((p) => [...p, { role: "user", text }]);
    setInput("");
    setRunning(true);
    try {
      const r = await fetch("/api/google/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: `[${cfg.name}] ${text}` }),
      });
      const d = await r.json();
      setMsgs((p) => [...p, { role: "ai", text: d.reply ?? "처리 완료" }]);
    } catch {
      setMsgs((p) => [...p, { role: "ai", text: "서버 연결 오류" }]);
    } finally {
      setRunning(false);
    }
  }, [running, cfg.name]);

  return (
    <PageShell title={`${cfg.icon} ${cfg.name}`} description="Google 앱 AI 에이전트" chatDomain="google">
      <div className="flex flex-col h-full w-full gap-4" style={{ minHeight: "calc(100vh - 120px)" }}>

        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl border"
              style={{ background: cfg.bg, borderColor: cfg.border }}>
              {cfg.icon}
            </div>
            <div>
              <h1 className="text-base font-bold text-[#111827]">{cfg.name}</h1>
              <a href={cfg.url} target="_blank" rel="noopener noreferrer"
                className="text-xs hover:underline" style={{ color: cfg.color }}>{cfg.url}</a>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a href={cfg.url} target="_blank" rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors hover:opacity-80"
              style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.border }}>
              사이트 열기 →
            </a>
            <Link href="/google"
              className="px-3 py-1.5 rounded-lg text-xs text-[#6B7280] border border-[#E5E7EB] hover:border-[#374151] transition-colors">
              ← 허브
            </Link>
          </div>
        </div>

        {/* 빠른 버튼 패널 */}
        <div className="bg-white border border-[#E5E7EB] rounded-2xl p-4 space-y-3">
          <p className="text-xs font-bold text-[#374151]">⚡ 빠른 작업</p>
          {cfg.quickGroups.map((g) => (
            <div key={g.label}>
              <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5"
                style={{ color: cfg.color }}>{g.label}</p>
              <div className="flex flex-wrap gap-2">
                {g.actions.map((a) => (
                  <button key={a.label} disabled={running}
                    onClick={() => send(a.prompt)}
                    className="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors hover:shadow-sm disabled:opacity-40"
                    style={{ background: cfg.bg, borderColor: cfg.border, color: cfg.color }}>
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* 채팅창 */}
        <div className="flex-1 flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden min-h-0">
          {/* 메시지 */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
            {msgs.length === 0 && (
              <div className="flex items-center justify-center h-full text-center">
                <div>
                  <p className="text-3xl mb-2">{cfg.icon}</p>
                  <p className="text-sm font-medium text-[#6B7280]">{cfg.name} AI 에이전트</p>
                  <p className="text-xs text-[#9CA3AF] mt-1">위 버튼을 클릭하거나 직접 입력하세요</p>
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "user" ? (
                  <div className="max-w-[70%] px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm text-white"
                    style={{ background: cfg.color }}>
                    {m.text}
                  </div>
                ) : (
                  <div className="max-w-[80%] px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm text-[#111827] bg-[#F9FAFB] border border-[#E5E7EB] whitespace-pre-wrap">
                    {m.text}
                  </div>
                )}
              </div>
            ))}
            {running && (
              <div className="flex justify-start">
                <div className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-[#F9FAFB] border border-[#E5E7EB]">
                  <span className="flex gap-1">
                    {[0, 150, 300].map((d) => (
                      <span key={d} className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce"
                        style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* 입력창 */}
          <div className="shrink-0 px-4 py-3 border-t border-[#E5E7EB] flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }}}
              placeholder={`${cfg.name}에게 지시하세요...`}
              disabled={running}
              className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 disabled:opacity-50"
              style={{ focusRingColor: cfg.color } as React.CSSProperties}
            />
            <button onClick={() => send(input)} disabled={running || !input.trim()}
              className="px-5 py-2.5 rounded-xl text-white text-sm font-semibold disabled:opacity-40 transition-colors"
              style={{ background: cfg.color }}>
              {running ? "···" : "전송"}
            </button>
          </div>
        </div>

      </div>
    </PageShell>
  );
}
