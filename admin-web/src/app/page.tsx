import { PageShell, KpiCard, Btn } from "@/components/ui";
import Link from "next/link";

const STAGES = [
  { id: "1A", label: "scaffold 생성", done: true },
  { id: "1B", label: "디자인 기반 이식", done: true },
  { id: "1C", label: "표준 UI 컴포넌트", done: true },
  { id: "1D", label: "/local-agents 정적 레이아웃", done: true },
  { id: "1E", label: "API 타입 / 클라이언트 설계", done: false },
  { id: "2",  label: "API 연동 (실시간)", done: false },
];

export default function Home() {
  return (
    <PageShell title="Haehan AI Admin" description="관리자 대시보드">
      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard title="등록 에이전트" value="—" description="Stage 11-UI-2에서 연동" />
        <KpiCard title="실행 중 태스크" value="—" accentColor="#1D4ED8" />
        <KpiCard title="완료 태스크"   value="—" accentColor="#059669" />
        <KpiCard title="실패 태스크"   value="—" accentColor="#B91C1C" />
      </div>

      {/* Navigation */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5 mb-4">
        <h2 className="text-[13px] font-bold text-[#0F172A] mb-3">메뉴</h2>
        <div className="flex flex-wrap gap-2">
          <Link href="/local-agents">
            <Btn variant="orange">로컬 에이전트 보기</Btn>
          </Link>
        </div>
      </div>

      {/* Stage progress */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5">
        <h2 className="text-[13px] font-bold text-[#0F172A] mb-3">
          Stage 11-UI 진행 현황
        </h2>
        <ul className="space-y-2">
          {STAGES.map((s) => (
            <li key={s.id} className="flex items-center gap-3">
              <span
                className={[
                  "inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold shrink-0",
                  s.done
                    ? "bg-[#F97316] text-white"
                    : "bg-[#F3F4F6] text-[#9CA3AF]",
                ].join(" ")}
              >
                {s.done ? "✓" : "·"}
              </span>
              <span
                className={[
                  "text-[13px]",
                  s.done
                    ? "text-[#374151] font-semibold"
                    : "text-[#9CA3AF]",
                ].join(" ")}
              >
                Stage 11-UI-{s.id} — {s.label}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </PageShell>
  );
}
