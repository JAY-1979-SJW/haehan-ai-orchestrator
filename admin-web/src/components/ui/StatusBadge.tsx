type BadgeConfig = { label: string; classes: string };

const BADGE_MAP: Record<string, BadgeConfig> = {
  // Agent status
  idle:              { label: "대기",     classes: "bg-[#F3F4F6] text-[#374151] border-[#D1D5DB]" },
  busy:              { label: "작업중",   classes: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]" },
  stale:             { label: "응답지연", classes: "bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]" },
  offline:           { label: "오프라인", classes: "bg-[#F9FAFB] text-[#9CA3AF] border-[#E5E7EB]" },

  // Task status
  queued:            { label: "대기",     classes: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]" },
  waiting_approval:  { label: "승인대기", classes: "bg-[#F5F3FF] text-[#6D28D9] border-[#DDD6FE]" },
  delivered:         { label: "전달됨",   classes: "bg-[#ECFDF5] text-[#065F46] border-[#A7F3D0]" },
  running:           { label: "실행중",   classes: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]" },
  completed:         { label: "완료",     classes: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]" },
  failed:            { label: "실패",     classes: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
  rejected:          { label: "거절",     classes: "bg-[#FEF2F2] text-[#991B1B] border-[#FCA5A5]" },
  cancel_requested:  { label: "취소요청", classes: "bg-[#FFFBEB] text-[#92400E] border-[#FDE68A]" },
  cancelled:         { label: "취소됨",   classes: "bg-[#F9FAFB] text-[#6B7280] border-[#D1D5DB]" },

  // Risk level
  low:    { label: "낮음", classes: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]" },
  medium: { label: "보통", classes: "bg-[#FFFBEB] text-[#D97706] border-[#FDE68A]" },
  high:   { label: "높음", classes: "bg-[#FEF2F2] text-[#B91C1C] border-[#FECACA]" },
};

const DEFAULT_BADGE: BadgeConfig = {
  label: "알수없음",
  classes: "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]",
};

interface StatusBadgeProps {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const config = BADGE_MAP[status] ?? DEFAULT_BADGE;
  return (
    <span
      className={[
        "inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border",
        config.classes,
      ].join(" ")}
    >
      {label ?? config.label}
    </span>
  );
}
