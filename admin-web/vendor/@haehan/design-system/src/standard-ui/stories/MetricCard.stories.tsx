import type { Meta, StoryObj } from '@storybook/react';
import { MetricCard } from '../components/cards/MetricCard';

const meta: Meta<typeof MetricCard> = {
  title: '카드/MetricCard',
  component: MetricCard,
  tags: ['autodocs'],
  argTypes: {
    accentColor: { control: 'color' },
  },
  parameters: { backgrounds: { default: 'light' } },
};
export default meta;

type Story = StoryObj<typeof MetricCard>;

export const 앱수: Story = {
  args: { label: '앱 수 (동)', value: 6, sub: '비서·입찰·CAD·출퇴근·위험성·문서' },
};
export const 임대단말기: Story = {
  args: { label: '임대 단말기', value: 22, sub: 'EUM 기준 현재 임대 중' },
};
export const 공유창고: Story = {
  args: { label: '공유 창고', value: 9, sub: 'Shared Warehouse 영역', accentColor: '#1E2D4A' },
};
export const 게이트항목: Story = {
  args: { label: '게이트 항목', value: 7, sub: 'FORBIDDEN·SECURITY·CIRCULAR 외', accentColor: '#059669' },
};
export const 클릭가능: Story = {
  args: {
    label: '입찰 공고 수',
    value: 134,
    sub: '이번 주 신규',
    accentColor: '#F97316',
    onClick: () => alert('카드 클릭'),
  },
};

export const 그리드보기: Story = {
  render: () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
      <MetricCard label="앱 수 (동)"  value={6}   sub="비서·입찰·CAD·출퇴근·위험성·문서" />
      <MetricCard label="임대 단말기" value={22}  sub="EUM 기준 현재 임대 중" />
      <MetricCard label="공유 창고"   value={9}   sub="Shared Warehouse" accentColor="#1E2D4A" />
      <MetricCard label="게이트 항목" value={7}   sub="FORBIDDEN·SECURITY 외" accentColor="#059669" />
    </div>
  ),
};
