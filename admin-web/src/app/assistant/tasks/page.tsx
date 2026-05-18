"use client";
/** /assistant/tasks — Task Queue (READ_ONLY inbox API wiring) */
import { useEffect, useState } from "react";
import { TaskTable } from "@/components/assistant/TaskTable";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { taskQueueMock } from "@/lib/assistant/mock";
import {
  getAssistantInbox,
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
  const [inboxState, setInboxState] = useState<ApiState<InboxResponse>>({
    status: "idle",
  });

  useEffect(() => {
    const ctrl = new AbortController();
    setInboxState({ status: "loading" });
    getAssistantInbox(ctrl.signal)
      .then((data) => {
        if (!data.items || data.items.length === 0) {
          setInboxState({ status: "empty" });
        } else {
          setInboxState({ status: "success", data });
        }
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setInboxState({ status: "mock_fallback", data: { items: [], total: 0 } });
      });
    return () => ctrl.abort();
  }, []);

  const displayTasks: AssistantTask[] =
    inboxState.status === "success"
      ? inboxToTasks(inboxState.data)
      : taskQueueMock;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-bold text-[#111827]">작업 큐</h1>
        <span className="text-xs font-mono bg-[#F3F4F6] text-[#6B7280] px-2 py-0.5 rounded">
          READ_ONLY
        </span>
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded">
          MUTATION_BLOCKED
        </span>
        {inboxState.status === "loading" && (
          <span className="text-xs text-[#9CA3AF] animate-pulse">
            inbox 연결 중…
          </span>
        )}
        {inboxState.status === "mock_fallback" && (
          <span className="text-xs text-[#F59E0B] font-mono">MOCK_FALLBACK</span>
        )}
        {inboxState.status === "error" && (
          <span className="text-xs text-[#EF4444] font-mono">INBOX_ERROR</span>
        )}
      </div>
      <DryRunNotice enabled />
      <ForbiddenActionBanner reason="execute / approve→execute 버튼 없음 (B-1, B-2) — NO_EXECUTE_CONNECTED" />

      {inboxState.status === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          inbox 로딩 중…
        </div>
      )}

      {inboxState.status === "empty" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          inbox가 비어 있습니다. (Empty State)
        </div>
      )}

      {(inboxState.status === "idle" ||
        inboxState.status === "success" ||
        inboxState.status === "mock_fallback") && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
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
