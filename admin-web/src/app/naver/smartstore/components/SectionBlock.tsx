import type { CatalogSection } from "../page";
import { ActionCard } from "./ActionCard";

const SECTION_COLOR: Record<string, string> = {
  read:     "border-[#BBF7D0] bg-[#F0FDF4] text-[#16A34A]",
  prepare:  "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C]",
  approval: "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
  submit:   "border-[#FECACA] bg-[#FEF2F2] text-[#DC2626]",
};

export function SectionBlock({ section }: { section: CatalogSection }) {
  const color = SECTION_COLOR[section.name] ?? "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]";
  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-3 px-3 py-2 rounded-lg border ${color}`}>
        <span className="font-bold text-sm uppercase">{section.name}</span>
        <span className="text-xs">총 {section.summary.total}개</span>
        <span className="text-xs">구현 {section.summary.implemented}개</span>
        {section.summary.approval_gated > 0 && (
          <span className="text-xs">승인필요 {section.summary.approval_gated}개</span>
        )}
      </div>
      <div className="grid grid-cols-1 gap-2 pl-2">
        {section.actions.map((a) => (
          <ActionCard key={a.action_id} action={a} />
        ))}
      </div>
    </div>
  );
}
