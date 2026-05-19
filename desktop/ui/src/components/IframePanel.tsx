import { useState } from 'react'
import { RefreshCw, ExternalLink } from 'lucide-react'

interface IframePanelProps {
  src: string
  title: string
}

export function IframePanel({ src, title }: IframePanelProps) {
  const [key, setKey] = useState(0)
  const [loading, setLoading] = useState(true)

  return (
    <div className="flex flex-col h-full bg-[#F5F7FA]">
      {/* 툴바 */}
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-[#E5E7EB] min-h-[40px]">
        <span className="text-[12px] text-[#6B7280] truncate">{src}</span>
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          <button
            onClick={() => { setLoading(true); setKey(k => k + 1) }}
            className="p-1.5 rounded-md text-[#6B7280] hover:bg-[#F5F7FA] hover:text-[#111827] transition-colors"
            title="새로고침"
          >
            <RefreshCw size={13} />
          </button>
          <button
            onClick={() => window.open(src, '_blank')}
            className="p-1.5 rounded-md text-[#6B7280] hover:bg-[#F5F7FA] hover:text-[#111827] transition-colors"
            title="외부 브라우저에서 열기"
          >
            <ExternalLink size={13} />
          </button>
        </div>
      </div>

      {/* iframe */}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#F5F7FA] z-10">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-[#F97316] border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-[12px] text-[#6B7280]">{title} 로딩 중…</p>
            </div>
          </div>
        )}
        <iframe
          key={key}
          src={src}
          title={title}
          className="w-full h-full border-none"
          onLoad={() => setLoading(false)}
          onError={() => setLoading(false)}
        />
      </div>
    </div>
  )
}
