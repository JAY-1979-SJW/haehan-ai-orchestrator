"use client";
/** /assistant/tasks — Task Queue (APP_TASK_QUEUE_READONLY_LIST_POLISH_01) */
import { useEffect, useState } from "react";
import { PageShell } from "@/components/ui/PageShell";
import { TaskTable } from "@/components/assistant/TaskTable";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { EmptyStatePanel } from "@/components/assistant/EmptyStatePanel";
import { taskQueueMock } from "@/lib/assistant/mock";
import {
  getAssistantInbox,
  makeMeta,
  type ApiState,
  type InboxResponse,
} from "@/lib/assistant/api";
import type { AssistantTask } from "@/types/assistant";

function inboxToTasks(inbox: InboxResponse): AssistantTask[] {
  if (!inbox.items || inbox.items.length === 0) return [];
  return inbox.items.map((item) => ({
    id: item.id ?? item.item_id ?? "",
    title: item.subject ?? "(제목 없음)",
    status: "READ_ONLY" as const,
    risk: "LOW" as const,
    provider: "EMAIL_GENERIC",
    action_type: "READ",
    dry_run: true,
    approval_token_exists: false,
    approval_token_id: null,
    allowed: true,
    requires_approval: false,
    blocked_reasons: [],
    summary: "inbox 읽기 전용 항목",
    created_at: item.received_at ?? new Date().toISOString(),
    updated_at: item.received_at ?? new Date().toISOString(),
  }));
}

export default function TaskQueuePage() {
  const [inboxState, setInboxState] = useState<ApiState<InboxResponse>>({ status: "idle" });

  useEffect(() => {
    const ctrl = new AbortController();
    setInboxState({ status: "loading" });
    getAssistantInbox(ctrl.signal)
      .then((data) => {
        if (!data.items || data.items.length === 0) {
          setInboxState({ status: "empty", meta: makeMeta("api") });
        } else {
          setInboxState({ status: "success", data, meta: makeMeta("api") });
        }
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const isNetwork = (err as Error).message?.includes("fetch");
        setInboxState({
          status: "mock_fallback",
          data: { items: [], total: 0 },
          meta: makeMeta("mock_fallback", isNetwork ? "network" : "unknown"),
        });
      });
    return () => ctrl.abort();
  }, []);

  const displayTasks: AssistantTask[] =
    inboxState.status === "success"
      ? inboxToTasks(inboxState.data)
      : taskQueueMock;

  const loadState =
    inboxState.status === "loading" ? "loading"
    : inboxState.status === "success" ? "success"
    : inboxState.status === "empty" ? "empty"
    : inboxState.status === "mock_fallback" ? "mock_fallback"
    : inboxState.status === "error" ? "error"
    : "idle";

  const taskCount =
    inboxState.status === "success" ? inboxState.data.items.length : taskQueueMock.length;

  return (
    <PageShell title="작업 목록" description="작업 큐 · 실행 현황" chatDomain="ops">
      <div className="space-y-4">
      {/* 헤더 배지 */}
      <div className="flex items-center gap-2 flex-wrap">
        <ApiConnectionStateBadge
          state={loadState}
          meta={inboxState.status === "success" || inboxState.status === "mock_fallback"
            ? inboxState.meta : undefined}
          label="inbox"
        />
        <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-2 py-0.5 rounded">
          {taskCount}건
        </span>
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded border border-[#FDE68A]">
          DRY_RUN_ONLY
        </span>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      {/* 배너 */}
      <ReadOnlyModeBanner />
      <DryRunNotice enabled />
      <ForbiddenActionBanner reason="이 화면은 작업을 보는 읽기 전용 화면입니다 (실행 기능 없음)" />

      {/* 로딩 */}
      {inboxState.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          작업 목록을 불러오는 중…
        </div>
      )}

      {/* 빈 상태 */}
      {inboxState.status === "empty" && (
        <EmptyStatePanel
          title="현재 표시할 작업이 없습니다"
          description="읽기 전용 화면입니다 (실행 기능 없음)"
          badge="읽기 전용"
        />
      )}

      {/* mock fallback 배너 */}
      {inboxState.status === "mock_fallback" && (
        <div className="flex items-center gap-2 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-xs text-[#92400E]">
          <span className="font-mono font-bold">MOCK_FALLBACK</span>
          <span>— API 응답 불가, mock 데이터 표시 중</span>
          <span className="ml-auto font-mono text-[10px]">읽기 전용</span>
        </div>
      )}

      {/* 에러 상태 */}
      {inboxState.status === "error" && (
        <div className="rounded-xl border border-[#FECACA] bg-[#FFF5F5] p-4 space-y-2">
          <div className="text-sm text-[#EF4444] font-semibold">inbox 연결 오류 — mock 데이터로 표시</div>
          <div className="text-xs text-[#9CA3AF]">상세 오류 표시 금지 (보안 정책)</div>
        </div>
      )}

      {/* 테이블 */}
      {(inboxState.status === "idle" ||
        inboxState.status === "success" ||
        inboxState.status === "mock_fallback" ||
        inboxState.status === "error") && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
          <TaskTable tasks={displayTasks} />
        </div>
      )}
      </div>
    </PageShell>
  );
}
