import type { Meta, StoryObj } from '@storybook/react';
import { Select } from '../components/forms/Select';

const meta: Meta<typeof Select> = {
  title: '폼/Select',
  component: Select,
  tags: ['autodocs'],
  parameters: { backgrounds: { default: 'white' } },
};
export default meta;

type Story = StoryObj<typeof Select>;

const GATE_OPTIONS = [
  { value: 'READ_ONLY_ALLOWED',    label: 'READ_ONLY_ALLOWED' },
  { value: 'DRAFT_ALLOWED',        label: 'DRAFT_ALLOWED' },
  { value: 'LOCAL_AGENT_REQUIRED', label: 'LOCAL_AGENT_REQUIRED' },
  { value: 'BLOCKED',              label: 'BLOCKED' },
];

const STATUS_OPTIONS = [
  { value: 'PASS',    label: 'PASS — 통과' },
  { value: 'WARN',    label: 'WARN — 경고' },
  { value: 'FAIL',    label: 'FAIL — 실패' },
  { value: 'HOLD',    label: 'HOLD — 보류' },
  { value: 'BLOCKED', label: 'BLOCKED — 차단' },
];

const APP_OPTIONS = [
  { value: 'secretary', label: '비서앱' },
  { value: 'g2b',       label: '입찰앱 (G2B)' },
  { value: 'cad',       label: 'CAD 자동화' },
  { value: 'commute',   label: '출퇴근 앱' },
  { value: 'risk',      label: '위험성평가표' },
  { value: 'docs',      label: '문서자동화' },
];

export const 게이트결정: Story = {
  args: { label: '게이트 결정', options: GATE_OPTIONS },
};
export const 상태선택: Story = {
  args: { label: '공정 상태', options: STATUS_OPTIONS },
};
export const 앱선택: Story = {
  args: { label: '대상 앱', options: APP_OPTIONS },
};
export const 오류상태: Story = {
  args: { label: '관할 지사', options: [
    { value: 'seoul', label: '서울지사' },
    { value: 'incheon', label: '인천지사' },
    { value: 'gyeonggi', label: '경기지사' },
  ], error: '선택 필수 항목입니다.' },
};
export const 레이블없음: Story = {
  args: { options: STATUS_OPTIONS },
};

export const 폼그룹: Story = {
  render: () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 20, background: '#fff', borderRadius: 8, border: '1px solid #E5E7EB' }}>
      <Select label="대상 앱"    options={APP_OPTIONS} />
      <Select label="게이트 결정" options={GATE_OPTIONS} />
      <Select label="공정 상태"  options={STATUS_OPTIONS} />
    </div>
  ),
};
