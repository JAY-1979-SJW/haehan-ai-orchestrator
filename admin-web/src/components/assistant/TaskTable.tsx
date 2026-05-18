/** TaskTable — 작업 큐 테이블 (APP_TASK_QUEUE_READONLY_LIST_POLISH_01)
 * read-only. execute/approve/reject 버튼 없음. token 원문 표시 금지.
 */
"use client";
import { useState } from "react";
import Link from "next/link";
import type { AssistantTask, ActionRisk } from "@/types/assistant";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";

// ── 상태 badge 매핑 ─────────────────────────────────────────────────────────
const STATUS_BADGE_MAP: Record<string, string> = {
  DRY_RUN:               "dry_run",
  BLOCKED:               "blocked",
  APPROVAL_DISPLAY_ONLY: "waiting_approval",
  READ_ONLY:             "queued",
  FUTURE:                "hold",
  ERROR:                 "failed",
  PENDING:               "queued",
};

// ── Dry-run badge ────────────────────────────────────────────────────────────
function DryRunBadge({ task }: { task: AssistantTask }) {
  if (task.dry_run === true) {
    return (
      <span className="inline-flex items-center text-[10px] font-mono bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-1.5 py-0.5 rounded">
        DRY_RUN
      </span>
    );
  }
  if (task.dry_run === null && task.allowed === false) {
    return (
      <span className="inline-flex items-center text-[10px] font-mono bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] px-1.5 py-0.5 rounded">
        TOKEN_BLOCKED
      </span>
    );
  }
  if (task.dry_run === null) {
    return (
      <span className="inline-flex items-center text-[10px] font-mono bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB] px-1.5 py-0.5 rounded">
        DRY_RUN_SAFE
      </span>
    );
  }
  return (
    <span className="inline-flex items-center text-[10px] font-mono bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A] px-1.5 py-0.5 rounded">
      ⚠ DRY_RUN=false
    </span>
  );
}

// ── Token display (redacted) ─────────────────────────────────────────────────
function TokenDisplay({ task }: { task: AssistantTask }) {
  if (task.approval_token_id === "redacted") {
    return (
      <span className="text-[10px] font-mono text-[#6D28D9] bg-[#F5F3FF] px-1.5 py-0.5 rounded border border-[#DDD6FE]">
        존재: redacted
      </span>
    );
  }
  if (task.approval_token_exists) {
    return (
      <span className="text-[10px] font-mono text-[#6D28D9] bg-[#F5F3FF] px-1.5 py-0.5 rounded border border-[#DDD6FE]">
        존재: redacted
      </span>
    );
  }
  return <span className="text-[10px] text-[#9CA3AF]">발행 없음</span>;
}

// ── 필터 버튼 ────────────────────────────────────────────────────────────────
const RISK_FILTERS: { value: ActionRisk | "ALL"; label: string }[] = [
  { value: "ALL", label: "전체" },
  { value: "LOW", label: "낮음" },
  { value: "MEDIUM", label: "보통" },
  { value: "HIGH", label: "높음" },
  { value: "CRITICAL", label: "위험" },
];

const STATUS_FILTERS = [
  { value: "ALL", label: "전체" },
  { value: "DRY_RUN", label: "DRY_RUN" },
  { value: "BLOCKED", label: "BLOCKED" },
  { value: "APPROVAL_DISPLAY_ONLY", label: "승인대기" },
  { value: "READ_ONLY", label: "읽기전용" },
  { value: "FUTURE", label: "예정" },
];

// ── TaskStatusLegend ─────────────────────────────────────────────────────────
function TaskStatusLegend() {
  return (
    <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#6B7280] border-t border-[#F3F4F6] pt-2 mt-2">
      <span className="bg-[#EFF6FF] text-[#1D4ED8] px-1.5 py-0.5 rounded border border-[#BFDBFE]">DRY_RUN</span>
      <span className="bg-[#FEF2F2] text-[#B91C1C] px-1.5 py-0.5 rounded border border-[#FECACA]">TOKEN_BLOCKED</span>
      <span className="bg-[#F3F4F6] text-[#6B7280] px-1.5 py-0.5 rounded border border-[#E5E7EB]">DRY_RUN_SAFE</span>
      <span className="text-[#9CA3AF]">— approve/execute 연결 없음 (B-1, B-2)</span>
    </div>
  );
}

