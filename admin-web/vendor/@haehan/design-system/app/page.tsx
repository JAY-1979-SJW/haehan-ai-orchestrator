'use client';

/**
 * 해한 디자인 시스템 — 견본 화면
 * 건축 공정 비유: 대지 → 단지 → 동 → 세대 → 창고 → 게이트 → 감리 → 준공
 */

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
} from '@standard-ui';
import type { ConstructionPhaseRow } from '@standard-ui/components/tables/ConstructionPhaseTable';

// ── 페이지 고유 컴포넌트 (표준 패키지 미포함) ─────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: 13, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase',
      letterSpacing: '0.08em', marginBottom: 12 }}>
      {children}
    </h2>
  );
}

// ── 공정표 데이터 ──────────────────────────────────────────────────────

const PHASE_ROWS: ConstructionPhaseRow[] = [
  { phase: '대지 조성',      code: 'FOUNDATION_01', status: 'DONE',    completedAt: '2026-04-22', notes: 'P1 App Foundation' },
  { phase: '공유 창고',      code: 'WAREHOUSE_01',  status: 'DONE',    completedAt: '2026-04-25', notes: 'Shared Warehouse' },
  { phase: '세대 배정',      code: 'ROOM_ALLOC_01', status: 'DONE',    completedAt: '2026-05-01', notes: 'Domain Room Allocation' },
  { phase: 'G2B 골조',       code: 'G2B_SKEL_01',  status: 'DONE',    completedAt: '2026-05-15', notes: 'Site Engine Skeleton' },
  { phase: '표준 UI',        code: 'STD_UI_01',    status: 'DONE',    completedAt: '2026-05-15', notes: '모델하우스 추출' },
  { phase: '본관 디자인시스템', code: 'DS_ROOT_01', status: 'DONE',   completedAt: '2026-05-15', notes: 'Import 통합 완료' },
  { phase: '비서앱 준공',    code: 'WEBAPP_01',    status: 'HOLD',    notes: '다음 단계' },
];

// ── 메인 페이지 ────────────────────────────────────────────────────────

