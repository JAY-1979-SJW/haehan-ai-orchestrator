"use client";
/** ProductsClient — 상품 관리 (목록/등록/일괄 등록) */
import { useState } from "react";

type Tab = "list" | "register" | "bulk";

const PRODUCT_STATUS: { label: string; badge: string }[] = [
  { label: "판매중",   badge: "bg-[#F0FDF4] text-[#16A34A] border-[#BBF7D0]" },
  { label: "일시품절", badge: "bg-[#FFF7ED] text-[#C2410C] border-[#FED7AA]" },
  { label: "판매중지", badge: "bg-[#FEF2F2] text-[#DC2626] border-[#FECACA]" },
];

const REGISTER_STEPS = [
  { step: 1, title: "카테고리 선택", desc: "정확한 카테고리 선택 (판매 수수료 결정)", required: true },
  { step: 2, title: "기본 정보",     desc: "상품명(최대 100자), 판매가(최소 10원), 재고 수량", required: true },
  { step: 3, title: "이미지 등록",   desc: "대표이미지 필수(최대 10MB), 추가이미지 선택", required: true },
  { step: 4, title: "상세 설명",     desc: "스마트에디터 또는 HTML 직접 작성", required: false },
  { step: 5, title: "저장 및 노출",  desc: "임시저장 → 최종 저장 → 노출 설정 확인", required: true },
];

const SAMPLE_PRODUCTS = [
  { name: "무선 LED 무드등 USB 충전식", status: "판매중",   price: "29,900원", stock: 142 },
  { name: "캠핑용 랜턴 방수 휴대용",   status: "일시품절", price: "45,000원", stock: 0 },
  { name: "야간 독서등 클립형",        status: "판매중지", price: "18,500원", stock: 23 },
];

export default function ProductsClient() {
  const [tab, setTab] = useState<Tab>("list");
  const [filter, setFilter] = useState<string>("전체");

  const TABS: { id: Tab; label: string }[] = [
    { id: "list",     label: "상품 목록" },
    { id: "register", label: "상품 등록" },
    { id: "bulk",     label: "일괄 등록" },
  ];

  const statusBadge = (status: string) => {
    const found = PRODUCT_STATUS.find((s) => s.label === status);
    return found?.badge ?? "bg-[#F3F4F6] text-[#6B7280] border-[#E5E7EB]";
  };

  const filtered = filter === "전체" ? SAMPLE_PRODUCTS : SAMPLE_PRODUCTS.filter((p) => p.status === filter);

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

        {/* ── 상품 목록 탭 ── */}
        {tab === "list" && (
          <div className="space-y-4">
            {/* 필터 */}
            <div className="flex gap-2 flex-wrap">
              {["전체", "판매중", "일시품절", "판매중지"].map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    filter === f
                      ? "border-[#F97316] bg-[#FFF7ED] text-[#C2410C] font-semibold"
                      : "border-[#E5E7EB] text-[#6B7280] hover:bg-[#F9FAFB]"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

            {/* 상품 목록 */}
            <div className="space-y-2">
              {filtered.map((product) => (
                <div key={product.name} className="border border-[#E5E7EB] rounded-xl p-4 bg-white flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-[#111827] truncate">{product.name}</p>
                    <p className="text-xs text-[#6B7280] mt-0.5">재고 {product.stock}개 · {product.price}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold shrink-0 ${statusBadge(product.status)}`}>
                    {product.status}
                  </span>
                </div>
              ))}
              {filtered.length === 0 && (
                <div className="border border-[#E5E7EB] rounded-xl p-8 text-center">
                  <p className="text-sm text-[#6B7280]">해당 상태의 상품이 없습니다.</p>
                </div>
              )}
            </div>

            {/* 셀러센터 바로가기 */}
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/list"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 상품 목록 바로가기 →
              </a>
            </div>
          </div>
        )}

        {/* ── 상품 등록 탭 ── */}
        {tab === "register" && (
          <div className="space-y-4">
            <p className="text-xs text-[#6B7280]">상품 등록은 5단계로 진행됩니다. 필수(*) 항목을 반드시 완료하세요.</p>
            <div className="space-y-3">
              {REGISTER_STEPS.map((s) => (
                <div key={s.step} className="flex gap-3 items-start border border-[#E5E7EB] rounded-xl p-4 bg-white">
                  <span
                    className={`text-xs font-bold rounded-full w-7 h-7 flex items-center justify-center shrink-0 ${
                      s.required
                        ? "bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA]"
                        : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                    }`}
                  >
                    {s.step}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-[#111827]">
                      {s.title}
                      {s.required && <span className="ml-1 text-[#DC2626]">*</span>}
                    </p>
                    <p className="text-xs text-[#6B7280] mt-0.5">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/new"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-4 py-2 rounded-lg bg-[#F97316] text-white hover:bg-[#EA6D0E] transition-colors font-semibold"
              >
                셀러센터에서 상품 등록 →
              </a>
            </div>
          </div>
        )}

        {/* ── 일괄 등록 탭 ── */}
        {tab === "bulk" && (
          <div className="space-y-4">
            <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-3">
              <p className="text-sm font-semibold text-[#111827]">CSV 일괄 등록 안내</p>
              <ol className="space-y-2">
                {[
                  "셀러센터 > 상품관리 > 상품 일괄 등록 접속",
                  "엑셀 양식(xlsx) 다운로드 후 상품 정보 입력",
                  "필수 컬럼: 카테고리ID, 상품명, 판매가, 재고, 대표이미지URL",
                  "파일 업로드 후 오류 항목 확인 및 수정",
                  "최종 등록 완료 후 노출 여부 설정",
                ].map((step, i) => (
                  <li key={i} className="flex gap-3 text-xs">
                    <span className="text-[#F97316] font-bold shrink-0">{i + 1}.</span>
                    <span className="text-[#374151]">{step}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div className="border border-[#FED7AA] bg-[#FFF7ED] rounded-xl p-4">
              <p className="text-xs font-semibold text-[#C2410C] mb-1">BulkRegister 모듈</p>
              <p className="text-xs text-[#92400E]">
                자동화 모듈 <span className="font-mono">SmartStore.bulk_register</span>를 통해 CSV 생성 및 업로드를 지원합니다.
                현재 <span className="font-semibold">approval_gated</span> 상태로 승인 후 실행 가능합니다.
              </p>
            </div>
            <div className="flex justify-end">
              <a
                href="https://sell.smartstore.naver.com/#/products/bulk"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded-lg border border-[#F97316] text-[#F97316] hover:bg-[#FFF7ED] transition-colors"
              >
                셀러센터 일괄 등록 바로가기 →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
