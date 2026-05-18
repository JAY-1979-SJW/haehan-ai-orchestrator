/** EmptyStatePanel — 빈 상태 공통 패널 */
interface Props {
  title?: string;
  description?: string;
  badge?: string;
}

export function EmptyStatePanel({
  title = "항목 없음",
  description = "현재 읽기 전용 inbox 항목 없음",
  badge = "READ_ONLY",
}: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] p-8 text-center">
      <span className="text-2xl">📭</span>
      <div className="text-sm font-semibold text-[#374151]">{title}</div>
      <div className="text-xs text-[#9CA3AF]">{description}</div>
      {badge && (
        <span className="mt-1 rounded bg-[#F3F4F6] px-2 py-0.5 font-mono text-[10px] text-[#6B7280]">
          {badge}
        </span>
      )}
    </div>
  );
}
