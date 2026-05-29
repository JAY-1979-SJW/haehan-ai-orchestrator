"use client";
/**
 * SmartStoreChat — AI 에이전트 채팅창
 * 대화 흐름: 사용자 말풍선(우) + AI 응답(좌) + 도구 실행 인라인 표시
 * /api/smartstore/chat Route Handler → Anthropic SDK → FastAPI 직접 호출 (단일 LLM)
 */
import { useState, useRef, useCallback, useEffect } from "react";

// ── 예시 칩 ──────────────────────────────────────────────────────────────────
const EXAMPLE_CHIPS = [
  { label: "상품 목록",     prompt: "상품 목록을 보여줘" },
  { label: "주문 확인",     prompt: "최근 주문 목록을 확인해줘" },
  { label: "정산 조회",     prompt: "정산 내역을 조회해줘" },
  { label: "리뷰 확인",     prompt: "최근 리뷰와 문의를 확인해줘" },
  { label: "상품 수집",     prompt: "CDP로 상품 목록을 실시간 수집해줘" },
  { label: "셀러센터 열기", prompt: "셀러센터 상품 목록 페이지를 열어줘" },
  { label: "통계 수집",     prompt: "데이터 분석 통계를 수집해줘" },
];

const TOOL_LABEL: Record<string, string> = {
  list_products:      "상품 목록 조회",
  collect_products:   "상품 목록 수집",
  list_orders:        "주문 목록 조회",
  collect_orders:     "주문 목록 수집",
  list_settlements:   "정산 내역 조회",
  collect_settlements:"정산 내역 수집",
  list_reviews:       "리뷰/문의 조회",
  collect_reviews:    "리뷰/문의 수집",
  list_stats:         "통계 조회",
  collect_stats:      "통계 수집",
  register_product:   "상품 등록",
  edit_product:       "상품 수정",
  open_seller_center: "셀러센터 이동",
};

// ── 메시지 타입 ──────────────────────────────────────────────────────────────
type StepItem = {
  step: number;
  tool: string;
  write: boolean;
  status: "running" | "ok" | "fail";
  detail?: string;
};

type AiBlock =
  | { type: "text";    text: string }
  | { type: "step";    item: StepItem }
  | { type: "confirm"; tool: string; inputs: Record<string, unknown>; message: string }
  | { type: "done";    steps: number }
  | { type: "error";   message: string };

type Message =
  | { role: "user";      text: string }
  | { role: "assistant"; blocks: AiBlock[]; streaming: boolean };

// ── Anthropic MessageParam 호환 타입 ─────────────────────────────────────────
type ChatMessage = { role: "user" | "assistant"; content: string };

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
  const [provider, setProvider]     = useState<"claude" | "gpt">("claude");
  const [pendingConfirm, setPendingConfirm] = useState<{
    tool: string; inputs: Record<string, unknown>; message: string; userText: string;
  } | null>(null);

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
    <div className="flex flex-col h-[calc(100vh-220px)] min-h-[400px] border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden">

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

// ── 사용자 말풍선 ─────────────────────────────────────────────────────────────
function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] bg-[#F97316] text-white rounded-2xl rounded-tr-md px-4 py-2.5 text-sm leading-relaxed shadow-sm">
        {text}
      </div>
    </div>
  );
}

// ── AI 말풍선 ────────────────────────────────────────────────────────────────
function AssistantBubble({
  blocks,
  streaming,
  pendingConfirm,
  onConfirm,
  onCancelConfirm,
}: {
  blocks: AiBlock[];
  streaming: boolean;
  pendingConfirm: { tool: string; inputs: Record<string, unknown>; message: string } | null;
  onConfirm: () => void;
  onCancelConfirm: () => void;
}) {
  const isEmpty = blocks.length === 0;

  return (
    <div className="flex justify-start gap-2">
      <div className="w-7 h-7 rounded-lg bg-[#F97316] flex items-center justify-center text-white text-xs font-bold shrink-0 mt-1">
        AI
      </div>
      <div className="max-w-[80%] min-w-[120px] bg-[#F9FAFB] border border-[#E5E7EB] rounded-2xl rounded-tl-md px-4 py-3 space-y-2 shadow-sm">
        {isEmpty && streaming && (
          <span className="flex gap-1 items-center h-5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-[#9CA3AF] animate-bounce [animation-delay:300ms]" />
          </span>
        )}

        {blocks.map((block, i) => (
          <BlockView
            key={i}
            block={block}
            pendingConfirm={pendingConfirm}
            onConfirm={onConfirm}
            onCancelConfirm={onCancelConfirm}
          />
        ))}

        {streaming && blocks.length > 0 && (
          <span className="inline-block w-1.5 h-4 bg-[#F97316] animate-pulse rounded-sm" />
        )}
      </div>
    </div>
  );
}

