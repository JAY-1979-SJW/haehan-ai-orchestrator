import type { Meta, StoryObj } from '@storybook/react';
import { ConstructionPhaseTable } from '../components/tables/ConstructionPhaseTable';
import type { ConstructionPhaseRow } from '../components/tables/ConstructionPhaseTable';

const meta: Meta<typeof ConstructionPhaseTable> = {
  title: '테이블/ConstructionPhaseTable',
  component: ConstructionPhaseTable,
  tags: ['autodocs'],
  parameters: { backgrounds: { default: 'white' } },
};
export default meta;

type Story = StoryObj<typeof ConstructionPhaseTable>;

const FULL_ROWS: ConstructionPhaseRow[] = [
  { phase: '대지 조성',       code: 'FOUNDATION_01',  status: 'DONE',    completedAt: '2026-04-22', notes: 'P1 App Foundation' },
  { phase: '공유 창고',       code: 'WAREHOUSE_01',   status: 'DONE',    completedAt: '2026-04-25', notes: 'Shared Warehouse' },
  { phase: '세대 배정',       code: 'ROOM_ALLOC_01',  status: 'DONE',    completedAt: '2026-05-01', notes: 'Domain Room Allocation' },
  { phase: 'G2B 골조',        code: 'G2B_SKEL_01',   status: 'DONE',    completedAt: '2026-05-15', notes: 'Site Engine Skeleton' },
  { phase: '표준 UI',         code: 'STD_UI_01',     status: 'DONE',    completedAt: '2026-05-15', notes: '모델하우스 추출' },
  { phase: '본관 디자인시스템', code: 'DS_ROOT_01',   status: 'DONE',    completedAt: '2026-05-15', notes: 'Storybook 포함' },
  { phase: '비서앱 준공',     code: 'WEBAPP_01',     status: 'HOLD',    notes: '다음 단계' },
  { phase: 'EUM 자동화',      code: 'EUM_AUTO_01',   status: 'PARTIAL', notes: '추출 완료, 대시보드 진행 중' },
  { phase: '입찰분석 앱',     code: 'G2B_APP_01',    status: 'HOLD' },
];

export const 전체공정: Story = { args: { rows: FULL_ROWS } };

export const 일부완료: Story = {
  args: {
    rows: FULL_ROWS.filter(r => ['DONE', 'PARTIAL'].includes(r.status)),
  },
};

export const 데이터없음: Story = {
  args: { rows: [], emptyMessage: '등록된 공정이 없습니다.' },
};

export const 경고포함: Story = {
  args: {
    rows: [
      { phase: '보안 감사',    code: 'SECURITY_01', status: 'WARN',  notes: '2건 미조치' },
      { phase: '게이트 점검', code: 'GATE_01',     status: 'PASS',  completedAt: '2026-05-14' },
      { phase: '배포 준비',    code: 'DEPLOY_01',   status: 'HOLD' },
    ],
  },
};
