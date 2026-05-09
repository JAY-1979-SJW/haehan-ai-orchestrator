"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  PageShell,
  Btn,
  KpiCard,
  StatusBadge,
  AdminTable,
  AdminThead,
  AdminTbody,
  AdminTr,
  AdminTh,
  AdminTd,
  EmptyRow,
  Modal,
} from "@/components/ui";
import {
  getLocalAgents,
  getAgentTasks,
  submitTask,
  chatWithCad,
  ApiError,
} from "@/lib/api";
import type { LocalAgent, LocalAgentTask } from "@/types/local-agent";
import type { CadChatResponse } from "@/lib/api";

// ── CAD 퀵 액션 (실제 action_registry 이름과 일치) ────────────────────────────

interface CadAction {
  action: string;
  label: string;
  description: string;
  icon: string;
}

const QUICK_ACTIONS: CadAction[] = [
  { action: "detect_cad_apps",   label: "AutoCAD 감지",     description: "현재 열린 AutoCAD 프로세스를 찾습니다",       icon: "🔍" },
  { action: "search_drawings",   label: "도면 목록",         description: "열려있는 도면 파일 목록을 조회합니다",         icon: "📄" },
  { action: "read_layers",       label: "레이어 목록",       description: "도면의 전체 레이어 목록과 색상을 가져옵니다",   icon: "📋" },
  { action: "read_entities",     label: "엔티티 통계",       description: "엔티티 유형별 개수를 집계합니다",             icon: "📊" },
  { action: "read_texts",        label: "텍스트 조회",       description: "모든 TEXT/MTEXT 내용을 읽어옵니다",           icon: "📝" },
  { action: "read_blocks",       label: "블록 목록",         description: "삽입된 블록 참조(INSERT) 목록을 가져옵니다",   icon: "🧩" },
  { action: "read_dimensions",   label: "치수 목록",         description: "치수(DIMENSION) 엔티티를 조회합니다",         icon: "📐" },
  { action: "read_geometry",     label: "선/원 조회",        description: "LINE·ARC·CIRCLE 좌표와 길이를 조회합니다",    icon: "📏" },
  { action: "read_modelspace",   label: "모델스페이스",      description: "모델스페이스 전체 구조를 요약합니다",          icon: "🗺️" },
  { action: "cad_inventory_collect", label: "전체 수집",     description: "레이어·블록·텍스트·엔티티를 한 번에 수집합니다", icon: "🗄️" },
];

const ALL_CAD_ACTIONS = new Set(QUICK_ACTIONS.map((a) => a.action));

// ── 채팅 메시지 타입 ───────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  action?: string | null;
  taskId?: string | null;
  taskStatus?: string | null;
  aiUsed?: boolean;
  ts: Date;
}

// ── 유틸 ──────────────────────────────────────────────────────────────────────

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function agentShort(id: string) {
  return id.slice(-8);
}

