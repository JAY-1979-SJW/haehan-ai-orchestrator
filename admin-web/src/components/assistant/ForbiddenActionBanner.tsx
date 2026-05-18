/** ForbiddenActionBanner — 실행 금지 안내 배너 */
export function ForbiddenActionBanner({ reason }: { reason?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-[#FEF2F2] border border-[#FECACA] px-4 py-2.5">
      <span className="text-lg">🚫</span>
      <div className="text-sm text-[#991B1B]">
        <span className="font-semibold">실행 금지</span>
        {reason && <span className="ml-1 text-[#B91C1C]">— {reason}</span>}
      </div>
    </div>
  );
}
