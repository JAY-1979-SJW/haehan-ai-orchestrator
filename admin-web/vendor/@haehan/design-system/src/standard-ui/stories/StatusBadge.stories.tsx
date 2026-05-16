import type { Meta, StoryObj } from '@storybook/react';
import { StatusBadge } from '../components/status/StatusBadge';

const meta: Meta<typeof StatusBadge> = {
  title: '상태/StatusBadge',
  component: StatusBadge,
  tags: ['autodocs'],
  argTypes: {
    status: {
      control: 'select',
      options: ['PASS', 'DONE', 'WARN', 'PARTIAL', 'FAIL', 'MISSING', 'HOLD', 'BLOCKED',
        'LOCAL_AGENT_REQUIRED', 'USER_DIRECT_REQUIRED', 'READ_ONLY_ALLOWED', 'DRAFT_ALLOWED'],
    },
    size: { control: 'radio', options: ['sm', 'md'] },
  },
};
export default meta;

type Story = StoryObj<typeof StatusBadge>;

export const 통과: Story = { args: { status: 'PASS' } };
export const 완료: Story = { args: { status: 'DONE' } };
export const 경고: Story = { args: { status: 'WARN' } };
export const 진행중: Story = { args: { status: 'PARTIAL' } };
export const 실패: Story = { args: { status: 'FAIL' } };
export const 누락: Story = { args: { status: 'MISSING' } };
export const 보류: Story = { args: { status: 'HOLD' } };
export const 차단: Story = { args: { status: 'BLOCKED' } };
export const 로컬에이전트: Story = { args: { status: 'LOCAL_AGENT_REQUIRED' } };
export const 직접실행: Story = { args: { status: 'USER_DIRECT_REQUIRED' } };
export const 읽기허용: Story = { args: { status: 'READ_ONLY_ALLOWED' } };
export const 초안허용: Story = { args: { status: 'DRAFT_ALLOWED' } };

export const 사용자레이블: Story = {
  args: { status: 'PASS', label: '이번 단계 완료' },
};
export const 소형: Story = {
  args: { status: 'WARN', size: 'sm' },
};

export const 전체보기: Story = {
  render: () => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
      {(['PASS', 'DONE', 'WARN', 'PARTIAL', 'FAIL', 'MISSING', 'HOLD', 'BLOCKED',
        'LOCAL_AGENT_REQUIRED', 'USER_DIRECT_REQUIRED', 'READ_ONLY_ALLOWED', 'DRAFT_ALLOWED'] as const).map(s => (
        <StatusBadge key={s} status={s} />
      ))}
    </div>
  ),
};
