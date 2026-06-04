"use client";
import { useState } from "react";

/**
 * UsageHelp — 각 기능 화면 상단의 접이식 "❓ 사용법" 안내.
 * 일반 사용자가 설명 없이도 단계대로 따라 할 수 있게 1·2·3 스텝으로 간결하게.
 */
export function UsageHelp({ title = "사용법", steps, defaultOpen = false }: {
  title?: string;
  steps: string[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-[#FDE68A] bg-[#FFFBEB] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-semibold text-[#92400E] hover:bg-[#FEF3C7] transition-colors"
      >
        <span>❓ {title}</span>
        <span className="text-xs font-normal text-[#B45309]">{open ? "▲ 접기" : "▼ 펼치기"}</span>
      </button>
      {open && (
        <ol className="px-5 pb-3 pt-1 space-y-1.5 text-xs text-[#78350F] list-decimal list-inside leading-relaxed">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
