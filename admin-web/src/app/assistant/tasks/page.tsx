"use client";
/** /assistant/tasks — Task Queue (inbox status card 보강) */
import { useEffect, useState } from "react";
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
    id: item.id,
    title: item.subject ?? "(제목 없음)",
    status: "PENDING" as const,
    risk: "LOW" as const,
    provider: "EMAIL_GENERIC" as const,
    action_type: "READ" as const,
    dry_run: true,
    approval_token_exists: false,
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

  const inboxCount =
    inboxState.status === "success" ? inboxState.data.items.length : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <h1 className="text-lg font-bold text-[#111827]">작업 큐</h1>
        <ApiConnectionStateBadge
          state={loadState}
          meta={inboxState.status === "success" || inboxState.status === "mock_fallback"
            ? inboxState.meta : undefined}
          label="inbox"
        />
        {inboxCount !== null && (
          <span className="text-xs font-mono text-[#6B7280] bg-[#F3F4F6] px-2 py-0.5 rounded">
            {inboxCount}건
          </span>
        )}
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded">
          DRY_RUN_ONLY
        </span>
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded">
          MUTATION_BLOCKED
        </span>
      </div>
      <ReadOnlyModeBanner />
      <DryRunNotice enabled />
      <ForbiddenActionBanner reason="execute / approve→execute 버튼 없음 (B-1, B-2) — NO_EXECUTE_CONNECTED" />

      {inboxState.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          inbox 로딩 중…
        </div>
      )}

      {inboxState.status === "empty" && (
        <EmptyStatePanel
          title="inbox 항목 없음"
          description="현재 읽기 전용 inbox 항목 없음 — DRY_RUN_ONLY"
          badge="READ_ONLY · DRY_RUN_ONLY"
        />
      )}

      {(inboxState.status === "idle" ||
        inboxState.status === "success" ||
        inboxState.status === "mock_fallback") && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
          {inboxState.status === "mock_fallback" && (
            <div className="mb-2 text-xs text-[#F59E0B] font-mono">
              ⚠ MOCK_FALLBACK — API 연결 실패, mock 데이터 표시
            </div>
          )}
          <TaskTable tasks={displayTasks} />
        </div>
      )}

      {inboxState.status === "error" && (
        <div className="rounded-xl border border-[#FEE2E2] bg-[#FFF5F5] p-4 text-sm text-[#EF4444]">
          inbox 연결 오류 — mock 데이터로 표시됩니다.
          <div className="mt-2">
            <TaskTable tasks={taskQueueMock} />
          </div>
        </div>
      )}
    </div>
  );
}
