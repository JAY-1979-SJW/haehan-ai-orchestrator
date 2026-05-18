/** /assistant/tasks/[id] — Task Detail */
import { TaskDetailPanel } from "@/components/assistant/TaskDetailPanel";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { taskQueueMock, taskDetailMock } from "@/lib/assistant/mock";
import Link from "next/link";

export default function TaskDetailPage({ params }: { params: { id: string } }) {
  const task = taskQueueMock.find((t) => t.id === params.id) ?? taskDetailMock;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Link href="/assistant/tasks" className="text-xs text-[#6B7280] hover:underline">← 작업 큐</Link>
        <h1 className="text-lg font-bold text-[#111827]">작업 상세</h1>
      </div>
      <ForbiddenActionBanner reason="execute / approve / reject 실행 연결 없음" />
      <TaskDetailPanel task={task} />
    </div>
  );
}
