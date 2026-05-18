/** DryRunNotice — POST /tasks dry-run-only 상태 표시 */
export function DryRunNotice({ enabled }: { enabled: boolean }) {
  if (!enabled) return null;
  return (
    <div className="flex items-center gap-2 rounded-lg bg-[#EFF6FF] border border-[#BFDBFE] px-4 py-2.5">
      <span className="text-lg">🔵</span>
      <div className="text-sm text-[#1D4ED8]">
        <span className="font-semibold">DRY_RUN 전용 모드</span>
        <span className="ml-1 text-[#2563EB]">— POST_TASKS_DRY_RUN_ENABLED=True. 실제 실행 차단됨</span>
      </div>
    </div>
  );
}
