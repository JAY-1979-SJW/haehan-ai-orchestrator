/** /assistant/tasks — Task Queue */
import { TaskTable } from "@/components/assistant/TaskTable";
import { DryRunNotice } from "@/components/assistant/DryRunNotice";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { taskQueueMock } from "@/lib/assistant/mock";

export default function TaskQueuePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-[#111827]">작업 큐</h1>
      <DryRunNotice enabled />
      <ForbiddenActionBanner reason="execute / approve→execute 버튼 없음 (B-1, B-2)" />
      <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm">
        <TaskTable tasks={taskQueueMock} />
      </div>
    </div>
  );
}
