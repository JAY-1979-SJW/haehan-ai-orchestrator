import type { Meta, StoryObj } from '@storybook/react';
import { TopAccentLine } from '../components/layout/TopAccentLine';

const meta: Meta<typeof TopAccentLine> = {
  title: '레이아웃/TopAccentLine',
  component: TopAccentLine,
  tags: ['autodocs'],
  parameters: {
    layout: 'fullscreen',
    backgrounds: { default: 'light' },
    docs: {
      description: {
        component: '모든 화면 상단 고정 4px Orange Accent Line. 브랜드 원칙상 필수 요소.',
      },
    },
  },
};
export default meta;

type Story = StoryObj<typeof TopAccentLine>;

export const 기본: Story = {
  render: () => (
    <div style={{ position: 'relative', height: 120, background: '#F5F7FA' }}>
      <TopAccentLine />
      <div style={{ paddingTop: 20, paddingLeft: 20, fontSize: 13, color: '#6B7280' }}>
        상단 4px Orange (#F97316) 고정 Accent Line — 모든 해한 앱에 공통 적용
      </div>
    </div>
  ),
};

export const 사이드바포함: Story = {
  render: () => (
    <div style={{ position: 'relative', height: 200 }}>
      <TopAccentLine />
      <div style={{ display: 'flex', paddingTop: 4, height: '100%' }}>
        <aside style={{ width: 224, background: '#1E2D4A', color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13 }}>
          Navy 사이드바
        </aside>
        <main style={{ flex: 1, background: '#F5F7FA', padding: 20, fontSize: 13, color: '#6B7280' }}>
          본문 영역
        </main>
      </div>
    </div>
  ),
};
