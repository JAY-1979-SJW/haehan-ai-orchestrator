"use client";
import type {
  KeywordSummaryResponse,
  MallAnalysisResponse,
  PriceDistResponse,
} from "@/lib/assistant/api";

interface AnalysisTabProps {
  analysisLoading: boolean;
  analysisError: string | null;
  kwSummary: KeywordSummaryResponse | null;
  mallData: MallAnalysisResponse | null;
  priceDist: PriceDistResponse | null;
  excludeLarge: boolean;
  setExcludeLarge: (v: boolean) => void;
  onFullAnalysis: () => void;
}

export function AnalysisTab({
  analysisLoading,
  analysisError,
  kwSummary,
  mallData,
  priceDist,
  excludeLarge,
  setExcludeLarge,
  onFullAnalysis,
}: AnalysisTabProps) {
  return (
    <div className="space-y-4 max-w-4xl">
      {/* 안내 */}
      <div className="border border-[#E0E7FF] bg-[#EEF2FF] rounded-xl px-4 py-3">
        <p className="text-xs font-bold text-[#4338CA]">DB 기반 시장 분석</p>
        <p className="text-xs text-[#4338CA] mt-0.5">
          수집된 {kwSummary?.total_products?.toLocaleString() ?? "…"} 건의 쇼핑 데이터를 분석합니다.
          [전체 분석] 버튼을 클릭하면 키워드 요약, 업체 현황, 가격 분포를 한 번에 조회합니다.
        </p>
      </div>

      {/* 전체 분석 버튼 + 조명 전문 업체 토글 */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={onFullAnalysis}
          disabled={analysisLoading}
          className="px-5 py-2 bg-[#4F46E5] text-white text-sm font-semibold rounded-lg hover:bg-[#4338CA] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {analysisLoading ? "분석 중…" : "전체 분석"}
        </button>
        <label className="flex items-center gap-2 text-sm text-[#374151] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={excludeLarge}
            onChange={(e) => setExcludeLarge(e.target.checked)}
            className="w-4 h-4 accent-[#4F46E5]"
          />
          조명 전문 업체만
        </label>
      </div>

      {/* 오류 */}
      {analysisError && (
        <div className="border border-[#FCA5A5] bg-[#FEF2F2] rounded-xl p-4">
          <p className="text-xs font-semibold text-[#DC2626] mb-1">분석 오류</p>
          <p className="text-xs text-[#7F1D1D] font-mono">{analysisError}</p>
        </div>
      )}

      {/* 키워드별 요약 테이블 */}
      {kwSummary && kwSummary.keywords.length > 0 && (
        <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
          <p className="text-xs font-semibold text-[#374151] px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
            키워드별 요약 — 총 {kwSummary.total_products.toLocaleString()}건
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[#F3F4F6] text-[#6B7280]">
                  <th className="text-left px-3 py-2 font-semibold">키워드</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">상품수</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">최저가</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">평균가</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">최고가</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">업체수</th>
                </tr>
              </thead>
              <tbody>
                {kwSummary.keywords.map((kw, idx) => (
                  <tr key={kw.query} className={idx % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                    <td className="px-3 py-2 font-medium text-[#111827]">{kw.query}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#374151]">{kw.count.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#16A34A]">
                      {kw.min_price != null ? kw.min_price.toLocaleString() + "원" : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[#EA580C]">
                      {kw.avg_price != null ? kw.avg_price.toLocaleString() + "원" : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[#DC2626]">
                      {kw.max_price != null ? kw.max_price.toLocaleString() + "원" : "—"}
                    </td>
                    <td className="px-3 py-2 text-right text-[#374151]">{kw.mall_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 가격대 분포 바 차트 */}
      {priceDist && priceDist.ranges.length > 0 && (
        <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white">
          <p className="text-xs font-semibold text-[#374151] mb-3">
            가격대 분포 — 가격 있는 상품 {priceDist.total_with_price.toLocaleString()}건
          </p>
          <div className="space-y-2">
            {(() => {
              const maxCount = Math.max(...priceDist.ranges.map((r) => r.count), 1);
              return priceDist.ranges.map((r) => (
                <div key={r.label} className="flex items-center gap-3">
                  <span className="text-xs text-[#6B7280] w-16 shrink-0 text-right">{r.label}</span>
                  <div className="flex-1 bg-[#F3F4F6] rounded-full h-4 overflow-hidden">
                    <div
                      className="h-4 bg-[#4F46E5] rounded-full transition-all"
                      style={{ width: `${Math.round((r.count / maxCount) * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-[#374151] w-16 text-right shrink-0">
                    {r.count.toLocaleString()}건
                  </span>
                </div>
              ));
            })()}
          </div>
        </div>
      )}

      {/* 상위 업체 테이블 */}
      {mallData && (
        <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
          <p className="text-xs font-semibold text-[#374151] px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB]">
            상위 업체 — 전체 {mallData.total_malls}개
            {excludeLarge && " (전문 업체만)"}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-[#F3F4F6] text-[#6B7280]">
                  <th className="text-left px-3 py-2 font-semibold">업체명</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">상품수</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">평균가</th>
                  <th className="text-right px-3 py-2 font-semibold whitespace-nowrap">최저가</th>
                  <th className="text-left px-3 py-2 font-semibold">구분</th>
                </tr>
              </thead>
              <tbody>
                {(excludeLarge
                  ? mallData.malls.filter((m) => !m.is_large)
                  : mallData.malls
                ).map((m, idx) => (
                  <tr key={m.mall_name} className={idx % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                    <td className="px-3 py-2 font-medium text-[#111827]">{m.mall_name}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#374151]">{m.count.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right font-mono text-[#EA580C]">
                      {m.avg_price != null ? m.avg_price.toLocaleString() + "원" : "—"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[#16A34A]">
                      {m.min_price != null ? m.min_price.toLocaleString() + "원" : "—"}
                    </td>
                    <td className="px-3 py-2 text-[#6B7280]">
                      {m.is_large ? (
                        <span className="px-1.5 py-0.5 bg-[#DBEAFE] text-[#1D4ED8] rounded text-[10px] font-semibold">대형몰</span>
                      ) : (
                        <span className="px-1.5 py-0.5 bg-[#D1FAE5] text-[#065F46] rounded text-[10px] font-semibold">전문</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 데이터 없음 안내 */}
      {!analysisLoading && !kwSummary && !analysisError && (
        <div className="border border-[#E5E7EB] bg-[#F9FAFB] rounded-xl p-8 text-center">
          <p className="text-sm text-[#6B7280]">[전체 분석] 버튼을 눌러 분석을 시작하세요.</p>
        </div>
      )}
    </div>
  );
}
