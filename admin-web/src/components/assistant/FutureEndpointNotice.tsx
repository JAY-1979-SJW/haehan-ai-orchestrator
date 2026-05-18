/** FutureEndpointNotice — 미구현 엔드포인트 안내 */
interface Props {
  endpoint?: string;
  reason?: string;
}

export function FutureEndpointNotice({
  endpoint = "FUTURE_ENDPOINT",
  reason = "이 기능은 향후 공정에서 연결될 예정입니다.",
}: Props) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-[#E5E7EB] bg-[#F9FAFB] px-3 py-2 text-xs text-[#6B7280]">
      <span className="mt-0.5 shrink-0">🔌</span>
      <div>
        <span className="font-mono text-[#9CA3AF]">{endpoint}</span>
        <span className="mx-1">—</span>
        <span>{reason}</span>
      </div>
      <span className="ml-auto shrink-0 font-mono text-[10px] text-[#D1D5DB]">FUTURE</span>
    </div>
  );
}
