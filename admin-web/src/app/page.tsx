'use client';
import Link from "next/link";
import { AppInstallButton } from "@/components/app/AppInstallButton";
import {
  TopAccentLine,
  StatusBadge,
  MetricCard,
  GateStatusCard,
  WarehouseCard,
  ConstructionPhaseTable,
  Button,
  Input,
  Select,
} from "@haehan/design-system";
import type { ConstructionPhaseRow } from "@haehan/design-system";

const AGENT_METRICS = [
  { label: "온라인 에이전트", value: "3", sub: "대 온라인", accentColor: "#059669" as const },
  { label: "대기 중 태스크", value: "7", sub: "건 대기", accentColor: "#F97316" as const },
  { label: "오늘 처리 완료", value: "24", sub: "건 완료", accentColor: "#1D4ED8" as const },
  { label: "승인 대기", value: "2", sub: "건 미처리", accentColor: "#B91C1C" as const },
];

const GATES = [
  {
    gateName: "FORBIDDEN_IMPORT",
    decision: "PASS" as const,
    reason: "역방향 import 없음",
  },
  {
    gateName: "SECURITY_PATTERN",
    decision: "PASS" as const,
    reason: "secret 노출 없음",
  },
  {
    gateName: "CIRCULAR_IMPORT",
    decision: "PASS" as const,
    reason: "순환 의존성 없음",
  },
  {
    gateName: "QUALITY_GATE",
    decision: "WARN" as const,
    reason: "미완성 모듈 3개",
  },
];

const WAREHOUSES = [
  {
    title: "EUM 단말기",
    path: "data/eum_all_devices_complete.json",
    fileCount: 22,
    status: "PASS" as const,
    description: "비전아이(주) 임대 현장 22개",
  },
  {
    title: "G2B 입찰",
    path: "data/g2b",
    fileCount: 154,
    status: "PASS" as const,
    description: "최근 동기화: 2026-05-14",
  },
  {
    title: "히웍스 공지",
    path: "data/hiworks",
    fileCount: 8,
    status: "HOLD" as const,
    description: "최근 동기화: 2026-05-13",
  },
  {
    title: "YouTube 콘텐츠",
    path: "data/youtube",
    fileCount: 5,
    status: "HOLD" as const,
    description: "최근 동기화: 2026-05-10",
  },
];

const PHASE_ROWS: ConstructionPhaseRow[] = [
  {
    phase: "기반 공사",
    code: "FOUNDATION_01",
    status: "DONE",
    completedAt: "2026-04-22",
    notes: "P1 App Foundation PASS",
  },
  {
    phase: "디자인시스템",
    code: "DS_ROOT_01",
    status: "DONE",
    completedAt: "2026-05-15",
    notes: "00.디자인시스템 구축",
  },
  {
    phase: "소비 앱 계약",
    code: "DS_CONSUMER_REF_01",
    status: "DONE",
    completedAt: "2026-05-15",
    notes: "@haehan/design-system 계약 고정",
  },
  {
    phase: "비서앱 웹 기초",
    code: "ASSISTANT_WEB_01",
    status: "IN_PROGRESS",
    completedAt: undefined,
    notes: "admin-web 첫 화면 구성 중",
  },
  {
    phase: "에이전트 제어 고도화",
    code: "AGENT_CTRL_01",
    status: "PENDING",
    completedAt: undefined,
    notes: "태스크 생성·취소·상태 폴링",
  },
  {
    phase: "승인/감사 로그",
    code: "AUDIT_LOG_01",
    status: "PENDING",
    completedAt: undefined,
    notes: "운영 통제 기능",
  },
  {
    phase: "도메인 공개",
    code: "DOMAIN_PUBLISH_01",
    status: "PENDING",
    completedAt: undefined,
    notes: "design.haehan-ai.kr 연결 예정",
  },
];

const APPROVAL_QUEUE = [
  { id: "APR-001", title: "히웍스 공지 자동 게시 승인", requestedAt: "09:12" },
  { id: "APR-002", title: "G2B 투찰 참여 여부 확인 요청", requestedAt: "08:44" },
];

