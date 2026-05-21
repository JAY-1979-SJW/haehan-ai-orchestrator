import { useEffect, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Sidebar } from '@/components/Sidebar'
import { ChatPanel } from '@/components/ChatPanel'
import { MenuDrawer } from '@/components/MenuDrawer'
import { IframePanel } from '@/components/IframePanel'
import {
  TaskQueuePanel, ApprovalPanel, NewsPanel, EumPanel,
  BrowserPanel, ScreenshotPanel, LogsPanel, SettingsPanel,
  BlogWritePanel, CafeWritePanel,
} from '@/components/panels/Panels'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'

const ADMIN_BASE = 'http://127.0.0.1:8765/proxy/admin'

const PANELS: Record<string, React.ComponentType> = {
  chat:             ChatPanel,
  task_queue:       TaskQueuePanel,
  approval:         ApprovalPanel,
  news:             NewsPanel,
  eum:              EumPanel,
  blog_write:       BlogWritePanel,
  cafe_write:       CafeWritePanel,
  browser:          BrowserPanel,
  screenshot:       ScreenshotPanel,
  logs:             LogsPanel,
  settings:         SettingsPanel,
  admin_dashboard:  () => <IframePanel src={`${ADMIN_BASE}/`}                  title="관리 대시보드" />,
  admin_ops:        () => <IframePanel src={`${ADMIN_BASE}/ops`}               title="운영 현황" />,
  admin_approvals:  () => <IframePanel src={`${ADMIN_BASE}/browser-approvals`} title="브라우저 승인" />,
  admin_agents:     () => <IframePanel src={`${ADMIN_BASE}/local-agents`}      title="로컬 에이전트" />,
  admin_filemap:    () => <IframePanel src={`${ADMIN_BASE}/file-map`}          title="파일맵" />,
  admin_cad:        () => <IframePanel src={`${ADMIN_BASE}/cad`}               title="CAD" />,
}

export default function App() {
  const { panel, sidebarCollapsed, setSidebarCollapsed, setConnected, setConnecting, handleWsMessage, addMessage } = useAppStore()
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    wsClient.onStatus((s) => {
      setConnected(s === 'connected')
      setConnecting(s === 'connecting')
    })
    wsClient.onMessage(handleWsMessage)
    wsClient.connect()

    setTimeout(() => {
      addMessage({
        role: 'system',
        text: 'Haehan AI 앱이 준비됐습니다. 메시지를 입력하거나 빠른 메뉴를 선택하세요.',
        ts: Date.now() / 1000,
      })
    }, 300)
  }, [])

  const ActivePanel = PANELS[panel] ?? ChatPanel

  return (
    <div className="flex flex-col h-full bg-[#F5F7FA]">
      {/* Top Accent Line — 표준 디자인 시스템 필수 */}
      <div className="h-1 bg-[#F97316] flex-shrink-0 w-full" />

      <div className="flex flex-1 min-h-0">
        <Sidebar onOpenDrawer={() => setDrawerOpen(true)} />

        <main className="flex-1 flex flex-col min-w-0 relative overflow-hidden">
          {sidebarCollapsed && (
            <button
              onClick={() => setSidebarCollapsed(false)}
              className="absolute top-3 left-3 z-10 p-1.5 rounded-md bg-white border border-[#E5E7EB] text-[#6B7280] hover:text-[#111827] shadow-sm transition-colors"
              title="사이드바 열기"
            >
              <ChevronRight size={14} />
            </button>
          )}
          <div className="flex-1 overflow-hidden flex flex-col">
            <ActivePanel />
          </div>
        </main>

        <MenuDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
      </div>
    </div>
  )
}
