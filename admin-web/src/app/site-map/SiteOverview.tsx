"use client";
/**
 * 사이트 개요 — 사용자와 업무 목록을 확정하기 위한 현황 (M9 기준서 §4-E).
 * 업무를 조회·입력·제출로 묶어 보여 주고, 사용자가 목적을 적어 확정할 업무가 몇 개 남았는지 알린다. 그 아래에 이 사이트가 무엇을 다루는지(메뉴 색인·데이터 소스·사이트 선언 도구)를 보인다.
 * 값은 없다 — 지도에는 구조만 저장된다.
 */
import type { SiteMap } from "./api";
import { RISK_LABEL } from "./api";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-[#E5E7EB] bg-white px-3 py-2">
      <div className="text-[10px] text-[#6B7280]">{label}</div>
      <div className={`text-base font-semibold ${tone ?? "text-[#111827]"}`}>{value}</div>
      {sub && <div className="text-[10px] text-[#9CA3AF]">{sub}</div>}
    </div>
  );
}

export function SiteOverview({ siteMap }: { siteMap: SiteMap }) {
  const tasks = siteMap.tasks;
  const byRisk = (r: "read" | "write" | "submit") => tasks.filter((t) => t.risk === r).length;
  const withPurpose = tasks.filter((t) => t.purpose.trim()).length;
  const verified = tasks.filter((t) => t.state === "verified").length;
  const menu = siteMap.menu ?? [];
  const seen = Math.max(siteMap.menu_total_seen ?? 0, menu.length);
  const sources = siteMap.data_sources ?? [];
  const tools = siteMap.declared_tools ?? [];
  return (
    <div className="space-y-2 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] p-3" data-testid="site-overview">
      <div className="text-xs font-semibold text-[#111827]">업무 목록 현황</div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Stat label={RISK_LABEL.read} value={`${byRisk("read")}개`} sub="AI 가 실행 가능" tone="text-[#16A34A]" />
        <Stat label={RISK_LABEL.write} value={`${byRisk("write")}개`} sub="사람 승인 필요" tone="text-[#D97706]" />
        <Stat label={RISK_LABEL.submit} value={`${byRisk("submit")}개`} sub="사람만" tone="text-[#DC2626]" />
        <Stat label="목적 확정" value={`${withPurpose}/${tasks.length}`} sub={tasks.length - withPurpose > 0 ? `${tasks.length - withPurpose}개는 목적을 적어 주세요` : "모두 확정"} />
        <Stat label="검증됨" value={`${verified}/${tasks.length}`} />
      </div>
      {(menu.length > 0 || sources.length > 0 || tools.length > 0) && (
        <div className="space-y-1 text-xs text-[#374151]">
          {menu.length > 0 && (
            <div data-testid="site-overview-menu">
              메뉴 색인 {menu.length}개
              {seen > menu.length && <span className="ml-1 rounded bg-amber-100 px-1.5 text-[10px] text-amber-800">관측 {seen}개 중 일부만 저장(잘림)</span>}
            </div>
          )}
          {tools.length > 0 && (
            <div data-testid="site-overview-tools">
              사이트가 선언한 도구 {tools.length}개 —{" "}
              {tools.map((t) => (
                <span key={t.name} className="mr-1.5">
                  {t.name}
                  {t.description ? ` (${t.description})` : ""}
                </span>
              ))}
            </div>
          )}
          {sources.length > 0 && (
            <details data-testid="site-overview-sources">
              <summary className="cursor-pointer text-[#6B7280]">데이터 소스 {sources.length}개 — 화면이 로드될 때 사이트가 부르는 데이터 API 의 구조(값은 저장하지 않음)</summary>
              <ul className="mt-1 space-y-0.5">
                {sources.slice(0, 30).map((s) => (
                  <li key={`${s.host}${s.path}`} className="text-[11px]">
                    <span className="font-mono">
                      {s.host}
                      {s.path}
                    </span>
                    {s.lists.length > 0 && (
                      <span className="text-[#6B7280]">
                        {" "}
                        · 목록 {s.lists.map((l) => `${l.path || "(최상위)"} ${l.count}건 [${l.fields.slice(0, 6).join(", ")}]`).join(" · ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
