"use client";
import type { SellerCenterPageKey } from "@/lib/assistant/api";

interface BulkTabProps {
  openingPage: SellerCenterPageKey | null;
  openMsg: { ok: boolean; text: string } | null;
  onOpenSellerCenter: (pageKey: SellerCenterPageKey) => void;
}

export default function BulkTab({ openingPage, openMsg, onOpenSellerCenter }: BulkTabProps) {
  return (
    <div className="space-y-4">
      <div className="border border-[#03C75A]/30 bg-[#F0FDF4] rounded-xl p-5 space-y-3">
        <div>
          <p className="text-sm font-semibold text-[#111827]">셀러센터에서 직접 일괄 등록</p>
          <p className="text-xs text-[#6B7280] mt-1">
            로그인된 CDP 브라우저를 일괄 등록 페이지로 이동합니다.
          </p>
        </div>
        <button
          onClick={() => onOpenSellerCenter("list")}
          disabled={openingPage === "list"}
          className="w-full py-3 rounded-xl bg-[#03C75A] text-white text-sm font-semibold hover:bg-[#02A84A] disabled:opacity-50 transition-colors"
        >
          {openingPage === "list" ? "브라우저 이동 중…" : "셀러센터 상품 관리 열기"}
        </button>
        {openMsg && (
          <p className={`text-xs text-center ${openMsg.ok ? "text-green-700" : "text-red-600"}`}>
            {openMsg.ok ? "✓ " : "✗ "}{openMsg.text}
          </p>
        )}
      </div>

      <div className="border border-[#E5E7EB] rounded-xl p-4 bg-white space-y-3">
        <p className="text-sm font-semibold text-[#111827]">CSV 일괄 등록 순서</p>
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
    </div>
  );
}
