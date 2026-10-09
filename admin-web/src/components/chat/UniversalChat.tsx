"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { EMPLOYEE_PROTOCOL } from "./employeeProtocol";
import { FaxApprovalCard } from "./FaxApprovalCard";
import { MAIL_DRAFT_CARDS } from "./mailDraftCards";
import { SITE_MAP_EXPLORE_CARDS } from "./siteMapCards";

/**
 * 답변 속 "[[종류:<id>]]" 표시를 카드(버튼)로 바꿔 보여 주는 규칙 — 화면(메일함 등)이 주입한다.
 * 공용 채팅이 각 화면의 카드를 직접 import 하면 화면↔채팅 순환이 생기므로 의존을 뒤집었다.
 */
export interface ExtraCard {
  /** `/g` 정규식. 첫 번째 캡처 그룹이 카드에 넘길 id 다. */
  mark: RegExp;
  render: (id: string) => ReactNode;
}

/** 입력창에 채워 주는 지시 단축 칩 — 누르면 입력창에 문장이 들어가고 사용자가 고쳐서 보낸다. */
export interface ChatPreset {
  label: string;
  prompt: string;
}

interface Props {
  /** 입력창 위에 보일 지시 칩(선택) */
  presets?: ChatPreset[];
  /** 화면이 주입하는 추가 카드 규칙(선택) — 예: 메일함의 [[mail-draft:<id>]] */
  extraCards?: ExtraCard[];
  domain?: string;
  /** 에이전트에 보내는 프롬프트 앞에 붙이는 지침(화면에 보이는 메시지는 그대로). 화면별 사용법 안내용. */
  agentHint?: string;
  title?: string;
  className?: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status: "pending" | "done" | "error";
  claudeSessionId?: string;
}

interface ChatSessionSummary {
  chat_id: string;
  title: string;
  model: string;
  updated_at: string;
  message_count: number;
}

const POLL_FAST_MS = 700; // 처음 20초는 촘촘히 — 짧은 질문의 완료 감지 지연을 줄인다
const POLL_FAST_WINDOW_MS = 20_000;
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 300_000; // 5분(백엔드 기본 timeout=300s와 정합) — 간격이 달라도 총 대기 시간은 시각으로 계산
const MODEL_LABELS: Record<string, string> = {
  "": "기본",
  sonnet: "Sonnet",
  opus: "Opus",
  haiku: "Haiku (빠름)",
  fable: "Fable",
};

