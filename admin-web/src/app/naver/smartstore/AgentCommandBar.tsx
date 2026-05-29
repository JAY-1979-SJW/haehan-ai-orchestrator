"use client";
/**
 * AgentCommandBar — 자연어 명령창 + 예시 칩 + SSE 진행 로그
 * 쓰기 작업은 confirm_required 이벤트 수신 후 사용자 승인 시 재실행
 */
import { useState, useRef, useCallback, useEffect } from "react";
import { runSmartStoreAgent, type AgentSSEEvent } from "@/lib/assistant/api";

// ── 예시 칩 ──────────────────────────────────────────────────────────────────
const EXAMPLE_CHIPS: { label: string; prompt: string; write?: boolean }[] = [
  { label: "상품 목록 보여줘",       prompt: "상품 목록을 보여줘" },
  { label: "주문 확인해줘",           prompt: "최근 주문 목록을 확인해줘" },
  { label: "정산 조회해줘",           prompt: "정산 내역을 조회해줘" },
  { label: "리뷰 확인해줘",           prompt: "최근 리뷰와 문의를 확인해줘" },
  { label: "상품 수집해줘",           prompt: "CDP로 상품 목록을 실시간 수집해줘" },
  { label: "셀러센터 열어줘",         prompt: "셀러센터 상품 목록 페이지를 열어줘" },
];

// ── 도구 이름 한글 레이블 ────────────────────────────────────────────────────
const TOOL_LABEL: Record<string, string> = {
  list_products:   "상품 목록 조회",
  list_orders:     "주문 목록 조회",
  list_reviews:    "리뷰/문의 조회",
  list_settlements:"정산 내역 조회",
  register_product:"상품 등록",
  edit_product:    "상품 수정",
  open_seller_center: "셀러센터 이동",
};

// ── 로그 아이템 타입 ─────────────────────────────────────────────────────────
type LogItem =
  | { kind: "text";    text: string }
  | { kind: "step";    step: number; tool: string; write: boolean; status: "running" | "ok" | "fail"; detail?: string }
  | { kind: "confirm"; tool: string; inputs: Record<string, unknown>; message: string }
  | { kind: "done";    steps: number }
  | { kind: "error";   message: string };

