"use client";
/** /assistant/logs — 로그·감사 (APP_LOGS_AUDIT_READONLY_VIEW_01) */
import { useEffect, useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { AuditLogList } from "@/components/assistant/AuditLogList";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { EmptyStatePanel } from "@/components/assistant/EmptyStatePanel";
import { auditLogsMock } from "@/lib/assistant/mock";
import {
  getOpsAuditEvents,
  makeMeta,
  type ApiState,
  type OpsAuditEventsResponse,
} from "@/lib/assistant/api";
import type { UnifiedLogEntry, OpsAuditEventRow } from "@/types/assistant";

// ── OpsAuditEventRow → UnifiedLogEntry 정규화 ────────────────────────────
function statusToLevel(status: OpsAuditEventRow["status"]): UnifiedLogEntry["level"] {
  if (status === "ok") return "INFO";
  if (status === "warn") return "WARN";
  if (status === "blocked") return "BLOCKED";
  return "ERROR";
}

function normalizeOpsEvents(events: OpsAuditEventRow[]): UnifiedLogEntry[] {
  return events.map((e) => ({
    id: e.eventId,
    timestamp: e.timestamp,
    level: statusToLevel(e.status),
    source: "ops-api" as const,
    eventType: e.eventType,
    actor: e.actor ?? null,
    taskId: e.taskId ?? null,
    summary: e.summary,
    redacted: true as const,
  }));
}

// ── auditLogsMock → UnifiedLogEntry 정규화 ───────────────────────────────
function normalizeMockLogs(): UnifiedLogEntry[] {
  return auditLogsMock.map((log) => ({
    id: log.id,
    timestamp: log.timestamp,
    level: log.level as UnifiedLogEntry["level"],
    source: "app-mock" as const,
    eventType: log.level,
    actor: null,
    taskId: null,
    summary: log.message,
    redacted: true as const,
  }));
}

export default function LogsAuditPage() {
  const [opsState, setOpsState] = useState<ApiState<OpsAuditEventsResponse>>({ status: "idle" });

  useEffect(() => {
    const ctrl = new AbortController();
    setOpsState({ status: "loading" });
    getOpsAuditEvents(ctrl.signal)
      .then((data) => {
        if (!data.events || data.events.length === 0) {
          setOpsState({ status: "empty", meta: makeMeta("api") });
        } else {
          setOpsState({ status: "success", data, meta: makeMeta("api") });
        }
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setOpsState({
          status: "mock_fallback",
          data: { events: [] },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const loadState =
    opsState.status === "loading" ? "loading"
    : opsState.status === "success" ? "success"
    : opsState.status === "empty" ? "empty"
    : opsState.status === "mock_fallback" ? "mock_fallback"
    : opsState.status === "error" ? "error"
    : "idle";

  const entries: UnifiedLogEntry[] =
    opsState.status === "success"
      ? normalizeOpsEvents(opsState.data.events)
      : normalizeMockLogs();

  const totalCount =
    opsState.status === "success" ? opsState.data.events.length : auditLogsMock.length;

  return (
    <PageShell title="시스템 로그" description="감사 이벤트 · 운영 로그" chatDomain="ops">
      <div className="space-y-4">
      {/* 헤더 배지 */}
      <div className="flex items-center gap-2 flex-wrap">
        <ApiConnectionStateBadge
          state={loadState}
          meta={opsState.status === "success" || opsState.status === "mock_fallback"
            ? opsState.meta : undefined}
          label="ops/audit-events"
        />
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-2 py-0.5 rounded">
          {totalCount}건
        </span>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      {/* 배너 */}
      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="이 화면은 기록을 보는 읽기 전용 화면입니다 (실행 기능 없음)" />

      {/* 로딩 */}
      {opsState.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          로그를 불러오는 중…
        </div>
      )}

      {/* mock fallback 배너 */}
      {opsState.status === "mock_fallback" && (
        <div className="flex items-center gap-2 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-xs text-[#92400E]">
          <span className="font-mono font-bold">MOCK_FALLBACK</span>
          <span>— API 응답 불가, mock 데이터 표시 중</span>
          <span className="ml-auto font-mono text-[10px]">읽기 전용</span>
        </div>
      )}

      {/* 빈 상태 */}
      {opsState.status === "empty" && (
        <EmptyStatePanel
          title="현재 기록된 이벤트가 없습니다"
          description="읽기 전용 화면입니다 (실행 기능 없음)"
          badge="읽기 전용 · 감사 기록"
        />
      )}

      {/* 에러 상태 */}
      {opsState.status === "error" && (
        <div className="rounded-xl border border-[#FECACA] bg-[#FFF5F5] p-4">
          <div className="text-sm text-[#EF4444] font-semibold">로그 연결 오류 — mock 데이터로 표시</div>
          <div className="text-xs text-[#9CA3AF] mt-1">상세 오류 표시 금지 (보안 정책)</div>
        </div>
      )}

      {/* 메인 로그 패널 */}
      {(opsState.status === "idle" ||
        opsState.status === "success" ||
        opsState.status === "mock_fallback" ||
        opsState.status === "error") && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
          <AuditLogList entries={entries} />
        </div>
      )}
      </div>
    </PageShell>
  );
}
