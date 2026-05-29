"use client";
/** StatsClient — 데이터 분석 (매출 통계/방문 통계/상품 분석) — CDP 수집 연동 */
import { useState } from "react";
import {
  getSSStats,
  collectSSStats,
  type SSStatsData,
} from "@/lib/assistant/api";

type Tab = "sales" | "traffic" | "products";

function fmt(v: number | undefined): string {
  if (v === undefined || v === null) return "–";
  return v.toLocaleString();
}

export default function StatsClient() {
  const [tab, setTab] = useState<Tab>("sales");
  const [data, setData] = useState<SSStatsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const TABS: { id: Tab; label: string }[] = [
    { id: "sales",    label: "매출 통계" },
    { id: "traffic",  label: "방문 통계" },
    { id: "products", label: "상품 분석" },
  ];

  async function handleCollect() {
    setLoading(true);
    setError(null);
    try {
      setData(await collectSSStats());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleLoad() {
    setLoading(true);
    setError(null);
    try {
      setData(await getSSStats());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-[#E5E7EB] p-4">
        {/* 탭 바 */}
        <div className="flex gap-1 border-b border-[#E5E7EB] mb-4 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`text-sm px-4 py-2 -mb-px border-b-2 transition-colors whitespace-nowrap ${
                tab === t.id
                  ? "border-[#F97316] text-[#F97316] font-semibold"
                  : "border-transparent text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 매출 통계 탭 ── */}
        {tab === "sales" && (
          <div className="space-y-4">
            {/* 수집/조회 버튼 */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleCollect}
                disabled={loading}
                className="px-4 py-2 bg-[#1D4ED8] text-white text-sm rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors font-semibold"
              >
                {loading ? "수집 중…" : "수집"}
              </button>
              <button
                onClick={handleLoad}
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

            {/* 오류 표시 */}
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

            {/* 수치 카드 */}
            {data?.ok && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                  { label: "오늘 매출",     value: fmt(data.sales_today),   sub: "오늘 누적 (원)" },
                  { label: "이번 주 매출",  value: fmt(data.sales_week),    sub: "주간 누적 (원)" },
                  { label: "이번 달 매출",  value: fmt(data.sales_month),   sub: "월간 누적 (원)" },
                  { label: "오늘 방문자",   value: fmt(data.visitors_today), sub: "순 방문자 (UV)" },
                  { label: "오늘 주문 수",  value: fmt(data.orders_today),  sub: "결제 완료 건수" },
                ].map((card) => (
                  <div key={card.label} className="border border-[#E5E7EB] rounded-xl p-4 bg-white">
                    <p className="text-xs text-[#6B7280] mb-1">{card.label}</p>
                    <p className="text-2xl font-bold text-[#111827]">{card.value}</p>
                    <p className="text-xs text-[#9CA3AF] mt-1">{card.sub}</p>
                  </div>
                ))}
              </div>
            )}

            {/* 미수집 안내 */}
            {!data && !error && (
              <div className="border border-[#E5E7EB] rounded-xl p-8 text-center space-y-2">
                <p className="text-sm text-[#6B7280]">아직 수집된 데이터가 없습니다.</p>
                <p className="text-xs text-[#9CA3AF]">[수집] 버튼을 눌러 셀러센터에서 통계를 가져오세요.</p>
                <button
                  onClick={handleCollect}
                  disabled={loading}
                  className="mt-2 px-4 py-2 bg-[#1D4ED8] text-white text-xs rounded-lg hover:bg-[#1E40AF] disabled:opacity-50 transition-colors"
                >
                  수집 시작
                </button>
              </div>
            )}

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/analytics/sales"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 매출 통계 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 방문 통계 탭 ── */}
        {tab === "traffic" && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { label: "방문자수 (UV)",  desc: "스토어 또는 상품 페이지를 방문한 순 방문자 수" },
                { label: "전환율 (CVR)",   desc: "방문자 중 실제 구매로 이어진 비율. 평균 1~5% 수준" },
                { label: "페이지뷰 (PV)",  desc: "방문자가 조회한 페이지 총 수 (UV 대비 높을수록 탐색 활발)" },
                { label: "이탈률",         desc: "첫 페이지만 보고 떠난 방문자 비율. 낮을수록 좋음" },
              ].map((item) => (
                <div key={item.label} className="border border-[#E5E7EB] rounded-xl p-4 bg-white">
                  <p className="text-sm font-semibold text-[#111827]">{item.label}</p>
                  <p className="text-xs text-[#6B7280] mt-1">{item.desc}</p>
                </div>
              ))}
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/analytics/visitor"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 방문 통계 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 상품 분석 탭 ── */}
        {tab === "products" && (
          <div className="space-y-4">
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#6B7280]">상품 분석 활용 팁</p>
              <ul className="space-y-1">
                {[
                  "클릭수 높고 구매전환율 낮은 상품 → 상세페이지·가격 점검",
                  "클릭수 낮고 구매전환율 높은 상품 → 노출 최적화 필요",
                  "구매전환율 1% 미만 → 이미지·제목·가격 경쟁력 재검토",
                ].map((tip, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] shrink-0">·</span>
                    {tip}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/analytics/product"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 상품 분석 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
