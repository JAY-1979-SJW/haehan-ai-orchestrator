import { ReactNode } from "react";
import Link from "next/link";

interface PageShellProps {
  title: string;
  description?: string;
  headerRight?: ReactNode;
  children: ReactNode;
}

export function PageShell({ title, description, headerRight, children }: PageShellProps) {
  return (
    <div className="flex min-h-screen bg-[#F5F7FA]">
      {/* Sidebar placeholder */}
      <aside className="hidden md:flex flex-col w-[220px] min-h-screen bg-white border-r border-[#E5E7EB] shrink-0">
        {/* Orange accent top */}
        <div className="h-[4px] bg-[#F97316]" />
        <div className="px-5 py-4">
          <span className="text-[13px] font-bold text-[#0F172A]">Haehan AI Admin</span>
        </div>
        <nav className="flex-1 px-3 py-2 space-y-0.5">
          <Link
            href="/"
            className="flex items-center px-3 py-2 text-[13px] text-[#374151] rounded hover:bg-[#F3F4F6] transition-colors"
          >
            홈
          </Link>
          <Link
            href="/local-agents"
            className="flex items-center px-3 py-2 text-[13px] text-[#374151] rounded hover:bg-[#F3F4F6] transition-colors"
          >
            로컬 에이전트
          </Link>
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Orange top accent */}
        <div className="h-[4px] bg-[#F97316]" />

        {/* Sticky header */}
        <header className="sticky top-0 z-10 bg-white border-b border-[#E5E7EB] px-5 md:px-6 h-[52px] flex items-center justify-between">
          <div>
            <span className="text-[14px] font-bold text-[#0F172A]">{title}</span>
            {description && (
              <span className="ml-3 text-[12px] text-[#6B7280]">{description}</span>
            )}
          </div>
          {headerRight && <div className="flex items-center gap-2">{headerRight}</div>}
        </header>

        {/* Page content */}
        <main className="flex-1 px-5 md:px-6 py-5 md:py-6">{children}</main>
      </div>
    </div>
  );
}
