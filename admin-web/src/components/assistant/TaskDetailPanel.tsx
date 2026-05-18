/** TaskDetailPanel — 작업 상세 (APP_TASK_DETAIL_READONLY_POLISH_01)
 * read-only. execute/approve/reject/delete 버튼 없음. token 원문 표시 금지.
 */
"use client";
import { useState } from "react";
import type { AssistantTask } from "@/types/assistant";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";

// ── 상태 badge 매핑 ────────────────────────────────────────────────────────
const STATUS_BADGE_MAP: Record<string, string> = {
  DRY_RUN:               "dry_run",
  BLOCKED:               "blocked",
  APPROVAL_DISPLAY_ONLY: "waiting_approval",
  READ_ONLY:             "queued",
  FUTURE:                "hold",
  ERROR:                 "failed",
  PENDING:               "queued",
};

// ── 값 없음 fallback ───────────────────────────────────────────────────────
function Empty({ label = "없음" }: { label?: string }) {
  return <span className="text-[#9CA3AF] italic text-[11px]">{label}</span>;
}

// ── 필드 행 ────────────────────────────────────────────────────────────────
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-1 border-b border-[#F9FAFB]">
      <dt className="text-[#6B7280] text-xs w-36 shrink-0">{label}</dt>
      <dd className="text-xs text-[#374151] min-w-0">{children}</dd>
    </div>
  );
}

// ── 섹션 헤더 ──────────────────────────────────────────────────────────────
function SectionHeader({ title, badge }: { title: string; badge?: string }) {
  return (
    <div className="flex items-center gap-2 mt-4 mb-1">
      <span className="text-sm font-semibold text-[#111827]">{title}</span>
      {badge && (
        <span className="text-[10px] font-mono bg-[#F3F4F6] text-[#6B7280] px-1.5 py-0.5 rounded border border-[#E5E7EB]">
          {badge}
        </span>
      )}
    </div>
  );
}

