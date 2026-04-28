"use client";

import { useEffect, useState, useCallback } from "react";
import {
  PageShell,
  FilterBar,
  FilterSelect,
  FilterSpacer,
  KpiCard,
  AdminTable,
  AdminThead,
  AdminTbody,
  AdminTr,
  AdminTh,
  AdminTd,
  EmptyRow,
  StatusBadge,
  EmptyState,
  Btn,
} from "@/components/ui";
import { Modal } from "@/components/ui/Modal";
import {
  getLocalAgents,
  getAgentTasks,
  cancelTask,
  requestCaptureScreenshot,
  ApiError,
} from "@/lib/api";
import type {
  LocalAgent,
  LocalAgentTask,
  AgentStatus,
  CaptureScreenshotResponse,
} from "@/types/local-agent";

// ─── 취소 버튼 활성화 정책 ────────────────────────────────────────────────────

function cancelButtonProps(status: string): {
  label: string;
  enabled: boolean;
  variant: "danger" | "secondary" | "ghost";
} | null {
  switch (status) {
    case "queued":
    case "waiting_approval":
      return { label: "취소", enabled: true, variant: "danger" };
    case "delivered":
    case "running":
      return { label: "취소 요청", enabled: true, variant: "secondary" };
    case "cancel_requested":
      return { label: "취소 요청됨", enabled: false, variant: "ghost" };
    case "cancelled":
      return { label: "취소됨", enabled: false, variant: "ghost" };
    default:
      return null;
  }
}

// ─── capture 버튼 활성화 정책 ─────────────────────────────────────────────────

function isCaptureEnabled(status: AgentStatus | string): boolean {
  return status === "idle" || status === "busy";
}

// ─── Task Action Cell ─────────────────────────────────────────────────────────

interface TaskActionCellProps {
  task: LocalAgentTask;
  onCancel: (task: LocalAgentTask) => void;
}

function TaskActionCell({ task, onCancel }: TaskActionCellProps) {
  const btn = cancelButtonProps(task.status);
  if (!btn) return <span className="text-[12px] text-[#9CA3AF]">—</span>;
  return (
    <Btn
      variant={btn.variant}
      size="xs"
      disabled={!btn.enabled}
      onClick={btn.enabled ? () => onCancel(task) : undefined}
    >
      {btn.label}
    </Btn>
  );
}

// ─── Loading Row ──────────────────────────────────────────────────────────────

function LoadingRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-8 text-center text-[13px] text-[#6B7280]">
        불러오는 중…
      </td>
    </tr>
  );
}

// ─── Cancel Error 메시지 ──────────────────────────────────────────────────────

function cancelErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400: return "취소 사유는 최대 200자입니다.";
      case 403: return "권한이 없습니다.";
      case 404: return "작업을 찾을 수 없습니다.";
      case 409: return "이미 취소되었거나 종료된 작업입니다.";
      default: return "취소 요청에 실패했습니다.";
    }
  }
  return "취소 요청에 실패했습니다.";
}

// ─── Capture Error 메시지 ─────────────────────────────────────────────────────

function captureErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 403: return "권한이 없습니다.";
      case 404: return "에이전트를 찾을 수 없습니다.";
      default: return `캡처 요청에 실패했습니다. (HTTP ${err.status})`;
    }
  }
  return "캡처 요청에 실패했습니다.";
}

// ─── Capture Success 표시 ─────────────────────────────────────────────────────

interface CaptureSuccessInfo {
  task_id: string;
  status: string;
  dry_run: boolean;
  approval_required: boolean;
}

function extractCaptureSuccessInfo(res: CaptureScreenshotResponse): CaptureSuccessInfo {
  return {
    task_id: res.task_id,
    status: res.status,
    dry_run: res.dry_run,
    approval_required: res.approval_required,
  };
}

// ─── Main Client Component ────────────────────────────────────────────────────

