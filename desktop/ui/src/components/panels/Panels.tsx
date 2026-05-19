import { useState, useEffect } from 'react'
import { RefreshCw } from 'lucide-react'
import { PanelShell, EmptyState, HelpSection, HelpTitle, HelpList, HelpNote, StatusCard } from './PanelShell'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'
import { cn } from '@/lib/utils'

// ── 작업 큐 ──────────────────────────────────────────────────────────────────
export function TaskQueuePanel() {
  const { tasks } = useAppStore()
  return (
    <PanelShell title="작업 큐" desc="서버에서 수신된 태스크 목록입니다. 실행 위치와 상태를 확인할 수 있습니다.">
      {tasks.length === 0
        ? <EmptyState title="대기 중인 작업이 없습니다" desc="서버에서 태스크가 전송되면 이곳에 표시됩니다." />
        : (
          <div className="space-y-3">
            {tasks.map(t => <TaskCard key={t.task_id} task={t} showActions={false} />)}
          </div>
        )
      }
    </PanelShell>
  )
}

// ── 승인 대기 ─────────────────────────────────────────────────────────────────
// MVP 잠금: 승인/거부 버튼 미노출 (조회 전용)
export function ApprovalPanel() {
  const { approvalTasks } = useAppStore()
  return (
    <PanelShell title="승인 대기" desc="사용자 승인이 필요한 작업 목록입니다. 승인은 autowork 관리 웹에서 처리하세요.">
      {approvalTasks.length === 0
        ? <EmptyState title="승인 대기 항목이 없습니다" desc="승인이 필요한 작업이 도착하면 이곳에 표시됩니다." />
        : (
          <div className="space-y-3">
            {approvalTasks.map(t => (
              <TaskCard key={t.task_id} task={t} showActions={false} />
            ))}
          </div>
        )
      }
      <HelpNote>승인/거부는 관리 웹(autowork.haehan-ai.kr/browser-approvals)에서 처리합니다.</HelpNote>
    </PanelShell>
  )
}

// ── 태스크 카드 공통 ──────────────────────────────────────────────────────────
function TaskCard({ task, showActions, onApprove, onReject }: {
  task: { task_id: string; action_type: string; domain?: string; risk_level: string; description?: string; execution_location?: string; status?: string; ts?: number }
  showActions?: boolean
  onApprove?: () => void
  onReject?: () => void
}) {
  const riskColor = {
    low:    'bg-emerald-50 text-emerald-700 border-emerald-200',
    medium: 'bg-amber-50 text-amber-700 border-amber-200',
    high:   'bg-red-50 text-red-700 border-red-200',
  }[task.risk_level] ?? 'bg-emerald-50 text-emerald-700 border-emerald-200'

  const timeStr = task.ts
    ? new Date(task.ts * 1000).toLocaleString('ko', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className="bg-white border border-zinc-200 rounded-lg px-4 py-3.5 shadow-sm">
      <div className="flex items-center gap-2 mb-2">
        <span className={cn('text-[10px] font-bold px-2 py-0.5 rounded border', riskColor)}>
          {task.risk_level.toUpperCase()}
        </span>
        <span className="text-[13px] font-semibold text-zinc-900">{task.action_type}</span>
        {task.domain && <span className="text-[11px] text-zinc-400">/ {task.domain}</span>}
      </div>
      {task.description && (
        <p className="text-[12px] text-zinc-600 mb-2 leading-relaxed">{task.description}</p>
      )}
      <div className="flex items-center justify-between text-[11px] text-zinc-400 mb-3">
        {task.execution_location && <span>실행 위치: {task.execution_location}</span>}
        <span className="ml-auto">{task.status ?? '수신 대기'}{timeStr && `  ${timeStr}`}</span>
      </div>
      {showActions && (
        <div className="flex gap-2">
          <button onClick={onApprove}
            className="flex-1 py-1.5 rounded-lg bg-emerald-600 text-white text-[12px] font-semibold hover:bg-emerald-700 transition-colors">
            승인
          </button>
          <button onClick={onReject}
            className="flex-1 py-1.5 rounded-lg bg-white border border-zinc-200 text-zinc-600 text-[12px] font-semibold hover:bg-zinc-50 transition-colors">
            거부
          </button>
        </div>
      )}
    </div>
  )
}

// ── 뉴스 ──────────────────────────────────────────────────────────────────────
export function NewsPanel() {
  return (
    <PanelShell title="뉴스" desc="네이버 뉴스를 조회합니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <p className="text-[13px] text-zinc-600 leading-relaxed">
          대화창에서 아래와 같이 입력하면 AI가 뉴스를 가져와 요약합니다.
        </p>
        <HelpList items={['오늘 뉴스 요약해줘', '최신 IT 뉴스 알려줘', '오늘 경제 뉴스 가져와']} />
      </HelpSection>
    </PanelShell>
  )
}

