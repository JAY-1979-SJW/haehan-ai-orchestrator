"use client";
import { useState } from "react";

export function HistoryRow({ record, index }: { record: Record<string, unknown>; index: number }) {
  const [open, setOpen] = useState(false);
  const ts = (record.generated_at ?? record.timestamp ?? "") as string;
  const wf = (record.workflow ?? "-") as string;
  const pt = (record.product_type ?? "-") as string;
  const dr = record.dry_run === true;
  return (
    <div className="border border-[#E5E7EB] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 bg-white hover:bg-[#F9FAFB] text-left"
      >
        <span className="text-xs text-[#9CA3AF] w-6 shrink-0">#{index + 1}</span>
        <span className="text-xs font-mono text-[#6B7280] w-40 shrink-0 truncate">{ts}</span>
        <span className="text-xs text-[#111827] font-medium">{wf}</span>
        <span className="text-xs text-[#6B7280]">{pt}</span>
        {dr ? (
          <span className="ml-auto text-xs bg-[#FFF7ED] text-[#C2410C] border border-[#FED7AA] px-1.5 py-0.5 rounded">테스트(미저장)</span>
        ) : (
          <span className="ml-auto text-xs bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded">live</span>
        )}
        <span className="text-xs text-[#9CA3AF] ml-2">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-[#E5E7EB] px-4 py-3 bg-[#F9FAFB] space-y-1">
          {Object.entries(record).map(([k, v]) => (
            <div key={k} className="flex gap-3 text-xs">
              <span className="font-mono text-[#6B7280] w-32 shrink-0">{k}</span>
              <span className="text-[#111827] break-all">{JSON.stringify(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
