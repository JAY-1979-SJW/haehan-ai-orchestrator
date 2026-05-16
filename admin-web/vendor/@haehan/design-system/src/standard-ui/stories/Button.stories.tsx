import type { Meta, StoryObj } from '@storybook/react';
import { Button } from '../components/forms/Button';

const meta: Meta<typeof Button> = {
  title: '폼/Button',
  component: Button,
  tags: ['autodocs'],
  argTypes: {
    variant: { control: 'select', options: ['primary', 'secondary', 'ghost', 'navy'] },
    size:    { control: 'radio',  options: ['xs', 'sm', 'md'] },
  },
  parameters: { backgrounds: { default: 'light' } },
};
export default meta;

type Story = StoryObj<typeof Button>;

export const 기본: Story = { args: { children: 'Primary 버튼', variant: 'primary' } };
export const Navy: Story = { args: { children: 'Navy 버튼', variant: 'navy' } };
export const Secondary: Story = { args: { children: 'Secondary 버튼', variant: 'secondary' } };
export const Ghost: Story = { args: { children: 'Ghost 버튼', variant: 'ghost' } };
export const 비활성: Story = { args: { children: '비활성화', variant: 'primary', disabled: true } };
export const 로딩중: Story = { args: { children: '저장 중', variant: 'primary', loading: true } };
export const 소형: Story = { args: { children: '확인', variant: 'primary', size: 'sm' } };
export const 최소형: Story = { args: { children: '삭제', variant: 'ghost', size: 'xs' } };

export const 버튼모음: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <Button variant="primary">저장</Button>
      <Button variant="navy">분석 실행</Button>
      <Button variant="secondary">취소</Button>
      <Button variant="ghost">초기화</Button>
      <Button variant="primary" disabled>비활성</Button>
      <Button variant="primary" loading>처리 중</Button>
    </div>
  ),
};
