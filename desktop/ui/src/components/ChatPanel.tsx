import { useRef, useEffect, useState } from 'react'
import { Send } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'

export function ChatPanel() {
  const { messages, addMessage } = useAppStore()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const hasMessages = messages.length > 0

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  function send() {
    const text = input.trim()
    if (!text) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    addMessage({ role: 'user', text, ts: Date.now() / 1000 })
    wsClient.send({ action: 'chat', text })
  }

  function quickSend(text: string) {
    addMessage({ role: 'user', text, ts: Date.now() / 1000 })
    wsClient.send({ action: 'chat', text })
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  return (
    <div className="flex flex-col h-full bg-white">

      {/* 메시지 영역 */}
      {hasMessages && (
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="max-w-2xl mx-auto px-6 py-8 flex flex-col gap-5">
            {messages.map(msg => <MessageRow key={msg.id} msg={msg} />)}
          </div>
        </div>
      )}

      {/* 입력창 영역 */}
      <div className={cn(
        'flex flex-col items-center',
        hasMessages
          ? 'border-t border-zinc-100 px-6 py-3 bg-white'
          : 'flex-1 justify-center px-6 pb-12 bg-[#FAFAFA]'
      )}>

        {/* 환영 */}
        {!hasMessages && (
          <div className="text-center mb-8">
            <div className="w-14 h-14 rounded-2xl bg-[rgba(249,115,22,0.08)] border border-[rgba(249,115,22,0.2)] flex items-center justify-center mx-auto mb-4">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  stroke="#f97316" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <h1 className="text-xl font-semibold text-zinc-900 mb-2">Haehan AI</h1>
            <p className="text-sm text-zinc-500">AI에게 지시하거나 질문하세요</p>
          </div>
        )}

        {/* 입력창 */}
        <div className={cn('w-full', !hasMessages && 'max-w-2xl')}>
          <div className="flex items-end gap-2 bg-white border border-zinc-200 rounded-xl px-4 py-2.5 shadow-sm focus-within:border-[#f97316]/50 focus-within:shadow-md transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="메시지 입력…"
              rows={1}
              className="flex-1 bg-transparent text-zinc-900 text-[13.5px] placeholder-zinc-400 resize-none outline-none leading-relaxed min-h-[22px] max-h-[120px]"
            />
            <button
              onClick={send}
              disabled={!input.trim()}
              className="w-8 h-8 rounded-lg bg-[#f97316] flex items-center justify-center text-white flex-shrink-0 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#ea580c] transition-colors"
            >
              <Send size={14} />
            </button>
          </div>
          <p className="text-center text-[11px] text-zinc-400 mt-2">
            Enter 전송 · Shift+Enter 줄바꿈
          </p>
        </div>

        {/* 퀵칩 */}
        {!hasMessages && (
          <div className="flex gap-2 flex-wrap justify-center mt-6">
            {[
              { label: '오늘 뉴스 요약해줘', q: '오늘 뉴스 요약해줘' },
              { label: 'EUM 단말기 현황', q: 'EUM 단말기 현황 확인해줘' },
              { label: '브라우저 상태 확인', q: '브라우저 상태 확인해줘' },
            ].map(chip => (
              <button
                key={chip.q}
                onClick={() => quickSend(chip.q)}
                className="px-3.5 py-1.5 rounded-full text-[12px] bg-white border border-zinc-200 text-zinc-600 hover:border-[#f97316]/40 hover:text-zinc-900 shadow-sm transition-colors"
              >
                {chip.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function MessageRow({ msg }: { msg: { role: string; text: string; ts: number } }) {
  const time = new Date(msg.ts * 1000).toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })

  if (msg.role === 'system') {
    return <div className="text-center text-[11px] text-zinc-400 py-1">{msg.text}</div>
  }

  const isUser = msg.role === 'user'
  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse', 'max-w-[88%]', isUser && 'self-end ml-auto')}>
      <div className={cn(
        'w-7 h-7 rounded-lg flex-shrink-0 flex items-center justify-center text-sm mt-0.5',
        isUser ? 'bg-[#f97316] text-white' : 'bg-zinc-100 border border-zinc-200'
      )}>
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="flex flex-col gap-1 min-w-0">
        <div className={cn(
          'text-[13.5px] leading-relaxed',
          isUser
            ? 'bg-[#f97316] text-white px-3.5 py-2 rounded-2xl rounded-tr-sm'
            : 'text-zinc-800'
        )}>
          {msg.text}
        </div>
        <div className={cn('text-[10px] text-zinc-400', isUser && 'text-right')}>{time}</div>
      </div>
    </div>
  )
}
