"use client";
import type { SSTableData, SellerCenterPageKey } from "@/lib/assistant/api";

interface ProductListTabProps {
  data: SSTableData | null;
  loading: boolean;
  error: string | null;
  openingPage: SellerCenterPageKey | null;
  findProductIdIndex: (headers: string[]) => number;
  extractProductId: (row: string[], pidIdx: number) => string | null;
  onCollect: () => void;
  onLoad: () => void;
  onOpenSellerCenter: (pageKey: SellerCenterPageKey) => void;
  onRowClick: (pid: string) => void;
}

export default function ProductListTab({
  data, loading, error, openingPage,
  findProductIdIndex, extractProductId,
  onCollect, onLoad, onOpenSellerCenter, onRowClick,
}: ProductListTabProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={onCollect}
          disabled={loading}
          className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors font-semibold"
        >
          {loading ? "수집 중…" : "수집"}
        </button>
        <button
          onClick={onLoad}
          disabled={loading}
          className="px-4 py-2 border border-[#E5E7EB] text-sm rounded-lg hover:bg-[#F9FAFB] disabled:opacity-50 transition-colors"
        >
          조회
        </button>
        {data?.collected_at && (
          <span className="text-xs text-[#9CA3AF]">
            수집: {data.collected_at}
            {data.duration_ms !== undefined && ` (${data.duration_ms}ms)`}
          </span>
        )}
      </div>

      {error && (
        <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-4">
          <p className="text-sm text-[#DC2626]">{error}</p>
        </div>
      )}
      {data?.error && (
        <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-4">
          <p className="text-sm text-[#DC2626]">{data.error}</p>
          {data.hint && <p className="text-xs text-[#9CA3AF] mt-1">{data.hint}</p>}
        </div>
      )}

      {data?.ok && data.headers && data.rows && (
        <div className="overflow-x-auto border border-[#E5E7EB] rounded-xl">
          <table className="w-full text-xs">
            <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
              <tr>
                {data.headers.map((h) => (
                  <th key={h} className="text-left px-3 py-2.5 text-[#6B7280] font-semibold whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => {
                const pidIdx = findProductIdIndex(data.headers!);
                const pid = extractProductId(row, pidIdx);
                return (
                  <tr
                    key={i}
                    onClick={() => { if (pid) onRowClick(pid); }}
                    className={`${i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"} ${pid ? "cursor-pointer hover:bg-[#FFF7ED] transition-colors" : ""}`}
                  >
                    {row.map((cell, j) => (
                      <td key={j} className="px-3 py-2 text-[#374151] whitespace-nowrap">{cell}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-xs text-[#9CA3AF] px-3 py-2 border-t border-[#E5E7EB]">
            행을 클릭하면 상품 상세를 확인할 수 있습니다.
          </p>
        </div>
      )}

      {!data && !error && (
        <div className="border border-[#E5E7EB] rounded-xl p-8 text-center space-y-2">
          <p className="text-sm text-[#6B7280]">아직 수집된 데이터가 없습니다.</p>
          <p className="text-xs text-[#9CA3AF]">[수집] 버튼을 눌러 셀러센터에서 데이터를 가져오세요.</p>
          <button
            onClick={onCollect}
            disabled={loading}
            className="mt-2 px-4 py-2 bg-[#1D4ED8] text-white text-xs rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors"
          >
            수집 시작
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => onOpenSellerCenter("list")}
          disabled={openingPage === "list"}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#03C75A] text-[#03C75A] hover:bg-[#F0FDF4] disabled:opacity-50 transition-colors"
        >
          {openingPage === "list" ? "이동 중…" : "셀러센터 상품 목록 열기 →"}
        </button>
      </div>
    </div>
  );
}
