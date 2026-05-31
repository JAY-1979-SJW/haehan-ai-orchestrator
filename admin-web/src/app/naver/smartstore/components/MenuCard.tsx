import { MENU_CARD_COLOR, type MenuItem } from "./constants";

export function MenuCard({ menu }: { menu: MenuItem }) {
  const color = MENU_CARD_COLOR[menu.key] ?? "border-[#E5E7EB] bg-[#F9FAFB] text-[#6B7280]";
  return (
    <div className={`border rounded-xl p-3 ${color} relative`}>
      {menu.locked && (
        <span className="absolute top-2 right-2 text-[10px] bg-[#FEF2F2] text-[#DC2626] border border-[#FECACA] px-1.5 py-0.5 rounded font-semibold">잠금</span>
      )}
      <p className="text-sm font-bold mb-1.5">{menu.label}</p>
      <ul className="space-y-0.5">
        {menu.features.map((f) => (
          <li key={f} className="text-xs opacity-80 flex items-center gap-1">
            <span className="w-1 h-1 rounded-full bg-current opacity-50 shrink-0" />
            {f}
          </li>
        ))}
      </ul>
    </div>
  );
}
