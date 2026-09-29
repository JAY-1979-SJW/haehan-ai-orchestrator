"use client";

import { useState, useRef, useEffect } from "react";

interface Props {
  domain?: string;
  title?: string;
  className?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status: "pending" | "done" | "error";
}

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 150; // 2s * 150 = 5분(백엔드 기본 timeout=300s와 정합)

interface TaskStatusResponse {
  status: string;
  result_data?: { result?: string } | null;
  result_summary?: string;
  failure_reason?: string;
  error_summary?: string;
  detail?: string | { message?: string };
}

interface RunAgentResponse {
  ok: boolean;
  agent_id: string;
  task_id: string;
  detail?: string | { message?: string };
}

function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

/**
 * 앱 내 AI 채팅 — 2026-09-29 재구현.
 *
 * 2026-09-24에는 "AI 작업은 Claude Code(MCP)로 합니다"라는 정적 안내만 표시하도록
 * 비워졌었다(개발자 자신의 Claude Code 세션을 쓰는 것을 전제). 오늘 사용자가 명시적으로
 * "앱 내부에 mcp를 연결해서 ai를 이용해서 작업이 되게 해줘"라고 요청 — 그 결정을 뒤집고
 * 실제 동작하는 입력창으로 되살린다.
 *
 * 경로: 이 컴포넌트 → POST /api/v1/ai-agent/run(신규 얇은 편의 엔드포인트, 로컬 에이전트
 * 자동 선택) → 기존 local_agent_registry 작업 큐 → local_agent/agent.py(WS 상시 클라이언트,
 * 사람이 별도로 python -m local_agent.agent --run 으로 기동해둬야 함) → 헤드리스
 * `claude -p --mcp-config .mcp.json` → 이 앱 자신의 MCP 서버(haehan-orchestrator) 호출.
 * 설계·실측 검증: docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md
 *
 * 결과가 나올 때까지 GET /api/v1/local-agents/{agent_id}/tasks/{task_id} 를 폴링한다
 * (신규 폴링 엔드포인트 없음, 기존 것 재사용).
 */
export function UniversalChat({ title, className = "" }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [agentUnavailable, setAgentUnavailable] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  async function pollTask(agentId: string, taskId: string, assistantId: string) {
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      let data: TaskStatusResponse;
      try {
        const res = await fetch(`/api/proxy/api/v1/local-agents/${agentId}/tasks/${taskId}`);
        data = await res.json();
        if (!res.ok) {
          const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
          throw new Error(detail || `HTTP ${res.status}`);
        }
      } catch (e: unknown) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, text: `조회 실패: ${errorMessage(e)}`, status: "error" } : m,
          ),
        );
        return;
      }

      if (data.status === "completed") {
        const resultText =
          data.result_data?.result ?? data.result_summary ?? "(결과 없음)";
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: String(resultText), status: "done" } : m)),
        );
        return;
      }
      if (data.status === "failed" || data.status === "timed_out" || data.status === "cancelled") {
        const reason = data.failure_reason || data.error_summary || data.status;
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: `작업 실패: ${reason}`, status: "error" } : m)),
        );
        return;
      }
      // queued/delivered/running 이면 계속 폴링
    }
    setMessages((prev) =>
      prev.map((m) => (m.id === assistantId ? { ...m, text: "시간 초과 — 응답이 오래 걸리고 있습니다.", status: "error" } : m)),
    );
  }

  async function handleSend() {
    const prompt = input.trim();
    if (!prompt || sending) return;
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", text: prompt, status: "done" };
    const assistantId = `a-${Date.now()}`;
    const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", text: "처리 중...", status: "pending" };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    try {
      const res = await fetch("/api/proxy/api/v1/ai-agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data: RunAgentResponse = await res.json();
      if (!res.ok || data.ok === false) {
        const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
        throw new Error(detail || `HTTP ${res.status}`);
      }
      await pollTask(data.agent_id, data.task_id, assistantId);
    } catch (e: unknown) {
      const msg = errorMessage(e);
      if (msg.includes("로컬 에이전트가 없습니다")) setAgentUnavailable(true);
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, text: msg, status: "error" } : m)));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className={`flex flex-col bg-white border border-[#E5E7EB] rounded-2xl overflow-hidden ${className}`}>
      <div className="px-4 py-3 border-b border-[#F3F4F6] shrink-0">
        <p className="text-sm font-bold text-[#111827]">{title ?? "AI 어시스턴트"}</p>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
        {messages.length === 0 && (
          <p className="text-xs text-[#9CA3AF] text-center py-6">
            무엇을 도와드릴까요? 앱 데이터 조회·작업을 텍스트로 요청하세요.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-xs whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-[#F97316] text-white"
                  : m.status === "error"
                    ? "bg-red-50 text-red-700 border border-red-200"
                    : "bg-[#F3F4F6] text-[#111827]"
              }`}
            >
              {m.status === "pending" ? (
                <span className="inline-flex items-center gap-1">
                  <span className="animate-pulse">●</span> {m.text}
                </span>
              ) : (
                m.text
              )}
            </div>
          </div>
        ))}
        {agentUnavailable && (
          <p className="text-[10px] text-amber-600 text-center px-2">
            로컬 에이전트 미연결 — <code>python -m local_agent.agent --run</code> 실행 필요
          </p>
        )}
      </div>

      <div className="shrink-0 border-t border-[#F3F4F6] p-2 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="요청을 입력하세요..."
          disabled={sending}
          className="flex-1 text-xs border border-[#E5E7EB] rounded-lg px-3 py-2 outline-none focus:border-[#F97316] disabled:bg-[#F9FAFB]"
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="text-xs font-semibold px-3 py-2 rounded-lg bg-[#F97316] text-white disabled:opacity-40"
        >
          전송
        </button>
      </div>
    </div>
  );
}
