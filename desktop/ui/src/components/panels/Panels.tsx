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
  const { connected } = useAppStore()
  const [name, setName] = useState(localStorage.getItem('user_name') || '사용자')
  const [role, setRole] = useState(localStorage.getItem('user_role') || 'any')
  const [saved, setSaved] = useState(false)

  // 등록 폼
  const [regCode, setRegCode] = useState('')
  const [serverUrlInput, setServerUrlInput] = useState('https://haehan-ai.kr/orchestrator')
  const [regStatus, setRegStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle')
  const [regMsg, setRegMsg] = useState('')

  // 에이전트 상태
  const [agentInfo, setAgentInfo] = useState<{agent_id?: string; server_url?: string; server_connected?: boolean} | null>(null)

  useEffect(() => {
    fetch('http://127.0.0.1:8765/agent/status')
      .then(r => r.json())
      .then(d => setAgentInfo(d))
      .catch(() => setAgentInfo(null))
  }, [regStatus])

  async function handleRegister() {
    if (!regCode.trim()) return
    setRegStatus('loading')
    setRegMsg('')
    try {
      const r = await fetch('http://127.0.0.1:8765/agent/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ registration_code: regCode.trim(), server_url: serverUrlInput.trim() }),
      })
      const d = await r.json()
      if (d.ok) {
        setRegStatus('ok')
        setRegMsg(`등록 완료 · ${d.agent_id}`)
        setRegCode('')
      } else {
        setRegStatus('error')
        setRegMsg(d.error || '등록 실패')
      }
    } catch (e) {
      setRegStatus('error')
      setRegMsg('로컬 서버 미연결')
    }
  }

  function save() {
    localStorage.setItem('user_name', name)
    localStorage.setItem('user_role', role)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <PanelShell title="설정" desc="서버 연결 및 사용자 정보를 설정합니다.">
      <div className="space-y-6">

        {/* 에이전트 연결 상태 */}
        <div className="bg-zinc-50 border border-zinc-200 rounded-lg px-4 py-3 space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">연결 상태</p>
          <div className="flex items-center gap-2">
            <span className={cn('inline-block w-2 h-2 rounded-full', connected ? 'bg-emerald-500' : 'bg-zinc-300')} />
            <span className="text-[13px] text-zinc-700">{connected ? '로컬 서버(8765) 연결됨' : '로컬 서버 미연결'}</span>
          </div>
          {agentInfo?.agent_id ? (
            <div className="pl-4 space-y-0.5">
              <p className="text-[12px] text-zinc-600">에이전트: <span className="font-mono">{agentInfo.agent_id}</span></p>
              <p className="text-[12px] text-zinc-600">서버: <span className="font-mono text-[11px]">{agentInfo.server_url}</span></p>
              <div className="flex items-center gap-1.5 mt-1">
                <span className={cn('inline-block w-1.5 h-1.5 rounded-full', agentInfo.server_connected ? 'bg-emerald-500' : 'bg-red-400')} />
                <span className="text-[11px] text-zinc-500">{agentInfo.server_connected ? '서버 WS 연결됨' : '서버 WS 미연결'}</span>
              </div>
            </div>
          ) : (
            <p className="text-[12px] text-zinc-400 pl-4">등록된 에이전트 없음</p>
          )}
        </div>

        {/* 에이전트 등록 */}
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-3">에이전트 등록</p>
          <div className="space-y-2 max-w-md">
            <input
              value={serverUrlInput} onChange={e => setServerUrlInput(e.target.value)}
              className="w-full bg-white border border-zinc-200 rounded-lg px-3 py-2 text-[12px] font-mono text-zinc-700 outline-none focus:border-[#f97316]/50"
              placeholder="https://haehan-ai.kr/orchestrator"
            />
            <div className="flex gap-2">
              <input
                value={regCode} onChange={e => setRegCode(e.target.value)}
                type="password"
                className="flex-1 bg-white border border-zinc-200 rounded-lg px-3 py-2 text-[13px] text-zinc-900 outline-none focus:border-[#f97316]/50 focus:ring-2 focus:ring-[#f97316]/10"
                placeholder="등록 코드 입력"
                onKeyDown={e => e.key === 'Enter' && handleRegister()}
              />
              <button
                onClick={handleRegister}
                disabled={regStatus === 'loading' || !regCode.trim()}
                className="px-4 py-2 rounded-lg text-[13px] font-semibold bg-[#f97316] text-white hover:bg-[#ea580c] disabled:opacity-40 transition-colors"
              >
                {regStatus === 'loading' ? '등록 중…' : '등록'}
              </button>
            </div>
            {regMsg && (
              <p className={cn('text-[12px]', regStatus === 'ok' ? 'text-emerald-600' : 'text-red-500')}>{regMsg}</p>
            )}
            <p className="text-[11px] text-zinc-400">관리자로부터 받은 1회용 등록 코드를 입력하세요.</p>
          </div>
        </div>

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

// ── 카페 글쓰기 ───────────────────────────────────────────────────────────────
const CAFE_BOARDS = [
  '건설질문&경험자의견',
  '건 설 인 수 다 방',
  '건 설 구 인 구 직',
  '기업홍보/기업자료',
  '건설 시공 관련 업무',
  '건설 노무 관련 업무',
  '건설 공무 관련 업무',
  '건설회사관리관련업무',
  '건설 자유 게시판',
]

export function CafeWritePanel() {
  const { cafeState, setCafeState } = useAppStore()
  const [cafeUrl, setCafeUrl] = useState('https://cafe.naver.com/0moo')
  const [board, setBoard] = useState(CAFE_BOARDS[0])
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [membersOnly, setMembersOnly] = useState(false)
  const [tags, setTags] = useState('')

  const isIdle       = cafeState.status === 'idle'
  const isWriting    = cafeState.status === 'writing'
  const isAwaiting   = cafeState.status === 'awaiting_approval'
  const isConfirming = cafeState.status === 'confirming'
  const isDone       = cafeState.status === 'done'
  const isError      = cafeState.status === 'error'
  const isBusy       = isWriting || isConfirming

  function handleWrite() {
    if (!title.trim() || !body.trim()) return
    setCafeState({ status: 'writing', error: '' })
    wsClient.send({
      action: 'cafe_write',
      cafe_url: cafeUrl,
      board,
      title: title.trim(),
      body: body.trim(),
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      members_only: membersOnly,
    })
  }

  function handleConfirm() {
    setCafeState({ status: 'confirming', error: '' })
    wsClient.send({ action: 'cafe_confirm' })
  }

  function handleReset() {
    setCafeState({ status: 'idle', title: '', board: '', bodyPreview: '', resultUrl: '', error: '' })
    setTitle('')
    setBody('')
  }

  return (
    <PanelShell title="카페 글쓰기" desc="네이버 카페 글을 작성하고 발행합니다. 발행 전 브라우저에서 내용을 확인한 뒤 최종 발행하세요.">
      <div className="space-y-5">

        {isDone && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
            <p className="text-[13px] font-semibold text-emerald-800 mb-1">발행 완료</p>
            {cafeState.resultUrl && (
              <a href={cafeState.resultUrl} target="_blank" rel="noopener noreferrer"
                className="text-[12px] text-emerald-700 underline break-all">
                {cafeState.resultUrl}
              </a>
            )}
            <button onClick={handleReset} className="mt-3 text-[12px] text-emerald-600 underline block">새 글 작성</button>
          </div>
        )}

        {isError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-[13px] font-semibold text-red-700 mb-1">오류</p>
            <p className="text-[12px] text-red-600">{cafeState.error || '알 수 없는 오류'}</p>
            <button onClick={handleReset} className="mt-2 text-[12px] text-red-500 underline">다시 시도</button>
          </div>
        )}

        {isAwaiting && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-2">
            <p className="text-[13px] font-semibold text-amber-800">브라우저에서 내용을 확인하세요</p>
            <div className="text-[12px] text-amber-700 space-y-1">
              <p><span className="font-medium">제목:</span> {cafeState.title}</p>
              <p><span className="font-medium">게시판:</span> {cafeState.board}</p>
              {cafeState.bodyPreview && (
                <p className="text-amber-600 text-[11px] mt-1 leading-relaxed">{cafeState.bodyPreview.slice(0, 80)}…</p>
              )}
            </div>
            <div className="flex gap-2 pt-2">
              <button onClick={handleConfirm}
                className="flex-1 py-2 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors">
                발행 확정
              </button>
              <button onClick={handleReset}
                className="flex-1 py-2 rounded-lg bg-white border border-zinc-200 text-[13px] text-zinc-600 hover:bg-zinc-50 transition-colors">
                취소
              </button>
            </div>
          </div>
        )}

        {(isIdle || isError) && (
          <>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">카페 URL</label>
              <input
                value={cafeUrl} onChange={e => setCafeUrl(e.target.value)}
                placeholder="https://cafe.naver.com/0moo"
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">게시판</label>
              <select
                value={board} onChange={e => setBoard(e.target.value)}
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
              >
                {CAFE_BOARDS.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">제목</label>
              <input
                value={title} onChange={e => setTitle(e.target.value)}
                placeholder="카페 글 제목을 입력하세요"
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">본문</label>
              <textarea
                value={body} onChange={e => setBody(e.target.value)}
                placeholder={"본문을 입력하세요.\n\n단락은 빈 줄로 구분됩니다."}
                rows={8}
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30 resize-y"
              />
            </div>

            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">태그 (쉼표 구분)</label>
                <input
                  value={tags} onChange={e => setTags(e.target.value)}
                  placeholder="건설, 공무, 현장"
                  className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
                />
              </div>
              <div className="flex items-center gap-2 pb-2">
                <input type="checkbox" id="cafe-members-only" checked={membersOnly} onChange={e => setMembersOnly(e.target.checked)}
                  className="w-4 h-4 rounded border-zinc-300 accent-[#f97316]" />
                <label htmlFor="cafe-members-only" className="text-[12px] text-zinc-600">카페회원 공개</label>
              </div>
            </div>

            <button
              onClick={handleWrite}
              disabled={!title.trim() || !body.trim()}
              className="w-full py-2.5 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              작성 시작
            </button>
          </>
        )}

        {isBusy && (
          <div className="flex items-center gap-3 py-4">
            <RefreshCw size={16} className="animate-spin text-[#f97316]" />
            <span className="text-[13px] text-zinc-600">
              {isWriting ? '카페 편집기에 작성 중...' : '발행 확정 중...'}
            </span>
          </div>
        )}
      </div>
    </PanelShell>
  )
}

