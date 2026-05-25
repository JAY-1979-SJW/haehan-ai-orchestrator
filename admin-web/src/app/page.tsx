"use client";

import Link from "next/link";
import {
  Alert,
  AppShell,
  Button,
  DataTable,
  Header,
  MetricCard,
  ReportList,
  Sidebar,
  StatusBadge,
} from "@/standard-ui";

const navGroups = [
  {
    label: "운영",
    items: [
      { href: "/", label: "Dashboard", active: true },
      { href: "/assistant/tasks", label: "Tasks" },
      { href: "/browser-approvals", label: "Approvals" },
      { href: "/local-agents", label: "Agents" },
    ],
  },
  {
    label: "관리",
    items: [
      { href: "/ops", label: "Audit" },
      { href: "/assistant/storage", label: "Tools" },
      { href: "/assistant/external-sites", label: "Connections" },
      { href: "/assistant/logs", label: "Reports" },
    ],
  },
  {
    label: "설정",
    items: [
      { href: "/assistant", label: "Consent" },
      { href: "/assistant/deployment", label: "Settings" },
    ],
  },
];

const metrics = [
  { label: "서버 상태", value: "정상", sub: "마지막 확인: 방금 전", accentColor: "#059669" },
  { label: "에이전트 연결", value: "1", sub: "주의 필요 0건", accentColor: "#2563EB" },
  { label: "승인 대기", value: "2", sub: "높은 위험 1건", accentColor: "#F97316" },
  { label: "실패/차단", value: "0", sub: "사용자 조치 없음", accentColor: "#B91C1C" },
];

const taskRows: Array<Record<string, unknown>> = [
  {
    id: "task-1024",
    action: "공고 페이지 읽기",
    state: "완료",
    approval: "불필요",
    owner: "browser.inspect",
    next: "보고서 열기",
  },
  {
    id: "task-1025",
    action: "메일 초안 준비",
    state: "승인 대기",
    approval: "필요",
    owner: "gmail.compose",
    next: "승인 검토",
  },
  {
    id: "task-1026",
    action: "에이전트 상태 확인",
    state: "진행 중",
    approval: "불필요",
    owner: "local_agent.status",
    next: "상태 새로고침",
  },
];

const approvalRows: Array<Record<string, unknown>> = [
  {
    id: "apr-2401",
    task: "task-1025",
    summary: "메일 초안 생성 후 사용자가 최종 전송",
    risk: "중간",
    expires: "30분 남음",
  },
  {
    id: "apr-2402",
    task: "task-1027",
    summary: "외부 사이트 제출 전 사용자 확인",
    risk: "높음",
    expires: "12분 남음",
  },
];

const reportItems = [
  {
    title: "앱 개발 기준서",
    path: "docs/baseline/APP_DEVELOPMENT_STANDARD.md",
    date: "2026-05-25",
    category: "LOCKED",
  },
  {
    title: "동의 기반 개발자료 export",
    path: "docs/reports/user_data_contribution_consent_20260525.md",
    date: "2026-05-25",
    category: "PASS",
  },
];

const taskColumns = [
  { key: "id", header: "작업 ID", width: 120 },
  { key: "action", header: "작업" },
  {
    key: "state",
    header: "상태",
    width: 110,
    render: (row: Record<string, unknown>) => (
      <StatusBadge
        status={row.state === "완료" ? "PASS" : row.state === "승인 대기" ? "WARN" : "PARTIAL"}
        label={String(row.state)}
        size="sm"
      />
    ),
  },
  { key: "approval", header: "승인", width: 90 },
  { key: "owner", header: "도구/모듈", width: 150 },
  { key: "next", header: "다음 조치", width: 120 },
];

const approvalColumns = [
  { key: "id", header: "승인 ID", width: 120 },
  { key: "task", header: "작업 ID", width: 120 },
  { key: "summary", header: "안전 요약" },
  {
    key: "risk",
    header: "위험",
    width: 90,
    render: (row: Record<string, unknown>) => (
      <StatusBadge
        status={row.risk === "높음" ? "HOLD" : "WARN"}
        label={String(row.risk)}
        size="sm"
      />
    ),
  },
  { key: "expires", header: "만료", width: 110 },
];

