import { useState, useRef, useEffect } from 'react'
import { ChevronLeft, ChevronRight, Plus, Settings, Menu, Wifi, WifiOff, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'

const user = {
  id:   localStorage.getItem('user_id')   || 'default',
  name: localStorage.getItem('user_name') || '사용자',
  role: localStorage.getItem('user_role') || 'any',
}

export function Sidebar({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  const { connected, connecting, panel, setPanel, sidebarCollapsed, setSidebarCollapsed,
          menuItems, badgeApproval, badgeTask } = useAppStore()
  const [popoverOpen, setPopoverOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node))
        setPopoverOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const visible = menuItems.filter(m => m.visible !== false)

  const sections: { label: string; items: typeof visible }[] = []
  visible.forEach(item => {
    const sec = sections.find(s => s.label === item.section)
    if (sec) sec.items.push(item)
    else sections.push({ label: item.section, items: [item] })
  })

  const getBadge = (id: string) => {
    if (id === 'approval')   return badgeApproval
    if (id === 'task_queue') return badgeTask
    return 0
  }

  const roleLabel = user.role === 'owner' ? 'Owner' : user.role === 'admin' ? 'Admin' : 'User'
  const initial = user.name.charAt(0).toUpperCase()

  return (
    <aside className={cn(
      'flex flex-col h-full border-r border-[#E5E7EB] transition-all duration-200 flex-shrink-0',
      'bg-[#F0F2F5]',
      sidebarCollapsed ? 'w-14' : 'w-56'
    )}>

      {/* 상단: 로고 + 접기 */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-[#E5E7EB] min-h-[48px]">
        {!sidebarCollapsed && (
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="w-6 h-6 rounded-md bg-[#F97316] flex items-center justify-center flex-shrink-0">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <span className="font-semibold text-[13px] text-[#111827] truncate">Haehan AI</span>
          </div>
        )}
        {sidebarCollapsed && (
          <div className="w-6 h-6 rounded-md bg-[#F97316] flex items-center justify-center mx-auto">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
        )}
        {!sidebarCollapsed && (
          <button
            onClick={() => setSidebarCollapsed(true)}
            className="p-1 rounded-md text-[#9CA3AF] hover:text-[#374151] hover:bg-[#E5E7EB] transition-colors flex-shrink-0"
            title="사이드바 접기"
          >
            <ChevronLeft size={14} />
          </button>
        )}
      </div>

      {/* 새 대화 */}
      <div className="px-2 pt-2.5 pb-1">
        <button
          onClick={() => { useAppStore.getState().clearMessages(); setPanel('chat') }}
          className={cn(
            'flex items-center gap-2 w-full px-3 py-1.5 rounded-md text-[12px] font-medium transition-colors',
            'border border-[#E5E7EB] bg-white text-[#374151] hover:bg-[#F9FAFB] hover:text-[#111827] shadow-sm',
            sidebarCollapsed && 'justify-center px-0'
          )}
          title="새 대화"
        >
          <Plus size={13} className="flex-shrink-0 text-[#F97316]" />
          {!sidebarCollapsed && <span>새 대화</span>}
        </button>
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-1 scrollbar-thin">
        {sections.map(sec => (
          <div key={sec.label} className="mb-2">
            {!sidebarCollapsed && (
              <div className="px-2 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
                {sec.label}
              </div>
            )}
            {sec.items.map(item => {
              const badge = getBadge(item.id)
              const active = panel === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => setPanel(item.id)}
                  title={sidebarCollapsed ? item.label : undefined}
                  className={cn(
                    'relative flex items-center gap-2 w-full px-2 py-1.5 rounded-md text-[12.5px] transition-colors mb-0.5',
                    active
                      ? 'bg-white text-[#F97316] font-semibold shadow-sm border border-[#E5E7EB]'
                      : 'text-[#6B7280] hover:bg-white hover:text-[#111827]',
                    sidebarCollapsed && 'justify-center px-0'
                  )}
                >
                  <span className="text-sm flex-shrink-0 w-5 text-center leading-none">{item.icon}</span>
                  {!sidebarCollapsed && (
                    <>
                      <span className="flex-1 truncate text-left">{item.label}</span>
                      {badge > 0 && (
                        <span className="text-[10px] font-bold bg-[#F97316] text-white rounded-full px-1.5 min-w-[18px] text-center">
                          {badge}
                        </span>
                      )}
                    </>
                  )}
                  {sidebarCollapsed && badge > 0 && (
                    <span className="absolute top-1 right-1 w-2 h-2 bg-[#F97316] rounded-full" />
                  )}
                </button>
              )
            })}
          </div>
        ))}
      </nav>

      {/* 하단 */}
      <div className="border-t border-[#E5E7EB] px-2 py-2 space-y-0.5">

        {/* 사용자 버튼 + 팝오버 */}
        <div className="relative" ref={popoverRef}>
          <button
            onClick={() => setPopoverOpen(v => !v)}
            className={cn(
              'flex items-center gap-2 w-full px-2 py-1.5 rounded-md transition-colors',
              'text-[#6B7280] hover:bg-white hover:text-[#111827]',
              sidebarCollapsed && 'justify-center px-0'
            )}
            title={sidebarCollapsed ? '사용자 메뉴' : undefined}
          >
            <div className="w-7 h-7 rounded-md bg-[#F97316] flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {initial}
            </div>
            {!sidebarCollapsed && (
              <>
                <div className="flex-1 min-w-0 text-left">
                  <div className="text-[12px] font-semibold text-[#111827] truncate">{user.name}</div>
                  <div className="text-[10px] text-[#9CA3AF]">{roleLabel}</div>
                </div>
                <span className="text-[#D1D5DB] text-xs">···</span>
              </>
            )}
          </button>

          {popoverOpen && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-white border border-[#E5E7EB] rounded-lg shadow-lg overflow-hidden z-50">
              <button
                onClick={() => { setPanel('settings'); setPopoverOpen(false) }}
                className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-[12.5px] text-[#374151] hover:bg-[#F5F7FA] transition-colors"
              >
                <Settings size={13} className="text-[#9CA3AF]" />
                <span>설정</span>
              </button>
              <div className="border-t border-[#F3F4F6]" />
              <button
                onClick={() => { onOpenDrawer(); setPopoverOpen(false) }}
                className="flex items-center gap-2.5 w-full px-3.5 py-2.5 text-[12.5px] text-[#374151] hover:bg-[#F5F7FA] transition-colors"
              >
                <Menu size={13} className="text-[#9CA3AF]" />
                <span>메뉴 편집</span>
              </button>
            </div>
          )}
        </div>

        {/* 연결 상태 */}
        <button
          onClick={() => !connected && !connecting && wsClient.reconnect()}
          className={cn(
            'flex items-center gap-2 w-full px-2 py-1.5 rounded-md text-[11px] transition-colors',
            !connected && !connecting && 'hover:bg-white cursor-pointer',
            sidebarCollapsed && 'justify-center px-0'
          )}
          title={connected ? '연결됨' : connecting ? '연결 중…' : '클릭하여 재연결'}
        >
          {connected
            ? <Wifi size={11} className="text-[#059669] flex-shrink-0" />
            : connecting
              ? <Loader2 size={11} className="text-[#D97706] flex-shrink-0 animate-spin" />
              : <WifiOff size={11} className="text-[#DC2626] flex-shrink-0" />
          }
          {!sidebarCollapsed && (
            <span className={connected ? 'text-[#059669]' : connecting ? 'text-[#D97706]' : 'text-[#DC2626]'}>
              {connected ? '연결됨' : connecting ? '연결 중…' : '연결 끊김 — 클릭하여 재연결'}
            </span>
          )}
        </button>
      </div>

      {/* collapsed 시 펼치기 */}
      {sidebarCollapsed && (
        <button
          onClick={() => setSidebarCollapsed(false)}
          className="flex items-center justify-center py-2 text-[#9CA3AF] hover:text-[#374151] transition-colors border-t border-[#E5E7EB]"
          title="사이드바 열기"
        >
          <ChevronRight size={14} />
        </button>
      )}
    </aside>
  )
}