interface TaskStatusResponse {
  status: string;
  result_data?: { result?: string; result_full?: string; session_id?: string } | null;
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

const FAX_APPROVE_MARK = /\[\[fax-approve:([0-9a-f]{32})\]\]/g;

/**
 * 답변 본문. "[[fax-approve:<id>]]" 는 팩스 승인 카드로, 화면이 주입한 규칙(`extraCards`, 예: "[[mail-draft:<id>]]" 메일 발송 승인 카드)은
 * 그 카드로 바꿔 보여 준다. 보내기는 카드 버튼(사람)으로만 된다 — AI 는 승인·발송 API 를 쓸 수 없다.
 */
function MessageBody({ text, extraCards = [] }: { text: string; extraCards?: ExtraCard[] }) {
  const faxIds = [...text.matchAll(FAX_APPROVE_MARK)].map((m) => m[1]);
  // 모든 창이 기본으로 처리하는 카드(메일 초안·사이트 탐색 승인) + 화면이 주입한 카드. 같은 규칙은 한 번만 쓴다(카드가 두 번 그려지지 않게).
  const cards = [...MAIL_DRAFT_CARDS, ...SITE_MAP_EXPLORE_CARDS, ...extraCards].filter(
    (c, i, all) => all.findIndex((o) => o.mark.source === c.mark.source) === i,
  );
  const extras = cards.map((c) => ({ card: c, ids: [...new Set([...text.matchAll(c.mark)].map((m) => m[1]))] }));
  if (faxIds.length === 0 && extras.every((e) => e.ids.length === 0)) return <>{text}</>;
  const cleaned = extras.reduce((acc, e) => acc.replace(e.card.mark, ""), text.replace(FAX_APPROVE_MARK, "")).trim();
  return (
    <>
      {cleaned}
      {[...new Set(faxIds)].map((id) => (
        <FaxApprovalCard key={id} authId={id} />
      ))}
      {extras.flatMap((e) => e.ids.map((id) => <span key={`${e.card.mark.source}:${id}`}>{e.card.render(id)}</span>))}
    </>
  );
}

function errorMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = (await res.json()) as T & { ok?: boolean; detail?: string | { message?: string } };
  if (!res.ok || data.ok === false) {
    const detail = typeof data.detail === "string" ? data.detail : data.detail?.message;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
}

/**
 * 앱 내 AI 채팅.
 *
 * 2026-09-30: 사용자 지시 "답변이 너무 느려 / 모델 선택 가능하게 / 이전 대화기록을 저장해서
 * 볼수 있게"로 3가지를 추가:
 *  - 모델 선택: 드롭다운 → POST /ai-agent/run 의 model 파라미터로 공식 --model 전달.
 *  - 대화기록 저장: /chat/sessions* (ai_orchestrator/tasks/chat_sessions.py, 신규) — 세션 목록/전환/삭제.
 *  - 속도: 같은 채팅의 다음 메시지부터 claude_session_id로 --resume 재사용(서버가 chat_id로
 *    자동 처리) → 시스템 프롬프트/CLAUDE.md 재렌더링 생략(공식 --system-prompt-snapshot 근거),
 *    실측상 냉간시작 대비 후속 메시지가 더 빠르다. 첫 메시지 자체의 지연(claude -p 프로세스
 *    기동 ~5초 + 모델 응답 ~2~4초)은 CLI 아키텍처상 이 세션에서 근본 해결하지 않음 — 다음
 *    세션 후보(상시 세션 프로세스 등)로 남김, 사용자에게 투명하게 설명.
 *
 * 경로: 이 컴포넌트 → POST /api/v1/ai-agent/run(로컬 에이전트 자동 선택) → 기존
 * local_agent_registry 작업 큐 → core/agent_runtime/agent.py(WS 상시 클라이언트) → 헤드리스
 * `claude -p --mcp-config .mcp.json` → 이 앱 자신의 MCP 서버(haehan-orchestrator) 호출.
 * 설계·실측 검증: docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md
 */
export function UniversalChat({ title, agentHint, presets, extraCards, className = "" }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [agentUnavailable, setAgentUnavailable] = useState(false);
  const [chatId, setChatId] = useState<string>("");
  const [model, setModel] = useState<string>("");
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  const refreshSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/proxy/api/v1/chat/sessions");
      const data = await res.json();
      if (res.ok && data.ok) setSessions(data.sessions ?? []);
    } catch {
      // 목록 조회 실패는 조용히 무시 — 새 대화 자체는 계속 가능해야 함
    }
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  async function loadSession(id: string) {
    try {
      const res = await fetch(`/api/proxy/api/v1/chat/sessions/${id}`);
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error("불러오기 실패");
      const s = data.session;
      setChatId(s.chat_id);
      setModel(s.model || "");
      setMessages(
        (s.messages as { role: "user" | "assistant"; text: string }[]).map((m, i) => ({
          id: `${s.chat_id}-${i}`,
          role: m.role,
          text: m.text,
          status: "done" as const,
        })),
      );
      setShowHistory(false);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, role: "assistant", text: `대화 불러오기 실패: ${errorMessage(e)}`, status: "error" },
      ]);
    }
  }

  function startNewChat() {
    setChatId("");
    setMessages([]);
    setShowHistory(false);
  }

  async function pollTask(agentId: string, taskId: string, assistantId: string, activeChatId: string) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
      const elapsed = Date.now() - startedAt;
      await new Promise((r) => setTimeout(r, elapsed < POLL_FAST_WINDOW_MS ? POLL_FAST_MS : POLL_INTERVAL_MS));
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
        // result 는 서버 필터가 500자로 자르므로, 전문이 담긴 result_full 을 먼저 쓴다.
        // 빈 문자열은 `??` 가 폴백하지 않아 빈 말풍선이 되므로 `||` 로 다음 후보로 넘긴다.
        const resultText = data.result_data?.result_full || data.result_data?.result || data.result_summary || "(결과 없음)";
        const claudeSessionId = data.result_data?.session_id ?? "";
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: String(resultText), status: "done" } : m)),
        );
        // 대화기록 저장 — assistant 응답 + 다음 메시지의 --resume용 claude_session_id 갱신
        postJson(`/api/proxy/api/v1/chat/sessions/${activeChatId}/messages`, {
          role: "assistant",
          text: String(resultText),
          task_id: taskId,
          claude_session_id: claudeSessionId,
        }).then(refreshSessions).catch(() => {});
        return;
      }
      if (data.status === "failed" || data.status === "timed_out" || data.status === "cancelled") {
        const reason = data.failure_reason || data.error_summary || data.status;
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, text: `작업 실패: ${reason}`, status: "error" } : m)),
        );
        return;
      }
      // queued/delivered/running 이면 계속 폴링(짧은 재연결 등으로 인한 재시도는 서버가
      // 자동 처리 — 사용자에게는 계속 "처리 중"으로만 보인다)
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
      let activeChatId = chatId;
      if (!activeChatId) {
        const created = await postJson<{ session: { chat_id: string } }>("/api/proxy/api/v1/chat/sessions", {
          first_message: prompt,
          model,
        });
        activeChatId = created.session.chat_id;
        setChatId(activeChatId);
      }
      // 사용자 메시지 먼저 저장(응답이 실패하거나 앱이 닫혀도 질문 자체는 남도록)
      postJson(`/api/proxy/api/v1/chat/sessions/${activeChatId}/messages`, { role: "user", text: prompt }).catch(
        () => {},
      );

      const data = await postJson<RunAgentResponse>("/api/proxy/api/v1/ai-agent/run", {
        // 모든 AI 창 공통 직원 업무 원칙 → 창별 지침 → 사용자 요청 순서로 붙인다(기준서 2026-10-04_ai_employee.md)
        prompt: [EMPLOYEE_PROTOCOL, agentHint, `사용자 요청: ${prompt}`].filter(Boolean).join("\n\n"),
        chat_id: activeChatId,
        model,
      });
      await pollTask(data.agent_id, data.task_id, assistantId, activeChatId);
      refreshSessions();
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
      <div className="px-4 py-3 border-b border-[#F3F4F6] shrink-0 flex items-center justify-between gap-2">
        <p className="text-sm font-bold text-[#111827] truncate">{title ?? "AI 어시스턴트"}</p>
        <div className="flex items-center gap-1.5 shrink-0">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={sending}
            className="text-[10px] border border-[#E5E7EB] rounded-lg px-1.5 py-1 outline-none bg-white disabled:opacity-50"
            title="모델 선택"
          >
            {Object.entries(MODEL_LABELS).map(([value, label]) => (
              <option key={value || "default"} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="text-[10px] px-2 py-1 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"
          >
            기록
          </button>
          <button
            onClick={startNewChat}
            className="text-[10px] px-2 py-1 rounded-lg border border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"
          >
            새 대화
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="border-b border-[#F3F4F6] max-h-40 overflow-y-auto shrink-0">
          {sessions.length === 0 ? (
            <p className="text-[10px] text-[#9CA3AF] text-center py-3">저장된 대화가 없습니다</p>
          ) : (
            sessions.map((s) => (
              <button
                key={s.chat_id}
                onClick={() => loadSession(s.chat_id)}
                className={`w-full text-left px-4 py-2 text-[11px] hover:bg-[#F9FAFB] border-b border-[#F9FAFB] last:border-0 ${
                  s.chat_id === chatId ? "bg-[#FFF7ED]" : ""
                }`}
              >
                <span className="font-medium text-[#111827]">{s.title}</span>
                <span className="text-[#9CA3AF] ml-2">{s.message_count}개 메시지</span>
              </button>
            ))
          )}
        </div>
      )}

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
                <MessageBody text={m.text} extraCards={extraCards} />
              )}
            </div>
          </div>
        ))}
        {agentUnavailable && (
          <p className="text-[10px] text-amber-600 text-center px-2">
            로컬 에이전트 미연결 — <code>python -m core.agent_runtime.agent --run</code> 실행 필요
          </p>
        )}
      </div>

      {presets && presets.length > 0 && (
        <div className="shrink-0 border-t border-[#F3F4F6] px-2 pt-2 flex flex-wrap gap-1" aria-label="지시 단축 칩">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              disabled={sending}
              onClick={() => setInput(p.prompt)}
              title={p.prompt}
              className="text-[10px] px-2 py-1 rounded-full border border-[#E5E7EB] bg-[#F9FAFB] text-[#374151] hover:bg-[#FFF7ED] hover:border-[#FED7AA] disabled:opacity-40"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
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
