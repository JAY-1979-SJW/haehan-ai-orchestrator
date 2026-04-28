"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "@/lib/nav";

interface PageShellProps {
  title: string;
  description?: string;
  headerRight?: ReactNode;
  children: ReactNode;
}

function isNavActive(href: string, exact: boolean | undefined, pathname: string): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(href + "/");
}

export function PageShell({ title, description, headerRight, children }: PageShellProps) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen bg-[#F5F7FA]">
      {/* Sidebar */}
      <aside className="hidden lg:flex flex-col w-[220px] min-h-screen bg-white shrink-0"
        style={{ borderRight: "1px solid #E5E7EB" }}>
        {/* Orange accent top */}
        <div className="h-1 shrink-0 bg-[#F97316]" />

        {/* Logo */}
        <div className="h-[56px] flex items-center px-4 shrink-0"
          style={{ borderBottom: "1px solid #F3F4F6" }}>
          <span className="text-[14px] font-bold text-[#0F172A]">
            Haehan <span className="text-[#F97316]">AI</span>
            <span className="text-[11px] font-normal text-[#9CA3AF] ml-1">Admin</span>
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV_ITEMS.map((item) => {
            const active = isNavActive(item.href, item.exact, pathname);
            return (
              <Link
                key={item.key}
                href={item.href}
                className="flex items-center gap-3 px-4 py-[10px] text-[13px] transition-colors relative no-underline"
                style={{
                  background: active ? "#FFF7ED" : "transparent",
                  color: active ? "#F97316" : "#6B7280",
                  fontWeight: active ? 600 : 400,
                }}
              >
                {active && (
                  <span
                    className="absolute left-0 top-0 bottom-0 rounded-r-full"
                    style={{ width: 3, background: "#F97316" }}
                  />
                )}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0 h-screen overflow-hidden">
        {/* Orange top accent */}
        <div className="h-1 bg-[#F97316] shrink-0" />

        {/* Sticky header */}
        <header className="shrink-0 bg-white z-10 px-4 md:px-6 h-[52px] flex items-center gap-3"
          style={{ borderBottom: "1px solid #F3F4F6" }}>
          <div className="flex-1 flex items-center gap-3 min-w-0">
            <span className="text-[14px] font-bold text-[#0F172A] truncate">{title}</span>
            {description && (
              <span className="text-[12px] text-[#6B7280] truncate hidden sm:block">{description}</span>
            )}
          </div>
          {headerRight && (
            <div className="flex items-center gap-2 shrink-0">{headerRight}</div>
          )}
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto px-5 md:px-6 py-5 md:py-6">{children}</main>
      </div>
    </div>
  );
}
