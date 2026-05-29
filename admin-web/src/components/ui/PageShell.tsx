"use client";

import { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_GROUPS } from "@/lib/nav";

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
    <div className="flex min-h-dvh bg-[#F5F7FA]">
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
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi}>
              <div className="px-4 pt-4 pb-1 text-[10px] font-semibold tracking-widest uppercase"
                style={{ color: "#9CA3AF" }}>
                {group.group}
              </div>
              {group.items.map((item) => {
                const active = isNavActive(item.href, item.exact, pathname);
                return (
                  <Link
                    key={item.key}
                    href={item.href}
                    className="flex items-center gap-3 px-4 py-[9px] text-[13px] transition-colors relative no-underline"
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
                    <span
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold"
                      style={{
                        background: active ? "#FED7AA" : "#F3F4F6",
                        color: active ? "#C2410C" : "#6B7280",
                      }}
                      aria-hidden="true"
                    >
                      {item.shortLabel.slice(0, 1)}
                    </span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main area */}
      <div className="flex h-dvh min-w-0 flex-1 flex-col overflow-hidden">
        {/* Orange top accent */}
        <div className="h-1 bg-[#F97316] shrink-0" />

        {/* Sticky header */}
        <header className="shrink-0 bg-white z-10 px-4 md:px-6 h-[56px] lg:h-[52px] flex items-center gap-3"
          style={{ borderBottom: "1px solid #F3F4F6" }}>
          <div className="flex-1 flex items-center gap-3 min-w-0">
            <span className="lg:hidden flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#F97316] text-[13px] font-bold text-white">
              AI
            </span>
            <span className="text-[14px] font-bold text-[#0F172A] truncate">{title}</span>
            {description && (
              <span className="text-[12px] text-[#6B7280] truncate hidden sm:block">{description}</span>
            )}
          </div>
          {headerRight && (
            <div className="flex items-center gap-2 shrink-0">{headerRight}</div>
          )}
        </header>

        {/* Page content — flex-1 + overflow-hidden so children can use h-full */}
        <main className="flex-1 min-h-0 overflow-y-auto px-4 py-4 pb-[calc(84px+env(safe-area-inset-bottom))] md:px-6 md:py-6 lg:pb-6">
          {children}
        </main>
      </div>

      <nav
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-[#E5E7EB] bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] pt-1 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden"
        aria-label="모바일 하단 메뉴"
      >
        {NAV_GROUPS.flatMap((g) => g.items).slice(0, 5).map((item) => {
          const active = isNavActive(item.href, item.exact, pathname);
          return (
            <Link
              key={item.key}
              href={item.href}
              className="flex h-[58px] min-w-0 flex-col items-center justify-center gap-1 rounded-md no-underline"
              style={{ color: active ? "#F97316" : "#6B7280" }}
              aria-current={active ? "page" : undefined}
            >
              <span
                className="flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold"
                style={{
                  background: active ? "#FFF7ED" : "transparent",
                  border: active ? "1px solid #FED7AA" : "1px solid transparent",
                }}
                aria-hidden="true"
              >
                {item.shortLabel.slice(0, 1)}
              </span>
              <span className="max-w-full truncate text-[11px] font-semibold">{item.shortLabel}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
