"use client";
/** MarketingClient — 마케팅/혜택 (쿠폰·할인/프로모션/SEO 최적화) */
import { useState } from "react";

type Tab = "coupons" | "promotions" | "seo";

const COUPON_TYPES = [
  {
    label: "즉시할인 쿠폰",
    desc: "상품 상세페이지에서 즉시 적용되는 할인 쿠폰. 구매 전환율 상승 효과.",
    badge: "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]",
  },
  {
    label: "다운로드 쿠폰",
    desc: "고객이 직접 다운로드하여 사용. 스토어 찜 고객 또는 신규 고객 대상 발급 가능.",
    badge: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
  },
  {
    label: "장바구니 쿠폰",
    desc: "장바구니 결제 시 자동 적용. 특정 금액 이상 구매 시 할인 조건 설정 가능.",
    badge: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]",
  },
];

const PROMOTIONS = [
  { name: "스마트스토어 성장 지원 프로모션", status: "진행중", period: "2026.04.01 ~ 2026.06.30" },
  { name: "여름 시즌 기획전",               status: "예정",   period: "2026.07.01 ~ 2026.08.31" },
];

const SEO_TIPS = [
  "상품명에 주요 검색 키워드 앞부분에 배치 (예: '[브랜드] 키워드 상품 특징')",
  "상품명은 30~40자 내외가 적합 (100자 제한이지만 검색 노출 최적화는 30~40자)",
  "카테고리 정확히 선택 — 잘못된 카테고리는 노출 불이익 발생",
  "대표 이미지 배경 흰색 권장, 상품 정면 촬영",
  "태그에 연관 검색어 5~10개 등록",
];

export default function MarketingClient() {
  const [tab, setTab] = useState<Tab>("coupons");

  const TABS: { id: Tab; label: string }[] = [
    { id: "coupons",    label: "쿠폰/할인" },
    { id: "promotions", label: "프로모션" },
    { id: "seo",        label: "SEO 최적화" },
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

        {/* ── 쿠폰/할인 탭 ── */}
        {tab === "coupons" && (
          <div className="space-y-4">
            <div className="space-y-3">
              {COUPON_TYPES.map((coupon) => (
                <div key={coupon.label} className={`border rounded-xl p-4 ${coupon.badge}`}>
                  <p className="text-sm font-semibold mb-1">{coupon.label}</p>
                  <p className="text-xs opacity-80">{coupon.desc}</p>
                </div>
              ))}
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#6B7280]">쿠폰 발급 주의사항</p>
              <ul className="space-y-1">
                {[
                  "최소 할인율 3%, 최소 금액 할인 100원 이상",
                  "쿠폰 유효기간 최대 90일",
                  "발급 수량 제한 또는 무제한 선택 가능",
                  "발급 후 취소 불가 — 신중히 설정",
                ].map((note, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] shrink-0">·</span>
                    {note}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/marketing/coupon"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 쿠폰 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 프로모션 탭 ── */}
        {tab === "promotions" && (
          <div className="space-y-4">
            <div className="space-y-2">
              {PROMOTIONS.map((promo) => (
                <div key={promo.name} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex items-start gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-[#111827]">{promo.name}</p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{promo.period}</p>
                  </div>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border font-semibold shrink-0 ${
                      promo.status === "진행중"
                        ? "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]"
                        : "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]"
                    }`}
                  >
                    {promo.status}
                  </span>
                </div>
              ))}
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-xs font-semibold text-[#6B7280]">프로모션 참여 방법</p>
              <ol className="space-y-1.5">
                {[
                  "셀러센터 > 혜택/마케팅 > 프로모션 관리 접속",
                  "진행 중인 프로모션 목록에서 참여 가능 항목 확인",
                  "조건 확인 후 참여 신청 (일부 프로모션은 초대 필요)",
                ].map((step, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ol>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/marketing/promotion"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 프로모션 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── SEO 최적화 탭 ── */}
        {tab === "seo" && (
          <div className="space-y-4">
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#16A34A]">SEOOptimizer</p>
                <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded">구현됨</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">최적화 모듈</span>
                  <span className="text-[#111827] font-mono">SmartStore.seo_optimizer</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">주요 기능</span>
                  <span className="text-[#111827]">상품명 키워드 분석, 태그 추천, 카테고리 최적화</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">승인 상태</span>
                  <span className="text-[#111827]">read-only 분석 가능 (변경은 approval_gated)</span>
                </div>
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">상품명 최적화 팁</p>
              <ul className="space-y-2">
                {SEO_TIPS.map((tip, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#374151]">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    {tip}
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/store/info"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 스토어 설정 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
