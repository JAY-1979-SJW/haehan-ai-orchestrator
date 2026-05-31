import { Btn } from "@/components/ui";
import type { LocalAgentTask } from "@/types/local-agent";

function cancelButtonProps(status: string): {
  label: string;
  enabled: boolean;
  variant: "danger" | "secondary" | "ghost";
} | null {
  switch (status) {
    case "queued":
    case "waiting_approval":
      return { label: "취소", enabled: true, variant: "danger" };
    case "delivered":
    case "running":
      return { label: "취소 요청", enabled: true, variant: "secondary" };
    case "cancel_requested":
      return { label: "취소 요청됨", enabled: false, variant: "ghost" };
    case "cancelled":
      return { label: "취소됨", enabled: false, variant: "ghost" };
    default:
      return null;
  }
}

export interface TaskActionCellProps {
  task: LocalAgentTask;
  canMutate: boolean;
  onCancel: (task: LocalAgentTask) => void;
  onApprovalAction: (task: LocalAgentTask) => void;
  onShowDetail: (task: LocalAgentTask) => void;
}

export function TaskActionCell({
  task, canMutate, onCancel, onApprovalAction, onShowDetail,
}: TaskActionCellProps) {
  const btn = cancelButtonProps(task.status);
  const isWaitingApproval = task.status === "waiting_approval";

  return (
    <div className="flex items-center gap-1 flex-wrap">
      <Btn
        variant="ghost"
        size="xs"
        title="작업 상세 보기 (read-only)"
        onClick={() => onShowDetail(task)}
      >
        상세
      </Btn>
      {isWaitingApproval && (
        <Btn
          variant="secondary"
          size="xs"
          disabled={!canMutate}
          title={!canMutate ? "admin/owner 권한 필요" : "작업 승인/거절 처리"}
          onClick={canMutate ? () => onApprovalAction(task) : undefined}
        >
          승인·거절
        </Btn>
      )}
      {btn && (
        <Btn
          variant={btn.variant}
          size="xs"
          disabled={!btn.enabled || !canMutate}
          title={!canMutate ? "admin/owner 권한 필요" : undefined}
          onClick={btn.enabled && canMutate ? () => onCancel(task) : undefined}
        >
          {btn.label}
        </Btn>
      )}
    </div>
  );
}
