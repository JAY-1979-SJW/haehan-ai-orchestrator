"use client";
/** /assistant/tasks/[id] — Task Detail (APP_TASK_DETAIL_READONLY_POLISH_01) */
import { useEffect, useState } from "react";
import Link from "next/link";
import { TaskDetailPanel } from "@/components/assistant/TaskDetailPanel";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { ApiConnectionStateBadge } from "@/components/assistant/ApiConnectionStateBadge";
import { taskQueueMock, taskDetailMock } from "@/lib/assistant/mock";
import type { AssistantTask } from "@/types/assistant";

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const [loadState, setLoadState] = useState<"loading" | "success" | "mock_fallback" | "error">("loading");
  const [task, setTask] = useState<AssistantTask | null>(null);

  useEffect(() => {
    const fromMock = taskQueueMock.find((t) => t.id === params.id) ?? (params.id === taskDetailMock.id ? taskDetailMock : null);
    if (fromMock) {
      setTask(fromMock);
      setLoadState("success");
    } else {
      // 목록에 없는 id는 mock fallback 기본 task 표시
      setTask(taskDetailMock);
      setLoadState("mock_fallback" as const);
    }
  }, [params.id]);

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 flex-wrap">
        <Link href="/assistant/tasks" className="text-xs text-[#6B7280] hover:underline font-mono">
          ← 작업 큐
        </Link>
        <h1 className="text-lg font-bold text-[#111827]">작업 상세</h1>
        <ApiConnectionStateBadge state={loadState} label="task-detail" />
        <span className="text-xs font-mono bg-[#FEE2E2] text-[#B91C1C] px-2 py-0.5 rounded border border-[#FECACA]">
          MUTATION_BLOCKED
        </span>
      </div>

      {/* 배너 */}
      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="execute / approve / reject / delete 실행 연결 없음 (B-1, B-2) — 이 화면은 읽기 전용 상세 화면입니다" />

      {/* mock fallback 알림 */}
      {(loadState === "mock_fallback" || loadState === "error") && (
        <div className="flex items-center gap-2 rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-xs text-[#92400E]">
          <span className="font-mono font-bold">MOCK_FALLBACK</span>
          <span>— 요청한 task id를 찾을 수 없어 기본 데이터 표시 중</span>
          <span className="ml-auto font-mono text-[10px]">id: {params.id}</span>
        </div>
      )}

      {/* 로딩 */}
      {loadState === "loading" && (
        <div className="rounded-xl border border-[#E5E7EB] bg-white p-6 text-center text-sm text-[#9CA3AF]">
          작업 상세를 불러오는 중…
        </div>
      )}

      {/* 상세 패널 */}
      {task && loadState !== "loading" && (
        <TaskDetailPanel task={task} />
      )}
    </div>
  );
}