// ── 메인 컴포넌트 ─────────────────────────────────────────────────────────────
export function TaskTable({ tasks }: { tasks: AssistantTask[] }) {
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const filtered = tasks.filter((t) => {
    const riskOk = riskFilter === "ALL" || t.risk === riskFilter;
    const statusOk = statusFilter === "ALL" || t.status === statusFilter;
    return riskOk && statusOk;
  });

  return (
    <div className="space-y-3">
      {/* 필터바 */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-[#9CA3AF] font-mono mr-1">위험도:</span>
          {RISK_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setRiskFilter(f.value)}
              className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
                riskFilter === f.value
                  ? "bg-[#1D4ED8] text-white border-[#1D4ED8]"
                  : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F3F4F6]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-[#9CA3AF] font-mono mr-1">상태:</span>
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`text-[10px] px-2 py-0.5 rounded border font-mono transition-colors ${
                statusFilter === f.value
                  ? "bg-[#6D28D9] text-white border-[#6D28D9]"
                  : "bg-white text-[#6B7280] border-[#E5E7EB] hover:bg-[#F3F4F6]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-[10px] font-mono text-[#9CA3AF] self-center ml-auto">
          {filtered.length}/{tasks.length}건 표시
        </span>
      </div>

      {/* 빈 상태 */}
      {filtered.length === 0 && (
        <div className="text-sm text-[#9CA3AF] py-8 text-center rounded-lg border border-[#E5E7EB] bg-[#F9FAFB]">
          현재 표시할 작업이 없습니다. <span className="font-mono text-[10px]">READ_ONLY</span>
        </div>
      )}

      {/* 테이블 */}
      {filtered.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-[#E5E7EB]">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-[#F9FAFB] border-b border-[#E5E7EB] text-[10px] text-[#6B7280] uppercase tracking-wide">
                <th className="text-left py-2.5 px-3">작업</th>
                <th className="text-left py-2.5 px-3">상태</th>
                <th className="text-left py-2.5 px-3">위험도</th>
                <th className="text-left py-2.5 px-3">제공자</th>
                <th className="text-left py-2.5 px-3">유형</th>
                <th className="text-left py-2.5 px-3">드라이런</th>
                <th className="text-left py-2.5 px-3">토큰</th>
                <th className="text-left py-2.5 px-3">요약</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((task) => (
                <tr key={task.id} className="border-b border-[#F3F4F6] hover:bg-[#FAFAFA] transition-colors">
                  <td className="py-2.5 px-3 min-w-[160px]">
                    <Link
                      href={`/assistant/tasks/${task.id}`}
                      className="text-[#1D4ED8] hover:underline font-medium text-xs leading-tight"
                    >
                      {task.title}
                    </Link>
                    {task.blocked_reasons && task.blocked_reasons.length > 0 && (
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {task.blocked_reasons.map((r) => (
                          <span key={r} className="text-[9px] font-mono bg-[#FEF2F2] text-[#B91C1C] px-1 py-0.5 rounded">
                            {r}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="py-2.5 px-3">
                    <StatusBadge status={STATUS_BADGE_MAP[task.status] ?? task.status.toLowerCase()} />
                  </td>
                  <td className="py-2.5 px-3">
                    <RiskBadge level={task.risk.toLowerCase() as "low" | "medium" | "high" | "critical"} />
                  </td>
                  <td className="py-2.5 px-3 font-mono text-[10px] text-[#6B7280]">{task.provider}</td>
                  <td className="py-2.5 px-3 font-mono text-[10px] text-[#9CA3AF]">{task.action_type}</td>
                  <td className="py-2.5 px-3">
                    <DryRunBadge task={task} />
                  </td>
                  <td className="py-2.5 px-3">
                    <TokenDisplay task={task} />
                  </td>
                  <td className="py-2.5 px-3 text-[11px] text-[#6B7280] max-w-[200px] truncate" title={task.summary}>
                    {task.summary ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TaskStatusLegend />
    </div>
  );
}
