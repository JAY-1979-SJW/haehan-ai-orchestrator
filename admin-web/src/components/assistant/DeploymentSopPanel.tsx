/** DeploymentSopPanel — 배포 SOP 표시 (버튼 없음, server_apply_allowed=false) */
import type { DeploymentStatus } from "@/types/assistant";
import { FutureEndpointNotice } from "@/components/assistant/FutureEndpointNotice";

export function DeploymentSopPanel({ status }: { status: DeploymentStatus }) {
  const headMatch = status.server_head === status.origin_head;
  return (
    <div className="rounded-xl border border-[#E5E7EB] bg-white p-4 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-[#111827]">배포 상태</span>
        <span className="text-[10px] font-mono bg-[#FEF3C7] text-[#92400E] px-1.5 py-0.5 rounded">
          server_apply_allowed=false
        </span>
      </div>
      <dl className="text-xs space-y-1.5">
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">서버 HEAD</dt>
          <dd className="font-mono">{status.server_head}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">origin HEAD</dt>
          <dd className="font-mono">{status.origin_head}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[#6B7280] w-32">동기화</dt>
          <dd className={headMatch ? "text-[#059669] font-semibold" : "text-[#D97706] font-semibold"}>
            {headMatch ? "SYNCED" : "DIFF"}
          </dd>
        </div>
        {status.build_required && (
          <div className="text-[#D97706] font-semibold">⚠ 빌드 필요 — 표시 전용 (자동 실행 없음)</div>
        )}
      </dl>
      <div className="pt-2 border-t border-[#F3F4F6]">
        <div className="text-xs text-[#374151] font-semibold mb-1">배포 SOP</div>
        <ol className="text-xs text-[#6B7280] space-y-0.5 list-decimal list-inside">
          {status.sop_steps.map((step, i) => (
            <li key={i} className="font-mono">{step}</li>
          ))}
        </ol>
        <p className="text-[10px] text-[#9CA3AF] mt-2">
          ⚠ 서버 재시작 버튼 없음 — 수동 SOP 준수 (배포 SOP 위반 시 baked-in 이미지 미반영)
        </p>
      </div>
      <FutureEndpointNotice
        endpoint="GET /api/v1/deployment/status"
        reason="서버 HEAD 실시간 조회는 향후 공정에서 연결될 예정입니다."
      />
    </div>
  );
}
