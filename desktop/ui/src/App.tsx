import { useEffect, useState } from 'react'
import { TitleBar } from '@/components/TitleBar'
import { Sidebar } from '@/components/Sidebar'
import { HamburgerDrawer } from '@/components/HamburgerDrawer'
import { ChatPanel } from '@/components/ChatPanel'
import { MenuDrawer } from '@/components/MenuDrawer'
import { IframePanel } from '@/components/IframePanel'
import {
  TaskQueuePanel, ApprovalPanel, NewsPanel, EumPanel, EumDashboardPanel,
  CafeListPanel,
  G2bPanel, GabiaPanel,
  HiworksMailPanel, HiworksCalPanel,
  GmailPanel, GdrivePanel, GsheetsPanel, GcalendarPanel, GdocsPanel,
  NaverMailPanel, YoutubePanel, SmartstorePanel, KakaoPanel,
  RemoteAccessPanel,
  BrowserPanel, ScreenshotPanel, LogsPanel, SettingsPanel,
  BlogWritePanel, CafeWritePanel,
  LocalAgentPanel,
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
  eum_dashboard:    EumDashboardPanel,
  g2b:              G2bPanel,
  gabia:            GabiaPanel,
  hiworks_mail:     HiworksMailPanel,
  hiworks_cal:      HiworksCalPanel,
  gmail:            GmailPanel,
  gdrive:           GdrivePanel,
  gsheets:          GsheetsPanel,
  gcalendar:        GcalendarPanel,
  gdocs:            GdocsPanel,
  naver_mail:       NaverMailPanel,
  blog_write:       BlogWritePanel,
  cafe_write:       CafeWritePanel,
  cafe_list:        CafeListPanel,
  youtube:          YoutubePanel,
  smartstore:       SmartstorePanel,
  kakao:            KakaoPanel,
  admin_dashboard:  () => <IframePanel src={`${ADMIN_BASE}/`}                  title="관리 대시보드" />,
  admin_ops:        () => <IframePanel src={`${ADMIN_BASE}/ops`}               title="운영 현황" />,
  admin_approvals:  () => <IframePanel src={`${ADMIN_BASE}/browser-approvals`} title="브라우저 승인" />,
  admin_agents:     () => <IframePanel src={`${ADMIN_BASE}/local-agents`}      title="로컬 에이전트" />,
  admin_filemap:    () => <IframePanel src={`${ADMIN_BASE}/file-map`}          title="파일맵" />,
  admin_cad:        () => <IframePanel src={`${ADMIN_BASE}/cad`}               title="CAD" />,
  local_agent:      LocalAgentPanel,
  remote_access:    RemoteAccessPanel,
  browser:          BrowserPanel,
  screenshot:       ScreenshotPanel,
  logs:             LogsPanel,
  settings:         SettingsPanel,
}

export default function App() {
  const { panel, setConnected, setConnecting } = useAppStore()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [hamburgerOpen, setHamburgerOpen] = useState(false)

  useEffect(() => {
    wsClient.onStatus((s) => {
      setConnected(s === 'connected')
      setConnecting(s === 'connecting')
    })
    // store에서 항상 최신 핸들러를 꺼내도록 래핑 — 클로저 고정 방지
    wsClient.onMessage((msg) => useAppStore.getState().handleWsMessage(msg))
    wsClient.connect()

    setTimeout(() => {
      useAppStore.getState().addMessage({
        role: 'system',
        text: 'Haehan AI가 준비됐습니다. 좌측 메뉴에서 기능을 선택하세요.',
        ts: Date.now() / 1000,
      })
    }, 300)
  }, [])

  const ActivePanel = PANELS[panel] ?? ChatPanel

  return (
    <div className="flex flex-col h-screen bg-[#F0F2F5] overflow-hidden">
      <TitleBar onHamburger={() => setHamburgerOpen(true)} />
      <div className="flex flex-1 min-h-0">
        <Sidebar onOpenDrawer={() => setDrawerOpen(true)} />
        <main className="flex-1 min-w-0 overflow-hidden bg-white">
          <ActivePanel key={panel} />
        </main>
      </div>
      <HamburgerDrawer
        open={hamburgerOpen}
        onClose={() => setHamburgerOpen(false)}
        onOpenMenuEditor={() => setDrawerOpen(true)}
      />
      <MenuDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  )
}
