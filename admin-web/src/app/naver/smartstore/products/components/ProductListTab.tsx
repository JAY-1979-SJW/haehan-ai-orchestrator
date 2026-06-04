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

      {data?.ok && data.headers && data.rows && (() => {
        // 셀러센터에서 수집할 때 섞여 들어온 '가짜 버튼' 열(수정/복사/시작하기 등) 숨김 — 실제 데이터 열만 표시
        const JUNK = new Set(["수정", "복사", "시작하기", "그룹 전환", "으로 판매", "스마트스토어", "삭제", "선택", ""]);
        const cols = data.headers!.map((h, i) => ({ label: (h || "").trim(), i })).filter((c) => !JUNK.has(c.label));
        const pidIdx = findProductIdIndex(data.headers!);
        return (
          <div className="overflow-x-auto border border-[#E5E7EB] rounded-xl">
            <table className="w-full text-xs">
              <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                <tr>
                  {cols.map((c) => (
                    <th key={c.i} className="text-left px-3 py-2.5 text-[#6B7280] font-semibold whitespace-nowrap">{c.label}</th>
                  ))}
                  <th className="text-left px-3 py-2.5 text-[#6B7280] font-semibold whitespace-nowrap">동작</th>
                </tr>
              </thead>
              <tbody>
                {data.rows!.map((row, i) => {
                  const pid = extractProductId(row, pidIdx);
                  return (
                    <tr
                      key={i}
                      onClick={() => { if (pid) onRowClick(pid); }}
                      className={`${i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"} ${pid ? "cursor-pointer hover:bg-[#FFF7ED] transition-colors" : ""}`}
                    >
                      {cols.map((c) => (
                        <td key={c.i} className="px-3 py-2 text-[#374151] whitespace-nowrap">{row[c.i]}</td>
                      ))}
                      <td className="px-3 py-2 whitespace-nowrap">
                        <button
                          onClick={(e) => { e.stopPropagation(); if (pid) window.open(`https://sell.smartstore.naver.com/#/products/${pid}`, "_blank"); }}
                          disabled={!pid}
                          className="px-2.5 py-1 rounded-lg border border-[#16A34A] text-[#16A34A] text-[11px] font-semibold hover:bg-[#F0FDF4] disabled:opacity-40"
                        >
                          셀러센터 열기
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="text-xs text-[#9CA3AF] px-3 py-2 border-t border-[#E5E7EB]">
              행 클릭 = 상품 선택(수정 탭 자동입력) · [셀러센터 열기] = 수정·복사·시작 등 실제 작업
            </p>
          </div>
        );
      })()}

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