// ── 접기/펼치기 JSON viewer ─────────────────────────────────────────────────
function JsonViewer({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  const json = JSON.stringify(data, null, 2);
  return (
    <div className="rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-2 mt-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-[10px] font-mono text-[#6B7280] hover:text-[#374151] flex items-center gap-1"
      >
        <span>{open ? "▼" : "▶"}</span>
        <span>{label}</span>
        <span className="ml-1 text-[#9CA3AF]">({json.length}자)</span>
      </button>
      {open && (
        <pre className="mt-2 text-[10px] font-mono text-[#374151] overflow-x-auto whitespace-pre-wrap break-all max-h-48">
          {json}
        </pre>
      )}
    </div>
  );
}

// ── DryRun 뱃지 ────────────────────────────────────────────────────────────
function DryRunInfo({ task }: { task: AssistantTask }) {
  if (task.dry_run === true)
    return <span className="text-[#1D4ED8] font-mono text-[10px] bg-[#EFF6FF] px-1.5 py-0.5 rounded border border-[#BFDBFE]">DRY_RUN</span>;
  if (task.dry_run === null && task.allowed === false)
    return <span className="text-[#B91C1C] font-mono text-[10px] bg-[#FEF2F2] px-1.5 py-0.5 rounded border border-[#FECACA]">TOKEN_BLOCKED</span>;
  if (task.dry_run === null)
    return <span className="text-[#6B7280] font-mono text-[10px] bg-[#F3F4F6] px-1.5 py-0.5 rounded border border-[#E5E7EB]">DRY_RUN_SAFE</span>;
  return <span className="text-[#92400E] font-mono text-[10px] bg-[#FEF3C7] px-1.5 py-0.5 rounded border border-[#FDE68A]">⚠ DRY_RUN=false</span>;
}

// ── 메인 컴포넌트 ──────────────────────────────────────────────────────────
export function TaskDetailPanel({ task }: { task: AssistantTask }) {
  return (
    <div className="space-y-2">
      {/* ── 기본 정보 카드 ── */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div>
            <p className="text-base font-semibold text-[#111827] leading-snug">{task.title}</p>
            <p className="text-[10px] font-mono text-[#9CA3AF] mt-0.5">{task.id}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <StatusBadge status={STATUS_BADGE_MAP[task.status] ?? task.status.toLowerCase()} />
            <RiskBadge level={task.risk.toLowerCase() as "low" | "medium" | "high" | "critical"} />
          </div>
        </div>

        <SectionHeader title="기본 정보" badge="READ_ONLY" />
        <dl className="space-y-0">
          <Field label="작업 ID">{task.id}</Field>
          <Field label="제목">{task.title}</Field>
          <Field label="상태">
            <StatusBadge status={STATUS_BADGE_MAP[task.status] ?? task.status.toLowerCase()} />
          </Field>
          <Field label="위험도">
            <RiskBadge level={task.risk.toLowerCase() as "low" | "medium" | "high" | "critical"} />
          </Field>
          <Field label="제공자"><span className="font-mono">{task.provider}</span></Field>
          <Field label="작업 유형"><span className="font-mono">{task.action_type}</span></Field>
          <Field label="드라이런"><DryRunInfo task={task} /></Field>
          <Field label="생성일시"><span className="font-mono">{task.created_at}</span></Field>
          <Field label="수정일시"><span className="font-mono">{task.updated_at}</span></Field>
        </dl>
      </div>

      {/* ── 요약 & 승인 정보 ── */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <SectionHeader title="요약 / 승인 정보" />
        <dl className="space-y-0">
          <Field label="요약">
            {task.summary ? task.summary : <Empty label="요약 없음" />}
          </Field>
          <Field label="실행 허용">
            {task.allowed === undefined ? <Empty /> : task.allowed
              ? <span className="text-[#059669] font-mono text-[10px]">ALLOWED</span>
              : <span className="text-[#B91C1C] font-mono text-[10px]">NOT_ALLOWED</span>}
          </Field>
          <Field label="승인 필요">
            {task.requires_approval === undefined ? <Empty /> : task.requires_approval
              ? <span className="text-[#D97706] font-mono text-[10px]">REQUIRES_APPROVAL</span>
              : <span className="text-[#6B7280] font-mono text-[10px]">AUTO_OK</span>}
          </Field>
          <Field label="승인 토큰">
            {task.approval_token_id === "redacted"
              ? <span className="text-[#6D28D9] font-mono text-[10px] bg-[#F5F3FF] px-1.5 py-0.5 rounded border border-[#DDD6FE]">존재: redacted</span>
              : task.approval_token_exists
                ? <span className="text-[#6D28D9] font-mono text-[10px] bg-[#F5F3FF] px-1.5 py-0.5 rounded border border-[#DDD6FE]">존재: redacted</span>
                : <Empty label="발행 없음" />}
          </Field>
        </dl>
      </div>

      {/* ── 차단 사유 & 경고 ── */}
      {task.blocked_reasons && task.blocked_reasons.length > 0 && (
        <div className="rounded-xl border border-[#FECACA] bg-[#FFF5F5] p-4 shadow-sm">
          <SectionHeader title="차단 사유" badge="BLOCKED" />
          <ul className="space-y-1 mt-1">
            {task.blocked_reasons.map((r) => (
              <li key={r} className="flex items-center gap-2">
                <span className="text-[10px] font-mono bg-[#FEF2F2] text-[#B91C1C] border border-[#FECACA] px-1.5 py-0.5 rounded">
                  {r}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── 에러/로그 영역 ── */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <SectionHeader title="에러 / 로그 요약" badge="READ_ONLY" />
        <div className="space-y-2 mt-1">
          <div className="rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-3">
            <p className="text-[10px] font-mono text-[#9CA3AF] mb-1">LAST_ERROR</p>
            <Empty label="에러 없음 — 상세 로그는 logs 탭에서 확인" />
          </div>
          <div className="rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-3">
            <p className="text-[10px] font-mono text-[#9CA3AF] mb-1">WARNING</p>
            <Empty label="경고 없음" />
          </div>
          <div className="rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] p-3">
            <p className="text-[10px] font-mono text-[#9CA3AF] mb-1">LOG_SUMMARY</p>
            <Empty label="아직 생성되지 않음 — APP_LOGS_AUDIT_READONLY_VIEW_01 공정 예정" />
          </div>
        </div>
      </div>

      {/* ── 원시 데이터 (접기/펼치기) ── */}
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <SectionHeader title="원시 데이터" badge="READ_ONLY_VIEWER" />
        <JsonViewer label="task payload (read-only)" data={{
          id: task.id,
          title: task.title,
          status: task.status,
          risk: task.risk,
          provider: task.provider,
          action_type: task.action_type,
          dry_run: task.dry_run,
          approval_token_exists: task.approval_token_exists,
          approval_token_id: task.approval_token_id ?? null,
          allowed: task.allowed ?? null,
          requires_approval: task.requires_approval ?? null,
          blocked_reasons: task.blocked_reasons ?? [],
          summary: task.summary ?? null,
          created_at: task.created_at,
          updated_at: task.updated_at,
        }} />
      </div>

      {/* ── read-only 정책 안내 ── */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#6B7280] border border-[#F3F4F6] rounded-lg px-3 py-2 bg-[#FAFAFA]">
        <span className="text-[#B91C1C]">execute 없음</span>
        <span>·</span>
        <span className="text-[#B91C1C]">approve 없음</span>
        <span>·</span>
        <span className="text-[#B91C1C]">reject 없음</span>
        <span>·</span>
        <span className="text-[#B91C1C]">delete 없음</span>
        <span>·</span>
        <span>token 원문 표시 금지</span>
        <span>·</span>
        <span>B-1, B-2 준수</span>
      </div>
    </div>
  );
}