function Panel({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: "#FFFFFF",
        border: "1px solid #E5E7EB",
        borderRadius: 8,
        padding: 18,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 14,
        }}
      >
        <h2 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#0F172A" }}>{title}</h2>
        {right}
      </div>
      {children}
    </section>
  );
}

export default function Home() {
  return (
    <AppShell
      sidebar={
        <Sidebar
          logo={
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>HAEHAN AI</div>
              <div style={{ marginTop: 4, fontSize: 11, color: "rgba(255,255,255,0.58)" }}>
                서버 기준 운영 앱
              </div>
            </div>
          }
          groups={navGroups}
          footer={
            <div style={{ fontSize: 11, color: "rgba(255,255,255,0.58)", lineHeight: 1.5 }}>
              표준 UI 기반
              <br />
              static/dry-run 화면
            </div>
          }
        />
      }
      header={
        <Header
          title="운영 대시보드"
          right={
            <>
              <StatusBadge status="PASS" label="서버 기준" />
              <StatusBadge status="READ_ONLY_ALLOWED" label="읽기 전용" />
            </>
          }
        />
      }
    >
      <div data-testid="app-standard-dashboard" style={{ padding: 24, maxWidth: 1320, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, marginBottom: 18 }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, lineHeight: 1.25, color: "#0F172A" }}>
              지금 처리할 일을 한 화면에서 확인합니다
            </h1>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#6B7280" }}>
              작업, 승인, 에이전트, 감사 기록은 서버가 가진 안전한 상태만 표시합니다.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
            <Link href="/ops">
              <Button variant="secondary">감사 보기</Button>
            </Link>
            <Link href="/assistant/tasks">
              <Button variant="primary">작업 보기</Button>
            </Link>
          </div>
        </div>

        <Alert type="info" title="표준 UI 기준 화면">
          이 화면은 앱 개발 기준서에 맞춘 첫 운영 화면입니다. 서버 API 연결 전까지 정적 계약 화면으로 유지합니다.
        </Alert>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
            gap: 12,
            marginTop: 18,
          }}
        >
          {metrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1.5fr) minmax(320px, 0.85fr)",
            gap: 16,
            marginTop: 16,
            alignItems: "start",
          }}
        >
          <div style={{ display: "grid", gap: 16 }}>
            <Panel
              title="최근 작업"
              right={<StatusBadge status="WARN" label="승인 대기 우선" size="sm" />}
            >
              <DataTable columns={taskColumns} rows={taskRows} keyField="id" />
            </Panel>

            <Panel title="승인 대기">
              <DataTable columns={approvalColumns} rows={approvalRows} keyField="id" />
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <Button variant="secondary" disabled title="서버 승인 API 연결 후 활성화됩니다.">
                  승인
                </Button>
                <Button variant="ghost" disabled title="서버 승인 API 연결 후 활성화됩니다.">
                  거절
                </Button>
              </div>
            </Panel>
          </div>

          <div style={{ display: "grid", gap: 16 }}>
            <Panel title="에이전트 연결">
              <div style={{ display: "grid", gap: 10 }}>
                {[
                  ["Connected", "주 작업 PC", "마지막 확인: 방금 전", "PASS"],
                  ["Waiting", "예비 에이전트", "작업 없음", "READ_ONLY_ALLOWED"],
                  ["Unknown", "외부 앱", "현재 범위 밖, 보고만 필요", "WARN"],
                ].map(([state, name, note, status]) => (
                  <div
                    key={name}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 10,
                      padding: "10px 12px",
                      border: "1px solid #E5E7EB",
                      borderRadius: 8,
                    }}
                  >
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0F172A" }}>{name}</div>
                      <div style={{ marginTop: 2, fontSize: 12, color: "#6B7280" }}>{note}</div>
                    </div>
                    <StatusBadge status={status} label={state} size="sm" />
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="동의 상태">
              <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>
                개발자료 제공 동의는 선택 사항이며 언제든 철회할 수 있습니다. 원문 프롬프트, 파일,
                이메일, 스크린샷, 토큰은 수집하지 않습니다.
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <StatusBadge status="WARN" label="선택 필요" />
                <Button variant="secondary" disabled title="동의 API 연결 후 활성화됩니다.">
                  동의 관리
                </Button>
              </div>
            </Panel>

            <Panel title="최근 보고서">
              <ReportList items={reportItems} />
            </Panel>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