// ── EUM ───────────────────────────────────────────────────────────────────────
export function EumPanel() {
  return (
    <PanelShell title="EUM 단말기" desc="건설근로자공제회 단말기 임대 현황을 조회합니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <p className="text-[13px] text-zinc-600 leading-relaxed">
          대화창에서 아래와 같이 입력하면 AI가 단말기 현황을 확인합니다.
        </p>
        <HelpList items={['EUM 단말기 현황 확인해줘', '임대 중인 단말기 몇 대야', '통신 단절된 단말기 있어?']} />
        <HelpNote>현재 임대 중 22대 · 임차인: 비전아이(주)</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 브라우저 상태 ─────────────────────────────────────────────────────────────
export function BrowserPanel() {
  const { browserStatus } = useAppStore()
  return (
    <PanelShell title="브라우저 상태" desc="AI 브라우저가 백그라운드에서 실행되며 작업 결과를 대화창으로 보고합니다.">
      <StatusCard rows={[
        { label: 'CDP 포트',  value: browserStatus.port  || '—', id: 'bs-port' },
        { label: '현재 URL',  value: browserStatus.url   || '—', id: 'bs-url'  },
        { label: '작업 상태', value: browserStatus.state || '대기', id: 'bs-state' },
      ]} />
      <HelpNote>브라우저는 화면에 표시되지 않으며, 작업 완료 시 대화창으로 결과를 보고합니다.</HelpNote>
    </PanelShell>
  )
}

// ── 스크린샷 ──────────────────────────────────────────────────────────────────
export function ScreenshotPanel() {
  return (
    <PanelShell title="스크린샷" desc="AI 브라우저 작업 중 캡처된 화면입니다.">
      <EmptyState title="캡처된 이미지가 없습니다" desc="AI 브라우저가 작업을 수행하면 캡처 이미지가 이곳에 저장됩니다." />
    </PanelShell>
  )
}

// ── 로그 ──────────────────────────────────────────────────────────────────────
export function LogsPanel() {
  const [lines, setLines] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [ts, setTs] = useState(0)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('http://127.0.0.1:8765/logs')
      if (r.ok) {
        const data = await r.json()
        setLines(data.lines ?? [])
        setTs(Date.now())
      }
    } catch {
      setLines(['로그 서버 미연결 — local_server 실행 확인'])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div className="flex flex-col h-full bg-[#FAFAFA]">
      <div className="flex items-center justify-between px-8 py-5 border-b border-zinc-200">
        <div>
          <h2 className="text-[17px] font-bold text-zinc-900 mb-0.5">로그</h2>
          <p className="text-[12px] text-zinc-400">
            {ts ? `마지막 갱신: ${new Date(ts).toLocaleTimeString('ko')}` : '로딩 중…'}
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 bg-white text-[12px] text-zinc-600 hover:bg-zinc-50 transition-colors disabled:opacity-40">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin px-8 py-4">
        {lines.length === 0
          ? <EmptyState title="로그가 없습니다" desc="작업이 실행되면 이력이 이곳에 기록됩니다." />
          : (
            <div className="font-mono text-[11px] text-zinc-700 space-y-0.5">
              {lines.map((l, i) => (
                <div key={i} className={cn('py-0.5 px-2 rounded',
                  l.includes('ERROR') || l.includes('FAIL') ? 'bg-red-50 text-red-700' :
                  l.includes('WARN') ? 'bg-amber-50 text-amber-700' :
                  l.includes('INFO') ? '' : 'text-zinc-400'
                )}>{l}</div>
              ))}
            </div>
          )
        }
      </div>
    </div>
  )
}

// ── 설정 ──────────────────────────────────────────────────────────────────────
export function SettingsPanel() {
  const [serverUrl, setServerUrl] = useState(localStorage.getItem('server_url') || 'wss://api.haehan-ai.kr/ws/desktop')
  const [name, setName] = useState(localStorage.getItem('user_name') || '사용자')
  const [role, setRole] = useState(localStorage.getItem('user_role') || 'any')
  const [saved, setSaved] = useState(false)

  function save() {
    localStorage.setItem('server_url', serverUrl)
    localStorage.setItem('user_name', name)
    localStorage.setItem('user_role', role)
    wsClient.reconnect()
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <PanelShell title="설정" desc="서버 연결 주소와 사용자 정보를 설정합니다.">
      <div className="space-y-6">
        <SettingsField label="서버 주소" help="메인 서버의 WebSocket 주소입니다. 변경 후 앱을 재시작하면 적용됩니다.">
          <input
            value={serverUrl} onChange={e => setServerUrl(e.target.value)}
            className="w-full max-w-md bg-white border border-zinc-200 rounded-lg px-3 py-2 text-[13px] text-zinc-900 outline-none focus:border-[#f97316]/50 focus:ring-2 focus:ring-[#f97316]/10 transition-all placeholder-zinc-400"
            placeholder="ws://localhost:8000/ws/desktop"
          />
        </SettingsField>

        <SettingsField label="사용자 이름">
          <input
            value={name} onChange={e => setName(e.target.value)}
            className="w-full max-w-md bg-white border border-zinc-200 rounded-lg px-3 py-2 text-[13px] text-zinc-900 outline-none focus:border-[#f97316]/50 focus:ring-2 focus:ring-[#f97316]/10 transition-all"
            placeholder="이름"
          />
        </SettingsField>

        <SettingsField label="역할" help="역할에 따라 사이드바 메뉴 항목이 달라집니다.">
          <select
            value={role} onChange={e => setRole(e.target.value)}
            className="w-48 bg-white border border-zinc-200 rounded-lg px-3 py-2 text-[13px] text-zinc-900 outline-none focus:border-[#f97316]/50 transition-colors"
          >
            <option value="any">User — 기본 기능</option>
            <option value="admin">Admin — 시스템 메뉴 포함</option>
            <option value="owner">Owner — 전체 권한</option>
          </select>
        </SettingsField>

        <button
          onClick={save}
          className={cn(
            'px-5 py-2 rounded-lg text-[13px] font-semibold transition-colors',
            saved ? 'bg-emerald-600 text-white' : 'bg-[#f97316] text-white hover:bg-[#ea580c]'
          )}
        >
          {saved ? '저장됨' : '저장'}
        </button>
      </div>
    </PanelShell>
  )
}

function SettingsField({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">
        {label}
      </label>
      {children}
      {help && <p className="text-[11px] text-zinc-400 mt-1.5 leading-relaxed">{help}</p>}
    </div>
  )
}
