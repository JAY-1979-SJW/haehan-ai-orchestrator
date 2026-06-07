"use client";
/**
 * LiveScreen — AI 작업 브라우저 안내.
 * CDP 브라우저가 별도 창으로 실행되므로 앱 내 화면 폴링 없이 안내만 표시.
 */

export function LiveScreen({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-col bg-[#0F172A] border border-[#E5E7EB] rounded-2xl overflow-hidden ${className}`}>
      <div className="px-3 h-[44px] flex items-center justify-between shrink-0 bg-[#111827] border-b border-[#1F2937]">
        <span className="text-xs font-bold text-[#E5E7EB]">🖥 AI 작업 브라우저</span>
        <span className="text-[10px] text-[#6EE7B7]">● 별도 창으로 실행 중</span>
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center">
        <div className="text-center px-6">
          <p className="text-sm text-[#9CA3AF]">AI가 작업할 때 별도 Chrome 창이 자동으로 열립니다.</p>
          <p className="text-[11px] text-[#6B7280] mt-1">작업 화면은 해당 Chrome 창에서 직접 확인하세요.</p>
        </div>
      </div>
    </div>
  );
}
