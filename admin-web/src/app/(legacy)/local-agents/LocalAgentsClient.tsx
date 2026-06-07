"use client";

import { useState } from "react";
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
import RegistrationCodesPanel from "./RegistrationCodesPanel";
import type { AgentStatus } from "@/types/local-agent";
import { RoleBadge } from "./components/RoleBadge";
import { TaskActionCell } from "./components/TaskActionCell";
import { DetailRow, ObserveSummarySection, AuditSummarySection } from "./components/DetailSections";
import { LoadingRow, DiagnosticsSection } from "./components/DiagnosticsSection";
import { formatTime } from "./components/helpers";

import { useCurrentUser } from "./hooks/useCurrentUser";
import { usePollingState, usePollingInterval } from "./hooks/usePolling";
import { useAgentData } from "./hooks/useAgentData";
import { useTaskData } from "./hooks/useTaskData";
import { useModals } from "./hooks/useModals";

// ─── capture 버튼 활성화 정책 ─────────────────────────────────────────────────

function isCaptureEnabled(status: AgentStatus | string): boolean {
  return status === "idle" || status === "busy";
}

// ─── Main Client Component ────────────────────────────────────────────────────

export default function LocalAgentsClient() {
  const { currentUser, userLoading, userError } = useCurrentUser();

  // Phase 1: get refs + state setters for polling (no callbacks yet)
  const [isDocumentHidden, setIsDocumentHidden] = useState(false);
  const polling = usePollingState();

  const agentData = useAgentData({
    currentUserRole: currentUser?.role,
    isPollingAgentsRef: polling.isPollingAgentsRef,
    setLastRefreshedAt: polling.setLastRefreshedAt,
    setPollingError: polling.setPollingError,
  });

  const taskData = useTaskData({
    currentUserRole: currentUser?.role,
    selectedAgentId: agentData.selectedAgentId,
    isPollingTasksRef: polling.isPollingTasksRef,
    setLastRefreshedAt: polling.setLastRefreshedAt,
    setPollingError: polling.setPollingError,
  });

  const modals = useModals({
    selectedAgentId: agentData.selectedAgentId,
    taskStatusFilter: taskData.taskStatusFilter,
    currentUserRole: currentUser?.role,
    fetchTasks: taskData.fetchTasks,
    fetchAgents: agentData.fetchAgents,
  });

  // Phase 2: wire polling interval with real callbacks
  usePollingInterval(
    polling,
    {
      backgroundFetchAgents: agentData.backgroundFetchAgents,
      backgroundFetchTasks: taskData.backgroundFetchTasks,
      selectedAgentId: agentData.selectedAgentId,
      taskStatusFilter: taskData.taskStatusFilter,
      cancelTargetTask: modals.cancelTargetTask,
      captureMode: modals.captureMode,
      captureTargetAgent: modals.captureTargetAgent,
      approvalTargetTask: modals.approvalTargetTask,
    },
    setIsDocumentHidden,
  );

  const {
    agents, agentsLoading, agentsError,
    selectedAgentId, setSelectedAgentId,
    agentStatusFilter, setAgentStatusFilter,
    diagnostics, diagnosticsError,
    fetchAgents,
  } = agentData;

  const {
    tasks, tasksLoading, tasksError,
    taskStatusFilter, setTaskStatusFilter,
    tasksTotal,
  } = taskData;

  const { pollingEnabled, setPollingEnabled, pollingError, lastRefreshedAt } = polling;

  // ── KPI (실제 agents 기준) ────────────────────────────────────────────────
  const kpiTotal = agents.length;
  const kpiIdle = agents.filter((a) => a.agent_status === "idle").length;
  const kpiBusy = agents.filter((a) => a.agent_status === "busy").length;
  const kpiOffline = agents.filter(
    (a) => (a.agent_status as AgentStatus) === "offline" || a.agent_status === "stale"
  ).length;

  // ── role helpers ─────────────────────────────────────────────────────────
  const canMutate =
    !userLoading && (currentUser?.role === "admin" || currentUser?.role === "owner");

  // ── agentStatusFilter: 프론트 필터링 ────────────────────────────────────
  const filteredAgents = agentStatusFilter
    ? agents.filter((a) => a.agent_status === agentStatusFilter)
    : agents;

  const selectedAgent = agents.find((a) => a.agent_id === selectedAgentId) ?? null;

  // ── 마지막 갱신 표시 ─────────────────────────────────────────────────────
  const lastRefreshedStr = lastRefreshedAt ? formatTime(lastRefreshedAt) : null;

  // ── polling 상태 배지 ────────────────────────────────────────────────────
  const captureModalOpen = modals.captureMode === "real" && modals.captureTargetAgent !== null;
  const pollingStatus: "active" | "paused" | "error" | "off" =
    !pollingEnabled ? "off" :
    pollingError ? "error" :
    (isDocumentHidden || captureModalOpen) ? "paused" :
    "active";

  const pollingStatusLabel: Record<typeof pollingStatus, string> = {
    active: "자동 갱신 중",
    paused: "일시중지",
    off: "자동 갱신 꺼짐",
    error: "자동 갱신 오류",
  };

  const pollingStatusColor: Record<typeof pollingStatus, string> = {
    active: "text-[#065F46] bg-[#D1FAE5]",
    paused: "text-[#92400E] bg-[#FEF3C7]",
    off: "text-[#6B7280] bg-[#F3F4F6]",
    error: "text-[#B91C1C] bg-[#FEE2E2]",
  };

  return (
    <PageShell
      title="로컬 에이전트"
      description="등록된 로컬 에이전트의 연결 상태와 작업 현황을 관리합니다."
      headerRight={
        <div className="flex items-center gap-3 flex-wrap justify-end">
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${pollingStatusColor[pollingStatus]}`}
          >
            {pollingStatusLabel[pollingStatus]}
          </span>
          {lastRefreshedStr && (
            <span className="text-[11px] text-[#9CA3AF]">
              마지막 갱신: {lastRefreshedStr}
            </span>
          )}
          {pollingError && (
            <span className="text-[11px] text-[#B91C1C]" title={pollingError}>
              {pollingError}
            </span>
          )}
          <Btn
            variant="ghost"
            size="xs"
            onClick={() => setPollingEnabled((v) => !v)}
          >
            {pollingEnabled ? "자동 새로고침 ON" : "자동 새로고침 OFF"}
          </Btn>
          <Btn variant="orange" size="sm" onClick={fetchAgents} disabled={agentsLoading}>
            새로고침
          </Btn>
        </div>
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

      {/* ── 운영 진단 섹션 (Stage 13E-3) ───────────────────────────────────────── */}
      <DiagnosticsSection diagnostics={diagnostics} error={diagnosticsError} />

      {/* ── capture 결과 배너 ─────────────────────────────────────────────────── */}
      {modals.captureSuccess && (
        <div className="mb-4 px-4 py-3 rounded-[8px] border border-[#D1FAE5] bg-[#ECFDF5] text-[13px] text-[#065F46] flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold mb-1">
              {modals.captureSuccess.dry_run
                ? "사전 점검 요청이 생성되었습니다."
                : "화면 캡처 요청이 생성되었습니다. 텔레그램 승인 후 실행됩니다."}
            </p>
            <p className="font-mono text-[12px] text-[#047857]">
              task_id: {modals.captureSuccess.task_id} &nbsp;|&nbsp; status: {modals.captureSuccess.status}
              &nbsp;|&nbsp; dry_run: {String(modals.captureSuccess.dry_run)} &nbsp;|&nbsp;
              approval_required: {String(modals.captureSuccess.approval_required)}
            </p>
          </div>
          <button
            onClick={() => modals.setCaptureSuccess(null)}
            className="text-[#6B7280] hover:text-[#374151] text-[16px] leading-none mt-0.5 flex-shrink-0"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
      )}

      {modals.captureError && modals.captureMode === null && (
        <div className="mb-4 px-4 py-3 rounded-[8px] border border-[#FEE2E2] bg-[#FEF2F2] text-[13px] text-[#B91C1C] flex items-start justify-between gap-3">
          <span>{modals.captureError}</span>
          <button
            onClick={() => modals.setCaptureError(null)}
            className="text-[#6B7280] hover:text-[#374151] text-[16px] leading-none mt-0.5 flex-shrink-0"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
      )}

      {/* ── 권한 안내 배지 ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-3">
        <RoleBadge
          currentUser={currentUser}
          userLoading={userLoading}
          userError={userError}
        />
      </div>

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
                  const agentOnline = isCaptureEnabled(agent.agent_status);
                  const captureEnabled = agentOnline && canMutate && !modals.captureLoading;
                  const captureTitle = !canMutate
                    ? "admin/owner 권한 필요"
                    : !agentOnline
                    ? "에이전트 오프라인"
                    : undefined;
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
                            title={captureTitle}
                            onClick={captureEnabled ? () => modals.handleDryRun(agent) : undefined}
                          >
                            사전 점검
                          </Btn>
                          <Btn
                            variant="ghost"
                            size="xs"
                            disabled={!captureEnabled}
                            title={captureTitle}
                            onClick={captureEnabled ? () => modals.handleOpenCaptureModal(agent) : undefined}
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
                      <TaskActionCell
                        task={task}
                        canMutate={canMutate}
                        onCancel={modals.setCancelTargetTask}
                        onApprovalAction={modals.handleOpenApprovalModal}
                        onShowDetail={modals.handleOpenDetail}
                      />
                    </AdminTd>
                  </AdminTr>
                ))
              )}
            </AdminTbody>
          </AdminTable>
        )}
      </div>

      {/* ── 등록코드 관리 (UI-AUTH-2) ──────────────────────────────────────── */}
      <RegistrationCodesPanel
        currentUser={currentUser}
        userLoading={userLoading}
        userError={userError}
      />

      {/* ── Task Detail (read-only) Modal — Stage 13B-1 ───────────────────── */}
      <Modal
        open={modals.detailTargetTask !== null}
        title="작업 상세 (read-only)"
        onClose={modals.handleCloseDetail}
        footer={
          <Btn variant="ghost" size="sm" onClick={modals.handleCloseDetail}>
            닫기
          </Btn>
        }
      >
        {modals.detailLoading && (
          <p className="text-[13px] text-[#6B7280]">불러오는 중…</p>
        )}
        {modals.detailError && (
          <p className="text-[13px] text-[#B91C1C]">{modals.detailError}</p>
        )}
        {!modals.detailLoading && !modals.detailError && modals.detailData && (
          <div className="space-y-2 text-[13px] text-[#374151]">
            <DetailRow label="작업 ID" value={modals.detailData.task_id} mono />
            <DetailRow label="에이전트 ID" value={modals.detailData.agent_id} mono />
            <DetailRow label="액션" value={modals.detailData.action} />
            <DetailRow label="위험도" value={modals.detailData.risk_level} />
            <DetailRow label="상태" value={modals.detailData.status} />
            <DetailRow label="요청자" value={modals.detailData.requested_by} />
            <DetailRow label="생성" value={modals.detailData.created_at} />
            <DetailRow label="갱신" value={modals.detailData.updated_at} />
            <DetailRow label="전달" value={modals.detailData.delivered_at ?? "—"} />
            <DetailRow label="시작" value={modals.detailData.started_at ?? "—"} />
            <DetailRow label="완료" value={modals.detailData.completed_at ?? "—"} />
            <DetailRow label="결과 요약" value={modals.detailData.result_summary ?? "—"} />
            {modals.detailData.error_summary && (
              <DetailRow label="오류 요약" value={modals.detailData.error_summary} danger />
            )}
            {modals.detailData.failure_reason && (
              <DetailRow label="실패 사유" value={modals.detailData.failure_reason} danger />
            )}
            {modals.detailData.timed_out_at && (
              <DetailRow label="타임아웃" value={modals.detailData.timed_out_at} danger />
            )}
            {modals.detailData.approved_at && (
              <DetailRow
                label="승인"
                value={`${modals.detailData.approved_at}${modals.detailData.approved_by ? " · " + modals.detailData.approved_by : ""}`}
              />
            )}
            {modals.detailData.rejected_at && (
              <DetailRow
                label="거절"
                value={`${modals.detailData.rejected_at}${modals.detailData.reject_reason ? " · " + modals.detailData.reject_reason : ""}`}
                danger
              />
            )}
            {modals.detailData.cancel_requested_at && (
              <DetailRow
                label="취소 요청"
                value={`${modals.detailData.cancel_requested_at}${modals.detailData.cancel_requested_by ? " · " + modals.detailData.cancel_requested_by : ""}`}
              />
            )}
            {modals.detailData.cancelled_at && (
              <DetailRow label="취소 완료" value={modals.detailData.cancelled_at} />
            )}
            {modals.detailData.cancel_reason && (
              <DetailRow label="취소 사유" value={modals.detailData.cancel_reason} />
            )}
            {modals.detailData.observe_summary && (
              <ObserveSummarySection obs={modals.detailData.observe_summary} />
            )}
            {modals.detailData.audit_summary && (
              <AuditSummarySection audit={modals.detailData.audit_summary} />
            )}
            <div className="mt-3 pt-3 border-t border-[#E5E7EB] text-[11px] text-[#6B7280] leading-relaxed">
              민감정보(쿠키·세션·토큰·Authorization·password·HTML 본문·query 원문)는
              표시하지 않습니다. 로컬 에이전트 감사 로그 원문은 PC에 보관되며
              admin-web 에 노출하지 않습니다.
            </div>
          </div>
        )}
      </Modal>

      {/* ── Cancel Modal ──────────────────────────────────────────────────────── */}
      <Modal
        open={modals.cancelTargetTask !== null}
        title="작업 취소"
        onClose={modals.handleCancelClose}
        footer={
          <>
            <Btn variant="ghost" size="sm" onClick={modals.handleCancelClose} disabled={modals.cancelLoading}>
              닫기
            </Btn>
            <Btn
              variant="danger"
              size="sm"
              onClick={modals.handleCancelSubmit}
              disabled={modals.cancelLoading || modals.cancelReason.length > 200}
            >
              {modals.cancelLoading ? "처리 중…" : "취소 요청"}
            </Btn>
          </>
        }
      >
        <p className="text-[13px] text-[#374151] mb-3">
          취소 후 상태가 변경됩니다. 실행 중인 작업은 즉시 중단이 아니라 취소 요청 상태로 전환될 수
          있습니다.
        </p>

        {modals.cancelTargetTask && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {modals.cancelTargetTask.task_id} — {modals.cancelTargetTask.action}
          </div>
        )}

        <textarea
          className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] text-[#374151] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
          rows={3}
          maxLength={200}
          placeholder="선택 사항 — 최대 200자"
          value={modals.cancelReason}
          onChange={(e) => {
            modals.setCancelReason(e.target.value);
            modals.setCancelError(null);
          }}
        />

        <div className="flex items-center justify-between mt-1">
          <span className="text-[11px] text-[#9CA3AF]">
            비밀번호·토큰 등 민감한 정보는 입력하지 마세요.
          </span>
          <span
            className={`text-[11px] ${modals.cancelReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}
          >
            {modals.cancelReason.length}/200
          </span>
        </div>

        {modals.cancelError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{modals.cancelError}</p>
        )}
      </Modal>

      {/* ── Approval Modal ───────────────────────────────────────────────────── */}
      <Modal
        open={modals.approvalTargetTask !== null}
        title="작업 승인 / 거절"
        onClose={modals.handleCloseApprovalModal}
        footer={
          <>
            <Btn variant="ghost" size="sm" onClick={modals.handleCloseApprovalModal} disabled={modals.approvalLoading}>
              닫기
            </Btn>
            <Btn
              variant="danger"
              size="sm"
              disabled={modals.approvalLoading || modals.approvalAction !== "reject"}
              onClick={modals.approvalAction === "reject" ? modals.handleApprovalSubmit : undefined}
            >
              {modals.approvalLoading && modals.approvalAction === "reject" ? "처리 중…" : "거절 확인"}
            </Btn>
            <Btn
              variant="orange"
              size="sm"
              disabled={modals.approvalLoading || modals.approvalAction !== "approve"}
              onClick={modals.approvalAction === "approve" ? modals.handleApprovalSubmit : undefined}
            >
              {modals.approvalLoading && modals.approvalAction === "approve" ? "처리 중…" : "승인 확인"}
            </Btn>
          </>
        }
      >
        <p className="text-[12px] text-[#6B7280] mb-2">
          이 버튼은 작업 실행 버튼이 아닙니다. 승인 시 작업이 에이전트에 전달되어 실행됩니다.
        </p>

        {modals.approvalTargetTask && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {modals.approvalTargetTask.task_id} — {modals.approvalTargetTask.action} &nbsp;
            <StatusBadge status={modals.approvalTargetTask.risk_level} />
          </div>
        )}

        <div className="flex gap-2 mb-3">
          <Btn
            variant={modals.approvalAction === "approve" ? "orange" : "ghost"}
            size="sm"
            disabled={modals.approvalLoading}
            onClick={() => { modals.setApprovalAction("approve"); modals.setApprovalError(null); }}
          >
            승인
          </Btn>
          <Btn
            variant={modals.approvalAction === "reject" ? "danger" : "ghost"}
            size="sm"
            disabled={modals.approvalLoading}
            onClick={() => { modals.setApprovalAction("reject"); modals.setApprovalError(null); }}
          >
            거절
          </Btn>
        </div>

        {modals.approvalAction === "reject" && (
          <>
            <textarea
              className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] text-[#374151] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
              rows={2}
              maxLength={200}
              placeholder="선택 사항 — 거절 사유 (최대 200자)"
              value={modals.approvalReason}
              onChange={(e) => { modals.setApprovalReason(e.target.value); modals.setApprovalError(null); }}
            />
            <div className="flex justify-between mt-1 mb-2">
              <span className="text-[11px] text-[#9CA3AF]">비밀번호·토큰 등 민감한 정보는 입력하지 마세요.</span>
              <span className={`text-[11px] ${modals.approvalReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}>
                {modals.approvalReason.length}/200
              </span>
            </div>
          </>
        )}

        {modals.approvalError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{modals.approvalError}</p>
        )}
      </Modal>

      {/* ── Capture Confirm Modal ─────────────────────────────────────────────── */}
      <Modal
        open={modals.captureMode === "real" && modals.captureTargetAgent !== null}
        title="화면 캡처 요청"
        onClose={modals.handleCloseCaptureModal}
        footer={
          <>
            <Btn
              variant="ghost"
              size="sm"
              onClick={modals.handleCloseCaptureModal}
              disabled={modals.captureLoading}
            >
              닫기
            </Btn>
            <Btn
              variant="orange"
              size="sm"
              onClick={modals.handleCaptureSubmit}
              disabled={modals.captureLoading || modals.captureReason.length > 200}
            >
              {modals.captureLoading ? "요청 중…" : "캡처 요청"}
            </Btn>
          </>
        }
      >
        {modals.captureTargetAgent && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {modals.captureTargetAgent.host} &nbsp;/&nbsp; {modals.captureTargetAgent.agent_id}
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
          value={modals.captureReason}
          onChange={(e) => {
            modals.setCaptureReason(e.target.value);
            modals.setCaptureError(null);
          }}
        />

        <div className="flex items-center justify-between mt-1">
          <span className="text-[11px] text-[#9CA3AF]" />
          <span
            className={`text-[11px] ${modals.captureReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}
          >
            {modals.captureReason.length}/200
          </span>
        </div>

        {modals.captureError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{modals.captureError}</p>
        )}
      </Modal>
    </PageShell>
  );
}
