import type { CurrentUser } from "@/types/auth";

export function RoleBadge({
  currentUser,
  userLoading,
  userError,
}: {
  currentUser: CurrentUser | null;
  userLoading: boolean;
  userError: boolean;
}) {
  if (userLoading) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-[#F3F4F6] text-[#9CA3AF]">
        권한 확인 중…
      </span>
    );
  }
  if (userError || !currentUser) {
    return (
      <span className="inline-flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] bg-[#FEE2E2] text-[#B91C1C] font-medium">
          권한 확인 실패
        </span>
        <span className="text-[11px] text-[#9CA3AF]">
          권한 확인 실패 시 위험 작업은 비활성화됩니다.
        </span>
      </span>
    );
  }
  const label: Record<string, string> = {
    owner: "소유자 권한",
    admin: "관리자 권한",
    viewer: "조회 전용 권한",
  };
  const color: Record<string, string> = {
    owner: "bg-[#FEF3C7] text-[#92400E]",
    admin: "bg-[#DBEAFE] text-[#1E40AF]",
    viewer: "bg-[#F3F4F6] text-[#6B7280]",
  };
  const roleLabel = label[currentUser.role] ?? `${currentUser.role} 권한`;
  const roleColor = color[currentUser.role] ?? "bg-[#F3F4F6] text-[#6B7280]";
  const hint =
    currentUser.role === "viewer"
      ? "조회 전용입니다. 취소·캡처는 admin/owner 권한이 필요합니다."
      : null;
  return (
    <span className="inline-flex items-center gap-2 flex-wrap">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium ${roleColor}`}>
        {currentUser.actor && (
          <span className="opacity-70">{currentUser.actor}</span>
        )}
        {currentUser.actor && <span>·</span>}
        {roleLabel}
      </span>
      {hint && (
        <span className="text-[11px] text-[#9CA3AF]">{hint}</span>
      )}
    </span>
  );
}