const QUICK_TASK_OPTIONS = [
  { value: "eum", label: "EUM 단말기 현황 추출" },
  { value: "g2b", label: "G2B 입찰 조회" },
  { value: "hiworks", label: "히웍스 공지 수집" },
  { value: "youtube", label: "YouTube 콘텐츠 분석" },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-[#F5F7FA]">
      {/* 1. 상단 4px 오렌지 Top Accent Line */}
      <TopAccentLine />

      <div className="mx-auto max-w-screen-xl px-4 py-6 sm:px-6 lg:px-8">

        {/* 2. 비서앱 대시보드 헤더 */}
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-[22px] font-bold text-[#0F172A]">해한 AI 비서</h1>
            <p className="mt-1 text-[13px] text-[#6B7280]">
              AI 오케스트레이터 운영 대시보드 — 에이전트·게이트·창고 통합 관제
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status="PASS" label="시스템 정상" />
            <AppInstallButton />
          </div>
        </div>

        {/* 3. 로컬 에이전트 ON/OFF 상태 카드 */}
        <section className="mb-6">
          <h2 className="mb-3 text-[13px] font-semibold text-[#374151]">로컬 에이전트 현황</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {AGENT_METRICS.map((m) => (
              <MetricCard
                key={m.label}
                label={m.label}
                value={m.value}
                sub={m.sub}
                accentColor={m.accentColor}
              />
            ))}
          </div>
        </section>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
          <div className="flex flex-col gap-6">

            {/* 4. 승인 대기 큐 요약 */}
            <section className="rounded-[12px] border border-[#E5E7EB] bg-white p-5">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-[13px] font-semibold text-[#374151]">승인 대기</h2>
                <StatusBadge status="WARN" label={`${APPROVAL_QUEUE.length}건 대기`} />
              </div>
              <ul className="space-y-2">
                {APPROVAL_QUEUE.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between rounded-lg bg-[#F9FAFB] px-3 py-2"
                  >
                    <div>
                      <span className="text-[11px] font-mono text-[#9CA3AF] mr-2">{item.id}</span>
                      <span className="text-[13px] text-[#374151]">{item.title}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[11px] text-[#9CA3AF]">{item.requestedAt}</span>
                      <Button variant="secondary" size="sm">승인</Button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {/* 5. 작업 실행 게이트 상태 */}
            <section>
              <h2 className="mb-3 text-[13px] font-semibold text-[#374151]">실행 게이트</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {GATES.map((g) => (
                  <GateStatusCard
                    key={g.gateName}
                    gateName={g.gateName}
                    decision={g.decision}
                    reason={g.reason}
                  />
                ))}
              </div>
            </section>

            {/* 7. 최근 작업 공정표 */}
            <section>
              <h2 className="mb-3 text-[13px] font-semibold text-[#374151]">작업 공정표</h2>
              <ConstructionPhaseTable rows={PHASE_ROWS} />
            </section>
          </div>

          <div className="flex flex-col gap-6">

            {/* 8. 빠른 작업 입력 영역 */}
            <section className="rounded-[12px] border border-[#E5E7EB] bg-white p-5">
              <h2 className="mb-4 text-[13px] font-semibold text-[#374151]">빠른 작업 생성</h2>
              <div className="flex flex-col gap-3">
                <Select
                  label="업무 도메인"
                  options={QUICK_TASK_OPTIONS}
                />
                <Input label="작업 제목" placeholder="예: 5월 EUM 단말기 현황 추출" />
                <Input label="메모 (선택)" placeholder="추가 지시사항 입력" />
                <Button variant="primary" size="md">
                  작업 생성
                </Button>
              </div>
            </section>

            {/* 6. 업무별 창고 카드 */}
            <section>
              <h2 className="mb-3 text-[13px] font-semibold text-[#374151]">업무 창고</h2>
              <div className="flex flex-col gap-3">
                {WAREHOUSES.map((w) => (
                  <WarehouseCard
                    key={w.title}
                    title={w.title}
                    path={w.path}
                    fileCount={w.fileCount}
                    status={w.status}
                    description={w.description}
                  />
                ))}
              </div>
            </section>

            {/* 운영 링크 */}
            <section className="rounded-[12px] border border-[#E5E7EB] bg-white p-5">
              <h2 className="mb-3 text-[13px] font-semibold text-[#374151]">운영 메뉴</h2>
              <div className="flex flex-col gap-2">
                {[
                  { href: "/local-agents", label: "로컬 에이전트 관리", badge: "운영 중" },
                  { href: "/cad", label: "AI CAD 워크스페이스", badge: "운영 중" },
                  { href: "/file-map", label: "파일 지도 리포트", badge: "신기능" },
                  { href: "/external-tasks", label: "외부 웹 업무 현황", badge: "신기능" },
                ].map((item) => (
                  <Link key={item.href} href={item.href}>
                    <div className="flex items-center justify-between rounded-lg bg-[#F9FAFB] px-3 py-2 hover:bg-[#F3F4F6] transition-colors">
                      <span className="text-[13px] text-[#374151]">{item.label}</span>
                      <StatusBadge status="PASS" label={item.badge} />
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