let _msgId = 0;
function nextId() { return String(++_msgId); }

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export default function CadClient() {
  // ── 에이전트 / 태스크 상태 ──
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [tasks, setTasks] = useState<LocalAgentTask[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);

  // ── 채팅 상태 ──
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "0",
      role: "assistant",
      content: "안녕하세요! AutoCAD 도면 AI 직원입니다. 에이전트를 선택하고 궁금한 내용을 자유롭게 질문해주세요.\n예) \"현재 도면의 레이어 목록을 보여줘\"",
      ts: new Date(),
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ── 퀵액션 / 기타 ──
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultTask, setResultTask] = useState<LocalAgentTask | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── 에이전트 로드 ──
  const loadAgents = useCallback(async () => {
    try {
      const { agents: all } = await getLocalAgents();
      setAgents(all);
      if (!selectedAgent && all.length > 0) {
        const online = all.find((a) => a.agent_status === "idle" || a.agent_status === "busy");
        setSelectedAgent(online?.agent_id ?? all[0].agent_id);
      }
    } catch { /* 무시 */ } finally {
      setLoadingAgents(false);
    }
  }, [selectedAgent]);

  // ── 태스크 로드 ──
  const loadTasks = useCallback(async () => {
    if (!selectedAgent) return;
    try {
      const resp = await getAgentTasks(selectedAgent, { limit: 30 });
      setTasks(resp.tasks.filter((t) => ALL_CAD_ACTIONS.has(t.action)));
    } catch { /* 무시 */ }
  }, [selectedAgent]);

  // ── 폴링 ──
  useEffect(() => {
    loadAgents();
    loadTasks();
    pollRef.current = setInterval(() => { loadAgents(); loadTasks(); }, 10_000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadAgents, loadTasks]);

  // ── 채팅 스크롤 ──
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── 채팅 전송 ──
  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text || chatLoading) return;
    if (!selectedAgent) { setError("에이전트를 먼저 선택하세요."); return; }

    const userMsg: ChatMessage = { id: nextId(), role: "user", content: text, ts: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);
    setError(null);

    try {
      const history = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const resp: CadChatResponse = await chatWithCad({ agent_id: selectedAgent, message: text, conversation: history });

      const aiMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: resp.reply,
        action: resp.action,
        taskId: resp.task_id,
        taskStatus: resp.task_status,
        aiUsed: resp.ai_used,
        ts: new Date(),
      };
      setMessages((prev) => [...prev, aiMsg]);
      if (resp.task_id) await loadTasks();
    } catch (e) {
      const detail = e instanceof ApiError ? JSON.stringify(e.detail) : String(e);
      const errMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: `오류가 발생했습니다: ${detail}`,
        ts: new Date(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setChatLoading(false);
    }
  };

  // ── 퀵 액션 실행 ──
  const runQuickAction = async (qa: CadAction) => {
    if (!selectedAgent) { setError("에이전트를 먼저 선택하세요."); return; }
    setError(null);
    setSubmitting(true);
    const userMsg: ChatMessage = { id: nextId(), role: "user", content: `[퀵액션] ${qa.label}`, ts: new Date() };
    setMessages((prev) => [...prev, userMsg]);
    try {
      const t = await submitTask(selectedAgent, { action: qa.action, params: {} });
      const aiMsg: ChatMessage = {
        id: nextId(),
        role: "assistant",
        content: `${qa.label} 태스크를 등록했습니다. (task: ${t.task_id?.slice(-8)}, 상태: ${t.status})`,
        action: qa.action,
        taskId: t.task_id,
        taskStatus: t.status,
        ts: new Date(),
      };
      setMessages((prev) => [...prev, aiMsg]);
      await loadTasks();
    } catch (e) {
      const msg = e instanceof ApiError ? JSON.stringify(e.detail) : String(e);
      setError(`실행 실패: ${msg}`);
    } finally {
      setSubmitting(false);
    }
  };

  // ── KPI ──
  const onlineCount = agents.filter((a) => a.agent_status === "idle" || a.agent_status === "busy").length;
  const doneCount   = tasks.filter((t) => t.status === "completed").length;
  const failCount   = tasks.filter((t) => t.status === "failed" || t.status === "rejected").length;
  const runCount    = tasks.filter((t) => t.status === "running" || t.status === "queued").length;

  const selectedAgentObj = agents.find((a) => a.agent_id === selectedAgent);

  return (
    <PageShell
      title="AI CAD 워크스페이스"
      description="자연어로 AutoCAD를 제어하세요"
      headerRight={<span className="text-[11px] text-[#9CA3AF]">10초 자동 갱신</span>}
    >
      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <KpiCard title="온라인 에이전트" value={onlineCount} />
        <KpiCard title="실행 중" value={runCount} />
        <KpiCard title="완료" value={doneCount} accentColor="#22c55e" />
        <KpiCard title="실패" value={failCount} accentColor={failCount > 0 ? "#EF4444" : "#F97316"} />
      </div>

      <div className="flex flex-col lg:flex-row gap-5">
        {/* ── 왼쪽 사이드바 ── */}
        <div className="flex flex-col gap-4 w-full lg:w-[260px] shrink-0">

          {/* 에이전트 선택 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-4">
            <h2 className="text-[12px] font-bold text-[#0F172A] mb-3">에이전트</h2>
            {loadingAgents ? (
              <p className="text-[11px] text-[#9CA3AF]">로딩 중...</p>
            ) : agents.length === 0 ? (
              <p className="text-[11px] text-[#9CA3AF]">등록된 에이전트 없음</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                {agents.map((a) => {
                  const isSelected = a.agent_id === selectedAgent;
                  const online = a.agent_status === "idle" || a.agent_status === "busy";
                  return (
                    <button
                      key={a.agent_id}
                      onClick={() => setSelectedAgent(a.agent_id)}
                      className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-left transition-colors"
                      style={{
                        background: isSelected ? "#FFF7ED" : "#F9FAFB",
                        border: isSelected ? "1.5px solid #F97316" : "1px solid #E5E7EB",
                      }}
                    >
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: online ? "#22c55e" : "#9CA3AF" }} />
                      <div className="min-w-0 flex-1">
                        <div className="text-[12px] font-semibold text-[#0F172A] truncate">{a.host}</div>
                        <div className="text-[10px] text-[#9CA3AF] font-mono">…{agentShort(a.agent_id)}</div>
                      </div>
                      <StatusBadge status={a.agent_status} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* 퀵 액션 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-4">
            <h2 className="text-[12px] font-bold text-[#0F172A] mb-3">빠른 실행</h2>
            <div className="flex flex-col gap-1.5">
              {QUICK_ACTIONS.map((qa) => (
                <button
                  key={qa.action}
                  onClick={() => runQuickAction(qa)}
                  disabled={submitting || !selectedAgent}
                  title={qa.description}
                  className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-left text-[12px] transition-colors hover:bg-[#FFF7ED] disabled:opacity-40"
                  style={{ border: "1px solid #E5E7EB" }}
                >
                  <span className="shrink-0">{qa.icon}</span>
                  <div className="min-w-0">
                    <div className="font-medium text-[#0F172A]">{qa.label}</div>
                    <div className="text-[10px] text-[#9CA3AF] truncate">{qa.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── 오른쪽: 채팅 + 이력 ── */}
        <div className="flex flex-col gap-4 flex-1 min-w-0">

          {/* 오류 배너 */}
          {error && (
            <div className="rounded-[8px] px-4 py-3 text-[12px]"
              style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B" }}>
              {error}
              <button className="ml-3 underline text-[11px]" onClick={() => setError(null)}>닫기</button>
            </div>
          )}

          {/* 선택 에이전트 정보 */}
          {selectedAgentObj && (
            <div className="rounded-[12px] bg-white border border-[#E5E7EB] px-5 py-3 flex flex-wrap gap-4 text-[12px]">
              <div><span className="text-[#9CA3AF] mr-1">호스트</span><span className="font-semibold">{selectedAgentObj.host}</span></div>
              <div><span className="text-[#9CA3AF] mr-1">OS</span><span>{selectedAgentObj.os_name}</span></div>
              <div><span className="text-[#9CA3AF] mr-1">ID</span><span className="font-mono text-[#6B7280]">…{agentShort(selectedAgentObj.agent_id)}</span></div>
              <div><span className="text-[#9CA3AF] mr-1">상태</span><StatusBadge status={selectedAgentObj.agent_status} /></div>
              <div><span className="text-[#9CA3AF] mr-1">응답</span><span>{fmtTime(selectedAgentObj.last_seen_at)}</span></div>
            </div>
          )}

          {/* ── AI 채팅 패널 ── */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] flex flex-col overflow-hidden"
            style={{ minHeight: 420, borderTop: "3px solid #F97316" }}>
            {/* 헤더 */}
            <div className="px-5 py-3 border-b border-[#F3F4F6] flex items-center gap-2 shrink-0">
              <span className="text-[12px] font-bold text-[#0F172A]">AI CAD 직원</span>
              <span className="text-[10px] text-[#9CA3AF]">자연어로 도면을 조회하세요</span>
              <button
                className="ml-auto text-[11px] text-[#9CA3AF] underline"
                onClick={() => setShowHistory(!showHistory)}
              >
                {showHistory ? "채팅 보기" : "태스크 이력"}
              </button>
            </div>

            {!showHistory ? (
              <>
                {/* 채팅 메시지 목록 */}
                <div className="flex-1 overflow-auto px-5 py-4 flex flex-col gap-3">
                  {messages.map((m) => (
                    <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div
                        className="max-w-[80%] rounded-[10px] px-4 py-2.5 text-[12px] leading-relaxed"
                        style={
                          m.role === "user"
                            ? { background: "#F97316", color: "white" }
                            : { background: "#F9FAFB", border: "1px solid #E5E7EB", color: "#374151" }
                        }
                      >
                        <p className="whitespace-pre-wrap">{m.content}</p>
                        {m.action && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono"
                              style={{ background: "#EFF6FF", color: "#1D4ED8" }}>
                              ▶ {m.action}
                            </span>
                            {m.taskId && (
                              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-mono"
                                style={{ background: "#F3F4F6", color: "#6B7280" }}>
                                task: …{m.taskId.slice(-8)}
                              </span>
                            )}
                            {m.taskStatus && <StatusBadge status={m.taskStatus} />}
                            {m.aiUsed !== undefined && (
                              <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px]"
                                style={{ background: m.aiUsed ? "#ECFDF5" : "#F3F4F6", color: m.aiUsed ? "#059669" : "#9CA3AF" }}>
                                {m.aiUsed ? "GPT" : "MOCK"}
                              </span>
                            )}
                          </div>
                        )}
                        <p className="mt-1 text-[10px] opacity-50">{m.ts.toLocaleTimeString("ko-KR")}</p>
                      </div>
                    </div>
                  ))}
                  {chatLoading && (
                    <div className="flex justify-start">
                      <div className="rounded-[10px] px-4 py-2.5 text-[12px]"
                        style={{ background: "#F9FAFB", border: "1px solid #E5E7EB", color: "#9CA3AF" }}>
                        AI가 분석 중...
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* 입력창 */}
                <div className="shrink-0 px-5 py-3 border-t border-[#F3F4F6] flex gap-2">
                  <input
                    className="flex-1 rounded-[8px] px-4 py-2 text-[13px]"
                    style={{ border: "1px solid #D1D5DB", outline: "none" }}
                    placeholder={selectedAgent ? "예) 레이어 목록을 보여줘" : "에이전트를 선택해주세요"}
                    value={chatInput}
                    disabled={!selectedAgent || chatLoading}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
                  />
                  <Btn
                    variant="orange"
                    size="sm"
                    onClick={sendChat}
                    disabled={!selectedAgent || chatLoading || !chatInput.trim()}
                  >
                    전송
                  </Btn>
                </div>
              </>
            ) : (
              /* 태스크 이력 */
              <div className="flex-1 overflow-auto">
                <AdminTable>
                  <AdminThead>
                    <AdminTr>
                      <AdminTh>액션</AdminTh>
                      <AdminTh>상태</AdminTh>
                      <AdminTh>생성</AdminTh>
                      <AdminTh>결과</AdminTh>
                    </AdminTr>
                  </AdminThead>
                  <AdminTbody>
                    {tasks.length === 0 ? (
                      <EmptyRow colSpan={4} message="CAD 태스크가 없습니다" />
                    ) : (
                      tasks.map((t) => (
                        <AdminTr key={t.task_id}>
                          <AdminTd><span className="font-mono text-[11px]">{t.action}</span></AdminTd>
                          <AdminTd><StatusBadge status={t.status} /></AdminTd>
                          <AdminTd>{fmtTime(t.created_at)}</AdminTd>
                          <AdminTd>
                            {t.result_summary ? (
                              <button className="text-[11px] text-[#F97316] underline" onClick={() => setResultTask(t)}>
                                보기
                              </button>
                            ) : t.failure_reason ? (
                              <span className="text-[11px] text-red-400 truncate max-w-[120px] inline-block">{t.failure_reason}</span>
                            ) : (
                              <span className="text-[11px] text-[#9CA3AF]">-</span>
                            )}
                          </AdminTd>
                        </AdminTr>
                      ))
                    )}
                  </AdminTbody>
                </AdminTable>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 결과 상세 모달 */}
      {resultTask && (
        <Modal
          open={!!resultTask}
          title={`결과 — ${resultTask.action}`}
          onClose={() => setResultTask(null)}
        >
          <div className="flex flex-col gap-3 text-[12px]">
            <div className="grid grid-cols-2 gap-2">
              <div><span className="text-[#9CA3AF]">태스크 ID</span><p className="font-mono text-[11px] break-all">{resultTask.task_id}</p></div>
              <div><span className="text-[#9CA3AF]">상태</span><p className="mt-0.5"><StatusBadge status={resultTask.status} /></p></div>
              <div><span className="text-[#9CA3AF]">생성</span><p>{fmtTime(resultTask.created_at)}</p></div>
              <div><span className="text-[#9CA3AF]">완료</span><p>{fmtTime(resultTask.completed_at)}</p></div>
            </div>
            {resultTask.result_summary && (
              <div>
                <span className="text-[#9CA3AF] block mb-1">결과</span>
                <pre className="text-[11px] whitespace-pre-wrap break-all overflow-auto max-h-[400px] rounded-[6px] p-3"
                  style={{ background: "#F9FAFB", border: "1px solid #F3F4F6" }}>
                  {resultTask.result_summary}
                </pre>
              </div>
            )}
            {resultTask.failure_reason && (
              <div><span className="text-[#9CA3AF] block mb-1">오류</span><p className="text-red-500">{resultTask.failure_reason}</p></div>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  );
}