export default function DesignSystemHome() {
  return (
    <>
      <TopAccentLine />

      {/* 전체 레이아웃 */}
      <div style={{ display: 'flex', minHeight: '100vh', paddingTop: 4 }}>

        {/* 사이드바 — 페이지 고유 레이아웃 (AppShell 별도 쇼케이스 대상) */}
        <aside style={{
          width: 224, flexShrink: 0, background: '#1E2D4A', color: '#fff',
          position: 'fixed', top: 4, bottom: 0, left: 0, overflowY: 'auto',
          display: 'flex', flexDirection: 'column',
        }}>
          <div style={{ padding: '20px 16px 12px' }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#F97316', marginBottom: 2 }}>
              해한
            </div>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>
              Design System
            </div>
          </div>
          <nav style={{ flex: 1, padding: '4px 8px' }}>
            {([
              ['대지 · 단지 구조', true],
              ['디자인 토큰', false],
              ['레이아웃', false],
              ['상태 배지', false],
              ['카드', false],
              ['테이블', false],
              ['폼', false],
              ['피드백', false],
              ['패턴', false],
            ] as [string, boolean][]).map(([label, active]) => (
              <div key={label} style={{
                padding: '8px 10px', borderRadius: 6,
                fontSize: 13, marginBottom: 2,
                background: active ? 'rgba(249,115,22,0.12)' : 'transparent',
                color: active ? '#F97316' : 'rgba(255,255,255,0.65)',
                fontWeight: active ? 600 : 400,
                cursor: 'pointer',
              }}>
                {label}
              </div>
            ))}
          </nav>
          <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.08)',
            fontSize: 11, color: 'rgba(255,255,255,0.3)' }}>
            v0.1.0 · 2026-05-15
          </div>
        </aside>

        {/* 본문 */}
        <main style={{ marginLeft: 224, flex: 1, padding: '24px 32px', background: '#F5F7FA' }}>

          {/* 페이지 헤더 */}
          <div style={{ marginBottom: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <h1 style={{ fontSize: 22, fontWeight: 700, color: '#0F172A', margin: 0 }}>
                해한 디자인 시스템
              </h1>
              <StatusBadge status="DONE" label="견본 화면" />
            </div>
            <p style={{ fontSize: 13, color: '#6B7280', margin: 0 }}>
              비서앱 · 입찰앱 · CAD앱 · 출퇴근앱 공통 UI 기준 — 건축 공정 비유로 구조화
            </p>
          </div>

          {/* KPI 행 */}
          <SectionTitle>대지 · 단지 현황 (KPI)</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
            <MetricCard label="앱 수 (동)"  value={6}  sub="비서·입찰·CAD·출퇴근·위험성·문서" />
            <MetricCard label="세대 수"     value={22} sub="G2B 기준 현재 임대 중" />
            <MetricCard label="창고 영역"   value={9}  sub="shared warehouse" accentColor="#1E2D4A" />
            <MetricCard label="게이트 항목" value={7}  sub="FORBIDDEN·SECURITY·CIRCULAR 외" accentColor="#059669" />
          </div>

          {/* 상태 배지 */}
          <SectionTitle>상태 배지 (StatusBadge)</SectionTitle>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 28 }}>
            {(['PASS','DONE','WARN','PARTIAL','FAIL','MISSING','HOLD','BLOCKED',
               'LOCAL_AGENT_REQUIRED','USER_DIRECT_REQUIRED'] as const).map(s => (
              <StatusBadge key={s} status={s} />
            ))}
          </div>

          {/* 게이트 카드 */}
          <SectionTitle>감리 게이트 (GateStatusCard)</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 28 }}>
            <GateStatusCard gateName="FORBIDDEN_IMPORT"    decision="PASS" count={0} />
            <GateStatusCard gateName="SECURITY_PATTERN"    decision="PASS" count={0} />
            <GateStatusCard gateName="CIRCULAR_IMPORT"     decision="PASS" count={0} />
            <GateStatusCard gateName="FAT_SITE"            decision="PASS" count={0} />
            <GateStatusCard gateName="ROUTER_THINNESS"     decision="WARN" count={2} />
            <GateStatusCard gateName="STORAGE_BOUNDARY"    decision="PASS" count={0} />
            <GateStatusCard gateName="SERVER_BROWSER_GUARD" decision="PASS" count={0} />
          </div>

          {/* 창고 카드 */}
          <SectionTitle>공유 창고 (WarehouseCard)</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 28 }}>
            <WarehouseCard title="G2B 공개공고 캐시"    path="data/g2b/public_notices/"  status="DONE" />
            <WarehouseCard title="첨부파일 저장소"       path="data/g2b/attachments/"     status="PARTIAL" />
            <WarehouseCard title="입찰분석 초안"         path="data/g2b/bid_analysis/"    status="HOLD" />
            <WarehouseCard title="Local Agent 감사 로그" path="data/local_agent/audit/"   status="DONE" />
          </div>

          {/* 공정표 테이블 */}
          <SectionTitle>건축 공정표 (ConstructionPhaseTable)</SectionTitle>
          <div style={{ marginBottom: 28 }}>
            <ConstructionPhaseTable rows={PHASE_ROWS} />
          </div>

          {/* 폼 요소 */}
          <SectionTitle>폼 요소 (Button / Input / Select)</SectionTitle>
          <div style={{ background: '#fff', borderRadius: 8, border: '1px solid #E5E7EB',
            padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 28 }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Button variant="primary">Primary 버튼</Button>
              <Button variant="navy">Navy 버튼</Button>
              <Button variant="secondary">Secondary 버튼</Button>
              <Button variant="primary" disabled>비활성화</Button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Input label="공사명" placeholder="예: 부곡커뮤니티센터 신축공사" />
              <Select
                label="게이트 결정"
                options={[
                  { value: 'READ_ONLY_ALLOWED',    label: 'READ_ONLY_ALLOWED' },
                  { value: 'DRAFT_ALLOWED',        label: 'DRAFT_ALLOWED' },
                  { value: 'LOCAL_AGENT_REQUIRED', label: 'LOCAL_AGENT_REQUIRED' },
                  { value: 'BLOCKED',              label: 'BLOCKED' },
                ]}
              />
            </div>
          </div>

          {/* 색상 토큰 — 페이지 고유 쇼케이스 */}
          <SectionTitle>디자인 토큰 — 색상</SectionTitle>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 28 }}>
            {([
              ['#F97316', 'Orange Primary'],
              ['#EA580C', 'Orange Hover'],
              ['#1E2D4A', 'Navy Base'],
              ['#253661', 'Navy Hover'],
              ['#F5F7FA', 'BG Base'],
              ['#FFFFFF', 'Card'],
              ['#0F172A', 'Text Primary'],
              ['#6B7280', 'Text Muted'],
              ['#059669', 'Success'],
              ['#D97706', 'Warning'],
              ['#DC2626', 'Error'],
              ['#2563EB', 'Info'],
            ] as [string, string][]).map(([hex, name]) => (
              <div key={hex} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 8,
                  background: hex,
                  border: hex === '#FFFFFF' ? '1px solid #E5E7EB' : 'none',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
                }} />
                <div style={{ fontSize: 10, color: '#6B7280', textAlign: 'center', maxWidth: 60 }}>{name}</div>
                <div style={{ fontSize: 10, fontFamily: 'monospace', color: '#9CA3AF' }}>{hex}</div>
              </div>
            ))}
          </div>

          {/* 준공 배너 — 페이지 고유 */}
          <div style={{
            background: '#FFF7ED', border: '1px solid #FED7AA', borderRadius: 8,
            padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#F97316', flexShrink: 0 }} />
            <div style={{ fontSize: 13, color: '#92400E' }}>
              <strong>다음 단계:</strong> 비서앱 준공 → Admin Ops Center 시공 → Storybook 연결
            </div>
          </div>

        </main>
      </div>
    </>
  );
}
