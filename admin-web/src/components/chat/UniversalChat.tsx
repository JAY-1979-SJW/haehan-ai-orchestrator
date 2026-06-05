"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useChatStream } from "./useChatStream";
import { CHAT_PRESETS, ChatChip } from "./chatPresets";

interface Msg {
  role: "user" | "ai" | "system";
  text: string;
  streaming?: boolean;
}

interface Props {
  domain?: string;
  presetChips?: ChatChip[];
  title?: string;
  className?: string;
}

export function UniversalChat({ domain = "default", presetChips, title, className = "" }: Props) {
  const chips = presetChips ?? CHAT_PRESETS[domain] ?? CHAT_PRESETS.default;
  const [msgs, setMsgs]         = useState<Msg[]>([]);
  const [input, setInput]       = useState("");
  const [running, setRunning]   = useState(false);
  const bottomRef               = useRef<HTMLDivElement>(null);
  const inputRef                = useRef<HTMLInputElement>(null);
  const { stream, abort }       = useChatStream();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  // 비동기 브라우저 작업 폴링 — 로그인 완료 후 백그라운드 결과를 채팅에 추가.
  const pollJob = useCallback(async (jobId: string) => {
    for (let i = 0; i < 100; i++) {          // 최대 ~5분 (100 × 3초)
      await new Promise(r => setTimeout(r, 3000));
      try {
        const res = await fetch(`/api/task/${jobId}`, { cache: "no-store" });
        const d = await res.json() as { status: string; result?: string };
        if (d.status === "done") {
          setMsgs(prev => [...prev, { role: "ai", text: d.result || "작업 완료", streaming: false }]);
          return;
        }
        if (d.status === "unknown") {
          setMsgs(prev => [...prev, { role: "ai", text: "작업을 찾을 수 없습니다.", streaming: false }]);
          return;
        }
      } catch { /* 폴링 일시 실패는 무시하고 재시도 */ }
    }
    setMsgs(prev => [...prev, { role: "ai", text: "⏱ 시간이 초과됐습니다 — 로그인 후 다시 명령해 주세요.", streaming: false }]);
  }, []);

  const send = useCallback(async (prompt: string) => {
    if (!prompt.trim() || running) return;
    setInput("");
    setRunning(true);

    setMsgs(prev => [...prev, { role: "user", text: prompt }]);
    setMsgs(prev => [...prev, { role: "ai", text: "", streaming: true }]);

    let fullText = "";
    try {
      await stream("/api/chat", { message: prompt, domain }, (event, data) => {
        if (event === "text") {
          const chunk = (data as { text: string }).text ?? "";
          fullText += chunk;
          setMsgs(prev => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "ai") next[next.length - 1] = { ...last, text: last.text + chunk };
            return next;
          });
        } else if (event === "done") {
          setMsgs(prev => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "ai") next[next.length - 1] = { ...last, streaming: false };
            return next;
          });
        } else if (event === "error") {
          const msg = (data as { message: string }).message ?? "오류가 발생했습니다.";
          setMsgs(prev => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "ai") next[next.length - 1] = { role: "ai", text: msg, streaming: false };
            return next;
          });
        }
      });

      // 비동기 브라우저 작업(job): 로그인 필요 시 마커가 옴 → 마커 제거 후 결과 폴링.
      const jm = fullText.match(/\[\[JOB:([A-Za-z0-9_-]+)\]\]/);
      if (jm) {
        setMsgs(prev => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "ai")
            next[next.length - 1] = { ...last, text: last.text.replace(/\n*\[\[JOB:[^\]]+\]\]/, "").trim(), streaming: false };
          return next;
        });
        await pollJob(jm[1]);
      }
    } catch {
      setMsgs(prev => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "ai") next[next.length - 1] = { role: "ai", text: "연결이 끊어졌습니다.", streaming: false };
        return next;
      });
    } finally {
      setRunning(false);
      inputRef.current?.focus();
    }
  }, [domain, running, stream, pollJob]);

  return (
    <div className={`flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden ${className}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 border-b border-[#F3F4F6] flex items-center justify-between shrink-0">
        <div>
          <p className="text-sm font-bold text-[#111827]">{title ?? "AI 어시스턴트"}</p>
          <p className="text-[11px] text-[#9CA3AF] mt-0.5">질문하거나 명령을 입력하세요</p>
        </div>
        {running && (
          <button onClick={abort}
            className="text-[10px] px-2 py-1 rounded-lg bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] font-semibold">
            중단
          </button>
        )}
      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
        {msgs.length === 0 && (
          <p className="text-[11px] text-[#9CA3AF] italic text-center py-4">
            아래 예시를 클릭하거나 직접 입력하세요
          </p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed whitespace-pre-wrap ${
              m.role === "user"
                ? "bg-[#F97316] text-white rounded-br-sm"
                : "bg-[#F9FAFB] border border-[#F3F4F6] text-[#111827] rounded-bl-sm"
            }`}>
              {m.text}
              {m.streaming && (
                <span className="inline-block w-1.5 h-3.5 bg-[#9CA3AF] ml-0.5 animate-pulse rounded-sm" />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 예시 칩 */}
      {chips.length > 0 && (
        <div className="px-3 py-2 border-t border-[#F3F4F6] flex flex-wrap gap-1.5 shrink-0">
          {chips.map((c) => (
            <button key={c.label} onClick={() => send(c.prompt)} disabled={running}
              className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] hover:bg-[#FED7AA] transition-colors disabled:opacity-40">
              {c.label}
            </button>
          ))}
        </div>
      )}

      {/* 입력창 */}
      <div className="px-3 pb-3 pt-2 flex gap-2 shrink-0">
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send(input)}
          placeholder="명령을 입력하세요..."
          disabled={running}
          className="flex-1 px-3 py-1.5 text-xs border border-[#E5E7EB] rounded-xl outline-none focus:border-[#F97316] text-[#111827] placeholder:text-[#9CA3AF] disabled:opacity-50"
        />
        <button onClick={() => send(input)} disabled={running || !input.trim()}
          className="px-3 py-1.5 rounded-xl text-xs font-bold bg-[#F97316] text-white hover:bg-[#EA580C] disabled:opacity-40 transition-colors shrink-0">
          전송
        </button>
      </div>
    </div>
  );
}
