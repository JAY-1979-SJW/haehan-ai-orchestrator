/** /assistant 레이아웃 — 비서앱 MVP shell */
import Link from "next/link";
import type { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "/assistant",              label: "대시보드" },
  { href: "/assistant/tasks",        label: "작업 큐" },
  { href: "/assistant/approval",     label: "승인 게이트" },
  { href: "/assistant/external-sites", label: "외부 사이트" },
  { href: "/assistant/logs",         label: "로그·감사" },
  { href: "/assistant/storage",      label: "스토리지" },
  { href: "/assistant/deployment",   label: "배포 상태" },
];

export const metadata = { title: "비서앱 MVP | Haehan AI Admin" };

export default function AssistantLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#F9FAFB] flex flex-col">
      <header className="bg-white border-b border-[#E5E7EB] px-4 py-3 flex items-center gap-4">
        <Link href="/assistant" className="text-sm font-bold text-[#111827]">
          비서앱 MVP
        </Link>
        <span className="text-xs bg-[#EFF6FF] text-[#1D4ED8] border border-[#BFDBFE] px-2 py-0.5 rounded font-semibold">
          DRY_RUN 전용
        </span>
        <span className="text-xs bg-[#FEF2F2] text-[#991B1B] border border-[#FECACA] px-2 py-0.5 rounded">
          실행 버튼 없음
        </span>
        <nav className="flex gap-1 ml-4 overflow-x-auto">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-xs px-3 py-1.5 rounded-lg text-[#374151] hover:bg-[#F3F4F6] whitespace-nowrap"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto">
          <Link href="/" className="text-xs text-[#6B7280] hover:underline">← 어드민 홈</Link>
        </div>
      </header>
      <main className="flex-1 p-4 max-w-6xl mx-auto w-full">{children}</main>
    </div>
  );
}
