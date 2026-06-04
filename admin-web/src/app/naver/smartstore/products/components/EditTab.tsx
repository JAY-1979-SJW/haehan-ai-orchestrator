"use client";
import type { ProductEditResult } from "@/lib/assistant/api";
import { ProductForm } from "./ProductForm";

interface EditTabProps {
  editProductId: string;
  editFields: string;
  editResult: ProductEditResult | null;
  editLoading: boolean;
  editError: string | null;
  onSetEditProductId: (v: string) => void;
  onSetEditFields: (v: string) => void;
  onEdit: () => void;
}

export default function EditTab({
  editProductId, editFields, editResult, editLoading, editError,
  onSetEditProductId, onSetEditFields, onEdit,
}: EditTabProps) {
  return (
    <div className="space-y-4">
      <div className="border border-[#DDD6FE] bg-[#F5F3FF] rounded-xl p-4 space-y-1">
        <p className="text-sm font-semibold text-[#7C3AED]">CDP 상품 수정 (임시저장 전용)</p>
        <p className="text-xs text-[#6D28D9]">
          수정할 필드만 입력하세요. 빈 값은 변경하지 않습니다.
          최종 저장은 브라우저에서 직접 확인 후 눌러주세요.
        </p>
      </div>

      <div>
        <p className="text-sm font-semibold text-[#111827] mb-1.5">상품번호</p>
        <div className="flex gap-2">
          <input
            value={editProductId}
            onChange={e => onSetEditProductId(e.target.value)}
            placeholder="예: 1234567890"
            className="flex-1 border border-[#E5E7EB] rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-[#7C3AED]"
          />
          <button
            onClick={() => {
              if (editProductId) {
                window.open(`https://sell.smartstore.naver.com/#/products/${editProductId}/edit`, "_blank");
              }
            }}
            disabled={!editProductId}
            className="px-3 py-2 text-xs border border-[#7C3AED] text-[#7C3AED] rounded-xl hover:bg-[#F5F3FF] disabled:opacity-40"
          >
            브라우저 열기
          </button>
        </div>
        <p className="text-[10px] text-[#9CA3AF] mt-1">
          상품 목록 탭에서 행을 클릭하면 상품번호가 자동 입력됩니다.
        </p>
      </div>

      <div>
        <p className="text-sm font-semibold text-[#111827] mb-1.5">수정할 항목</p>
        <p className="text-xs text-[#9CA3AF] mb-2">
          바꿀 항목만 입력하세요 · 비워둔 항목은 그대로 유지됩니다
        </p>
        <ProductForm value={editFields} onChange={onSetEditFields} />
      </div>

      <button
        onClick={onEdit}
        disabled={editLoading || !editProductId.trim()}
        className="w-full py-3 rounded-xl bg-[#7C3AED] text-white text-sm font-semibold hover:bg-[#6D28D9] disabled:opacity-50 transition-colors"
      >
        {editLoading ? "수정 중…" : "CDP 상품 수정 (임시저장)"}
      </button>

      {editError && (
        <div className="border border-[#FECACA] bg-[#FEF2F2] rounded-xl p-3">
          <p className="text-sm text-[#DC2626] whitespace-pre-wrap">{editError}</p>
        </div>
      )}

      {editResult && (
        <div className={`border rounded-xl p-4 space-y-3 ${
          editResult.ok ? "border-[#BBF7D0] bg-[#F0FDF4]" : "border-[#FECACA] bg-[#FEF2F2]"
        }`}>
          <p className={`text-sm font-semibold ${editResult.ok ? "text-[#16A34A]" : "text-[#DC2626]"}`}>
            {editResult.ok ? `✓ 상품 ${editResult.product_id} 임시저장 완료` : "✗ 수정 실패"}
          </p>
          {editResult.steps && (
            <div className="space-y-1">
              {Object.entries(editResult.steps).map(([step, r]) => (
                <div key={step} className="flex items-center gap-2 text-xs">
                  <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    r.ok ? "bg-[#03C75A] text-white" : "bg-[#DC2626] text-white"
                  }`}>{r.ok ? "✓" : "✗"}</span>
                  <span className="font-mono text-[#6B7280] w-24 shrink-0">{step}</span>
                  {!r.ok && r.error != null && <span className="text-[#DC2626] truncate">{String(r.error as unknown)}</span>}
                  {r.ok && r.selector != null && <span className="text-[#9CA3AF] truncate">{String((r as Record<string,unknown>).selector)}</span>}
                </div>
              ))}
            </div>
          )}
          {editResult.hint && <p className="text-xs text-[#92400E]">{editResult.hint}</p>}
        </div>
      )}
    </div>
  );
}
