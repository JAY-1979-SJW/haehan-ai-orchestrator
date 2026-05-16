import type { Meta, StoryObj } from '@storybook/react';
import { Input } from '../components/forms/Input';

const meta: Meta<typeof Input> = {
  title: '폼/Input',
  component: Input,
  tags: ['autodocs'],
  parameters: { backgrounds: { default: 'white' } },
};
export default meta;

type Story = StoryObj<typeof Input>;

export const 기본: Story = {
  args: { label: '공사명', placeholder: '예: 부곡커뮤니티센터 신축공사' },
};
export const 값입력됨: Story = {
  args: { label: '발주기관', defaultValue: '경기도청' },
};
export const 오류상태: Story = {
  args: { label: '입찰번호', placeholder: '2024-0001', error: '유효하지 않은 형식입니다.' },
};
export const 필수입력: Story = {
  args: { label: '현장 코드', placeholder: 'HAE-2026-001', required: true },
};
export const 레이블없음: Story = {
  args: { placeholder: '검색어를 입력하세요' },
};
export const 비활성: Story = {
  args: { label: '처리일', defaultValue: '2026-05-15', disabled: true },
};

export const 폼그룹: Story = {
  render: () => (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 20, background: '#fff', borderRadius: 8, border: '1px solid #E5E7EB' }}>
      <Input label="공사명"   placeholder="예: 부곡커뮤니티센터 신축공사" />
      <Input label="발주기관" placeholder="예: 경기도청" />
      <Input label="입찰번호" placeholder="2024-0001" />
      <Input label="예산금액" placeholder="100,000,000 원" />
    </div>
  ),
};
