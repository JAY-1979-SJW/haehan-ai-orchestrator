"use client";
/** StatsClient — 데이터 분석 (매출 통계/방문 통계/상품 분석) */
import { useState } from "react";

type Tab = "sales" | "traffic" | "products";

const SALES_CARDS = [
  { label: "오늘 매출",   value: "–",       sub: "실시간 데이터는 셀러센터에서 확인" },
  { label: "이번 주 매출", value: "–",       sub: "월~오늘 누적" },
  { label: "이번 달 매출", value: "–",       sub: "월초부터 오늘까지 누적" },
];

const TOP_PRODUCTS = [
  { name: "무선 LED 무드등 USB 충전식", clicks: 1240, cvr: "3.8%" },
  { name: "캠핑용 랜턴 방수 휴대용",   clicks: 890,  cvr: "2.1%" },
  { name: "야간 독서등 클립형",        clicks: 560,  cvr: "4.5%" },
];

export default function StatsClient() {
  const [tab, setTab] = useState<Tab>("sales");

  const TABS: { id: Tab; label: string }[] = [
    { id: "sales",    label: "매출 통계" },
    { id: "traffic",  label: "방문 통계" },
    { id: "products", label: "상품 분석" },
  ];

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
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {SALES_CARDS.map((card) => (
                <div key={card.label} className="border border-[#E5E7EB] rounded-xl p-4 bg-white">
                  <p className="text-xs text-[#6B7280] mb-1">{card.label}</p>
                  <p className="text-2xl font-bold text-[#111827]">{card.value}</p>
                  <p className="text-xs text-[#9CA3AF] mt-1">{card.sub}</p>
                </div>
              ))}
            </div>

            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#C2410C] mb-1">실시간 매출 데이터</p>
              <p className="text-xs text-[#92400E]">
                실시간 매출 데이터는 API 연동이 필요합니다. 정확한 수치는 셀러센터 데이터분석 메뉴에서 확인하세요.
              </p>
              <a
                href="https://sell.smartstore.naver.com/#/analytics/sales"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-2 text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-white transition-colors"
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
            <div className="border border-[#E5E7EB] rounded-xl overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-[#F9FAFB] border-b border-[#E5E7EB]">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-[#6B7280] font-semibold">상품명</th>
                    <th className="text-right px-4 py-2.5 text-[#6B7280] font-semibold">클릭수</th>
                    <th className="text-right px-4 py-2.5 text-[#6B7280] font-semibold">구매전환율</th>
                  </tr>
                </thead>
                <tbody>
                  {TOP_PRODUCTS.map((p, i) => (
                    <tr key={p.name} className={i % 2 === 0 ? "bg-white" : "bg-[#F9FAFB]"}>
                      <td className="px-4 py-2.5 text-[#111827]">{p.name}</td>
                      <td className="px-4 py-2.5 text-right text-[#374151]">{p.clicks.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right">
                        <span className="text-[#16A34A] font-semibold">{p.cvr}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

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