export default function AgentCommandBar() {
  const [input, setInput]     = useState("");
  const [running, setRunning] = useState(false);
  const [logs, setLogs]       = useState<LogItem[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<{
    tool: string; inputs: Record<string, unknown>; message: string; prompt: string;
  } | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const pushLog = useCallback((item: LogItem) => {
    setLogs((prev) => [...prev, item]);
  }, []);

  const updateLastStep = useCallback((step: number, status: "ok" | "fail", detail?: string) => {
    setLogs((prev) => prev.map((l) =>
      l.kind === "step" && l.step === step ? { ...l, status, detail } : l
    ));
  }, []);

  const execute = useCallback(async (prompt: string, confirmed: boolean) => {
    if (!prompt.trim()) return;
    abortRef.current = new AbortController();
    setRunning(true);
    setPendingConfirm(null);
    if (!confirmed) setLogs([]);

    try {
      await runSmartStoreAgent(
        prompt,
        confirmed,
        (e: AgentSSEEvent) => {
          if (e.event === "text") {
            pushLog({ kind: "text", text: e.data.text });
          } else if (e.event === "step_start") {
            pushLog({ kind: "step", step: e.data.step, tool: e.data.tool, write: e.data.write, status: "running" });
          } else if (e.event === "step_done") {
            updateLastStep(e.data.step, e.data.ok ? "ok" : "fail",
              !e.data.ok ? (e.data.result?.error as string | undefined) : undefined);
          } else if (e.event === "confirm_required") {
            setPendingConfirm({ tool: e.data.tool, inputs: e.data.inputs, message: e.data.message, prompt });
            pushLog({ kind: "confirm", tool: e.data.tool, inputs: e.data.inputs, message: e.data.message });
          } else if (e.event === "done") {
            pushLog({ kind: "done", steps: e.data.steps });
          } else if (e.event === "error") {
            pushLog({ kind: "error", message: e.data.message });
          }
        },
        abortRef.current.signal,
      );
    } catch (err: unknown) {
      if (err instanceof Error && err.name !== "AbortError") {
        pushLog({ kind: "error", message: String(err) });
      }
    } finally {
      setRunning(false);
    }
  }, [pushLog, updateLastStep]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    execute(input, false);
  }

  function handleChip(prompt: string) {
    setInput(prompt);
    execute(prompt, false);
  }

  function handleConfirm() {
    if (!pendingConfirm) return;
    execute(pendingConfirm.prompt, true);
  }

  function handleCancel() {
    abortRef.current?.abort();
    setPendingConfirm(null);
    setRunning(false);
  }

  return (
    <div className="border border-[#E5E7EB] rounded-2xl bg-white overflow-hidden mb-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
        <span className="text-sm font-bold text-[#111827]">AI 명령</span>
        <span className="text-xs text-[#9CA3AF]">자연어로 스마트스토어를 제어하세요</span>
        {running && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-[#F97316] font-semibold">
            <span className="inline-block w-2 h-2 rounded-full bg-[#F97316] animate-pulse" />
            실행 중
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {/* 예시 칩 */}
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_CHIPS.map((c) => (
            <button
              key={c.prompt}
              onClick={() => handleChip(c.prompt)}
              disabled={running}
              className="text-xs px-3 py-1.5 rounded-full border border-[#E5E7EB] text-[#374151] bg-white hover:bg-[#F3F4F6] hover:border-[#D1D5DB] disabled:opacity-40 transition-colors"
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* 입력창 */}
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="예: 무드등 29800원 재고 50개로 등록해줘"
            disabled={running}
            className="flex-1 border border-[#E5E7EB] rounded-xl px-4 py-2.5 text-sm text-[#111827] placeholder:text-[#9CA3AF] focus:outline-none focus:ring-2 focus:ring-[#F97316]/30 focus:border-[#F97316] disabled:opacity-50 transition-all"
          />
          <button
            type="submit"
            disabled={running || !input.trim()}
            className="px-4 py-2.5 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] disabled:opacity-40 transition-colors shrink-0"
          >
            {running ? "…" : "실행"}
          </button>
          {running && (
            <button
              type="button"
              onClick={handleCancel}
              className="px-3 py-2.5 rounded-xl border border-[#E5E7EB] text-xs text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
            >
              중단
            </button>
          )}
        </form>

        {/* 진행 로그 */}
        {logs.length > 0 && (
          <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
            <div className="px-3 py-2 bg-[#F9FAFB] border-b border-[#E5E7EB] flex items-center justify-between">
              <span className="text-xs font-semibold text-[#6B7280] uppercase tracking-wide">진행 로그</span>
              <button
                onClick={() => { setLogs([]); setPendingConfirm(null); }}
                disabled={running}
                className="text-xs text-[#9CA3AF] hover:text-[#6B7280] disabled:opacity-40"
              >
                지우기
              </button>
            </div>
            <div className="max-h-64 overflow-y-auto p-3 space-y-2">
              {logs.map((log, i) => (
                <LogRow key={i} log={log} />
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {/* 승인 다이얼로그 */}
        {pendingConfirm && !running && (
          <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4 space-y-3">
            <div>
              <p className="text-sm font-semibold text-[#C2410C]">작업 승인 필요</p>
              <p className="text-xs text-[#92400E] mt-1">{pendingConfirm.message}</p>
            </div>
            <div className="bg-white border border-[#FED7AA] rounded-lg p-3 space-y-1">
              <p className="text-xs font-semibold text-[#6B7280] mb-1">실행 내용</p>
              {Object.entries(pendingConfirm.inputs).map(([k, v]) => (
                <div key={k} className="flex gap-3 text-xs">
                  <span className="font-mono text-[#92400E] w-20 shrink-0">{k}</span>
                  <span className="text-[#111827]">{String(v)}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleConfirm}
                className="flex-1 py-2 rounded-xl bg-[#F97316] text-white text-sm font-semibold hover:bg-[#EA580C] transition-colors"
              >
                승인하고 실행
              </button>
              <button
                onClick={() => setPendingConfirm(null)}
                className="flex-1 py-2 rounded-xl border border-[#E5E7EB] text-sm text-[#6B7280] hover:bg-[#F9FAFB] transition-colors"
              >
                취소
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function LogRow({ log }: { log: LogItem }) {
  if (log.kind === "text") {
    return (
      <p className="text-xs text-[#374151] leading-relaxed">{log.text}</p>
    );
  }

  if (log.kind === "step") {
    const statusIcon =
      log.status === "running" ? <span className="inline-block w-3 h-3 rounded-full bg-[#F97316] animate-pulse" /> :
      log.status === "ok"      ? <span className="text-[#16A34A] font-bold">✓</span> :
                                 <span className="text-[#DC2626] font-bold">✗</span>;
    return (
      <div className="flex items-center gap-2 text-xs">
        <span className="w-5 h-5 rounded-full bg-[#F3F4F6] border border-[#E5E7EB] flex items-center justify-center text-[10px] font-bold text-[#6B7280] shrink-0">
          {log.step}
        </span>
        {statusIcon}
        <span className={`font-medium ${log.write ? "text-[#C2410C]" : "text-[#1D4ED8]"}`}>
          {TOOL_LABEL[log.tool] ?? log.tool}
        </span>
        {log.write && (
          <span className="text-[10px] bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded font-semibold">쓰기</span>
        )}
        {log.detail && (
          <span className="text-[#DC2626] truncate">{log.detail}</span>
        )}
      </div>
    );
  }

  if (log.kind === "confirm") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#C2410C]">
        <span>⚠</span>
        <span>{log.message}</span>
      </div>
    );
  }

  if (log.kind === "done") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#16A34A] font-semibold">
        <span>✓</span>
        <span>완료 — {log.steps}단계 처리됨</span>
      </div>
    );
  }

  if (log.kind === "error") {
    return (
      <div className="flex items-center gap-2 text-xs text-[#DC2626]">
        <span>✗</span>
        <span>{log.message}</span>
      </div>
    );
  }

  return null;
}
