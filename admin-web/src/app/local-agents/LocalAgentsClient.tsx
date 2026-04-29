"use client";

import { useEffect, useState, useCallback, useRef } from "react";
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
  getLocalAgentTask,
  cancelTask,
  approveLocalAgentTask,
  rejectLocalAgentTask,
  requestCaptureScreenshot,
  getCurrentUser,
  getLocalAgentsDiagnostics,
  ApiError,
} from "@/lib/api";
import type {
  LocalAgent,
  LocalAgentTask,
  LocalAgentTaskDetail,
  LocalAgentDiagnostics,
  ObserveSummary,
  AuditSummary,
  AgentStatus,
  CaptureScreenshotResponse,
} from "@/types/local-agent";
import type { CurrentUser } from "@/types/auth";

// ─── polling 상수 ─────────────────────────────────────────────────────────────

const POLLING_INTERVAL_MS = 15_000;

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

// ─── Role Badge ───────────────────────────────────────────────────────────────

function RoleBadge({
  currentUser,
  userLoading,
  userError,
}: {
  currentUser: CurrentUser | null;
  userLoading: boolean;
  userError: boolean;
}) {
  if (userLoading) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-[#F3F4F6] text-[#9CA3AF]">
        권한 확인 중…
      </span>
    );
  }
  if (userError || !currentUser) {
    return (
      <span className="inline-flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-[#FEE2E2] text-[#B91C1C] font-medium">
          권한 확인 실패
        </span>
        <span className="text-[11px] text-[#9CA3AF]">
          권한 확인 실패 시 위험 작업은 비활성화됩니다.
        </span>
      </span>
    );
  }
  const label: Record<string, string> = {
    owner: "소유자 권한",
    admin: "관리자 권한",
    viewer: "조회 전용 권한",
  };
  const color: Record<string, string> = {
    owner: "bg-[#FEF3C7] text-[#92400E]",
    admin: "bg-[#DBEAFE] text-[#1E40AF]",
    viewer: "bg-[#F3F4F6] text-[#6B7280]",
  };
  const roleLabel = label[currentUser.role] ?? `${currentUser.role} 권한`;
  const roleColor = color[currentUser.role] ?? "bg-[#F3F4F6] text-[#6B7280]";
  const hint =
    currentUser.role === "viewer"
      ? "조회 전용입니다. 취소·캡처는 admin/owner 권한이 필요합니다."
      : null;
  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium ${roleColor}`}>
        {currentUser.actor && (
          <span className="opacity-70">{currentUser.actor}</span>
        )}
        {currentUser.actor && <span>·</span>}
        {roleLabel}
      </span>
      {hint && (
        <span className="text-[11px] text-[#9CA3AF]">{hint}</span>
      )}
    </span>
  );
}

// ─── Task Action Cell ─────────────────────────────────────────────────────────

interface TaskActionCellProps {
  task: LocalAgentTask;
  canMutate: boolean;
  onCancel: (task: LocalAgentTask) => void;
  onApprovalAction: (task: LocalAgentTask) => void;
  onShowDetail: (task: LocalAgentTask) => void;
}

function TaskActionCell({
  task, canMutate, onCancel, onApprovalAction, onShowDetail,
}: TaskActionCellProps) {
  const btn = cancelButtonProps(task.status);
  const isWaitingApproval = task.status === "waiting_approval";

  return (
    <div className="flex items-center gap-1 flex-wrap">
      <Btn
        variant="ghost"
        size="xs"
        title="작업 상세 보기 (read-only)"
        onClick={() => onShowDetail(task)}
      >
        상세
      </Btn>
      {isWaitingApproval && (
        <Btn
          variant="secondary"
          size="xs"
          disabled={!canMutate}
          title={!canMutate ? "admin/owner 권한 필요" : "작업 승인/거절 처리"}
          onClick={canMutate ? () => onApprovalAction(task) : undefined}
        >
          승인·거절
        </Btn>
      )}
      {btn && (
        <Btn
          variant={btn.variant}
          size="xs"
          disabled={!btn.enabled || !canMutate}
          title={!canMutate ? "admin/owner 권한 필요" : undefined}
          onClick={btn.enabled && canMutate ? () => onCancel(task) : undefined}
        >
          {btn.label}
        </Btn>
      )}
    </div>
  );
}

// ─── Detail Row (read-only, Stage 13B-1) ─────────────────────────────────────

interface DetailRowProps {
  label: string;
  value: string;
  mono?: boolean;
  danger?: boolean;
}

function DetailRow({ label, value, mono, danger }: DetailRowProps) {
  return (
    <div className="flex items-start gap-2">
      <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">{label}</div>
      <div
        className={[
          "flex-1 break-all",
          mono ? "font-mono text-[12px]" : "text-[13px]",
          danger ? "text-[#B91C1C]" : "text-[#111827]",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

// ─── Observe Summary Section (Stage 13B-3B) ──────────────────────────────────

const _STATUS_BADGE_COLOR: Record<string, string> = {
  ok: "bg-[#D1FAE5] text-[#065F46]",
  blocked: "bg-[#FEE2E2] text-[#B91C1C]",
  failed: "bg-[#FEE2E2] text-[#B91C1C]",
};

// page_structure_counts에서 표시 허용 키 (텍스트 원본 제외, count 정수만)
const _PSC_KEYS = [
  "headings", "links", "buttons", "inputs", "forms", "tables",
] as const;

function ObserveSummarySection({ obs }: { obs: ObserveSummary }) {
  const statusColor =
    _STATUS_BADGE_COLOR[obs.status_category ?? ""] ??
    "bg-[#F3F4F6] text-[#6B7280]";

  // page_structure_counts: 허용된 키만, 정수 값만 표시
  const psc = obs.page_structure_counts;
  const pscItems =
    psc && typeof psc === "object"
      ? _PSC_KEYS.flatMap((k) => {
          const v = psc[k];
          return typeof v === "number" ? [{ k, v }] : [];
        })
      : [];

  return (
    <div className="mt-3 pt-3 border-t border-[#E5E7EB]">
      <div className="mb-2 text-[12px] font-semibold text-[#374151]">관찰 요약</div>
      <div className="space-y-1.5">
        {/* 상태 badge */}
        {obs.status_category && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">상태</div>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${statusColor}`}
            >
              {obs.status_category}
            </span>
          </div>
        )}
        {/* 페이지 제목 — text only, 링크화 금지 */}
        {obs.title && (
          <DetailRow label="페이지 제목" value={obs.title} />
        )}
        {/* URL 분류 */}
        {obs.url_category && (
          <DetailRow label="URL 분류" value={obs.url_category} mono />
        )}
        {/* final_url_sanitized — text only, anchor 금지 */}
        {obs.final_url_sanitized && (
          <DetailRow label="최종 URL" value={obs.final_url_sanitized} mono />
        )}
        {/* 로그인 필요 가능성 — true 일 때만 */}
        {obs.login_required_hint === true && (
          <DetailRow label="로그인 감지" value="로그인 필요 가능성 있음" />
        )}
        {/* 관찰 페이지 수 */}
        {obs.pages_observed_count !== null &&
          obs.pages_observed_count !== undefined && (
          <DetailRow
            label="관찰 페이지"
            value={String(obs.pages_observed_count)}
          />
        )}
        {/* 모달 후보 수 — 목록 원문 표시 금지, count만 */}
        {obs.modal_candidates_count !== null &&
          obs.modal_candidates_count !== undefined && (
          <DetailRow
            label="모달 후보"
            value={String(obs.modal_candidates_count)}
          />
        )}
        {/* HTML 축약 여부 — boolean만 */}
        {typeof obs.html_truncated === "boolean" && (
          <DetailRow
            label="HTML 축약"
            value={obs.html_truncated ? "예" : "아니오"}
          />
        )}
        {/* 페이지 구조 카운트 — 원본 구조 금지, count 요약만 */}
        {pscItems.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              페이지 구조
            </div>
            <div className="flex flex-wrap gap-1.5">
              {pscItems.map(({ k, v }) => (
                <span
                  key={k}
                  className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-1.5 py-0.5 rounded"
                >
                  {k}={v}
                </span>
              ))}
            </div>
          </div>
        )}
        {/* 오류/차단 — enum 코드만, danger 색 */}
        {obs.error_category && (
          <DetailRow label="오류 분류" value={obs.error_category} danger />
        )}
        {obs.blocked_reason && (
          <DetailRow label="차단 사유" value={obs.blocked_reason} danger />
        )}
        {/* 관찰 시각 */}
        {obs.observed_at && (
          <DetailRow label="관찰 시각" value={obs.observed_at} />
        )}
      </div>
    </div>
  );
}