export default function LocalAgentsClient() {
  // ── agents ────────────────────────────────────────────────────────────────
  const [agents, setAgents] = useState<LocalAgent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [agentStatusFilter, setAgentStatusFilter] = useState<string>("");

  // ── tasks ─────────────────────────────────────────────────────────────────
  const [tasks, setTasks] = useState<LocalAgentTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [taskStatusFilter, setTaskStatusFilter] = useState<string>("");
  const [tasksTotal, setTasksTotal] = useState(0);

  // ── cancel modal ──────────────────────────────────────────────────────────
  const [cancelTargetTask, setCancelTargetTask] = useState<LocalAgentTask | null>(null);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelLoading, setCancelLoading] = useState(false);

  // ── capture state ─────────────────────────────────────────────────────────
  const [captureTargetAgent, setCaptureTargetAgent] = useState<LocalAgent | null>(null);
  const [captureMode, setCaptureMode] = useState<"dry_run" | "real" | null>(null);
  const [captureLoading, setCaptureLoading] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [captureSuccess, setCaptureSuccess] = useState<CaptureSuccessInfo | null>(null);
  const [captureReason, setCaptureReason] = useState<string>("");

  // ── agent 목록 fetch ──────────────────────────────────────────────────────
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    setAgentsError(null);
    try {
      const data = await getLocalAgents();
      setAgents(data.agents);
      if (data.agents.length > 0) {
        setSelectedAgentId((prev) => prev ?? data.agents[0].agent_id);
      }
    } catch (err) {
      setAgentsError(
        err instanceof ApiError ? `API ${err.status}: ${err.message}` : "에이전트 목록 조회 실패"
      );
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // ── task 목록 fetch ───────────────────────────────────────────────────────
  const fetchTasks = useCallback(async (agentId: string, status: string) => {
    setTasksLoading(true);
    setTasksError(null);
    try {
      const data = await getAgentTasks(agentId, {
        limit: 50,
        status: status || undefined,
      });
      setTasks(data.tasks);
      setTasksTotal(data.total);
    } catch (err) {
      setTasksError(
        err instanceof ApiError ? `API ${err.status}: ${err.message}` : "작업 목록 조회 실패"
      );
      setTasks([]);
      setTasksTotal(0);
    } finally {
      setTasksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAgentId) {
      fetchTasks(selectedAgentId, taskStatusFilter);
    }
  }, [selectedAgentId, taskStatusFilter, fetchTasks]);

  // ── cancel submit ─────────────────────────────────────────────────────────
  const handleCancelSubmit = useCallback(async () => {
    if (!cancelTargetTask || !selectedAgentId) return;
    setCancelLoading(true);
    setCancelError(null);
    try {
      await cancelTask(selectedAgentId, cancelTargetTask.task_id, cancelReason);
      setCancelTargetTask(null);
      setCancelReason("");
      await Promise.all([
        fetchTasks(selectedAgentId, taskStatusFilter),
        fetchAgents(),
      ]);
    } catch (err) {
      setCancelError(cancelErrorMessage(err));
    } finally {
      setCancelLoading(false);
    }
  }, [cancelTargetTask, selectedAgentId, cancelReason, taskStatusFilter, fetchTasks, fetchAgents]);

  const handleCancelClose = useCallback(() => {
    if (cancelLoading) return;
    setCancelTargetTask(null);
    setCancelReason("");
    setCancelError(null);
  }, [cancelLoading]);

  // ── capture: 사전 점검 ────────────────────────────────────────────────────
  const handleDryRun = useCallback(async (agent: LocalAgent) => {
    setCaptureSuccess(null);
    setCaptureError(null);
    setCaptureLoading(true);
    try {
      const res = await requestCaptureScreenshot(agent.agent_id, {
        dryRun: true,
        reason: "admin_web_dry_run_check",
      });
      setCaptureSuccess(extractCaptureSuccessInfo(res));
    } catch (err) {
      setCaptureError(captureErrorMessage(err));
    } finally {
      setCaptureLoading(false);
    }
  }, []);

  // ── capture: 실제 캡처 Modal open ─────────────────────────────────────────
  const handleOpenCaptureModal = useCallback((agent: LocalAgent) => {
    setCaptureTargetAgent(agent);
    setCaptureMode("real");
    setCaptureError(null);
    setCaptureSuccess(null);
    setCaptureReason("");
  }, []);

  // ── capture: Modal close ──────────────────────────────────────────────────
  const handleCloseCaptureModal = useCallback(() => {
    if (captureLoading) return;
    setCaptureTargetAgent(null);
    setCaptureMode(null);
    setCaptureError(null);
    setCaptureReason("");
  }, [captureLoading]);

  // ── capture: 실제 캡처 submit ─────────────────────────────────────────────
  const handleCaptureSubmit = useCallback(async () => {
    if (!captureTargetAgent) return;
    setCaptureLoading(true);
    setCaptureError(null);
    try {
      const res = await requestCaptureScreenshot(captureTargetAgent.agent_id, {
        dryRun: false,
        reason: captureReason.trim() || undefined,
      });
      const info = extractCaptureSuccessInfo(res);
      setCaptureTargetAgent(null);
      setCaptureMode(null);
      setCaptureReason("");
      setCaptureSuccess(info);
      await Promise.all([
        fetchAgents(),
        ...(selectedAgentId === captureTargetAgent.agent_id
          ? [fetchTasks(captureTargetAgent.agent_id, taskStatusFilter)]
          : []),
      ]);
    } catch (err) {
      setCaptureError(captureErrorMessage(err));
    } finally {
      setCaptureLoading(false);
    }
  }, [captureTargetAgent, captureReason, selectedAgentId, taskStatusFilter, fetchAgents, fetchTasks]);

  // ── KPI (실제 agents 기준) ────────────────────────────────────────────────
  const kpiTotal = agents.length;
  const kpiIdle = agents.filter((a) => a.agent_status === "idle").length;
  const kpiBusy = agents.filter((a) => a.agent_status === "busy").length;
  const kpiOffline = agents.filter(
    (a) => (a.agent_status as AgentStatus) === "offline" || a.agent_status === "stale"
  ).length;

  // ── agentStatusFilter: 프론트 필터링 ────────────────────────────────────
  const filteredAgents = agentStatusFilter
    ? agents.filter((a) => a.agent_status === agentStatusFilter)
    : agents;

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId) ?? null;

  return (
    <PageShell
      title="로컬 에이전트"
      description="등록된 로컬 에이전트의 연결 상태와 작업 현황을 관리합니다."
      headerRight={
        <Btn variant="orange" size="sm" onClick={fetchAgents} disabled={agentsLoading}>
          새로고침
        </Btn>
      }
    >
      {/* ── KPI 카드 ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="전체 에이전트" value={kpiTotal} />
        <KpiCard title="대기" value={kpiIdle} accentColor="#6B7280" description="idle" />
        <KpiCard title="작업중" value={kpiBusy} accentColor="#F97316" description="busy" />
        <KpiCard
          title="오프라인"
          value={kpiOffline}
          accentColor="#9CA3AF"
          description="offline / stale"
        />
      </div>

      {/* ── capture 결과 배너 ─────────────────────────────────────────────────── */}
      {captureSuccess && (
        <div className="mb-4 px-4 py-3 rounded-[8px] border border-[#D1FAE5] bg-[#ECFDF5] text-[13px] text-[#065F46] flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold mb-1">
              {captureSuccess.dry_run
                ? "사전 점검 요청이 생성되었습니다."
                : "화면 캡처 요청이 생성되었습니다. 텔레그램 승인 후 실행됩니다."}
            </p>
            <p className="font-mono text-[12px] text-[#047857]">
              task_id: {captureSuccess.task_id} &nbsp;|&nbsp; status: {captureSuccess.status}
              &nbsp;|&nbsp; dry_run: {String(captureSuccess.dry_run)} &nbsp;|&nbsp;
              approval_required: {String(captureSuccess.approval_required)}
            </p>
          </div>
          <button
            onClick={() => setCaptureSuccess(null)}
            className="text-[#6B7280] hover:text-[#374151] text-[16px] leading-none mt-0.5 flex-shrink-0"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
      )}

      {captureError && captureMode === null && (
        <div className="mb-4 px-4 py-3 rounded-[8px] border border-[#FEE2E2] bg-[#FEF2F2] text-[13px] text-[#B91C1C] flex items-start justify-between gap-3">
          <span>{captureError}</span>
          <button
            onClick={() => setCaptureError(null)}
            className="text-[#6B7280] hover:text-[#374151] text-[16px] leading-none mt-0.5 flex-shrink-0"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
      )}

      {/* ── Agent 상태 필터 ───────────────────────────────────────────────────── */}
      <FilterBar>
        <FilterSelect
          label="에이전트 상태"
          value={agentStatusFilter}
          onChange={(e) => setAgentStatusFilter(e.target.value)}
        >
          <option value="">전체</option>
          <option value="idle">대기</option>
          <option value="busy">작업중</option>
          <option value="stale">응답지연</option>
          <option value="offline">오프라인</option>
        </FilterSelect>
        <FilterSpacer />
        <span className="text-[12px] text-[#9CA3AF]">
          {agentsLoading ? "불러오는 중…" : `총 ${filteredAgents.length}건`}
        </span>
      </FilterBar>

      {/* ── Agent 목록 ────────────────────────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-[#E5E7EB] flex items-center justify-between">
          <span className="text-[13px] font-bold text-[#0F172A]">에이전트 목록</span>
          <span className="text-[12px] text-[#6B7280]">총 {filteredAgents.length}건</span>
        </div>

        {agentsError ? (
          <div className="px-5 py-8">
            <EmptyState title="데이터를 불러오지 못했습니다" description={agentsError} />
          </div>
        ) : (
          <AdminTable>
            <AdminThead>
              <AdminTr>
                <AdminTh>Agent ID</AdminTh>
                <AdminTh>Host</AdminTh>
                <AdminTh>OS</AdminTh>
                <AdminTh>Version</AdminTh>
                <AdminTh>상태</AdminTh>
                <AdminTh>활성작업</AdminTh>
                <AdminTh>현재작업</AdminTh>
                <AdminTh>최근확인</AdminTh>
                <AdminTh>Actions</AdminTh>
              </AdminTr>
            </AdminThead>
            <AdminTbody>
              {agentsLoading ? (
                <LoadingRow colSpan={9} />
              ) : filteredAgents.length === 0 ? (
                <EmptyRow colSpan={9} message="등록된 에이전트가 없습니다." />
              ) : (
                filteredAgents.map((agent) => {
                  const captureEnabled = isCaptureEnabled(agent.agent_status) && !captureLoading;
                  return (
                    <AdminTr
                      key={agent.agent_id}
                      className={agent.agent_id === selectedAgentId ? "bg-orange-50" : undefined}
                    >
                      <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                        {agent.agent_id}
                      </AdminTd>
                      <AdminTd className="font-semibold">{agent.host}</AdminTd>
                      <AdminTd className="text-[#6B7280]">{agent.os_name}</AdminTd>
                      <AdminTd className="font-mono text-[12px]">{agent.version}</AdminTd>
                      <AdminTd>
                        <StatusBadge status={agent.agent_status} />
                      </AdminTd>
                      <AdminTd className="text-center">{agent.active_task_count}</AdminTd>
                      <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                        {agent.current_task_id ?? "—"}
                      </AdminTd>
                      <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                        {agent.last_seen_at ?? "—"}
                      </AdminTd>
                      <AdminTd>
                        <div className="flex items-center gap-1 flex-wrap">
                          <Btn
                            variant="ghost"
                            size="xs"
                            onClick={() => {
                              setSelectedAgentId(agent.agent_id);
                              setTaskStatusFilter("");
                            }}
                          >
                            작업 보기
                          </Btn>
                          <Btn
                            variant="ghost"
                            size="xs"
                            disabled={!captureEnabled}
                            onClick={captureEnabled ? () => handleDryRun(agent) : undefined}
                          >
                            사전 점검
                          </Btn>
                          <Btn
                            variant="ghost"
                            size="xs"
                            disabled={!captureEnabled}
                            onClick={captureEnabled ? () => handleOpenCaptureModal(agent) : undefined}
                          >
                            화면 캡처
                          </Btn>
                        </div>
                      </AdminTd>
                    </AdminTr>
                  );
                })
              )}
            </AdminTbody>
          </AdminTable>
        )}
      </div>

      {/* ── 선택된 Agent 작업 목록 ────────────────────────────────────────────── */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-[#E5E7EB] flex items-center gap-3">
          <span className="text-[13px] font-bold text-[#0F172A]">작업 목록</span>
          {selectedAgent ? (
            <span className="text-[12px] text-[#6B7280]">
              에이전트:{" "}
              <span className="font-mono font-semibold text-[#F97316]">
                {selectedAgent.agent_id}
              </span>{" "}
              ({selectedAgent.host})
            </span>
          ) : (
            <span className="text-[12px] text-[#9CA3AF]">에이전트를 선택하세요</span>
          )}
        </div>

        <div className="px-5 py-2 border-b border-[#E5E7EB]">
          <FilterBar>
            <FilterSelect
              label="태스크 상태"
              value={taskStatusFilter}
              onChange={(e) => setTaskStatusFilter(e.target.value)}
            >
              <option value="">전체</option>
              <option value="queued">대기</option>
              <option value="waiting_approval">승인대기</option>
              <option value="running">실행중</option>
              <option value="completed">완료</option>
              <option value="failed">실패</option>
              <option value="cancelled">취소됨</option>
            </FilterSelect>
            <FilterSpacer />
            <span className="text-[12px] text-[#6B7280]">
              {tasksLoading ? "불러오는 중…" : `총 ${tasksTotal}건`}
            </span>
          </FilterBar>
        </div>

        {tasksError ? (
          <div className="px-5 py-8">
            <EmptyState title="데이터를 불러오지 못했습니다" description={tasksError} />
          </div>
        ) : (
          <AdminTable>
            <AdminThead>
              <AdminTr>
                <AdminTh>Task ID</AdminTh>
                <AdminTh>Action</AdminTh>
                <AdminTh>Status</AdminTh>
                <AdminTh>Risk</AdminTh>
                <AdminTh>Requested By</AdminTh>
                <AdminTh>Created</AdminTh>
                <AdminTh>Updated</AdminTh>
                <AdminTh>Failure Reason</AdminTh>
                <AdminTh>Actions</AdminTh>
              </AdminTr>
            </AdminThead>
            <AdminTbody>
              {tasksLoading ? (
                <LoadingRow colSpan={9} />
              ) : !selectedAgentId ? (
                <EmptyRow colSpan={9} message="에이전트를 선택하면 작업 목록이 표시됩니다." />
              ) : tasks.length === 0 ? (
                <EmptyRow colSpan={9} message="작업 내역이 없습니다." />
              ) : (
                tasks.map((task) => (
                  <AdminTr key={task.task_id}>
                    <AdminTd className="font-mono text-[12px] text-[#6B7280]">
                      {task.task_id}
                    </AdminTd>
                    <AdminTd className="font-semibold">{task.action}</AdminTd>
                    <AdminTd>
                      <StatusBadge status={task.status} />
                    </AdminTd>
                    <AdminTd>
                      <StatusBadge status={task.risk_level} />
                    </AdminTd>
                    <AdminTd className="text-[#6B7280]">{task.requested_by}</AdminTd>
                    <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                      {task.created_at}
                    </AdminTd>
                    <AdminTd className="text-[12px] text-[#9CA3AF] whitespace-nowrap">
                      {task.updated_at}
                    </AdminTd>
                    <AdminTd className="text-[12px] text-[#B91C1C] max-w-[160px] truncate">
                      {task.failure_reason ?? "—"}
                    </AdminTd>
                    <AdminTd>
                      <TaskActionCell task={task} onCancel={setCancelTargetTask} />
                    </AdminTd>
                  </AdminTr>
                ))
              )}
            </AdminTbody>
          </AdminTable>
        )}
      </div>

      {/* ── Cancel Modal ──────────────────────────────────────────────────────── */}
      <Modal
        open={cancelTargetTask !== null}
        title="작업 취소"
        onClose={handleCancelClose}
        footer={
          <>
            <Btn variant="ghost" size="sm" onClick={handleCancelClose} disabled={cancelLoading}>
              닫기
            </Btn>
            <Btn
              variant="danger"
              size="sm"
              onClick={handleCancelSubmit}
              disabled={cancelLoading || cancelReason.length > 200}
            >
              {cancelLoading ? "처리 중…" : "취소 요청"}
            </Btn>
          </>
        }
      >
        <p className="text-[13px] text-[#374151] mb-3">
          취소 후 상태가 변경됩니다. 실행 중인 작업은 즉시 중단이 아니라 취소 요청 상태로 전환될 수
          있습니다.
        </p>

        {cancelTargetTask && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {cancelTargetTask.task_id} — {cancelTargetTask.action}
          </div>
        )}

        <textarea
          className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] text-[#374151] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
          rows={3}
          maxLength={200}
          placeholder="선택 사항 — 최대 200자"
          value={cancelReason}
          onChange={(e) => {
            setCancelReason(e.target.value);
            setCancelError(null);
          }}
        />

        <div className="flex items-center justify-between mt-1">
          <span className="text-[11px] text-[#9CA3AF]">
            비밀번호·토큰 등 민감한 정보는 입력하지 마세요.
          </span>
          <span
            className={`text-[11px] ${cancelReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}
          >
            {cancelReason.length}/200
          </span>
        </div>

        {cancelError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{cancelError}</p>
        )}
      </Modal>

      {/* ── Capture Confirm Modal ─────────────────────────────────────────────── */}
      <Modal
        open={captureMode === "real" && captureTargetAgent !== null}
        title="화면 캡처 요청"
        onClose={handleCloseCaptureModal}
        footer={
          <>
            <Btn
              variant="ghost"
              size="sm"
              onClick={handleCloseCaptureModal}
              disabled={captureLoading}
            >
              닫기
            </Btn>
            <Btn
              variant="orange"
              size="sm"
              onClick={handleCaptureSubmit}
              disabled={captureLoading || captureReason.length > 200}
            >
              {captureLoading ? "요청 중…" : "캡처 요청"}
            </Btn>
          </>
        }
      >
        {captureTargetAgent && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {captureTargetAgent.host} &nbsp;/&nbsp; {captureTargetAgent.agent_id}
          </div>
        )}

        <p className="text-[13px] text-[#374151] mb-2">
          승인 후 로컬 PC에서 1회 화면 캡처가 실행됩니다. 서버에는 이미지가 업로드되지 않습니다.
        </p>
        <p className="text-[13px] font-semibold text-[#B91C1C] mb-4">
          비밀번호, OTP, 인증서, 카드정보 화면에서는 캡처하지 마세요.
        </p>

        <textarea
          className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] text-[#374151] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
          rows={3}
          maxLength={200}
          placeholder="선택 사항 — 요청 사유"
          value={captureReason}
          onChange={(e) => {
            setCaptureReason(e.target.value);
            setCaptureError(null);
          }}
        />

        <div className="flex items-center justify-between mt-1">
          <span className="text-[11px] text-[#9CA3AF]" />
          <span
            className={`text-[11px] ${captureReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}
          >
            {captureReason.length}/200
          </span>
        </div>

        {captureError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{captureError}</p>
        )}
      </Modal>
    </PageShell>
  );
}
