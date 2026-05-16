import type { Meta, StoryObj } from '@storybook/react';
import { WarehouseCard } from '../components/cards/WarehouseCard';

const meta: Meta<typeof WarehouseCard> = {
  title: '카드/WarehouseCard',
  component: WarehouseCard,
  tags: ['autodocs'],
  parameters: { backgrounds: { default: 'light' } },
};
export default meta;

type Story = StoryObj<typeof WarehouseCard>;

export const 공고캐시완료: Story = {
  args: { title: 'G2B 공개공고 캐시', path: 'data/g2b/public_notices/', status: 'DONE', fileCount: 312 },
};
export const 첨부파일진행중: Story = {
  args: { title: '첨부파일 저장소', path: 'data/g2b/attachments/', status: 'PARTIAL', fileCount: 48,
    description: '낙찰 결과 파일 미수신' },
};
export const 입찰분석보류: Story = {
  args: { title: '입찰분석 초안', path: 'data/g2b/bid_analysis/', status: 'HOLD' },
};
export const 단말기임대로그: Story = {
  args: { title: 'EUM 임대 로그', path: 'data/eum/device_logs/', status: 'DONE', fileCount: 22 },
};
export const 위험성평가보류: Story = {
  args: { title: '위험성평가 결과', path: 'data/risk_assessment/', status: 'HOLD',
    description: '앱 연동 대기 중' },
};

export const 창고목록: Story = {
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <WarehouseCard title="G2B 공개공고 캐시"    path="data/g2b/public_notices/"  status="DONE"    fileCount={312} />
      <WarehouseCard title="첨부파일 저장소"       path="data/g2b/attachments/"     status="PARTIAL" fileCount={48} />
      <WarehouseCard title="입찰분석 초안"         path="data/g2b/bid_analysis/"    status="HOLD" />
      <WarehouseCard title="EUM 임대 단말기 로그"  path="data/eum/device_logs/"     status="DONE"    fileCount={22} />
      <WarehouseCard title="Local Agent 감사 로그" path="data/local_agent/audit/"   status="DONE" />
    </div>
  ),
};
