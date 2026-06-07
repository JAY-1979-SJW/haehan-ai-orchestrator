"use client";
/** 구글 허브 — 좌측 서비스 카드 그리드 (검색 + 그룹별 카드) */
import { type Service, CATALOG, GROUPS, GROUP_COLORS } from "./googleCatalog";

export function ServiceGrid({ query, setQuery, onCardClick, onOpen, onAction }: {
  query: string;
  setQuery: (v: string) => void;
  onCardClick: (s: Service) => void;
  onOpen: (e: React.MouseEvent, s: Service) => void;
  onAction: (e: React.MouseEvent, s: Service) => void;
}) {
  const filtered = CATALOG.filter((s) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.desc.includes(q) || s.g.includes(q);
  });

  return (
    <div className="flex-1 min-w-0 space-y-4 overflow-y-auto pr-1">
      {/* 검색 바 */}
      <div className="bg-white border border-[#E5E7EB] rounded-2xl px-4 py-2.5 flex items-center gap-2 sticky top-0 z-10">
        <span className="text-[#9CA3AF] text-sm shrink-0">🔍</span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="서비스 이름·기능 검색..."
          className="flex-1 text-sm outline-none text-[#111827] placeholder:text-[#9CA3AF] bg-transparent"
        />
        {query && (
          <button onClick={() => setQuery("")}
            className="text-xs text-[#9CA3AF] hover:text-[#6B7280] shrink-0">지우기</button>
        )}
        <span className="text-xs text-[#9CA3AF] whitespace-nowrap shrink-0">
          {filtered.length}/{CATALOG.length}
        </span>
      </div>

      {/* 그룹별 카드 */}
      {GROUPS.map((g) => {
        const items = filtered.filter((s) => s.g === g);
        if (!items.length) return null;
        const theme = GROUP_COLORS[g] ?? GROUP_COLORS["계정·정보"];
        return (
          <div key={g} className="space-y-2">
            <p className="text-[10px] font-bold tracking-widest uppercase px-1" style={{ color: theme.color }}>{g}</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2">
              {items.map((s) => (
                <div
                  key={s.name}
                  onClick={() => onCardClick(s)}
                  className="bg-white border rounded-xl p-3 cursor-pointer transition-all hover:shadow-sm select-none"
                  style={{ borderColor: "#E5E7EB", background: "#FFFFFF" }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg leading-none shrink-0">{s.icon}</span>
                    <span className="text-xs font-semibold text-[#111827] truncate">{s.name}</span>
                  </div>
                  <p className="text-[10px] text-[#6B7280] leading-tight mb-2 line-clamp-2">{s.desc}</p>
                  <div className="flex gap-1 flex-wrap">
                    <button
                      onClick={(e) => onOpen(e, s)}
                      className="text-[10px] font-semibold px-2 py-0.5 rounded-md border transition-colors hover:opacity-80"
                      style={{ background: theme.bg, color: theme.color, borderColor: theme.border }}>
                      열기
                    </button>
                    {s.doKey && s.doLabel && (
                      <button
                        onClick={(e) => onAction(e, s)}
                        className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-[#F0FDF4] text-[#16A34A] border border-[#BBF7D0] hover:bg-[#BBF7D0] transition-colors">
                        {s.doLabel}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
