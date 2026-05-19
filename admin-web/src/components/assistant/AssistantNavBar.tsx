"use client";
/** 비서앱 MVP 네비게이션 — 활성 탭 하이라이트 (APP_NAV_ACTIVE_STATE_POLISH_01) */
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/assistant",               label: "대시보드",   exact: true },
  { href: "/assistant/tasks",         label: "작업 큐",    exact: false },
  { href: "/assistant/approval",      label: "승인 게이트", exact: false },
  { href: "/assistant/external-sites", label: "외부 사이트", exact: false },
  { href: "/assistant/news",           label: "뉴스",       exact: false },
  { href: "/assistant/logs",          label: "로그·감사",  exact: false },
  { href: "/assistant/storage",       label: "스토리지",   exact: false },
  { href: "/assistant/deployment",    label: "배포 상태",  exact: false },
];

export function AssistantNavBar() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 ml-4 overflow-x-auto">
      {NAV_ITEMS.map((item) => {
        const isActive = item.exact
          ? pathname === item.href
          : pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`text-xs px-3 py-1.5 rounded-lg whitespace-nowrap transition-colors ${
              isActive
                ? "bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] font-semibold"
                : "text-[#374151] hover:bg-[#F3F4F6]"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
