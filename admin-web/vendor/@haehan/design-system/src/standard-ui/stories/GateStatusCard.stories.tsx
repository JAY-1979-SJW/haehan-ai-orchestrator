import type { Meta, StoryObj } from '@storybook/react';
import { GateStatusCard } from '../components/cards/GateStatusCard';

const meta: Meta<typeof GateStatusCard> = {
  title: '카드/GateStatusCard',
  component: GateStatusCard,
  tags: ['autodocs'],
  parameters: { backgrounds: { default: 'light' } },
};
export default meta;

type Story = StoryObj<typeof GateStatusCard>;

export const 금지임포트통과: Story = {
  args: { gateName: 'FORBIDDEN_IMPORT', decision: 'PASS', count: 0 },
};
export const 보안패턴통과: Story = {
  args: { gateName: 'SECURITY_PATTERN', decision: 'PASS', count: 0 },
};
export const 순환임포트경고: Story = {
  args: { gateName: 'CIRCULAR_IMPORT', decision: 'WARN', count: 2, reason: '2개 순환 참조 감지됨' },
};
export const 라우터비대실패: Story = {
  args: { gateName: 'FAT_SITE', decision: 'FAIL', count: 5, reason: '라우터에 SQL 직접 작성 감지' },
};
export const 서버브라우저보호: Story = {
  args: { gateName: 'SERVER_BROWSER_GUARD', decision: 'PASS', count: 0 },
};

export const 전체게이트보기: Story = {
  render: () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
      <GateStatusCard gateName="FORBIDDEN_IMPORT"    decision="PASS" count={0} />
      <GateStatusCard gateName="SECURITY_PATTERN"    decision="PASS" count={0} />
      <GateStatusCard gateName="CIRCULAR_IMPORT"     decision="PASS" count={0} />
      <GateStatusCard gateName="FAT_SITE"            decision="PASS" count={0} />
      <GateStatusCard gateName="ROUTER_THINNESS"     decision="WARN" count={2} reason="라우터 두께 초과 2건" />
      <GateStatusCard gateName="STORAGE_BOUNDARY"    decision="PASS" count={0} />
      <GateStatusCard gateName="SERVER_BROWSER_GUARD" decision="PASS" count={0} />
    </div>
  ),
};