// ─── Audit Summary Section (Stage 13C-3B) ───────────────────────────────────

const _AUDIT_STATUS_BADGE_COLOR: Record<string, string> = {
  blocked: "bg-[#FEE2E2] text-[#B91C1C]",
  allowed: "bg-[#D1FAE5] text-[#065F46]",
  denied: "bg-[#FEE2E2] text-[#B91C1C]",
  error: "bg-[#FEE2E2] text-[#B91C1C]",
};

// STORE_AND_DISPLAY fields only — do NOT render STORE_ONLY fields
const _AUDIT_DICT_KEYS = ["policy_decision_counts", "target_kind_counts", "action_kind_counts"] as const;

function AuditSummarySection({ audit }: { audit: AuditSummary }) {
  // count 필드: audit_event_count, allowed/blocked/denied/error_event_count
  const countFields = [
    { label: "감사 이벤트", key: "audit_event_count" as const },
    { label: "허용됨", key: "allowed_event_count" as const },
    { label: "차단됨", key: "blocked_event_count" as const },
    { label: "거절됨", key: "denied_event_count" as const },
    { label: "오류", key: "error_event_count" as const },
  ];

  const countItems = countFields.flatMap(({ label, key }) => {
    const v = audit[key];
    return typeof v === "number" ? [{ label, value: v }] : [];
  });

  // 카테고리 필드: audit_event_categories
  const categories = Array.isArray(audit.audit_event_categories)
    ? audit.audit_event_categories.filter((c) => typeof c === "string")
    : [];

  // 정책 결정 카운트 — policy/target/action_kind_counts
  const dictItems = _AUDIT_DICT_KEYS.flatMap((key) => {
    const dict = audit[key];
    if (!dict || typeof dict !== "object") return [];
    const pairs = Object.entries(dict)
      .filter(([_, v]) => typeof v === "number")
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    return pairs.length > 0 ? [{ label: key.replace(/_/g, " "), pairs }] : [];
  });

  return (
    <div className="mt-3 pt-3 border-t border-[#E5E7EB]">
      <div className="mb-2 text-[12px] font-semibold text-[#374151]">감사 요약</div>
      <div className="space-y-1.5">
        {/* 감사 윈도우 — 시작/종료 시각 */}
        {(audit.audit_window_started_at || audit.audit_window_ended_at) && (
          <>
            {audit.audit_window_started_at && (
              <DetailRow label="감사 시작" value={audit.audit_window_started_at} />
            )}
            {audit.audit_window_ended_at && (
              <DetailRow label="감사 종료" value={audit.audit_window_ended_at} />
            )}
          </>
        )}

        {/* 카운트 필드 — count만 표시 */}
        {countItems.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              이벤트 수
            </div>
            <div className="flex flex-wrap gap-2">
              {countItems.map(({ label, value }) => (
                <span
                  key={label}
                  className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-1.5 py-0.5 rounded"
                >
                  {label}: {value}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 마지막 이벤트 — category 및 status enum만 */}
        {audit.last_event_category && (
          <DetailRow label="마지막 분류" value={audit.last_event_category} mono />
        )}
        {audit.last_event_status && (
          <DetailRow label="마지막 상태" value={audit.last_event_status} mono />
        )}

        {/* 카테고리 목록 — enum text only, 목록 원문 금지 */}
        {categories.length > 0 && (
          <div className="flex items-start gap-2">
            <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
              분류 목록
            </div>
            <div className="flex flex-wrap gap-1.5">
              {categories.map((cat) => (
                <span
                  key={cat}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-[#F3F4F6] text-[#374151]"
                >
                  {cat}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 정책 결정, 대상, 액션 카운트 — dict key=value pairs only */}
        {dictItems.length > 0 && (
          dictItems.map(({ label, pairs }) => (
            <div key={label} className="flex items-start gap-2">
              <div className="w-24 shrink-0 text-[12px] text-[#6B7280]">
                {label}
              </div>
              <div className="font-mono text-[11px] bg-[#F3F4F6] text-[#374151] px-2 py-1 rounded break-all">
                {pairs}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
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

// ─── Diagnostics Section (Stage 13E-3) ─────────────────────────────────────────

function DiagnosticsSection({
  diagnostics,
  error,
}: {
  diagnostics: LocalAgentDiagnostics | null;
  error: string | null;
}) {
  if (!diagnostics && !error) return null;

  if (error) {
    return (
      <div className="mb-6 px-4 py-3 rounded-[8px] border border-[#FEE2E2] bg-[#FEF2F2] text-[12px] text-[#B91C1C]">
        {error}
      </div>
    );
  }

  if (!diagnostics) return null;

  // 상태 배지 색상
  const statusColor = {
    ok: "bg-[#D1FAE5] text-[#065F46]",
    warn: "bg-[#FEF3C7] text-[#92400E]",
    error: "bg-[#FEE2E2] text-[#B91C1C]",
  }[diagnostics.status] || "bg-[#F3F4F6] text-[#6B7280]";

  const repoBoundaryColor = {
    pass: "bg-[#D1FAE5] text-[#065F46]",
    fail: "bg-[#FEE2E2] text-[#B91C1C]",
    not_checked: "bg-[#F3F4F6] text-[#6B7280]",
  }[diagnostics.repo_boundary_status] || "bg-[#F3F4F6] text-[#6B7280]";

  const waitingApprovalColor = diagnostics.tasks.waiting_approval > 0 ? "text-[#B91C1C]" : "";
  const failedColor = diagnostics.tasks.failed > 0 ? "text-[#B91C1C]" : "";

  return (
    <div className="mb-6">
      <div className="text-[13px] font-bold text-[#0F172A] mb-4">운영 진단</div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* 상태 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">진단 상태</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${statusColor}`}>
                {diagnostics.status}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">Repo Boundary</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${repoBoundaryColor}`}>
                {diagnostics.repo_boundary_status}
              </span>
            </div>
          </div>
        </div>

        {/* Agent 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">에이전트 상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">전체</span>
              <span className="text-[13px] font-semibold">{diagnostics.agents.total}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">온라인</span>
              <span className="text-[13px] font-semibold text-[#059669]">{diagnostics.agents.online}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">오프라인/응답지연</span>
              <span className="text-[13px] font-semibold text-[#9CA3AF]">
                {diagnostics.agents.offline + diagnostics.agents.stale}
              </span>
            </div>
          </div>
        </div>

        {/* Task 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">작업 상태</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">전체</span>
              <span className="text-[13px] font-semibold">{diagnostics.tasks.total}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">실행중</span>
              <span className="text-[13px] font-semibold text-[#F97316]">{diagnostics.tasks.running}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-[12px] text-[#6B7280] ${waitingApprovalColor ? "font-semibold" : ""}`}>
                승인대기
              </span>
              <span className={`text-[13px] font-semibold ${waitingApprovalColor}`}>
                {diagnostics.tasks.waiting_approval}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-[12px] text-[#6B7280] ${failedColor ? "font-semibold" : ""}`}>
                실패
              </span>
              <span className={`text-[13px] font-semibold ${failedColor}`}>
                {diagnostics.tasks.failed}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">완료</span>
              <span className="text-[13px] font-semibold text-[#059669]">{diagnostics.tasks.completed}</span>
            </div>
          </div>
        </div>

        {/* Summary 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">요약 정보</div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">결과 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_result_summary}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">관찰 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_observe_summary}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-[#6B7280]">감사 요약</span>
              <span className="text-[13px] font-semibold">{diagnostics.summaries.with_audit_summary}</span>
            </div>
          </div>
        </div>

        {/* Latest 카드 */}
        <div className="bg-white border border-[#E5E7EB] rounded-[8px] p-4">
          <div className="text-[11px] font-semibold text-[#6B7280] mb-3">최근 작업</div>
          <div className="space-y-2 text-[11px]">
            {diagnostics.latest.task_status && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">상태</span>
                <span className="font-semibold">{diagnostics.latest.task_status}</span>
              </div>
            )}
            {diagnostics.latest.task_created_at && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">생성</span>
                <span className="font-mono text-[10px]">{diagnostics.latest.task_created_at.split("T")[0]}</span>
              </div>
            )}
            {diagnostics.latest.task_updated_at && (
              <div className="flex items-center justify-between">
                <span className="text-[#6B7280]">업데이트</span>
                <span className="font-mono text-[10px]">{diagnostics.latest.task_updated_at.split("T")[0]}</span>
              </div>
            )}
          </div>
        </div>

        {/* Warnings 카드 */}
        {diagnostics.warnings.length > 0 && (
          <div className="bg-white border border-[#FEE2E2] rounded-[8px] p-4">
            <div className="text-[11px] font-semibold text-[#B91C1C] mb-3">경고</div>
            <div className="flex flex-wrap gap-1.5">
              {diagnostics.warnings.map((warning) => (
                <span
                  key={warning}
                  className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-[#FEE2E2] text-[#B91C1C]"
                >
                  {warning}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Role-aware 공통 오류 메시지 ──────────────────────────────────────────────

function roleAwareAuthMessage(status: 401 | 403, role: string | undefined): string {
  if (status === 401) return "로그인이 필요합니다. 브라우저 인증 상태를 확인하세요.";
  if (role === "viewer") return "조회 전용 권한입니다. admin/owner 권한이 필요합니다.";
  if (!role) return "권한 확인이 필요합니다. admin/owner 권한이 필요합니다.";
  return "권한이 없습니다. 서버 권한 정책을 확인하세요.";
}

// ─── Cancel Error 메시지 ──────────────────────────────────────────────────────

function cancelErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400: return "취소 사유는 최대 200자입니다.";
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "작업을 찾을 수 없습니다.";
      case 409: return "이미 취소되었거나 종료된 작업입니다.";
      default: return "취소 요청에 실패했습니다.";
    }
  }
  return "취소 요청에 실패했습니다.";
}

// ─── Approval Error 메시지 ───────────────────────────────────────────────────

function approvalErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 400: return "요청이 유효하지 않습니다. (작업 상태 또는 token_id 확인 필요)";
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "작업 또는 승인 토큰을 찾을 수 없습니다.";
      case 409: return "이미 처리된 승인 요청입니다.";
      case 410: return "승인 토큰이 만료되었습니다. 새로운 요청을 생성하세요.";
      case 429: return "승인 요청이 너무 많습니다. 잠시 후 재시도하세요.";
      default: return `승인 처리에 실패했습니다. (HTTP ${err.status})`;
    }
  }
  return "승인 처리에 실패했습니다.";
}

// ─── Capture Error 메시지 ─────────────────────────────────────────────────────

function captureErrorMessage(err: unknown, role?: string): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
      case 403: return roleAwareAuthMessage(err.status, role);
      case 404: return "에이전트를 찾을 수 없습니다.";
      default: return `캡처 요청에 실패했습니다. (HTTP ${err.status})`;
    }
  }
  return "캡처 요청에 실패했습니다.";
}

// ─── 조회 Error 메시지 ────────────────────────────────────────────────────────

function fetchErrorMessage(err: unknown, fallback: string, role?: string): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return roleAwareAuthMessage(401, role);
    if (err.status === 403) return roleAwareAuthMessage(403, role);
    return `API ${err.status}: ${err.message}`;
  }
  return fallback;
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

// ─── 시각 포맷 ────────────────────────────────────────────────────────────────

function formatTime(date: Date): string {
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ─── Main Client Component ────────────────────────────────────────────────────

export default function LocalAgentsClient() {
  // ── current user ──────────────────────────────────────────────────────────
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  const [userError, setUserError] = useState(false);

  // ── diagnostics ──────────────────────────────────────────────────────────────
  const [diagnostics, setDiagnostics] = useState<LocalAgentDiagnostics | null>(null);
  const [diagnosticsError, setDiagnosticsError] = useState<string | null>(null);

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

  // ── task detail (read-only) modal — Stage 13B-1 ───────────────────────────
  const [detailTargetTask, setDetailTargetTask] = useState<LocalAgentTask | null>(null);
  const [detailData, setDetailData] = useState<LocalAgentTaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // ── capture state ─────────────────────────────────────────────────────────
  const [captureTargetAgent, setCaptureTargetAgent] = useState<LocalAgent | null>(null);
  const [captureMode, setCaptureMode] = useState<"dry_run" | "real" | null>(null);
  const [captureLoading, setCaptureLoading] = useState(false);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [captureSuccess, setCaptureSuccess] = useState<CaptureSuccessInfo | null>(null);
  const [captureReason, setCaptureReason] = useState<string>("");

  // ── approval state ────────────────────────────────────────────────────────
  const [approvalTargetTask, setApprovalTargetTask] = useState<LocalAgentTask | null>(null);
  const [approvalAction, setApprovalAction] = useState<"approve" | "reject" | null>(null);
  const [approvalReason, setApprovalReason] = useState<string>("");
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const approvalModalOpenRef = useRef(false);

  // ── polling state ─────────────────────────────────────────────────────────
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(true);
  const [isDocumentHidden, setIsDocumentHidden] = useState(false);

  // ── polling refs ──────────────────────────────────────────────────────────
  const isPollingAgentsRef = useRef(false);
  const isPollingTasksRef = useRef(false);
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingEnabledRef = useRef(true);
  const prevPollingEnabledRef = useRef(true);

  // stale-closure 방지: interval 내에서 최신 state 참조용 ref
  const selectedAgentIdRef = useRef<string | null>(null);
  const taskStatusFilterRef = useRef<string>("");
  const cancelModalOpenRef = useRef(false);
  const captureModalOpenRef = useRef(false);

  useEffect(() => { selectedAgentIdRef.current = selectedAgentId; }, [selectedAgentId]);
  useEffect(() => { taskStatusFilterRef.current = taskStatusFilter; }, [taskStatusFilter]);
  useEffect(() => { cancelModalOpenRef.current = cancelTargetTask !== null; }, [cancelTargetTask]);
  useEffect(() => {
    captureModalOpenRef.current = captureMode === "real" && captureTargetAgent !== null;
  }, [captureMode, captureTargetAgent]);
  useEffect(() => {
    approvalModalOpenRef.current = approvalTargetTask !== null;
  }, [approvalTargetTask]);
  useEffect(() => { pollingEnabledRef.current = pollingEnabled; }, [pollingEnabled]);

  // ── diagnostics fetch ────────────────────────────────────────────────────────
  const fetchDiagnostics = useCallback(async () => {
    setDiagnosticsError(null);
    try {
      const res = await getLocalAgentsDiagnostics();
      setDiagnostics(res.diagnostics);
    } catch (err) {
      setDiagnosticsError(
        fetchErrorMessage(err, "진단 정보를 불러올 수 없음", currentUser?.role)
      );
    }
  }, [currentUser?.role]);

  // ── agent 목록 fetch (최초 로딩 / 수동 새로고침) ──────────────────────────
  const fetchAgents = useCallback(async () => {
    setAgentsLoading(true);
    setAgentsError(null);
    try {
      const data = await getLocalAgents();
      setAgents(data.agents);
      if (data.agents.length > 0) {
        setSelectedAgentId((prev) => prev ?? data.agents[0].agent_id);
      }
      setLastRefreshedAt(new Date());
    } catch (err) {
      setAgentsError(fetchErrorMessage(err, "에이전트 목록 조회 실패", currentUser?.role));
    } finally {
      setAgentsLoading(false);
    }
  }, [currentUser?.role]);

  useEffect(() => {
    let cancelled = false;
    setUserLoading(true);
    setUserError(false);
    getCurrentUser()
      .then((u) => { if (!cancelled) { setCurrentUser(u); setUserLoading(false); } })
      .catch(() => { if (!cancelled) { setUserError(true); setUserLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    fetchAgents();
    fetchDiagnostics();
  }, [fetchAgents, fetchDiagnostics]);

  // ── task 목록 fetch (최초 로딩 / 수동 새로고침) ───────────────────────────
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
      setLastRefreshedAt(new Date());
    } catch (err) {
      setTasksError(fetchErrorMessage(err, "작업 목록 조회 실패", currentUser?.role));
      setTasks([]);
      setTasksTotal(0);
    } finally {
      setTasksLoading(false);
    }
  }, [currentUser?.role]);

  useEffect(() => {
    if (selectedAgentId) {
      fetchTasks(selectedAgentId, taskStatusFilter);
    }
  }, [selectedAgentId, taskStatusFilter, fetchTasks]);

  // ── background fetch (polling 전용) ───────────────────────────────────────
  // agentsLoading/tasksLoading을 변경하지 않음 — loading skeleton 깜빡임 없음

  const backgroundFetchAgents = useCallback(async () => {
    if (isPollingAgentsRef.current) return;
    isPollingAgentsRef.current = true;
    try {
      const [agentsData, diagData] = await Promise.all([
        getLocalAgents(),
        getLocalAgentsDiagnostics().catch(() => null),
      ]);
      setAgents(agentsData.agents);
      if (diagData) {
        setDiagnostics(diagData.diagnostics);
        setDiagnosticsError(null);
      }
      setLastRefreshedAt(new Date());
      setPollingError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? `API ${err.status}` : "네트워크 오류";
      setPollingError(`자동 새로고침 실패: ${msg}`);
    } finally {
      isPollingAgentsRef.current = false;
    }
  }, []);

  const backgroundFetchTasks = useCallback(async (agentId: string, status: string) => {
    if (isPollingTasksRef.current) return;
    isPollingTasksRef.current = true;
    try {
      const data = await getAgentTasks(agentId, {
        limit: 50,
        status: status || undefined,
      });
      setTasks(data.tasks);
      setTasksTotal(data.total);
      setLastRefreshedAt(new Date());
      setPollingError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? `API ${err.status}` : "네트워크 오류";
      setPollingError(`자동 새로고침 실패: ${msg}`);
    } finally {
      isPollingTasksRef.current = false;
    }
  }, []);

  // ── polling interval ──────────────────────────────────────────────────────

  useEffect(() => {
    if (!pollingEnabled) return;

    const tick = () => {
      if (document.hidden) return;
      if (!pollingEnabledRef.current) return;

      const captureOpen = captureModalOpenRef.current;
      const cancelOpen = cancelModalOpenRef.current;
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;

      if (!captureOpen) {
        backgroundFetchAgents();
      }
      if (!captureOpen && !cancelOpen && agentId) {
        backgroundFetchTasks(agentId, statusFilter);
      }
    };

    pollingIntervalRef.current = setInterval(tick, POLLING_INTERVAL_MS);

    return () => {
      if (pollingIntervalRef.current !== null) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [pollingEnabled, backgroundFetchAgents, backgroundFetchTasks]);

  // ── ON 복귀 시 즉시 background refresh 1회 ───────────────────────────────

  useEffect(() => {
    if (pollingEnabled && !prevPollingEnabledRef.current) {
      backgroundFetchAgents();
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;
      if (agentId) backgroundFetchTasks(agentId, statusFilter);
    }
    prevPollingEnabledRef.current = pollingEnabled;
  }, [pollingEnabled, backgroundFetchAgents, backgroundFetchTasks]);

  // ── visibilitychange: 탭 복귀 시 즉시 background refresh ──────────────────

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsDocumentHidden(document.hidden);
      if (document.hidden) return;
      if (!pollingEnabledRef.current) return;

      const captureOpen = captureModalOpenRef.current;
      const cancelOpen = cancelModalOpenRef.current;
      const agentId = selectedAgentIdRef.current;
      const statusFilter = taskStatusFilterRef.current;

      if (!captureOpen) {
        backgroundFetchAgents();
      }
      if (!captureOpen && !cancelOpen && agentId) {
        backgroundFetchTasks(agentId, statusFilter);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [backgroundFetchAgents, backgroundFetchTasks]);

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
      setCancelError(cancelErrorMessage(err, currentUser?.role));
    } finally {
      setCancelLoading(false);
    }
  }, [cancelTargetTask, selectedAgentId, cancelReason, taskStatusFilter, fetchTasks, fetchAgents, currentUser?.role]);

  const handleCancelClose = useCallback(() => {
    if (cancelLoading) return;
    setCancelTargetTask(null);
    setCancelReason("");
    setCancelError(null);
  }, [cancelLoading]);

  // ── approval: modal open ──────────────────────────────────────────────────
  const handleOpenApprovalModal = useCallback((task: LocalAgentTask) => {
    setApprovalTargetTask(task);
    setApprovalAction(null);
    setApprovalReason("");
    setApprovalError(null);
  }, []);

  // ── task detail (read-only) — Stage 13B-1 ─────────────────────────────────
  const handleOpenDetail = useCallback(async (task: LocalAgentTask) => {
    if (!selectedAgentId) return;
    setDetailTargetTask(task);
    setDetailData(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const detail = await getLocalAgentTask(selectedAgentId, task.task_id);
      setDetailData(detail);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 403) {
          setDetailError(roleAwareAuthMessage(err.status as 401 | 403, currentUser?.role));
        } else if (err.status === 404) {
          setDetailError("작업을 찾을 수 없습니다.");
        } else {
          setDetailError("작업 상세 조회에 실패했습니다.");
        }
      } else {
        setDetailError("작업 상세 조회에 실패했습니다.");
      }
    } finally {
      setDetailLoading(false);
    }
  }, [selectedAgentId, currentUser?.role]);

  const handleCloseDetail = useCallback(() => {
    setDetailTargetTask(null);
    setDetailData(null);
    setDetailError(null);
    setDetailLoading(false);
  }, []);

  const handleCloseApprovalModal = useCallback(() => {
    if (approvalLoading) return;
    setApprovalTargetTask(null);
    setApprovalAction(null);
    setApprovalReason("");
    setApprovalError(null);
  }, [approvalLoading]);

  // ── approval: submit ──────────────────────────────────────────────────────
  const handleApprovalSubmit = useCallback(async () => {
    if (!approvalTargetTask || !approvalAction || !selectedAgentId) return;
    setApprovalLoading(true);
    setApprovalError(null);
    try {
      // 개별 조회로 token_id 취득 (to_list_safe에는 없음)
      const detail = await getLocalAgentTask(selectedAgentId, approvalTargetTask.task_id);
      if (!detail.token_id) {
        setApprovalError("승인 토큰을 찾을 수 없습니다. 작업 상태를 확인하세요.");
        return;
      }
      const body = {
        token_id: detail.token_id,
        reason: approvalReason.trim() || undefined,
      };
      if (approvalAction === "approve") {
        await approveLocalAgentTask(selectedAgentId, approvalTargetTask.task_id, body);
      } else {
        await rejectLocalAgentTask(selectedAgentId, approvalTargetTask.task_id, body);
      }
      setApprovalTargetTask(null);
      setApprovalAction(null);
      setApprovalReason("");
      await Promise.all([
        fetchTasks(selectedAgentId, taskStatusFilter),
        fetchAgents(),
      ]);
    } catch (err) {
      setApprovalError(approvalErrorMessage(err, currentUser?.role));
    } finally {
      setApprovalLoading(false);
    }
  }, [
    approvalTargetTask, approvalAction, approvalReason, selectedAgentId,
    taskStatusFilter, fetchTasks, fetchAgents, currentUser?.role,
  ]);

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
      setCaptureError(captureErrorMessage(err, currentUser?.role));
    } finally {
      setCaptureLoading(false);
    }
  }, [currentUser?.role]);

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
      setCaptureError(captureErrorMessage(err, currentUser?.role));
    } finally {
      setCaptureLoading(false);
    }
  }, [captureTargetAgent, captureReason, selectedAgentId, taskStatusFilter, fetchAgents, fetchTasks, currentUser?.role]);

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
  const captureModalOpen = captureMode === "real" && captureTargetAgent !== null;
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
                  const captureEnabled = agentOnline && canMutate && !captureLoading;
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
                            onClick={captureEnabled ? () => handleDryRun(agent) : undefined}
                          >
                            사전 점검
                          </Btn>
                          <Btn
                            variant="ghost"
                            size="xs"
                            disabled={!captureEnabled}
                            title={captureTitle}
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
                      <TaskActionCell
                        task={task}
                        canMutate={canMutate}
                        onCancel={setCancelTargetTask}
                        onApprovalAction={handleOpenApprovalModal}
                        onShowDetail={handleOpenDetail}
                      />
                    </AdminTd>
                  </AdminTr>
                ))
              )}
            </AdminTbody>
          </AdminTable>
        )}
      </div>

      {/* ── Task Detail (read-only) Modal — Stage 13B-1 ───────────────────── */}
      <Modal
        open={detailTargetTask !== null}
        title="작업 상세 (read-only)"
        onClose={handleCloseDetail}
        footer={
          <Btn variant="ghost" size="sm" onClick={handleCloseDetail}>
            닫기
          </Btn>
        }
      >
        {detailLoading && (
          <p className="text-[13px] text-[#6B7280]">불러오는 중…</p>
        )}
        {detailError && (
          <p className="text-[13px] text-[#B91C1C]">{detailError}</p>
        )}
        {!detailLoading && !detailError && detailData && (
          <div className="space-y-2 text-[13px] text-[#374151]">
            <DetailRow label="작업 ID" value={detailData.task_id} mono />
            <DetailRow label="에이전트 ID" value={detailData.agent_id} mono />
            <DetailRow label="액션" value={detailData.action} />
            <DetailRow label="위험도" value={detailData.risk_level} />
            <DetailRow label="상태" value={detailData.status} />
            <DetailRow label="요청자" value={detailData.requested_by} />
            <DetailRow label="생성" value={detailData.created_at} />
            <DetailRow label="갱신" value={detailData.updated_at} />
            <DetailRow label="전달" value={detailData.delivered_at ?? "—"} />
            <DetailRow label="시작" value={detailData.started_at ?? "—"} />
            <DetailRow label="완료" value={detailData.completed_at ?? "—"} />
            <DetailRow label="결과 요약" value={detailData.result_summary ?? "—"} />
            {detailData.error_summary && (
              <DetailRow label="오류 요약" value={detailData.error_summary} danger />
            )}
            {detailData.failure_reason && (
              <DetailRow label="실패 사유" value={detailData.failure_reason} danger />
            )}
            {detailData.timed_out_at && (
              <DetailRow label="타임아웃" value={detailData.timed_out_at} danger />
            )}
            {detailData.approved_at && (
              <DetailRow
                label="승인"
                value={`${detailData.approved_at}${detailData.approved_by ? " · " + detailData.approved_by : ""}`}
              />
            )}
            {detailData.rejected_at && (
              <DetailRow
                label="거절"
                value={`${detailData.rejected_at}${detailData.reject_reason ? " · " + detailData.reject_reason : ""}`}
                danger
              />
            )}
            {detailData.cancel_requested_at && (
              <DetailRow
                label="취소 요청"
                value={`${detailData.cancel_requested_at}${detailData.cancel_requested_by ? " · " + detailData.cancel_requested_by : ""}`}
              />
            )}
            {detailData.cancelled_at && (
              <DetailRow label="취소 완료" value={detailData.cancelled_at} />
            )}
            {detailData.cancel_reason && (
              <DetailRow label="취소 사유" value={detailData.cancel_reason} />
            )}
            {/* 관찰 요약 섹션 — observe_summary가 있을 때만 표시 */}
            {detailData.observe_summary && (
              <ObserveSummarySection obs={detailData.observe_summary} />
            )}
            {/* 감사 요약 섹션 — audit_summary가 있을 때만 표시 */}
            {detailData.audit_summary && (
              <AuditSummarySection audit={detailData.audit_summary} />
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

      {/* ── Approval Modal ───────────────────────────────────────────────────── */}
      <Modal
        open={approvalTargetTask !== null}
        title="작업 승인 / 거절"
        onClose={handleCloseApprovalModal}
        footer={
          <>
            <Btn variant="ghost" size="sm" onClick={handleCloseApprovalModal} disabled={approvalLoading}>
              닫기
            </Btn>
            <Btn
              variant="danger"
              size="sm"
              disabled={approvalLoading || approvalAction !== "reject"}
              onClick={approvalAction === "reject" ? handleApprovalSubmit : undefined}
            >
              {approvalLoading && approvalAction === "reject" ? "처리 중…" : "거절 확인"}
            </Btn>
            <Btn
              variant="orange"
              size="sm"
              disabled={approvalLoading || approvalAction !== "approve"}
              onClick={approvalAction === "approve" ? handleApprovalSubmit : undefined}
            >
              {approvalLoading && approvalAction === "approve" ? "처리 중…" : "승인 확인"}
            </Btn>
          </>
        }
      >
        <p className="text-[12px] text-[#6B7280] mb-2">
          이 버튼은 작업 실행 버튼이 아닙니다. 승인 시 작업이 에이전트에 전달되어 실행됩니다.
        </p>

        {approvalTargetTask && (
          <div className="mb-3 text-[12px] text-[#6B7280] font-mono bg-[#F3F4F6] rounded px-3 py-2">
            {approvalTargetTask.task_id} — {approvalTargetTask.action} &nbsp;
            <StatusBadge status={approvalTargetTask.risk_level} />
          </div>
        )}

        <div className="flex gap-2 mb-3">
          <Btn
            variant={approvalAction === "approve" ? "orange" : "ghost"}
            size="sm"
            disabled={approvalLoading}
            onClick={() => { setApprovalAction("approve"); setApprovalError(null); }}
          >
            승인
          </Btn>
          <Btn
            variant={approvalAction === "reject" ? "danger" : "ghost"}
            size="sm"
            disabled={approvalLoading}
            onClick={() => { setApprovalAction("reject"); setApprovalError(null); }}
          >
            거절
          </Btn>
        </div>

        {approvalAction === "reject" && (
          <>
            <textarea
              className="w-full border border-[#E5E7EB] rounded px-3 py-2 text-[13px] text-[#374151] resize-none focus:outline-none focus:ring-1 focus:ring-[#F97316]"
              rows={2}
              maxLength={200}
              placeholder="선택 사항 — 거절 사유 (최대 200자)"
              value={approvalReason}
              onChange={(e) => { setApprovalReason(e.target.value); setApprovalError(null); }}
            />
            <div className="flex justify-between mt-1 mb-2">
              <span className="text-[11px] text-[#9CA3AF]">비밀번호·토큰 등 민감한 정보는 입력하지 마세요.</span>
              <span className={`text-[11px] ${approvalReason.length > 200 ? "text-[#B91C1C] font-semibold" : "text-[#9CA3AF]"}`}>
                {approvalReason.length}/200
              </span>
            </div>
          </>
        )}

        {approvalError && (
          <p className="mt-2 text-[12px] text-[#B91C1C]">{approvalError}</p>
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
