/** TaskTable — 작업 큐 테이블 (read-only, execute 버튼 없음) */
import Link from "next/link";
import type { AssistantTask } from "@/types/assistant";
import { RiskBadge } from "@/components/ui/RiskBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";

const STATUS_BADGE_MAP: Record<string, string> = {
  DRY_RUN:              "dry_run",
  BLOCKED:              "blocked",
  APPROVAL_DISPLAY_ONLY:"waiting_approval",
  READ_ONLY:            "queued",
  FUTURE:               "hold",
  ERROR:                "failed",
};

export function TaskTable({ tasks }: { tasks: AssistantTask[] }) {
  if (tasks.length === 0) {
    return <div className="text-sm text-[#9CA3AF] py-8 text-center">대기 중인 작업이 없습니다.</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[#E5E7EB] text-xs text-[#6B7280] uppercase">
            <th className="text-left py-2 px-3">작업</th>
            <th className="text-left py-2 px-3">상태</th>
            <th className="text-left py-2 px-3">위험도</th>
            <th className="text-left py-2 px-3">제공자</th>
            <th className="text-left py-2 px-3">드라이런</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id} className="border-b border-[#F3F4F6] hover:bg-[#F9FAFB]">
              <td className="py-2 px-3">
                <Link
                  href={`/assistant/tasks/${task.id}`}
                  className="text-[#1D4ED8] hover:underline font-medium"
                >
                  {task.title}
                </Link>
              </td>
              <td className="py-2 px-3">
                <StatusBadge status={STATUS_BADGE_MAP[task.status] ?? task.status} />
              </td>
              <td className="py-2 px-3">
                <RiskBadge level={task.risk.toLowerCase() as "low"|"medium"|"high"|"critical"} />
              </td>
              <td className="py-2 px-3 font-mono text-xs text-[#6B7280]">{task.provider}</td>
              <td className="py-2 px-3">
                {task.dry_run
                  ? <span className="text-xs text-[#1D4ED8] font-semibold">DRY_RUN</span>
                  : <span className="text-xs text-[#9CA3AF]">—</span>
                }
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
