"use client";
import type { SearchState } from "./types";

interface BlogTabProps {
  blogQuery: string;
  setBlogQuery: (v: string) => void;
  blogPages: number;
  setBlogPages: (v: number) => void;
  blogState: SearchState;
  onRun: () => void;
  onList: () => void;
}

export function BlogTab({
  blogQuery,
  setBlogQuery,
  blogPages,
  setBlogPages,
  blogState,
  onRun,
  onList,
}: BlogTabProps) {
  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex gap-2">
        <input
          type="text"
          value={blogQuery}
          onChange={(e) => setBlogQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onRun()}
          placeholder="블로그 검색어를 입력하세요"
          className="flex-1 border border-[#E5E7EB] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827] placeholder-[#9CA3AF]"
        />
        <select
          value={blogPages}
          onChange={(e) => setBlogPages(Number(e.target.value))}
          className="border border-[#E5E7EB] rounded-lg px-2 py-2 text-sm focus:outline-none focus:border-[#F97316] text-[#111827]"
        >
          {[1, 2, 3, 5].map((n) => (
            <option key={n} value={n}>{n}페이지</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onRun}
          disabled={blogState.running || !blogQuery.trim()}
          className="px-4 py-2 bg-[#F97316] text-white text-sm font-semibold rounded-lg hover:bg-[#EA6C0A] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {blogState.running ? "실행 중…" : "검색 실행"}
        </button>
        <button
          onClick={onList}
          disabled={blogState.listLoading}
          className="px-4 py-2 border border-[#E5E7EB] text-[#374151] text-sm font-semibold rounded-lg hover:bg-[#F9FAFB] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {blogState.listLoading ? "조회 중…" : "결과 조회"}
        </button>
      </div>

      {blogState.error && (
        <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#DC2626] mb-1">오류</p>
          <p className="text-xs text-[#7F1D1D] font-mono">{blogState.error}</p>
        </div>
      )}

      {blogState.result && (
        <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#16A34A] mb-2">실행 완료</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <dt className="text-[#6B7280]">상태</dt>
            <dd className="font-mono text-[#111827]">{blogState.result.status}</dd>
            <dt className="text-[#6B7280]">수집 건수</dt>
            <dd className="font-mono text-[#111827]">{blogState.result.collected}</dd>
            <dt className="text-[#6B7280]">DB 상태</dt>
            <dd className="font-mono text-[#111827]">{blogState.result.db_status}</dd>
            <dt className="text-[#6B7280]">소요 시간</dt>
            <dd className="font-mono text-[#111827]">{blogState.result.duration_ms} ms</dd>
          </dl>
        </div>
      )}

      {blogState.listError && (
        <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#DC2626] mb-1">결과 조회 오류</p>
          <p className="text-xs text-[#7F1D1D] font-mono">{blogState.listError}</p>
        </div>
      )}

      {blogState.listData && (
        <div className="border border-[#E5E7EB] bg-white rounded-xl p-4">
          <p className="text-xs font-semibold text-[#374151] mb-2">
            결과 목록 ({Array.isArray(blogState.listData) ? blogState.listData.length : "—"}건)
          </p>
          <details>
            <summary className="text-xs text-[#9CA3AF] cursor-pointer hover:text-[#6B7280]">원문 데이터 보기</summary>
            <pre className="text-xs text-[#374151] font-mono whitespace-pre-wrap overflow-x-auto max-h-64 mt-2">
              {JSON.stringify(blogState.listData, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
