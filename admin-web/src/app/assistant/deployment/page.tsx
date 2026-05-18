/** /assistant/deployment — Deployment Status (restart/compose 버튼 없음) */
import { DeploymentSopPanel } from "@/components/assistant/DeploymentSopPanel";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { deploymentStatusMock } from "@/lib/assistant/mock";

export default function DeploymentStatusPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-[#111827]">배포 상태</h1>
      <ForbiddenActionBanner reason="서버 재시작 / docker compose 버튼 없음" />
      <DeploymentSopPanel status={deploymentStatusMock} />
    </div>
  );
}