// ── 블록 렌더러 ───────────────────────────────────────────────────────────────
function BlockView({
  block,
  pendingConfirm,
  onConfirm,
  onCancelConfirm,
}: {
  block: AiBlock;
  pendingConfirm: { tool: string; inputs: Record<string, unknown>; message: string } | null;
  onConfirm: () => void;
  onCancelConfirm: () => void;
}) {
  if (block.type === "text") {
    return <p className="text-sm text-[#111827] leading-relaxed whitespace-pre-wrap">{block.text}</p>;
  }

  if (block.type === "step") {
    const { item } = block;
    const icon =
      item.status === "running" ? <span className="w-3 h-3 rounded-full bg-[#F97316] animate-pulse shrink-0" /> :
      item.status === "ok"      ? <span className="text-[#16A34A] font-bold text-sm shrink-0">✓</span> :
                                  <span className="text-[#DC2626] font-bold text-sm shrink-0">✗</span>;
    return (
      <div className="flex items-center gap-2 text-xs py-1 px-2 bg-white rounded-lg border border-[#E5E7EB]">
        <span className="w-5 h-5 rounded-full bg-[#F3F4F6] border border-[#E5E7EB] flex items-center justify-center text-[10px] font-bold text-[#6B7280] shrink-0">
          {item.step}
        </span>
        {icon}
        <span className={`font-medium ${item.write ? "text-[#C2410C]" : "text-[#1D4ED8]"}`}>
          {TOOL_LABEL[item.tool] ?? item.tool}
        </span>
        {item.write && (
          <span className="text-[10px] bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded font-semibold">
            쓰기
          </span>
        )}
        {item.detail && <span className="text-[#DC2626] truncate">{item.detail}</span>}
      </div>
    );
  }

  if (block.type === "confirm") {
    // pendingConfirm이 있을 때만 버튼 활성화
    const active = !!pendingConfirm;
    return (
      <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-3 space-y-2">
        <p className="text-xs font-semibold text-[#C2410C]">작업 승인 필요</p>
        <p className="text-xs text-[#92400E]">{block.message}</p>
        <div className="bg-white border border-[#FED7AA] rounded-lg p-2 space-y-1">
          {Object.entries(block.inputs).map(([k, v]) => (
            <div key={k} className="flex gap-2 text-xs">
              <span className="font-mono text-[#92400E] w-20 shrink-0">{k}</span>
              <span className="text-[#111827]">{String(v)}</span>
            </div>
          ))}
        </div>
        {active && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={onConfirm}
              className="flex-1 py-1.5 rounded-lg bg-[#F97316] text-white text-xs font-semibold hover:bg-[#EA580C] transition-colors"
            >
              승인하고 실행
            </button>
            <button
              onClick={onCancelConfirm}
              className="flex-1 py-1.5 rounded-lg border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
            >
              취소
            </button>
          </div>
        )}
      </div>
    );
  }

  if (block.type === "done") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#16A34A] font-semibold pt-1">
        <span>✓</span>
        <span>완료 — {block.steps}단계 처리됨</span>
      </div>
    );
  }

  if (block.type === "error") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#DC2626] bg-[#FEF2F2] border border-[#FECACA] rounded-lg px-3 py-2">
        <span className="font-bold shrink-0">✗</span>
        <span>{block.message}</span>
      </div>
    );
  }

  return null;
}
