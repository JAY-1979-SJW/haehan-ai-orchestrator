import { PageShell, Btn } from "@/components/ui";
import Link from "next/link";

const OP_ITEMS = [
  {
    label: "로컬 에이전트 관리",
    description: "에이전트 목록 조회 · 태스크 실행 · 스크린샷 확인",
    href: "/local-agents",
    badge: "운영 중",
    badgeCls: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]",
    cta: "바로 가기",
  },
  {
    label: "파일 지도 리포트",
    description: "로컬 파일 스캔 결과 · 민감정보 마스킹 관리",
    href: "/file-map",
    badge: "신기능",
    badgeCls: "bg-[#ECFDF5] text-[#059669] border-[#6EE7B7]",
    cta: "바로 가기",
  },
  {
    label: "승인 / 감사 로그",
    description: "운영 통제 기능 — 구현 예정",
    href: null,
    badge: "준비 중",
    badgeCls: "bg-[#EFF6FF] text-[#1D4ED8] border-[#BFDBFE]",
    cta: null,
  },
  {
    label: "시스템 문서",
    description: "운영 기준 및 아키텍처 문서 — docs/ 폴더 참조",
    href: null,
    badge: "문서 기준",
    badgeCls: "bg-[#F3F4F6] text-[#374151] border-[#D1D5DB]",
    cta: null,
  },
];

const PLATFORM_STATUS = [
  { label: "로컬 에이전트 운영 화면", where: "admin-web (이 화면)", status: "운영 기준" },
  { label: "legacy FastAPI admin",    where: "/admin (FastAPI)",      status: "deprecated fallback" },
  { label: "승인 / 권한 / 감사로그",  where: "admin-web — 예정",      status: "구현 예정" },
];

export default function Home() {
  return (
    <PageShell title="운영 대시보드" description="Haehan AI Orchestrator 관리자 UI">
      {/* Quick action cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-4 mb-6">
        {OP_ITEMS.map((item) => (
          <div
            key={item.label}
            className="bg-white border border-[#E5E7EB] rounded-[12px] p-5 flex flex-col gap-3"
            style={{ borderTop: "3px solid #F97316" }}
          >
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-bold text-[#0F172A] flex-1">{item.label}</span>
              <span
                className={[
                  "inline-flex items-center text-[11px] font-semibold px-2 py-0.5 rounded-full border",
                  item.badgeCls,
                ].join(" ")}
              >
                {item.badge}
              </span>
            </div>
            <p className="text-[12px] text-[#6B7280] leading-relaxed flex-1">{item.description}</p>
            {item.href && item.cta && (
              <Link href={item.href}>
                <Btn variant="orange">{item.cta}</Btn>
              </Link>
            )}
          </div>
        ))}
      </div>

      {/* Platform status */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5 mb-4">
        <h2 className="text-[13px] font-bold text-[#0F172A] mb-3">현재 운영 기준</h2>
        <table className="w-full text-[12px]">
          <thead>
            <tr className="text-[#9CA3AF] border-b border-[#F3F4F6]">
              <th className="text-left font-semibold pb-2 pr-4">기능</th>
              <th className="text-left font-semibold pb-2 pr-4">위치</th>
              <th className="text-left font-semibold pb-2">상태</th>
            </tr>
          </thead>
          <tbody>
            {PLATFORM_STATUS.map((row) => (
              <tr key={row.label} className="border-b border-[#F9FAFB] last:border-0">
                <td className="py-2 pr-4 text-[#374151]">{row.label}</td>
                <td className="py-2 pr-4 text-[#6B7280]">{row.where}</td>
                <td className="py-2 text-[#6B7280]">{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Next steps */}
      <div className="bg-white border border-[#E5E7EB] rounded-[12px] p-5">
        <h2 className="text-[13px] font-bold text-[#0F172A] mb-3">다음 작업 방향</h2>
        <ul className="space-y-2 text-[12px] text-[#6B7280]">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[#F97316] shrink-0" />
            local-agent 실제 제어 안정화 — 태스크 생성·취소·상태 폴링
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[#D1D5DB] shrink-0" />
            승인 / 권한 / 감사 로그 고도화 — 운영 통제 기능 추가
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-[#D1D5DB] shrink-0" />
            admin-web 공통 컴포넌트 / 디자인 토큰 정리
          </li>
        </ul>
      </div>
    </PageShell>
  );
}
