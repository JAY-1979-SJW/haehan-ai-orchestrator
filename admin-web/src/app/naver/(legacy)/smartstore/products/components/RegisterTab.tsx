"use client";
import type { SellerCenterPageKey } from "@/lib/assistant/api";
import { REGISTER_STEPS } from "./tabConstants";

interface RegisterTabProps {
  openingPage: SellerCenterPageKey | null;
  openMsg: { ok: boolean; text: string } | null;
  onOpenSellerCenter: (pageKey: SellerCenterPageKey) => void;
}

export default function RegisterTab({ openingPage, openMsg, onOpenSellerCenter }: RegisterTabProps) {
  return (
    <div className="space-y-4">
      <div className="border border-[#03C75A]/30 bg-[#F0FDF4] rounded-xl p-5 space-y-3">
        <div>
          <p className="text-sm font-semibold text-[#111827]">셀러센터에서 직접 등록</p>
          <p className="text-xs text-[#6B7280] mt-1">
            로그인된 CDP 브라우저를 상품 등록 페이지로 이동합니다. 브라우저에서 직접 작성하세요.
          </p>
        </div>
        <button
          onClick={() => onOpenSellerCenter("register")}
          disabled={openingPage === "register"}
          className="w-full py-3 rounded-xl bg-[#03C75A] text-white text-sm font-semibold hover:bg-[#02A84A] disabled:opacity-50 transition-colors"
        >
          {openingPage === "register" ? "브라우저 이동 중…" : "셀러센터 상품 등록 페이지 열기"}
        </button>
        {openMsg && (
          <p className={`text-xs text-center ${openMsg.ok ? "text-green-700" : "text-red-600"}`}>
            {openMsg.ok ? "✓ " : "✗ "}{openMsg.text}
          </p>
        )}
      </div>

      <p className="text-xs text-[#6B7280]">등록 전 아래 항목을 순서대로 완료하세요.</p>
      <div className="space-y-2">
        {REGISTER_STEPS.map((s) => (
          <div key={s.step} className="flex gap-3 items-start border border-[#E5E7EB] rounded-xl p-3 bg-white">
            <span className={`text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shrink-0 ${
              s.required ? "bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA]" : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
            }`}>
              {s.step}
            </span>
            <div>
              <p className="text-sm font-semibold text-[#111827]">
                {s.title}{s.required && <span className="ml-1 text-[#DC2626]">*</span>}
              </p>
              <p className="text-xs text-[#6B7280] mt-0.5">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
