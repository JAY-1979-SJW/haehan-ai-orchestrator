"use client";

import { useState } from "react";

type QuoteType = "이동형_임대" | "벽부형_임대" | "벽부형_구매";

const QUOTE_TYPES: { value: QuoteType; label: string; needsMonths: boolean }[] = [
  { value: "이동형_임대", label: "이동형 임대 (90,000원/월) — 안전 사이트 제공", needsMonths: true },
  { value: "벽부형_임대", label: "벽부형 임대 (70,000원/월)", needsMonths: true },
  { value: "벽부형_구매", label: "벽부형 구매 (1,200,000원/EA)", needsMonths: false },
];

export function QuotePanel() {
  const [recipient, setRecipient] = useState("");
  const [quoteType, setQuoteType] = useState<QuoteType>("이동형_임대");
  const [quantity, setQuantity] = useState(1);
  const [months, setMonths] = useState(6);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = QUOTE_TYPES.find((t) => t.value === quoteType)!;

  const unitPrice =
    quoteType === "이동형_임대" ? 90_000 : quoteType === "벽부형_임대" ? 70_000 : 1_200_000;
  const supplyAmount = selected.needsMonths
    ? unitPrice * quantity * months
    : unitPrice * quantity;
  const taxAmount = Math.floor(supplyAmount * 0.1);
  const total = supplyAmount + taxAmount;

  async function handleGenerate() {
    if (!recipient.trim()) {
      setError("현장명(수신처)을 입력하세요.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = {
        recipient: recipient.trim(),
        quote_type: quoteType,
        quantity,
      };
      if (selected.needsMonths) body.months = months;

      const res = await fetch("/api/v1/eum/quote/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? "생성 실패");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeName = recipient.trim().replace(/\s+/g, "_").slice(0, 30);
      a.download = `견적서_${safeName}_${quoteType}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-sm font-semibold text-gray-700">견적서 자동 작성</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* 현장명 */}
        <div className="sm:col-span-2">
          <label className="mb-1 block text-xs font-medium text-gray-600">현장명 (수신처)</label>
          <input
            type="text"
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="예) (주)성원전기 귀하"
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
          />
        </div>

        {/* 견적 유형 */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">견적 유형</label>
          <select
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={quoteType}
            onChange={(e) => setQuoteType(e.target.value as QuoteType)}
          >
            {QUOTE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {/* 수량 */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-600">수량 (EA)</label>
          <input
            type="number"
            min={1}
            className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={quantity}
            onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))}
          />
        </div>

        {/* 임대 개월 */}
        {selected.needsMonths && (
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">임대 개월수</label>
            <input
              type="number"
              min={1}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={months}
              onChange={(e) => setMonths(Math.max(1, Number(e.target.value)))}
            />
          </div>
        )}

        {/* 금액 미리보기 */}
        <div className="sm:col-span-2 rounded bg-gray-50 px-4 py-3 text-sm">
          <div className="flex justify-between text-gray-600">
            <span>공급가액</span>
            <span>{supplyAmount.toLocaleString()} 원</span>
          </div>
          <div className="flex justify-between text-gray-600">
            <span>세액 (10%)</span>
            <span>{taxAmount.toLocaleString()} 원</span>
          </div>
          <div className="mt-1 flex justify-between border-t border-gray-200 pt-1 font-semibold text-gray-800">
            <span>합계</span>
            <span>{total.toLocaleString()} 원</span>
          </div>
        </div>
      </div>

      {error && (
        <p className="mt-3 text-xs text-red-500">{error}</p>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="mt-4 w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "생성 중…" : "견적서 xlsx 다운로드"}
      </button>
    </section>
  );
}
