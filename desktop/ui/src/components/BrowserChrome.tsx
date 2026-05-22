import { useState, useRef, useEffect } from 'react'
import {
  ChevronLeft, ChevronRight, RotateCw, Plus,
  Wifi, WifiOff, Loader2, Settings, Menu, Home,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'

const user = {
  id:   localStorage.getItem('user_id')   || 'default',
  name: localStorage.getItem('user_name') || '사용자',
  role: localStorage.getItem('user_role') || 'any',
}


interface BrowserChromeProps {
  onOpenDrawer: () => void
  onReload: () => void
  onNavigate: (id: string) => void
  history: string[]
  historyIndex: number
  onBack: () => void
  onForward: () => void
}

export function BrowserChrome({
  onOpenDrawer, onReload, onNavigate, history, historyIndex, onBack, onForward,
}: BrowserChromeProps) {
  const {
    connected, connecting, panel,
    menuItems, badgeApproval, badgeTask,
  } = useAppStore()

  const [profileOpen, setProfileOpen] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node))
        setProfileOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const visible = menuItems.filter(m => m.visible !== false)

  const getBadge = (id: string) => {
    if (id === 'approval')   return badgeApproval
    if (id === 'task_queue') return badgeTask
    return 0
  }

  const canBack = historyIndex > 0
  const canForward = historyIndex < history.length - 1

  return (
    <div className="flex flex-col flex-shrink-0 select-none" style={{ WebkitAppRegion: 'drag' } as any}>

      {/* ── 탭 바 ──────────────────────────────────────────────────── */}
      <div
        className="flex items-end gap-0 px-2 pt-1.5 bg-[#DEE1E6] overflow-x-auto scrollbar-none"
        style={{ WebkitAppRegion: 'no-drag' } as any}
      >
        {visible.map(item => {
          const active = panel === item.id
          const badge = getBadge(item.id)
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                'relative flex items-center gap-1.5 px-3 py-1.5 text-[12px] rounded-t-md transition-all flex-shrink-0 max-w-[160px] min-w-[80px] group',
                active
                  ? 'bg-[#F0F2F5] text-[#111827] font-semibold z-10 shadow-sm'
                  : 'bg-transparent text-[#6B7280] hover:bg-[#E8EAED] hover:text-[#374151]',
              )}
              title={item.label}
            >
              <span className="text-[13px] flex-shrink-0">{item.icon}</span>
              <span className="truncate flex-1 text-left">{item.label}</span>
              {badge > 0 && (
                <span className="text-[9px] font-bold bg-[#F97316] text-white rounded-full px-1 min-w-[15px] text-center">
                  {badge}
                </span>
              )}
              {/* 탭 하단 활성 선 */}
              {active && <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#F97316] rounded-t-sm" />}
            </button>
          )
        })}

        {/* 새 탭 버튼 */}
        <button
          onClick={() => { useAppStore.getState().clearMessages(); onNavigate('chat') }}
          className="flex items-center justify-center w-7 h-7 mb-1 ml-1 rounded-full text-[#6B7280] hover:bg-[#E8EAED] hover:text-[#374151] transition-colors flex-shrink-0"
          title="새 대화"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* ── 주소바 / 네비게이션 바 ─────────────────────────────────── */}
      <div
        className="flex items-center gap-1.5 px-2 py-1.5 bg-[#F0F2F5] border-b border-[#D1D5DB]"
        style={{ WebkitAppRegion: 'no-drag' } as any}
      >
        {/* 뒤로/앞으로/새로고침/홈 */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={onBack}
            disabled={!canBack}
            className="w-7 h-7 flex items-center justify-center rounded-full text-[#6B7280] hover:bg-[#E8EAED] disabled:opacity-30 disabled:cursor-default transition-colors"
            title="뒤로"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            onClick={onForward}
            disabled={!canForward}
            className="w-7 h-7 flex items-center justify-center rounded-full text-[#6B7280] hover:bg-[#E8EAED] disabled:opacity-30 disabled:cursor-default transition-colors"
            title="앞으로"
          >
            <ChevronRight size={16} />
          </button>
          <button
            onClick={onReload}
            className="w-7 h-7 flex items-center justify-center rounded-full text-[#6B7280] hover:bg-[#E8EAED] transition-colors"
            title="새로고침"
          >
            <RotateCw size={14} />
          </button>
          <button
            onClick={() => onNavigate('chat')}
            className="w-7 h-7 flex items-center justify-center rounded-full text-[#6B7280] hover:bg-[#E8EAED] transition-colors"
            title="홈 (대화)"
          >
            <Home size={14} />
          </button>
        </div>

        {/* 가운데 여백 */}
        <div className="flex-1" />

        {/* 우측 버튼 그룹 */}
        <div className="flex items-center gap-0.5">
          {/* 연결 상태 */}
          <button
            onClick={() => !connected && !connecting && wsClient.reconnect()}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-[#E8EAED] transition-colors"
            title={connected ? '연결됨' : connecting ? '연결 중…' : '클릭하여 재연결'}
          >
            {connected
              ? <Wifi size={13} className="text-[#059669]" />
              : connecting
                ? <Loader2 size={13} className="text-[#D97706] animate-spin" />
                : <WifiOff size={13} className="text-[#DC2626]" />
            }
          </button>

          {/* 프로필 */}
          <div className="relative" ref={profileRef}>
            <button
              onClick={() => setProfileOpen(v => !v)}
              className="w-7 h-7 rounded-full bg-[#F97316] flex items-center justify-center text-white text-[11px] font-bold hover:opacity-90 transition-opacity"
              title={user.name}
            >
              {user.name.charAt(0).toUpperCase()}
            </button>
            {profileOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 bg-white border border-[#E5E7EB] rounded-xl shadow-lg overflow-hidden z-50">
                <div className="px-3.5 py-3 border-b border-[#F3F4F6]">
                  <div className="text-[13px] font-semibold text-[#111827]">{user.name}</div>
                  <div className="text-[11px] text-[#9CA3AF]">
                    {user.role === 'owner' ? 'Owner' : user.role === 'admin' ? 'Admin' : 'User'}
                  </div>
                </div>
                <button
                  onClick={() => { onNavigate('settings'); setProfileOpen(false) }}
                  className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-[12.5px] text-[#374151] hover:bg-[#F5F7FA]"
                >
                  <Settings size={13} className="text-[#9CA3AF]" />
                  설정
                </button>
                <button
                  onClick={() => { onOpenDrawer(); setProfileOpen(false) }}
                  className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-[12.5px] text-[#374151] hover:bg-[#F5F7FA]"
                >
                  <Menu size={13} className="text-[#9CA3AF]" />
                  메뉴 편집
                </button>
                <div className="border-t border-[#F3F4F6]" />
                <button
                  onClick={() => { wsClient.reconnect(); setProfileOpen(false) }}
                  className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-[12.5px] text-[#374151] hover:bg-[#F5F7FA]"
                >
                  <RotateCw size={13} className="text-[#9CA3AF]" />
                  서버 재연결
                </button>
              </div>
            )}
          </div>

          {/* 메뉴 (점 3개) */}
          <button
            onClick={onOpenDrawer}
            className="w-7 h-7 flex items-center justify-center rounded-full text-[#6B7280] hover:bg-[#E8EAED] transition-colors"
            title="메뉴"
          >
            <Menu size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
