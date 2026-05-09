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
  ApiError,
} from "@/lib/api";
import type { LocalAgent, LocalAgentTask } from "@/types/local-agent";

// ── CAD 액션 정의 ──────────────────────────────────────────────────────────────

interface CadAction {
  action: string;
  label: string;
  description: string;
  params?: Record<string, unknown>;
  icon: string;
}

const QUICK_ACTIONS: CadAction[] = [
  {
    action: "DETECT_CAD_APPS",
    label: "AutoCAD 감지",
    description: "현재 열린 AutoCAD 프로세스를 모두 찾습니다",
    icon: "🔍",
  },
  {
    action: "GET_ACTIVE_DOCUMENT",
    label: "현재 도면 정보",
    description: "활성 도면의 파일명·경로·크기를 조회합니다",
    icon: "📄",
  },
  {
    action: "READ_LAYERS",
    label: "레이어 목록",
    description: "현재 도면의 전체 레이어 목록과 색상을 가져옵니다",
    icon: "📋",
  },
  {
    action: "READ_ENTITIES",
    label: "엔티티 통계",
    description: "도면 내 엔티티 유형별 개수를 집계합니다",
    icon: "📊",
  },
  {
    action: "READ_TEXT_ENTITIES",
    label: "텍스트 조회",
    description: "도면 내 모든 TEXT/MTEXT 내용을 읽어옵니다",
    icon: "📝",
  },
  {
    action: "READ_BLOCKS",
    label: "블록 목록",
    description: "삽입된 블록 참조(INSERT) 목록을 가져옵니다",
    icon: "🧩",
  },
  {
    action: "READ_DIMENSIONS",
    label: "치수 목록",
    description: "도면 내 치수(DIMENSION) 엔티티를 모두 조회합니다",
    icon: "📐",
  },
  {
    action: "READ_GEOMETRY",
    label: "선/원 조회",
    description: "LINE·ARC·CIRCLE 좌표와 길이를 조회합니다",
    icon: "📏",
  },
  {
    action: "CAD_INVENTORY_COLLECT_AND_PUSH",
    label: "전체 인벤토리 수집",
    description: "레이어·블록·텍스트·엔티티를 한 번에 수집해 서버로 전송합니다",
    icon: "🗄️",
  },
];

const ALL_ACTIONS = QUICK_ACTIONS.map((a) => a.action);

// ── 유틸 ──────────────────────────────────────────────────────────────────────

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function agentShort(id: string) {
  return id.slice(-8);
}

// ── 컴포넌트 ──────────────────────────────────────────────────────────────────

