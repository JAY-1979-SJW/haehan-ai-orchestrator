"use client";
/** ReviewsClient — 리뷰/문의 (고객 리뷰/고객 문의/자동응답 설정) */
import { useState } from "react";

type Tab = "reviews" | "inquiries" | "autorespond";

const STAR_DIST: { star: number; count: number; pct: number }[] = [
  { star: 5, count: 84, pct: 84 },
  { star: 4, count: 10, pct: 10 },
  { star: 3, count: 3,  pct: 3  },
  { star: 2, count: 2,  pct: 2  },
  { star: 1, count: 1,  pct: 1  },
];

const INQUIRY_TYPES = [
  { type: "배송 문의",  desc: "배송 예정일, 운송장 조회 등", sla: "12시간 내" },
  { type: "상품 문의",  desc: "스펙, 재질, 사용법 등",       sla: "24시간 내" },
  { type: "환불 문의",  desc: "교환/반품/취소 요청",         sla: "24시간 내" },
];

const AUTO_TEMPLATES = [
  { label: "5점 리뷰",       template: "소중한 리뷰 감사드립니다! 항상 최선을 다하겠습니다." },
  { label: "4점 리뷰",       template: "리뷰 감사드립니다. 더 나은 서비스를 위해 노력하겠습니다." },
  { label: "3점 이하 리뷰",  template: "불편을 드려 죄송합니다. 문의사항은 채팅으로 연락 부탁드립니다." },
];

export default function ReviewsClient() {
  const [tab, setTab] = useState<Tab>("reviews");

  const TABS: { id: Tab; label: string }[] = [
    { id: "reviews",     label: "고객 리뷰" },
    { id: "inquiries",   label: "고객 문의" },
    { id: "autorespond", label: "자동응답 설정" },
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

        {/* ── 고객 리뷰 탭 ── */}
        {tab === "reviews" && (
          <div className="space-y-4">
            {/* 별점 분포 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-3">
                <p className="text-sm font-semibold text-[#111827]">별점 분포</p>
                <span className="text-xs bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] px-2 py-0.5 rounded font-semibold">
                  평균 4.7점
                </span>
              </div>
              <div className="space-y-2">
                {STAR_DIST.map((row) => (
                  <div key={row.star} className="flex items-center gap-3">
                    <span className="text-xs text-[#6B7280] w-8 shrink-0">{row.star}점</span>
                    <div className="flex-1 bg-[#F3F4F6] rounded-full h-2 overflow-hidden">
                      <div
                        className="h-full bg-[#F97316] rounded-full"
                        style={{ width: `${row.pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-[#6B7280] w-12 text-right shrink-0">{row.count}건</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 리뷰 관리 정책 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-[#111827]">리뷰 관리 정책</p>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">평균 별점 목표</span>
                  <span className="text-[#111827]">4.5점 이상 유지</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">수동 응답 기준</span>
                  <span className="text-[#111827]">3점 이하 리뷰는 24시간 내 수동 응답 권장</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">리뷰 삭제 요청</span>
                  <span className="text-[#111827]">허위 리뷰만 네이버 고객센터에 신고 가능</span>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/reviews"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 리뷰 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 고객 문의 탭 ── */}
        {tab === "inquiries" && (
          <div className="space-y-4">
            <div className="space-y-2">
              {INQUIRY_TYPES.map((item) => (
                <div key={item.type} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex items-start gap-4">
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-[#111827]">{item.type}</p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{item.desc}</p>
                  </div>
                  <span className="text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-2 py-0.5 rounded font-semibold shrink-0">
                    {item.sla}
                  </span>
                </div>
              ))}
            </div>

            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#C2410C] mb-1">응답 SLA</p>
              <p className="text-xs text-[#92400E]">
                네이버 셀러 평가 기준: <strong>24시간 내</strong> 미답변 시 응답률 하락. 응답률 90% 미만 시 노출 불이익 발생 가능.
              </p>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/inquiries"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 문의 관리 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 자동응답 설정 탭 ── */}
        {tab === "autorespond" && (
          <div className="space-y-4">
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#16A34A]">ReviewAutoResponder</p>
                <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded">구현됨</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">자동응답 모듈</span>
                  <span className="text-[#111827] font-mono">SmartStore.reviews.auto_responder</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">트리거 조건</span>
                  <span className="text-[#111827]">신규 리뷰 등록 후 1시간 이내 자동 응답</span>
                </div>
                <div className="flex gap-3">
                  <span className="font-semibold text-[#6B7280] w-28 shrink-0">승인 상태</span>
                  <span className="text-[#111827]">read-only (응답 발행은 approval_gated)</span>
                </div>
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">응답 템플릿</p>
              <div className="space-y-2">
                {AUTO_TEMPLATES.map((tmpl) => (
                  <div key={tmpl.label} className="border border-[#E5E7EB] rounded-lg p-3 bg-[#F9FAFB]">
                    <p className="text-xs font-semibold text-[#374151] mb-1">{tmpl.label}</p>
                    <p className="text-xs text-[#6B7280] italic">&ldquo;{tmpl.template}&rdquo;</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