// ── 블로그 작성 ───────────────────────────────────────────────────────────────
export function BlogWritePanel() {
  const { blogState, setBlogState } = useAppStore()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'neighbors' | 'private'>('public')
  const [brandTags, setBrandTags] = useState('')

  const isIdle      = blogState.status === 'idle'
  const isWriting   = blogState.status === 'writing'
  const isAwaiting  = blogState.status === 'awaiting_approval'
  const isConfirming = blogState.status === 'confirming'
  const isDone      = blogState.status === 'done'
  const isError     = blogState.status === 'error'
  const isBusy      = isWriting || isConfirming

  function handleWrite() {
    if (!title.trim() || !body.trim()) return
    setBlogState({ status: 'writing', error: '' })
    wsClient.send({
      action: 'blog_write',
      title: title.trim(),
      body: body.trim(),
      visibility,
      brand_tags: brandTags.split(',').map(t => t.trim()).filter(Boolean),
    })
  }

  function handleConfirm() {
    setBlogState({ status: 'confirming', error: '' })
    wsClient.send({ action: 'blog_confirm' })
  }

  function handleReset() {
    setBlogState({ status: 'idle', title: '', tags: [], bodyPreview: '', resultUrl: '', error: '' })
    setTitle('')
    setBody('')
  }

  const visibilityLabel = { public: '전체공개', neighbors: '이웃공개', private: '비공개' }

  return (
    <PanelShell title="블로그 작성" desc="네이버 블로그 글을 작성하고 발행합니다. 발행 전 브라우저에서 내용을 확인한 뒤 최종 발행하세요.">
      <div className="space-y-5">

        {/* 작성 완료 */}
        {isDone && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
            <p className="text-[13px] font-semibold text-emerald-800 mb-1">발행 완료</p>
            {blogState.resultUrl && (
              <a href={blogState.resultUrl} target="_blank" rel="noopener noreferrer"
                className="text-[12px] text-emerald-700 underline break-all">
                {blogState.resultUrl}
              </a>
            )}
            <button onClick={handleReset}
              className="mt-3 text-[12px] text-emerald-600 underline block">
              새 글 작성
            </button>
          </div>
        )}

        {/* 오류 */}
        {isError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-[13px] font-semibold text-red-700 mb-1">오류</p>
            <p className="text-[12px] text-red-600">{blogState.error || '알 수 없는 오류'}</p>
            <button onClick={handleReset} className="mt-2 text-[12px] text-red-500 underline">다시 시도</button>
          </div>
        )}

        {/* 승인 대기 */}
        {isAwaiting && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-2">
            <p className="text-[13px] font-semibold text-amber-800">브라우저에서 내용을 확인하세요</p>
            <div className="text-[12px] text-amber-700 space-y-1">
              <p><span className="font-medium">제목:</span> {blogState.title}</p>
              <p><span className="font-medium">공개:</span> {visibilityLabel[blogState.visibility as keyof typeof visibilityLabel] ?? blogState.visibility}</p>
              <p><span className="font-medium">태그:</span> {blogState.tags.slice(0, 8).join(', ')}{blogState.tags.length > 8 ? ` 외 ${blogState.tags.length - 8}개` : ''}</p>
              {blogState.bodyPreview && (
                <p className="text-amber-600 text-[11px] mt-1 leading-relaxed">{blogState.bodyPreview.slice(0, 80)}…</p>
              )}
            </div>
            <div className="flex gap-2 pt-2">
              <button onClick={handleConfirm}
                className="flex-1 py-2 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors">
                발행 확정
              </button>
              <button onClick={handleReset}
                className="flex-1 py-2 rounded-lg bg-white border border-zinc-200 text-[13px] text-zinc-600 hover:bg-zinc-50 transition-colors">
                취소
              </button>
            </div>
          </div>
        )}

        {/* 입력 폼 — idle/error 상태 */}
        {(isIdle || isError) && (
          <>
            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">제목</label>
              <input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="블로그 글 제목을 입력하세요"
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">본문</label>
              <textarea
                value={body}
                onChange={e => setBody(e.target.value)}
                placeholder={"본문을 입력하세요.\n\n단락은 빈 줄로 구분됩니다."}
                rows={10}
                className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30 resize-y"
              />
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">공개설정</label>
                <select
                  value={visibility}
                  onChange={e => setVisibility(e.target.value as typeof visibility)}
                  className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
                >
                  <option value="public">전체공개</option>
                  <option value="neighbors">이웃공개</option>
                  <option value="private">비공개</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">브랜드 태그 (쉼표 구분)</label>
                <input
                  value={brandTags}
                  onChange={e => setBrandTags(e.target.value)}
                  placeholder="해한AI, 비전아이"
                  className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
                />
              </div>
            </div>

            <HelpNote>태그는 제목·본문을 분석해 자동 생성됩니다. 브랜드 태그는 항상 우선 포함됩니다.</HelpNote>

            <button
              onClick={handleWrite}
              disabled={!title.trim() || !body.trim()}
              className="w-full py-2.5 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              작성 시작
            </button>
          </>
        )}

        {/* 진행 중 */}
        {isBusy && (
          <div className="flex items-center gap-3 py-4">
            <RefreshCw size={16} className="animate-spin text-[#f97316]" />
            <span className="text-[13px] text-zinc-600">
              {isWriting ? '블로그 편집기에 작성 중...' : '발행 확정 중...'}
            </span>
          </div>
        )}

      </div>
    </PanelShell>
  )
}
