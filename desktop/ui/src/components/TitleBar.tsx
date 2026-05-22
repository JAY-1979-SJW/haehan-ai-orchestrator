import { Minus, Square, X, Menu } from 'lucide-react'

declare global {
  interface Window {
    electronAPI?: {
      minimize: () => void
      maximize: () => void
      close: () => void
    }
  }
}

interface TitleBarProps {
  onHamburger: () => void
}

export function TitleBar({ onHamburger }: TitleBarProps) {
  const minimize = () => window.electronAPI?.minimize()
  const maximize = () => window.electronAPI?.maximize()
  const close    = () => window.electronAPI?.close()

  return (
    <div
      className="flex items-center justify-between h-9 px-2 bg-[#F0F2F5] border-b border-[#D1D5DB] flex-shrink-0 select-none"
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    >
      {/* 좌측: 햄버거 + 앱명 */}
      <div
        className="flex items-center gap-1.5"
        style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
      >
        <button
          onClick={onHamburger}
          className="w-7 h-7 flex items-center justify-center rounded text-[#6B7280] hover:bg-[#E5E7EB] transition-colors"
          title="메뉴"
        >
          <Menu size={15} />
        </button>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-[#F97316] flex items-center justify-center flex-shrink-0">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="text-[12px] font-semibold text-[#111827]">Haehan AI</span>
        </div>
      </div>

      {/* 우측: 창 제어 버튼 */}
      <div
        className="flex items-center gap-0.5"
        style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
      >
        <button onClick={minimize} className="w-8 h-7 flex items-center justify-center rounded text-[#6B7280] hover:bg-[#E5E7EB] transition-colors" title="최소화">
          <Minus size={12} />
        </button>
        <button onClick={maximize} className="w-8 h-7 flex items-center justify-center rounded text-[#6B7280] hover:bg-[#E5E7EB] transition-colors" title="최대화">
          <Square size={11} />
        </button>
        <button onClick={close} className="w-8 h-7 flex items-center justify-center rounded text-[#6B7280] hover:bg-[#DC2626] hover:text-white transition-colors" title="닫기">
          <X size={12} />
        </button>
      </div>
    </div>
  )
}
