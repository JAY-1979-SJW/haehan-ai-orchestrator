/** /assistant/deployment — Deployment Status (restart/compose 버튼 없음, server_apply_allowed=false) */
import { DeploymentSopPanel } from "@/components/assistant/DeploymentSopPanel";
import { ForbiddenActionBanner } from "@/components/assistant/ForbiddenActionBanner";
import { ReadOnlyModeBanner } from "@/components/assistant/ReadOnlyModeBanner";
import { deploymentStatusMock } from "@/lib/assistant/mock";

export default function DeploymentStatusPage() {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-lg font-bold text-[#111827]">배포 상태</h1>
        <span className="text-xs font-mono bg-[#FEF3C7] text-[#92400E] px-2 py-0.5 rounded">
          server_apply_allowed=false
        </span>
      </div>
      <ReadOnlyModeBanner />
      <ForbiddenActionBanner reason="서버 재시작 / docker compose 버튼 없음" />
      <DeploymentSopPanel status={deploymentStatusMock} />
    </div>
  );
}
