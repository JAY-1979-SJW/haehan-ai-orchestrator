/** ReadOnlyModeBanner — 전체 읽기 전용 모드 표시 */
export function ReadOnlyModeBanner() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-[#BFDBFE] bg-[#EFF6FF] px-3 py-2 text-xs text-[#1D4ED8]">
      <span className="font-mono font-bold">READ_ONLY</span>
      <span className="text-[#3B82F6]">·</span>
      <span>이 화면은 조회 전용입니다. 실행·승인·변경 버튼이 없습니다.</span>
      <span className="ml-auto font-mono text-[10px] text-[#93C5FD]">mutation_allowed=false</span>
    </div>
  );
}
