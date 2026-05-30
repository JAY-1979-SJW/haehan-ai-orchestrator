"use client";
/**
 * SmartStoreChat — AI 에이전트 채팅창
 * 대화 흐름: 사용자 말풍선(우) + AI 응답(좌) + 도구 실행 인라인 표시
 * /api/smartstore/chat Route Handler → Anthropic SDK → FastAPI 직접 호출 (단일 LLM)
 */
import { useState, useRef, useCallback, useEffect } from "react";
import { QUICK_GROUPS, EXAMPLE_CHIPS } from "./components/constants";
import { UserBubble } from "./components/UserBubble";
import { AssistantBubble } from "./components/AssistantBubble";
import type { Message, ChatMessage, AiBlock } from "./components/types";

// ── SSE 파서 ─────────────────────────────────────────────────────────────────
async function readSSE(
  res: Response,
  onEvent: (event: string, data: unknown) => void,
) {
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const part of parts) {
      const eventLine = part.match(/^event: (.+)/m)?.[1]?.trim();
      const dataLine  = part.match(/^data: (.+)/m)?.[1]?.trim();
      if (eventLine && dataLine) {
        try { onEvent(eventLine, JSON.parse(dataLine)); } catch { /* ignore */ }
      }
    }
  }
}

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────
export default function SmartStoreChat() {
  const [messages, setMessages]     = useState<Message[]>([]);
  const historyRef = useRef<ChatMessage[]>([]);  // ref로 관리 — state race 방지
  const [input, setInput]           = useState("");
  const [running, setRunning]       = useState(false);
  const [provider, setProvider]     = useState<"claude" | "gpt">("gpt");
  const [pendingConfirm, setPendingConfirm] = useState<{
    tool: string; inputs: Record<string, unknown>; message: string; userText: string;
  } | null>(null);

  const [quickOpen, setQuickOpen] = useState(false);
  const abortRef  = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const pushBlock = useCallback((block: AiBlock) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      return [...prev.slice(0, -1), { ...last, blocks: [...last.blocks, block] }];
    });
  }, []);

  const updateStep = useCallback((step: number, status: "ok" | "fail", detail?: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      return [
        ...prev.slice(0, -1),
        {
          ...last,
          blocks: last.blocks.map((b) =>
            b.type === "step" && b.item.step === step
              ? { ...b, item: { ...b.item, status, detail } }
              : b
          ),
        },
      ];
    });
  }, []);

  const finishAssistant = useCallback((summaryText?: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      return [...prev.slice(0, -1), { ...last, streaming: false }];
    });
    if (summaryText) {
      historyRef.current = [...historyRef.current, { role: "assistant", content: summaryText }];
    }
  }, []);

  const execute = useCallback(async (userText: string, confirmed: boolean) => {
    if (!userText.trim() || running) return;

    // API 전송용 history를 동기적으로 구성 (ref → race 없음)
    let apiMessages: ChatMessage[];
    if (!confirmed) {
      historyRef.current = [...historyRef.current, { role: "user", content: userText }];
      apiMessages = historyRef.current;
      setMessages((prev) => [
        ...prev,
        { role: "user", text: userText },
        { role: "assistant", blocks: [], streaming: true },
      ]);
    } else {
      // confirmed 재실행: 현재 이력에 user 메시지 추가 (이미 없는 경우만)
      apiMessages = [...historyRef.current, { role: "user", content: userText }];
      setMessages((prev) => [...prev, { role: "assistant", blocks: [], streaming: true }]);
    }

    setPendingConfirm(null);
    abortRef.current = new AbortController();
    setRunning(true);

    let collectedText = "";

    try {
      const res = await fetch("/api/smartstore/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: apiMessages, confirmed, provider }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        pushBlock({ type: "error", message: `서버 오류: HTTP ${res.status}` });
        return;
      }

      await readSSE(res, (event, data) => {
        const d = data as Record<string, unknown>;
        if (event === "text") {
          const t = String(d.text ?? "");
          collectedText += t;
          pushBlock({ type: "text", text: t });
        } else if (event === "step_start") {
          pushBlock({
            type: "step",
            item: {
              step: d.step as number,
              tool: d.tool as string,
              write: d.write as boolean,
              status: "running",
            },
          });
        } else if (event === "step_done") {
          updateStep(
            d.step as number,
            d.ok ? "ok" : "fail",
            !d.ok ? ((d.result as Record<string, unknown>)?.error as string | undefined) : undefined,
          );
        } else if (event === "confirm_required") {
          pushBlock({
            type: "confirm",
            tool: d.tool as string,
            inputs: d.inputs as Record<string, unknown>,
            message: d.message as string,
          });
          setPendingConfirm({
            tool:     d.tool as string,
            inputs:   d.inputs as Record<string, unknown>,
            message:  d.message as string,
            userText,
          });
        } else if (event === "done") {
          pushBlock({ type: "done", steps: d.steps as number });
        } else if (event === "error") {
          pushBlock({ type: "error", message: d.message as string });
        }
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        pushBlock({ type: "error", message: String(err) });
      }
    } finally {
      finishAssistant(collectedText || undefined);
      setRunning(false);
    }
  }, [running, provider, pushBlock, updateStep, finishAssistant]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    execute(text, false);
  }

  function handleChip(prompt: string) {
    setInput("");
    execute(prompt, false);
  }

  function handleConfirm() {
    if (!pendingConfirm) return;
    execute(pendingConfirm.userText, true);
  }

  function handleStop() {
    abortRef.current?.abort();
    setPendingConfirm(null);
    setRunning(false);
  }

  return (
    <div className="flex flex-col h-full min-h-[400px] border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden">

      {/* 헤더 */}
      <div className="shrink-0 flex items-center gap-2 px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
        <span className="w-7 h-7 rounded-lg bg-[#F97316] flex items-center justify-center text-white text-xs font-bold shrink-0">AI</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-bold text-[#111827]">스마트스토어 AI 에이전트</p>
          <p className="text-xs text-[#9CA3AF]">자연어로 상품·주문·정산·리뷰를 제어합니다</p>
        </div>
        {/* 모델 토글 */}
        <div className="flex items-center gap-1 shrink-0 bg-[#F3F4F6] rounded-lg p-0.5">
          {(["claude", "gpt"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setProvider(p)}
              disabled={running}
              className={`text-xs px-2.5 py-1 rounded-md font-semibold transition-colors disabled:opacity-50 ${
                provider === p
                  ? p === "claude"
                    ? "bg-[#F97316] text-white shadow-sm"
                    : "bg-[#10A37F] text-white shadow-sm"
                  : "text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {p === "claude" ? "Claude" : "GPT"}
            </button>
          ))}
        </div>

        {running && (
          <span className="flex items-center gap-1.5 text-xs text-[#F97316] font-semibold shrink-0">
            <span className="w-2 h-2 rounded-full bg-[#F97316] animate-pulse" />
            처리 중
          </span>
        )}
        {messages.length > 0 && !running && (
          <button
            onClick={() => { setMessages([]); historyRef.current = []; setPendingConfirm(null); }}
            className="text-xs text-[#9CA3AF] hover:text-[#6B7280] shrink-0 transition-colors"
          >
            초기화
          </button>
        )}
      </div>

      {/* 빠른 버튼 패널 */}
      <div className="shrink-0 border-b border-[#E5E7EB]">
        <button
          onClick={() => setQuickOpen((p) => !p)}
          className="w-full flex items-center justify-between px-4 py-2 text-xs text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
        >
          <span className="font-semibold text-[#374151]">⚡ 빠른 작업</span>
          <span>{quickOpen ? "▲" : "▼"}</span>
        </button>
        {quickOpen && (
          <div className="px-3 pb-3 space-y-2 bg-[#FAFAFA]">
            {QUICK_GROUPS.map((g) => (
              <div key={g.label}>
                <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5 px-1"
                  style={{ color: g.color }}>{g.label}</p>
                <div className="flex flex-wrap gap-1.5">
                  {g.actions.map((a) => (
                    <button
                      key={a.label}
                      disabled={running}
                      onClick={() => { handleChip(a.prompt); setQuickOpen(false); }}
                      className="px-2.5 py-1 rounded-full text-xs font-medium border transition-colors disabled:opacity-40 hover:shadow-sm"
                      style={{ background: g.bg, borderColor: g.border, color: g.color }}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 메시지 영역 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="w-14 h-14 rounded-2xl bg-[#FFF7ED] border border-[#FED7AA] flex items-center justify-center text-2xl">
              🤖
            </div>
            <div>
              <p className="text-sm font-semibold text-[#111827]">무엇을 도와드릴까요?</p>
              <p className="text-xs text-[#9CA3AF] mt-1">아래 예시를 클릭하거나 직접 입력하세요</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2 max-w-md">
              {EXAMPLE_CHIPS.map((c) => (
                <button
                  key={c.prompt}
                  onClick={() => handleChip(c.prompt)}
                  className="text-xs px-3 py-1.5 rounded-full border border-[#E5E7EB] text-[#374151] bg-white hover:bg-[#FFF7ED] hover:border-[#FED7AA] hover:text-[#C2410C] transition-colors"
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <UserBubble key={i} text={msg.text} />
          ) : (
            <AssistantBubble
              key={i}
              blocks={msg.blocks}
              streaming={msg.streaming}
              pendingConfirm={pendingConfirm}
              onConfirm={handleConfirm}
              onCancelConfirm={() => setPendingConfirm(null)}
            />
          )
        )}
        <div ref={bottomRef} />
      </div>

      {/* 예시 칩 (메시지 있을 때) */}
      {messages.length > 0 && !running && (
        <div className="shrink-0 flex gap-2 overflow-x-auto px-4 py-2 border-t border-[#E5E7EB] bg-[#F9FAFB]">
          {EXAMPLE_CHIPS.slice(0, 5).map((c) => (
            <button
              key={c.prompt}
              onClick={() => handleChip(c.prompt)}
              className="text-xs px-3 py-1 rounded-full border border-[#E5E7EB] text-[#6B7280] bg-white hover:bg-[#F3F4F6] whitespace-nowrap transition-colors shrink-0"
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {/* 입력창 */}
      <div className="shrink-0 px-4 py-3 border-t border-[#E5E7EB] bg-white">
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="예: 무드등 29800원 재고 50개로 등록해줘"
            disabled={running}
            className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:ring-2 focus:ring-[#F97316]/30 focus:border-[#F97316] disabled:opacity-50 transition-all resize-none"
          />
          {running ? (
            <button
              type="button"
              onClick={handleStop}
              className="shrink-0 px-4 py-2.5 rounded-xl border border-[#E5E7EB] text-sm text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
            >
              중단
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="shrink-0 px-4 py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-40 transition-colors"
            >
              전송
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
