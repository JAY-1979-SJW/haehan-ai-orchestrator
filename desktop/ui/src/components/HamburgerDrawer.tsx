import { useEffect, useRef } from 'react'
import { X, Plus, Settings, Menu, Wifi, WifiOff, Loader2, RotateCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'

interface HamburgerDrawerProps {
  open: boolean
  onClose: () => void
  onOpenMenuEditor: () => void
}

const user = {
  name: localStorage.getItem('user_name') || '사용자',
  role: localStorage.getItem('user_role') || 'any',
}

export function HamburgerDrawer({ open, onClose, onOpenMenuEditor }: HamburgerDrawerProps) {
  const { connected, connecting, panel, setPanel, menuItems, badgeApproval, badgeTask } = useAppStore()
  const drawerRef = useRef<HTMLDivElement>(null)

  // 외부 클릭 시 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, onClose])

  // ESC 키로 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  const visible = menuItems.filter(m => m.visible !== false)

  // 섹션별 그룹화
  const sections: { label: string; items: typeof visible }[] = []
  visible.forEach(item => {
    const sec = sections.find(s => s.label === item.section)
    if (sec) sec.items.push(item)
    else sections.push({ label: item.section ?? '기타', items: [item] })
  })

  const getBadge = (id: string) => {
    if (id === 'approval')   return badgeApproval
    if (id === 'task_queue') return badgeTask
    return 0
  }

  const roleLabel = user.role === 'owner' ? 'Owner' : user.role === 'admin' ? 'Admin' : 'User'

  function navigate(id: string) {
    setPanel(id)
    onClose()
  }

  return (
    <>
      {/* 백드롭 */}
      <div
        className={cn(
          'fixed inset-0 z-40 transition-all duration-300',
          open ? 'bg-black/40 backdrop-blur-[2px] pointer-events-auto' : 'bg-transparent pointer-events-none'
        )}
        aria-hidden
      />

      {/* 드로어 패널 */}
      <div
        ref={drawerRef}
        className={cn(
          'fixed top-0 left-0 bottom-0 z-50 w-72 bg-white shadow-2xl',
          'flex flex-col transition-transform duration-300 ease-in-out',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* 헤더 — 유저 프로필 */}
        <div className="flex items-center justify-between px-4 py-4 bg-gradient-to-r from-[#F97316] to-[#EA580C]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-white/30 flex items-center justify-center text-white font-bold text-[15px]">
              {user.name.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="text-white font-semibold text-[13px]">{user.name}</div>
              <div className="text-white/70 text-[11px]">{roleLabel}</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full text-white/80 hover:bg-white/20 transition-colors"
          >
            <X size={15} />
          </button>
        </div>

        {/* 빠른 액션 */}
        <div className="flex gap-2 px-4 py-3 border-b border-zinc-100">
          <button
            onClick={() => { useAppStore.getState().clearMessages(); navigate('chat') }}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-[#F97316]/10 text-[#F97316] text-[12px] font-semibold hover:bg-[#F97316]/20 transition-colors"
          >
            <Plus size={13} /> 새 대화
          </button>
          <button
            onClick={() => { navigate('settings') }}
            className="flex items-center justify-center w-9 rounded-lg bg-zinc-100 text-zinc-500 hover:bg-zinc-200 transition-colors"
          >
            <Settings size={14} />
          </button>
          <button
            onClick={() => { onOpenMenuEditor(); onClose() }}
            className="flex items-center justify-center w-9 rounded-lg bg-zinc-100 text-zinc-500 hover:bg-zinc-200 transition-colors"
            title="메뉴 편집"
          >
            <Menu size={14} />
          </button>
        </div>

        {/* 메뉴 네비게이션 */}
        <nav className="flex-1 overflow-y-auto px-3 py-2 scrollbar-thin">
          {sections.map(sec => (
            <div key={sec.label} className="mb-3">
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                {sec.label}
              </div>
              <div className="space-y-0.5">
                {sec.items.map(item => {
                  const badge = getBadge(item.id)
                  const active = panel === item.id
                  return (
                    <button
                      key={item.id}
                      onClick={() => navigate(item.id)}
                      className={cn(
                        'relative flex items-center gap-3 w-full px-3 py-2 rounded-lg text-[13px] transition-colors',
                        active
                          ? 'bg-[#F97316]/10 text-[#F97316] font-semibold'
                          : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900'
                      )}
                    >
                      <span className="text-[15px] w-5 text-center flex-shrink-0">{item.icon}</span>
                      <span className="flex-1 text-left">{item.label}</span>
                      {badge > 0 && (
                        <span className="text-[10px] font-bold bg-[#F97316] text-white rounded-full px-1.5 min-w-[18px] text-center">
                          {badge}
                        </span>
                      )}
                      {active && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-[#F97316] rounded-r-full" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* 하단 — 연결 상태 */}
        <div className="border-t border-zinc-100 px-4 py-3 space-y-2">
          <button
            onClick={() => !connected && !connecting && wsClient.reconnect()}
            className="flex items-center gap-2.5 w-full text-[12px] transition-colors"
          >
            {connected
              ? <><Wifi size={13} className="text-emerald-500 flex-shrink-0" /><span className="text-emerald-600">서버 연결됨</span></>
              : connecting
                ? <><Loader2 size={13} className="text-amber-500 animate-spin flex-shrink-0" /><span className="text-amber-600">연결 중…</span></>
                : <><WifiOff size={13} className="text-red-500 flex-shrink-0" /><span className="text-red-500">연결 끊김 — 클릭하여 재연결</span></>
            }
          </button>
          <button
            onClick={() => { wsClient.reconnect(); onClose() }}
            className="flex items-center gap-2 w-full px-3 py-1.5 rounded-lg text-[11.5px] text-zinc-500 hover:bg-zinc-50 transition-colors"
          >
            <RotateCw size={12} />
            서버 재연결
          </button>
        </div>
      </div>
    </>
  )
}
