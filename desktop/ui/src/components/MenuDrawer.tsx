import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'
import type { MenuItem } from '@/lib/ws'

interface MenuDrawerProps {
  open: boolean
  onClose: () => void
}

export function MenuDrawer({ open, onClose }: MenuDrawerProps) {
  const { menuItems, setMenuItems } = useAppStore()
  const [draft, setDraft] = useState<MenuItem[]>([])
  const [dragIdx, setDragIdx] = useState<number | null>(null)

  useEffect(() => {
    if (open) setDraft(menuItems.map(m => ({ ...m })))
  }, [open])

  function toggle(id: string) {
    setDraft(d => d.map(m => m.id === id ? { ...m, visible: !m.visible } : m))
  }

  function save() {
    setMenuItems(draft)
    const userId = localStorage.getItem('user_id') || 'default'
    wsClient.send({ action: 'save_menu', user_id: userId, items: draft })
    onClose()
  }

  return (
    <>
      <div
        onClick={onClose}
        className={cn(
          'fixed inset-0 bg-black/20 z-40 transition-opacity duration-200',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
      />
      <div className={cn(
        'fixed top-0 right-0 bottom-0 w-80 bg-white border-l border-zinc-200 z-50',
        'flex flex-col shadow-2xl transition-transform duration-200'
        , open ? 'translate-x-0' : 'translate-x-full'
      )}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-100">
          <span className="text-[14px] font-bold text-zinc-900">메뉴 설정</span>
          <button onClick={onClose} className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 hover:bg-zinc-100 transition-colors">
            <X size={16} />
          </button>
        </div>

        <p className="px-5 py-3 text-[12px] text-zinc-500">
          항목을 켜거나 끄고, 드래그해서 순서를 변경하세요.
        </p>

        <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-2">
          {draft.map((item, idx) => {
            const prevSection = idx > 0 ? draft[idx - 1].section : null
            const showSection = item.section && item.section !== prevSection
            return (
            <div key={item.id}>
              {showSection && (
                <div className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-400">
                  {item.section}
                </div>
              )}
            <div
              key={item.id + '_row'}
              draggable
              onDragStart={() => setDragIdx(idx)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragIdx === null || dragIdx === idx) return
                const next = [...draft]
                const [moved] = next.splice(dragIdx, 1)
                next.splice(idx, 0, moved)
                setDraft(next)
                setDragIdx(null)
              }}
              onDragEnd={() => setDragIdx(null)}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1 cursor-grab transition-colors',
                'hover:bg-zinc-50',
                dragIdx === idx && 'opacity-40'
              )}
            >
              <input
                type="checkbox"
                checked={item.visible !== false}
                onChange={() => toggle(item.id)}
                className="w-4 h-4 accent-[#f97316] flex-shrink-0"
              />
              <span className="text-base flex-shrink-0">{item.icon}</span>
              <span className="flex-1 text-[13px] text-zinc-800">{item.label}</span>
              <span className="text-zinc-300 text-xs select-none">⠿</span>
            </div>
            </div>
          )})}
        </div>

        <div className="flex gap-2 px-5 py-4 border-t border-zinc-100">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-lg bg-white border border-zinc-200 text-[13px] text-zinc-600 hover:bg-zinc-50 transition-colors"
          >
            취소
          </button>
          <button
            onClick={save}
            className="flex-1 py-2 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors"
          >
            저장
          </button>
        </div>
      </div>
    </>
  )
}