export default function CadClient() {
  // ── 상태 ──
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [tasks, setTasks] = useState<LocalAgentTask[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 커스텀 액션 패널
  const [customAction, setCustomAction] = useState("DETECT_CAD_APPS");
  const [customParams, setCustomParams] = useState("{}");
  const [paramsError, setParamsError] = useState<string | null>(null);

  // 결과 모달
  const [resultTask, setResultTask] = useState<LocalAgentTask | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── 에이전트 목록 로드 ──
  const loadAgents = useCallback(async () => {
    try {
      const { agents: all } = await getLocalAgents();
      // CAD 워커는 일반 로컬 에이전트와 동일 목록에서 필터 없이 전체 표시
      setAgents(all);
      if (!selectedAgent && all.length > 0) {
        const online = all.find((a) => a.agent_status === "idle" || a.agent_status === "busy");
        setSelectedAgent(online?.agent_id ?? all[0].agent_id);
      }
    } catch {
      // 무시 (백그라운드 갱신)
    } finally {
      setLoadingAgents(false);
    }
  }, [selectedAgent]);

  // ── 태스크 목록 로드 ──
  const loadTasks = useCallback(async () => {
    if (!selectedAgent) return;
    try {
      const resp = await getAgentTasks(selectedAgent, { limit: 30 });
      // CAD 관련 액션만 필터
      setTasks(
        resp.tasks.filter(
          (t) => ALL_ACTIONS.includes(t.action) || t.action.startsWith("CAD") || t.action.startsWith("READ") || t.action.startsWith("DETECT") || t.action.startsWith("GET")
        )
      );
    } catch {
      // 무시
    }
  }, [selectedAgent]);

  // ── 폴링 ──
  useEffect(() => {
    loadAgents();
    loadTasks();
    pollRef.current = setInterval(() => {
      loadAgents();
      loadTasks();
    }, 10_000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadAgents, loadTasks]);

  // ── 퀵 액션 실행 ──
  const runAction = async (action: CadAction) => {
    if (!selectedAgent) {
      setError("에이전트를 먼저 선택하세요.");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await submitTask(selectedAgent, { action: action.action, params: action.params ?? {} });
      await loadTasks();
    } catch (e) {
      const msg = e instanceof ApiError ? JSON.stringify(e.detail) : String(e);
      setError(`태스크 실행 실패: ${msg}`);
    } finally {
      setSubmitting(false);
    }
  };

  // ── 커스텀 액션 실행 ──
  const runCustom = async () => {
    if (!selectedAgent) { setError("에이전트를 먼저 선택하세요."); return; }
    let params: Record<string, unknown> = {};
    try {
      params = JSON.parse(customParams);
      setParamsError(null);
    } catch {
      setParamsError("params가 유효한 JSON이 아닙니다");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await submitTask(selectedAgent, { action: customAction, params });
      await loadTasks();
    } catch (e) {
      const msg = e instanceof ApiError ? JSON.stringify(e.detail) : String(e);
      setError(`태스크 실행 실패: ${msg}`);
    } finally {
      setSubmitting(false);
    }
  };

  // ── KPI ──
  const onlineCount = agents.filter((a) => a.agent_status === "idle" || a.agent_status === "busy").length;
  const doneCount = tasks.filter((t) => t.status === "completed").length;
  const failCount = tasks.filter((t) => t.status === "failed" || t.status === "rejected").length;
  const runCount = tasks.filter((t) => t.status === "running" || t.status === "queued").length;

  const selectedAgentObj = agents.find((a) => a.agent_id === selectedAgent);

  return (
    <PageShell
      title="AI CAD 워크스페이스"
      description="로컬 AutoCAD를 원격에서 조회·제어합니다"
      headerRight={
        <span className="text-[11px] text-[#6B7280]">
          10초마다 자동 갱신
        </span>
      }
    >
      {/* KPI */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <KpiCard title="온라인 에이전트" value={onlineCount} />
        <KpiCard title="실행 중" value={runCount} />
        <KpiCard title="완료" value={doneCount} />
        <KpiCard title="실패" value={failCount} accentColor={failCount > 0 ? "#EF4444" : "#F97316"} />
      </div>

      <div className="flex flex-col lg:flex-row gap-5">
        {/* ── 왼쪽: 에이전트 선택 + 퀵 액션 ── */}
        <div className="flex flex-col gap-4 w-full lg:w-[300px] shrink-0">

          {/* 에이전트 선택 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-4">
            <h2 className="text-[12px] font-bold text-[#0F172A] mb-3">에이전트 선택</h2>
            {loadingAgents ? (
              <p className="text-[12px] text-[#9CA3AF]">로딩 중...</p>
            ) : agents.length === 0 ? (
              <p className="text-[12px] text-[#9CA3AF]">등록된 에이전트 없음</p>
            ) : (
              <div className="flex flex-col gap-2">
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
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: online ? "#22c55e" : "#9CA3AF" }}
                      />
                      <div className="min-w-0">
                        <div className="text-[12px] font-semibold text-[#0F172A] truncate">
                          {a.host}
                        </div>
                        <div className="text-[10px] text-[#9CA3AF] font-mono">
                          …{agentShort(a.agent_id)}
                        </div>
                      </div>
                      <span className="ml-auto shrink-0">
                        <StatusBadge status={a.agent_status} />
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* 퀵 액션 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-4">
            <h2 className="text-[12px] font-bold text-[#0F172A] mb-3">빠른 실행</h2>
            <div className="flex flex-col gap-2">
              {QUICK_ACTIONS.map((qa) => (
                <button
                  key={qa.action}
                  onClick={() => runAction(qa)}
                  disabled={submitting || !selectedAgent}
                  title={qa.description}
                  className="flex items-center gap-2 rounded-[8px] px-3 py-2 text-left text-[12px] transition-colors hover:bg-[#FFF7ED] disabled:opacity-40"
                  style={{ border: "1px solid #E5E7EB" }}
                >
                  <span>{qa.icon}</span>
                  <div className="min-w-0">
                    <div className="font-medium text-[#0F172A]">{qa.label}</div>
                    <div className="text-[10px] text-[#9CA3AF] truncate">{qa.description}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* 커스텀 액션 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-4">
            <h2 className="text-[12px] font-bold text-[#0F172A] mb-3">커스텀 액션</h2>
            <div className="flex flex-col gap-2">
              <input
                className="w-full rounded-[6px] px-3 py-1.5 text-[12px] font-mono"
                style={{ border: "1px solid #D1D5DB", outline: "none" }}
                value={customAction}
                onChange={(e) => setCustomAction(e.target.value)}
                placeholder="ACTION_NAME"
              />
              <textarea
                className="w-full rounded-[6px] px-3 py-1.5 text-[12px] font-mono resize-none"
                style={{ border: "1px solid #D1D5DB", outline: "none" }}
                rows={3}
                value={customParams}
                onChange={(e) => setCustomParams(e.target.value)}
                placeholder='{"key": "value"}'
              />
              {paramsError && (
                <p className="text-[11px] text-red-500">{paramsError}</p>
              )}
              <Btn
                variant="orange"
                onClick={runCustom}
                disabled={submitting || !selectedAgent || !customAction}
              >
                {submitting ? "실행 중..." : "실행"}
              </Btn>
            </div>
          </div>
        </div>

        {/* ── 오른쪽: 결과 패널 ── */}
        <div className="flex flex-col gap-4 flex-1 min-w-0">

          {/* 오류 배너 */}
          {error && (
            <div
              className="rounded-[8px] px-4 py-3 text-[12px]"
              style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B" }}
            >
              {error}
              <button
                className="ml-3 underline text-[11px]"
                onClick={() => setError(null)}
              >
                닫기
              </button>
            </div>
          )}

          {/* 선택된 에이전트 정보 */}
          {selectedAgentObj && (
            <div
              className="rounded-[12px] bg-white border border-[#E5E7EB] px-5 py-3 flex flex-wrap gap-4 text-[12px]"
            >
              <div>
                <span className="text-[#9CA3AF] mr-1">호스트</span>
                <span className="font-semibold text-[#0F172A]">{selectedAgentObj.host}</span>
              </div>
              <div>
                <span className="text-[#9CA3AF] mr-1">OS</span>
                <span>{selectedAgentObj.os_name}</span>
              </div>
              <div>
                <span className="text-[#9CA3AF] mr-1">Agent ID</span>
                <span className="font-mono text-[#6B7280]">…{agentShort(selectedAgentObj.agent_id)}</span>
              </div>
              <div>
                <span className="text-[#9CA3AF] mr-1">상태</span>
                <StatusBadge status={selectedAgentObj.agent_status} />
              </div>
              <div>
                <span className="text-[#9CA3AF] mr-1">마지막 응답</span>
                <span>{fmtTime(selectedAgentObj.last_seen_at)}</span>
              </div>
            </div>
          )}

          {/* 최근 결과 카드 (completed 중 최신 1건) */}
          {(() => {
            const latest = tasks.find((t) => t.status === "completed" && t.result_summary);
            if (!latest) return null;
            return (
              <div
                className="rounded-[12px] bg-white border border-[#E5E7EB] p-5"
                style={{ borderTop: "3px solid #22c55e" }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[12px] font-bold text-[#0F172A]">최근 결과</span>
                  <span className="text-[11px] text-[#9CA3AF] font-mono">{latest.action}</span>
                  <span className="ml-auto text-[11px] text-[#9CA3AF]">{fmtTime(latest.completed_at)}</span>
                </div>
                <pre
                  className="text-[11px] text-[#374151] whitespace-pre-wrap break-all overflow-auto max-h-[300px] rounded-[6px] p-3"
                  style={{ background: "#F9FAFB", border: "1px solid #F3F4F6" }}
                >
                  {latest.result_summary}
                </pre>
                <button
                  className="mt-2 text-[11px] text-[#F97316] underline"
                  onClick={() => setResultTask(latest)}
                >
                  상세 보기
                </button>
              </div>
            );
          })()}

          {/* 태스크 이력 테이블 */}
          <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden">
            <div className="px-5 py-3 border-b border-[#F3F4F6] flex items-center gap-2">
              <span className="text-[12px] font-bold text-[#0F172A]">CAD 태스크 이력</span>
              <span className="text-[11px] text-[#9CA3AF]">(최근 30건)</span>
            </div>
            <AdminTable>
              <AdminThead>
                <AdminTr>
                  <AdminTh>액션</AdminTh>
                  <AdminTh>상태</AdminTh>
                  <AdminTh>생성</AdminTh>
                  <AdminTh>완료</AdminTh>
                  <AdminTh>결과</AdminTh>
                </AdminTr>
              </AdminThead>
              <AdminTbody>
                {tasks.length === 0 ? (
                  <EmptyRow colSpan={5} message="CAD 태스크가 없습니다" />
                ) : (
                  tasks.map((t) => (
                    <AdminTr key={t.task_id}>
                      <AdminTd>
                        <span className="font-mono text-[11px] text-[#374151]">{t.action}</span>
                      </AdminTd>
                      <AdminTd>
                        <StatusBadge status={t.status} />
                      </AdminTd>
                      <AdminTd>{fmtTime(t.created_at)}</AdminTd>
                      <AdminTd>{fmtTime(t.completed_at)}</AdminTd>
                      <AdminTd>
                        {t.result_summary ? (
                          <button
                            className="text-[11px] text-[#F97316] underline"
                            onClick={() => setResultTask(t)}
                          >
                            보기
                          </button>
                        ) : t.failure_reason ? (
                          <span className="text-[11px] text-red-400 truncate max-w-[120px] inline-block">
                            {t.failure_reason}
                          </span>
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
        </div>
      </div>

      {/* 결과 상세 모달 */}
      {resultTask && (
        <Modal
          open={!!resultTask}
          title={`결과 상세 — ${resultTask.action}`}
          onClose={() => setResultTask(null)}
        >
          <div className="flex flex-col gap-3 text-[12px]">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="text-[#9CA3AF]">태스크 ID</span>
                <p className="font-mono text-[11px] text-[#374151] break-all">{resultTask.task_id}</p>
              </div>
              <div>
                <span className="text-[#9CA3AF]">상태</span>
                <p className="mt-0.5"><StatusBadge status={resultTask.status} /></p>
              </div>
              <div>
                <span className="text-[#9CA3AF]">생성</span>
                <p>{fmtTime(resultTask.created_at)}</p>
              </div>
              <div>
                <span className="text-[#9CA3AF]">완료</span>
                <p>{fmtTime(resultTask.completed_at)}</p>
              </div>
            </div>
            {resultTask.result_summary && (
              <div>
                <span className="text-[#9CA3AF] block mb-1">결과</span>
                <pre
                  className="text-[11px] text-[#374151] whitespace-pre-wrap break-all overflow-auto max-h-[400px] rounded-[6px] p-3"
                  style={{ background: "#F9FAFB", border: "1px solid #F3F4F6" }}
                >
                  {resultTask.result_summary}
                </pre>
              </div>
            )}
            {resultTask.failure_reason && (
              <div>
                <span className="text-[#9CA3AF] block mb-1">오류</span>
                <p className="text-red-500">{resultTask.failure_reason}</p>
              </div>
            )}
          </div>
        </Modal>
      )}
    </PageShell>
  );
}
