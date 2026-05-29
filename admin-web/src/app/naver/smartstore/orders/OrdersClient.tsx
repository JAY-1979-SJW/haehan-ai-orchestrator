"use client";
/** OrdersClient — 주문/정산 (주문 현황/정산 내역/배송 처리) */
import { useState } from "react";

type Tab = "status" | "settlement" | "delivery";

const ORDER_FLOW = ["결제완료", "배송준비", "배송중", "배송완료"];

const ORDER_STEPS = [
  { label: "주문 목록",    desc: "판매관리 > 주문 목록에서 전체 주문 확인" },
  { label: "발송 처리",    desc: "송장번호 입력 후 배송 상태 자동 업데이트" },
  { label: "반품/교환",    desc: "고객 요청 수락 → 회수 완료 → 환불 처리" },
];

const SETTLEMENT_INFO = [
  { label: "정산 주기",   value: "구매 확정일 기준 영업일 +2일" },
  { label: "월 정산일",   value: "매월 25일 (공휴일 시 전 영업일)" },
  { label: "정산 내역",   value: "정산관리 > 정산 내역에서 확인" },
  { label: "세금계산서",  value: "월별 세금계산서 자동 발행" },
  { label: "정산 계좌",   value: "판매자 정보 > 정산 계좌에서 설정" },
];

export default function OrdersClient() {
  const [tab, setTab] = useState<Tab>("status");

  const TABS: { id: Tab; label: string }[] = [
    { id: "status",     label: "주문 현황" },
    { id: "settlement", label: "정산 내역" },
    { id: "delivery",   label: "배송 처리" },
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

        {/* ── 주문 현황 탭 ── */}
        {tab === "status" && (
          <div className="space-y-5">
            {/* 주문 흐름 */}
            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">주문 처리 흐름</p>
              <div className="flex items-center gap-2 flex-wrap">
                {ORDER_FLOW.map((step, i) => (
                  <div key={step} className="flex items-center gap-2">
                    <span className="text-xs px-3 py-1.5 rounded-full bg-[#F0FDF4] border border-[#BBF7D0] text-[#16A34A] font-semibold">
                      {step}
                    </span>
                    {i < ORDER_FLOW.length - 1 && <span className="text-[#9CA3AF] text-sm">→</span>}
                  </div>
                ))}
              </div>
            </div>

            {/* 주문 처리 항목 */}
            <div className="space-y-2">
              {ORDER_STEPS.map((item) => (
                <div key={item.label} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex gap-4">
                  <span className="text-xs font-semibold text-[#F97316] bg-[#FFF7ED] border border-[#FED7AA] px-2 py-1 rounded shrink-0">
                    {item.label}
                  </span>
                  <p className="text-xs text-[#6B7280] self-center">{item.desc}</p>
                </div>
              ))}
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/orders/list"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 주문 목록 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 정산 내역 탭 ── */}
        {tab === "settlement" && (
          <div className="space-y-4">
            <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#7C3AED]">정산 주기 안내</p>
              <div className="space-y-2">
                {SETTLEMENT_INFO.map((item) => (
                  <div key={item.label} className="flex gap-3 text-xs">
                    <span className="font-semibold text-[#6B7280] w-24 shrink-0">{item.label}</span>
                    <span className="text-[#111827]">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-[#111827]">정산 계좌 연결 안내</p>
              <ol className="space-y-1.5">
                {[
                  "셀러센터 > 판매자 정보 > 정산 계좌 접속",
                  "사업자 명의 계좌 또는 본인 명의 계좌 등록",
                  "계좌 인증 완료 후 정산 수령 시작",
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
                href="https://sell.smartstore.naver.com/#/settlement"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 정산 내역 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 배송 처리 탭 ── */}
        {tab === "delivery" && (
          <div className="space-y-4">
            <div className="border border-[#BBF7D0] bg-[#F0FDF4] rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-[#16A34A]">N배송 연동</p>
              <p className="text-xs text-[#15803D]">
                네이버 N배송과 연동하면 운송장 자동 입력 및 배송 상태 자동 추적이 가능합니다.
              </p>
            </div>

            <div className="border border-[#E5E7EB] rounded-xl p-4 space-y-3">
              <p className="text-sm font-semibold text-[#111827]">배송 처리 절차</p>
              <div className="space-y-2">
                {[
                  { step: "1", label: "주문 확인",    desc: "결제 완료 주문 목록 확인 (주문 접수 후 24시간 내 처리 권장)" },
                  { step: "2", label: "상품 출고",    desc: "상품 포장 및 택배사 인계" },
                  { step: "3", label: "운송장 등록",  desc: "셀러센터에서 운송장 번호 입력 또는 N배송 자동 연동" },
                  { step: "4", label: "배송 추적",    desc: "배송 상태 자동 업데이트 및 고객 알림 발송" },
                ].map((item) => (
                  <div key={item.step} className="flex gap-3">
                    <span className="text-xs font-bold text-[#F97316] bg-[#FFF7ED] border border-[#FED7AA] rounded-full w-6 h-6 flex items-center justify-center shrink-0">
                      {item.step}
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-[#111827]">{item.label}</p>
                      <p className="text-xs text-[#6B7280]">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/delivery"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 배송 관리 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
