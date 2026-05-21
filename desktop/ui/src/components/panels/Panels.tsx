import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Bot, Cpu, Play, Square, X, Camera, Globe, Loader2, AlertCircle } from 'lucide-react'
import { PanelShell, EmptyState, HelpSection, HelpTitle, HelpList, HelpNote, StatusCard } from './PanelShell'
import { useAppStore } from '@/store/appStore'
import { wsClient } from '@/lib/ws'
import { cn } from '@/lib/utils'
import { localAgentApi, type LocalAgentHealth } from '@/api/localAgent'

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
export function ApprovalPanel() {
  const { approvalTasks, removeTask } = useAppStore()

  function handleApprove(task_id: string) {
    wsClient.send({ action: 'approve', task_id })
    removeTask(task_id)
  }

  function handleReject(task_id: string) {
    wsClient.send({ action: 'reject', task_id })
    removeTask(task_id)
  }

  return (
    <PanelShell title="승인 대기" desc="AI가 실행을 요청한 작업 목록입니다. 내용을 확인하고 승인 또는 거부하세요.">
      {approvalTasks.length === 0
        ? <EmptyState title="승인 대기 항목이 없습니다" desc="AI가 승인이 필요한 작업을 요청하면 이곳에 표시됩니다." />
        : (
          <div className="space-y-3">
            {approvalTasks.map(t => (
              <TaskCard
                key={t.task_id}
                task={t}
                showActions={true}
                onApprove={() => handleApprove(t.task_id)}
                onReject={() => handleReject(t.task_id)}
              />
            ))}
          </div>
        )
      }
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
// ── 브라우저 상태 ─────────────────────────────────────────────────────────────
// ── Login Watcher 이벤트 라벨 ─────────────────────────────────────────────────
const EVT_LABELS: Record<string, { label: string; color: string }> = {
  target_created:       { label: '탭 열림',         color: 'text-emerald-600' },
  target_closed:        { label: '탭 닫힘',         color: 'text-zinc-400'    },
  target_url_changed:   { label: 'URL 변경',        color: 'text-blue-500'   },
  target_title_changed: { label: '제목 변경',        color: 'text-zinc-500'   },
  auth_popup_detected:  { label: '🔔 인증 팝업',    color: 'text-amber-600'  },
  login_state_changed:  { label: '로그인 상태 변경', color: 'text-violet-600' },
}

const LOGIN_STATE_LABELS: Record<string, { label: string; color: string }> = {
  LOGGED_IN:            { label: '로그인됨',    color: 'text-emerald-600' },
  LOGIN_REQUIRED:       { label: '로그인 필요', color: 'text-amber-500'   },
  LOGIN_IN_PROGRESS:    { label: '로그인 중',   color: 'text-blue-500'    },
  LOGIN_ACTION_STARTED: { label: '로그인 시도', color: 'text-blue-400'    },
  LOGIN_FAILED:         { label: '로그인 실패', color: 'text-red-500'      },
  SESSION_EXPIRED:      { label: '세션 만료',   color: 'text-orange-500'  },
  POPUP_WAITING:        { label: '팝업 대기',   color: 'text-amber-600'   },
  LOGIN_UNKNOWN:        { label: '알 수 없음',  color: 'text-zinc-400'    },
}

export function BrowserPanel() {
  const { browserStatus, browserTabsState, setBrowserTabsState,
          loginWatcherState, setLoginWatcherRunning, addLoginWatcherEvent: _a,
          clearLoginWatcherEvents } = useAppStore()
  const [statusLoading, setStatusLoading] = useState(false)
  const [startLoading, setStartLoading]   = useState(false)
  const [quitLoading, setQuitLoading]     = useState(false)
  const [tabLoading, setTabLoading]       = useState(false)
  const [lastTs, setLastTs]               = useState(0)
  void _a  // used via store only

  const requestStatus = useCallback(() => {
    setStatusLoading(true)
    wsClient.send({ action: 'browser_status' })
    setTimeout(() => { setStatusLoading(false); setLastTs(Date.now()) }, 800)
  }, [])

  const requestTabs = useCallback(() => {
    setTabLoading(true)
    setBrowserTabsState({ status: 'loading' })
    wsClient.send({ action: 'tab_list' })
    setTimeout(() => setTabLoading(false), 1000)
  }, [setBrowserTabsState])

  useEffect(() => { requestStatus(); requestTabs() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function handleStart() {
    setStartLoading(true)
    wsClient.send({ action: 'browser_start' })
    setTimeout(() => { setStartLoading(false); requestStatus() }, 1500)
  }

  function handleQuit() {
    setQuitLoading(true)
    wsClient.send({ action: 'browser_quit' })
    setTimeout(() => { setQuitLoading(false); requestStatus(); setBrowserTabsState({ status: 'idle', tabs: [] }) }, 1500)
  }

  function handleTabClose(tab_id: string) {
    wsClient.send({ action: 'tab_close', tab_id })
    setTimeout(() => requestTabs(), 600)
  }

  const alive = browserStatus.cdp_alive === true
  const statusLabel = alive ? '실행 중' : browserStatus.cdp_alive === false ? '정지' : '확인 필요'
  const statusColor = alive ? 'text-emerald-600' : 'text-red-500'

  return (
    <PanelShell title="브라우저 상태" desc="AI CDP 브라우저의 실행 상태와 탭 목록을 실시간으로 확인하고 제어합니다.">
      {/* 상태 카드 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Globe size={14} className={alive ? 'text-emerald-500' : 'text-zinc-400'} />
          <span className={`text-[13px] font-semibold ${statusColor}`}>{statusLabel}</span>
          {browserStatus.tab_count !== undefined && (
            <span className="text-[11px] text-zinc-400 ml-1">탭 {browserStatus.tab_count}개</span>
          )}
          {browserStatus.message_ko && (
            <span className="text-[11px] text-zinc-400 ml-2">{browserStatus.message_ko}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={requestStatus}
            disabled={statusLoading}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-zinc-200 bg-white text-[11px] text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={11} className={statusLoading ? 'animate-spin' : ''} />
            새로고침
          </button>
          <button
            onClick={handleStart}
            disabled={startLoading || alive}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500 text-white text-[11px] hover:bg-emerald-600 disabled:opacity-40 transition-colors"
          >
            {startLoading ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            시작
          </button>
          <button
            onClick={handleQuit}
            disabled={quitLoading || !alive}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-red-500 text-white text-[11px] hover:bg-red-600 disabled:opacity-40 transition-colors"
          >
            {quitLoading ? <Loader2 size={11} className="animate-spin" /> : <Square size={11} />}
            종료
          </button>
        </div>
      </div>

      {browserStatus.error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-100 text-[12px] text-red-600 mb-3">
          <AlertCircle size={13} /> {browserStatus.error}
        </div>
      )}

      {lastTs > 0 && (
        <p className="text-[11px] text-zinc-400 mb-4">마지막 조회: {new Date(lastTs).toLocaleTimeString('ko')}</p>
      )}

      {/* 탭 목록 */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-semibold text-zinc-700">열린 탭</span>
        <button
          onClick={requestTabs}
          disabled={tabLoading}
          className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-zinc-500 hover:bg-zinc-100 disabled:opacity-40 transition-colors"
        >
          <RefreshCw size={10} className={tabLoading ? 'animate-spin' : ''} /> 새로고침
        </button>
      </div>

      {browserTabsState.status === 'loading' && (
        <div className="flex items-center gap-2 text-[12px] text-zinc-400 py-3">
          <Loader2 size={13} className="animate-spin" /> 탭 목록 로딩 중…
        </div>
      )}
      {browserTabsState.status === 'done' && browserTabsState.tabs.length === 0 && (
        <EmptyState title="열린 탭 없음" desc="브라우저를 시작하거나 탭 목록을 새로고침하세요." />
      )}
      {browserTabsState.tabs.length > 0 && (
        <div className="space-y-1.5">
          {browserTabsState.tabs.map(tab => (
            <div
              key={tab.tab_id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-100 bg-white hover:bg-zinc-50 group"
            >
              <Globe size={12} className="text-zinc-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-zinc-800 truncate">{tab.title || '(제목 없음)'}</div>
                <div className="text-[10px] text-zinc-400 truncate">{tab.url}</div>
              </div>
              <button
                onClick={() => handleTabClose(tab.tab_id)}
                className="opacity-0 group-hover:opacity-100 flex items-center justify-center w-5 h-5 rounded text-zinc-400 hover:text-red-500 hover:bg-red-50 transition-all"
                title="탭 닫기"
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── Login Watcher ── */}
      <div className="mt-6 border-t border-zinc-100 pt-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold text-zinc-700">로그인 감시</span>
            <span className={cn(
              'text-[10px] px-1.5 py-0.5 rounded-full font-semibold',
              loginWatcherState.running
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-zinc-100 text-zinc-500'
            )}>
              {loginWatcherState.running ? '● 실행 중' : '○ 정지'}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={clearLoginWatcherEvents}
              className="px-2 py-1 rounded text-[11px] text-zinc-400 hover:bg-zinc-100 transition-colors"
            >
              초기화
            </button>
            {loginWatcherState.running ? (
              <button
                onClick={() => { setLoginWatcherRunning(false); wsClient.send({ action: 'login_watcher_stop' }) }}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-zinc-200 text-zinc-700 text-[11px] hover:bg-zinc-300 transition-colors"
              >
                <Square size={10} /> 감시 중지
              </button>
            ) : (
              <button
                onClick={() => { wsClient.send({ action: 'login_watcher_start' }) }}
                disabled={!alive}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-violet-500 text-white text-[11px] hover:bg-violet-600 disabled:opacity-40 transition-colors"
              >
                <Play size={10} /> 감시 시작
              </button>
            )}
          </div>
        </div>

        {/* 로그인 상태 현황 */}
        {Object.keys(loginWatcherState.loginStates).length > 0 && (
          <div className="mb-3 space-y-1">
            {Object.entries(loginWatcherState.loginStates).map(([tid, state]) => {
              const meta = LOGIN_STATE_LABELS[state] ?? { label: state, color: 'text-zinc-500' }
              const tab = browserTabsState.tabs.find(t => t.tab_id === tid)
              return (
                <div key={tid} className="flex items-center gap-2 px-2 py-1 rounded bg-zinc-50 text-[11px]">
                  <span className={`font-semibold ${meta.color}`}>{meta.label}</span>
                  <span className="text-zinc-500 truncate flex-1">{tab?.title || tab?.url || tid}</span>
                </div>
              )
            })}
          </div>
        )}

        {/* 이벤트 로그 */}
        {loginWatcherState.events.length === 0 ? (
          <p className="text-[11px] text-zinc-400 py-2">
            {loginWatcherState.running ? '이벤트 대기 중…' : '감시를 시작하면 브라우저 탭 변경과 로그인 상태를 실시간으로 수신합니다.'}
          </p>
        ) : (
          <div className="space-y-0.5 max-h-48 overflow-y-auto scrollbar-thin">
            {[...loginWatcherState.events].reverse().map((ev, i) => {
              const meta = EVT_LABELS[ev.type] ?? { label: ev.type, color: 'text-zinc-500' }
              const stateVal = ev.type === 'login_state_changed'
                ? (ev.extra as Record<string, string>)?.state ?? ''
                : ''
              const stateMeta = stateVal ? (LOGIN_STATE_LABELS[stateVal] ?? { label: stateVal, color: 'text-zinc-500' }) : null
              return (
                <div key={i} className="flex items-start gap-2 px-2 py-1 rounded hover:bg-zinc-50 text-[11px]">
                  <span className="text-zinc-300 flex-shrink-0 font-mono">
                    {new Date(ev.ts * 1000).toLocaleTimeString('ko')}
                  </span>
                  <span className={`font-semibold flex-shrink-0 ${meta.color}`}>{meta.label}</span>
                  {stateMeta && (
                    <span className={`flex-shrink-0 ${stateMeta.color}`}>[{stateMeta.label}]</span>
                  )}
                  <span className="text-zinc-500 truncate">{ev.title || ev.sanitized_url}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="mt-4">
        <HelpNote>CDP 브라우저는 화면에 표시되지 않으며, AI가 자동으로 조작합니다. 작업 완료 시 대화창으로 결과를 보고합니다.</HelpNote>
      </div>
    </PanelShell>
  )
}

// ── 스크린샷 ──────────────────────────────────────────────────────────────────
export function ScreenshotPanel() {
  const { screenshotState, setScreenshotState } = useAppStore()

  const requestScreenshot = useCallback(() => {
    setScreenshotState({ status: 'loading', error: '' })
    wsClient.send({ action: 'screenshot' })
  }, [setScreenshotState])

  useEffect(() => { requestScreenshot() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const { status, data, format, error, ts } = screenshotState

  return (
    <div className="flex flex-col h-full bg-[#FAFAFA]">
      <div className="flex items-center justify-between px-8 py-5 border-b border-zinc-200 flex-shrink-0">
        <div>
          <h2 className="text-[17px] font-bold text-zinc-900 mb-0.5">스크린샷</h2>
          <p className="text-[12px] text-zinc-400">
            {ts ? `마지막 캡처: ${new Date(ts).toLocaleTimeString('ko')}` : 'AI 브라우저 현재 화면'}
          </p>
        </div>
        <button
          onClick={requestScreenshot}
          disabled={status === 'loading'}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 bg-white text-[12px] text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 transition-colors"
        >
          {status === 'loading'
            ? <Loader2 size={12} className="animate-spin" />
            : <Camera size={12} />
          }
          캡처
        </button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {status === 'idle' && (
          <EmptyState title="캡처된 이미지가 없습니다" desc="캡처 버튼을 누르거나 브라우저가 실행 중인지 확인하세요." />
        )}
        {status === 'loading' && (
          <div className="flex items-center justify-center h-64 gap-2 text-[13px] text-zinc-400">
            <Loader2 size={16} className="animate-spin" /> 스크린샷 캡처 중…
          </div>
        )}
        {status === 'error' && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <AlertCircle size={32} className="text-red-400" />
            <p className="text-[13px] text-red-500 text-center max-w-xs">{error || '캡처 실패'}</p>
            <button
              onClick={requestScreenshot}
              className="px-3 py-1.5 rounded-lg bg-zinc-100 text-zinc-600 text-[12px] hover:bg-zinc-200 transition-colors"
            >
              다시 시도
            </button>
          </div>
        )}
        {status === 'done' && data && (
          <div className="flex flex-col items-center gap-3">
            <img
              src={`data:image/${format};base64,${data}`}
              alt="브라우저 스크린샷"
              className="max-w-full rounded-lg border border-zinc-200 shadow-sm"
              style={{ maxHeight: 'calc(100vh - 240px)' }}
            />
            <p className="text-[11px] text-zinc-400">
              캡처 시각: {ts ? new Date(ts).toLocaleTimeString('ko') : '—'}
            </p>
          </div>
        )}
        {status === 'done' && !data && (
          <EmptyState title="이미지 데이터 없음" desc="브라우저가 실행 중인지 확인하세요." />
        )}
      </div>
    </div>
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

// ── 로컬 AI 에이전트 ──────────────────────────────────────────────────────────

type AgentProvider = '서버 AI' | '로컬 AI'
type RunStatus = 'idle' | 'running' | 'done' | 'error'

export function LocalAgentPanel() {
  const [provider, setProvider] = useState<AgentProvider>('서버 AI')
  const [prompt, setPrompt] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-5')
  const [useMcp, setUseMcp] = useState(true)
  const [status, setStatus] = useState<RunStatus>('idle')
  const [result, setResult] = useState('')
  const [providerInfo, setProviderInfo] = useState('')
  const [health, setHealth] = useState<LocalAgentHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(false)

  // 로컬 AI health 조회
  async function loadHealth() {
    setHealthLoading(true)
    try {
      const h = await localAgentApi.health()
      setHealth(h)
    } catch {
      setHealth(null)
    } finally {
      setHealthLoading(false)
    }
  }

  useEffect(() => { loadHealth() }, [])

  async function handleRun() {
    if (!prompt.trim()) return
    setStatus('running')
    setResult('')
    setProviderInfo('')

    try {
      if (provider === '로컬 AI') {
        // 로컬 AI: local_server(8765)/local-agent/run
        const res = await localAgentApi.run({ prompt: prompt.trim(), model, use_mcp: useMcp })
        setResult(res.result)
        setProviderInfo(`provider: ${res.provider} | model: ${res.model}`)
        setStatus(res.ok ? 'done' : 'error')
      } else {
        // 서버 AI: /api/v1/agent/run (프록시 → cad.haehan-ai.kr)
        const res = await fetch('http://127.0.0.1:8765/api/v1/agent/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: prompt.trim(), model }),
        })
        const data = await res.json()
        setResult(data.result ?? data.detail ?? JSON.stringify(data))
        setProviderInfo(`provider: 서버 AI | model: ${model}`)
        setStatus(res.ok ? 'done' : 'error')
      }
    } catch (e: unknown) {
      setResult(`요청 실패: ${e instanceof Error ? e.message : String(e)}`)
      setStatus('error')
    }
  }

  function handleReset() {
    setStatus('idle')
    setResult('')
    setProviderInfo('')
    setPrompt('')
  }

  const isBusy = status === 'running'

  return (
    <PanelShell title="로컬 AI 에이전트" desc="로컬 AI(Anthropic SDK + MCP) 또는 서버 AI를 선택하여 CAD 물량산출 에이전트를 실행합니다.">
      <div className="space-y-5">

        {/* provider 선택 */}
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">실행 위치</p>
          <div className="flex gap-2">
            {(['서버 AI', '로컬 AI'] as AgentProvider[]).map(p => (
              <button
                key={p}
                onClick={() => setProvider(p)}
                className={cn(
                  'flex items-center gap-1.5 px-4 py-2 rounded-lg border text-[13px] font-semibold transition-colors',
                  provider === p
                    ? 'bg-[#f97316] text-white border-[#f97316]'
                    : 'bg-white text-zinc-600 border-zinc-200 hover:bg-zinc-50'
                )}
              >
                {p === '로컬 AI' ? <Cpu size={14} /> : <Bot size={14} />}
                {p}
              </button>
            ))}
          </div>
          {provider === '로컬 AI' && (
            <div className="mt-2">
              {healthLoading ? (
                <p className="text-[11px] text-zinc-400">상태 확인 중…</p>
              ) : health ? (
                <div className="flex flex-wrap gap-2 mt-1">
                  <span className={cn('text-[10px] px-2 py-0.5 rounded border font-semibold',
                    health.available ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-red-50 text-red-600 border-red-200'
                  )}>
                    {health.available ? '로컬 AI 가용' : '로컬 AI 불가'}
                  </span>
                  {health.anthropic_sdk && <span className="text-[10px] px-2 py-0.5 rounded border bg-zinc-50 text-zinc-600 border-zinc-200">Anthropic SDK</span>}
                  {health.api_key_set && <span className="text-[10px] px-2 py-0.5 rounded border bg-zinc-50 text-zinc-600 border-zinc-200">API Key 설정됨</span>}
                  {health.claude_cli && <span className="text-[10px] px-2 py-0.5 rounded border bg-zinc-50 text-zinc-600 border-zinc-200">Claude CLI</span>}
                  {health.mcp_server_found && <span className="text-[10px] px-2 py-0.5 rounded border bg-zinc-50 text-zinc-600 border-zinc-200">MCP 서버 발견</span>}
                </div>
              ) : (
                <p className="text-[11px] text-red-500">로컬 서버(8765) 미연결</p>
              )}
              {/* MCP 사용 토글 */}
              <label className="flex items-center gap-2 mt-2 cursor-pointer w-fit">
                <input type="checkbox" checked={useMcp} onChange={e => setUseMcp(e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-zinc-300 accent-[#f97316]" />
                <span className="text-[12px] text-zinc-600">CAD MCP 서버 연결</span>
              </label>
            </div>
          )}
        </div>

        {/* 모델 선택 */}
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">모델</label>
          <select
            value={model} onChange={e => setModel(e.target.value)}
            className="w-full max-w-xs border border-zinc-200 rounded-lg px-3 py-2 text-[13px] text-zinc-900 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30"
          >
            <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
            <option value="claude-opus-4-5">claude-opus-4-5</option>
            <option value="claude-haiku-4-5">claude-haiku-4-5</option>
          </select>
        </div>

        {/* 프롬프트 입력 */}
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-widest text-zinc-400 mb-2">프롬프트</label>
          <textarea
            value={prompt} onChange={e => setPrompt(e.target.value)}
            placeholder={"CAD 물량산출 작업을 입력하세요.\n예: 서부청소년 프로젝트 현재 상태 확인해줘"}
            rows={5}
            disabled={isBusy}
            className="w-full border border-zinc-200 rounded-lg px-3 py-2.5 text-[13px] text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-[#f97316]/30 resize-y disabled:bg-zinc-50"
          />
        </div>

        {/* 실행 버튼 */}
        {(status === 'idle' || status === 'error') && (
          <button
            onClick={handleRun}
            disabled={!prompt.trim()}
            className="w-full py-2.5 rounded-lg bg-[#f97316] text-white text-[13px] font-semibold hover:bg-[#ea580c] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {provider} 실행
          </button>
        )}

        {/* 실행 중 */}
        {isBusy && (
          <div className="flex items-center gap-3 py-4">
            <RefreshCw size={16} className="animate-spin text-[#f97316]" />
            <span className="text-[13px] text-zinc-600">{provider} 처리 중… (최대 120초)</span>
          </div>
        )}

        {/* 결과 */}
        {(status === 'done' || status === 'error') && (
          <div className={cn('rounded-lg border p-4 space-y-2',
            status === 'done' ? 'bg-zinc-50 border-zinc-200' : 'bg-red-50 border-red-200'
          )}>
            <div className="flex items-center justify-between">
              <p className={cn('text-[11px] font-semibold',
                status === 'done' ? 'text-zinc-500' : 'text-red-600'
              )}>
                {status === 'done' ? '실행 완료' : '오류 발생'}
                {providerInfo && ` — ${providerInfo}`}
              </p>
              <button onClick={handleReset}
                className="text-[11px] text-zinc-400 underline hover:text-zinc-600">
                초기화
              </button>
            </div>
            <pre className="whitespace-pre-wrap text-[12px] text-zinc-800 font-mono leading-relaxed max-h-96 overflow-y-auto scrollbar-thin">
              {result}
            </pre>
          </div>
        )}

      </div>
    </PanelShell>
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

// ── 카페 목록 / 게시글 조회 ───────────────────────────────────────────────────
export function CafeListPanel() {
  const { cafeListState, cafePostsState, cafeReadState } = useAppStore()
  const [selectedCafe, setSelectedCafe] = useState<{ name: string; url: string } | null>(null)
  const [selectedPost, setSelectedPost] = useState<{ title: string; link: string } | null>(null)

  function loadCafes() {
    useAppStore.getState().setCafeListState({ status: 'loading', cafes: [], error: '' })
    wsClient.send({ action: 'naver_cafe_list' })
  }
  function loadPosts(url: string) {
    useAppStore.getState().setCafePostsState({ status: 'loading', cafe_url: url, posts: [], error: '' })
    wsClient.send({ action: 'naver_cafe_posts', cafe_url: url })
  }
  function readPost(link: string, title: string) {
    setSelectedPost({ title, link })
    useAppStore.getState().setCafeReadState({ status: 'loading', post: null, error: '' })
    wsClient.send({ action: 'naver_cafe_read', post_url: link })
  }

  return (
    <PanelShell title="카페 목록" desc="내가 가입한 네이버 카페 목록과 게시글을 조회합니다.">
      <div className="space-y-5">

        {/* 카페 목록 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">내 카페</span>
            <button onClick={loadCafes} disabled={cafeListState.status === 'loading'}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#F97316] text-white text-[11px] font-semibold hover:bg-[#ea580c] disabled:opacity-40 transition-colors">
              <RefreshCw size={11} className={cafeListState.status === 'loading' ? 'animate-spin' : ''} />
              {cafeListState.status === 'loading' ? '조회 중…' : '카페 목록 가져오기'}
            </button>
          </div>
          {cafeListState.status === 'error' && <p className="text-[12px] text-red-500">{cafeListState.error}</p>}
          {cafeListState.cafes.length > 0 && (
            <div className="grid grid-cols-2 gap-1.5">
              {cafeListState.cafes.map(c => (
                <button key={c.cafe_id}
                  onClick={() => { setSelectedCafe({ name: c.name, url: c.url }); setSelectedPost(null); loadPosts(c.url) }}
                  className={cn(
                    'text-left px-3 py-2 rounded-lg border text-[12px] transition-colors',
                    selectedCafe?.url === c.url
                      ? 'border-[#F97316] bg-orange-50 text-[#F97316] font-semibold'
                      : 'border-zinc-200 hover:bg-zinc-50 text-zinc-700'
                  )}>
                  <div className="font-medium truncate">{c.name}</div>
                  <div className="text-[10px] text-zinc-400 truncate">{c.cafe_id}</div>
                </button>
              ))}
            </div>
          )}
          {cafeListState.status === 'idle' && cafeListState.cafes.length === 0 && (
            <EmptyState title="조회 버튼을 클릭하세요" desc="네이버에 로그인된 브라우저에서 내 카페 목록을 가져옵니다." />
          )}
        </div>

        {/* 게시글 목록 */}
        {selectedCafe && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-widest text-zinc-400">{selectedCafe.name} 최근 글</span>
              <button onClick={() => loadPosts(selectedCafe.url)} disabled={cafePostsState.status === 'loading'}
                className="flex items-center gap-1 px-2 py-1 rounded text-[11px] text-zinc-500 hover:bg-zinc-100 disabled:opacity-40">
                <RefreshCw size={10} className={cafePostsState.status === 'loading' ? 'animate-spin' : ''} />새로고침
              </button>
            </div>
            {cafePostsState.status === 'loading' && (
              <div className="flex items-center gap-2 py-3 text-zinc-400 text-[12px]"><RefreshCw size={13} className="animate-spin" />게시글 로딩 중…</div>
            )}
            {cafePostsState.posts.length > 0 && (
              <div className="divide-y divide-zinc-100 border border-zinc-200 rounded-lg overflow-hidden">
                {cafePostsState.posts.map((p, i) => (
                  <button key={i} onClick={() => readPost(p.link, p.title)}
                    className="flex items-start gap-2 w-full px-3 py-2 hover:bg-zinc-50 text-left transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="text-[12.5px] text-zinc-900 font-medium truncate">{p.title}</div>
                      <div className="text-[10px] text-zinc-400">{p.author} · {p.date}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
            {cafePostsState.status === 'error' && <p className="text-[12px] text-red-500">{cafePostsState.error}</p>}
          </div>
        )}

        {/* 글 본문 */}
        {selectedPost && (
          <div className="border border-zinc-200 rounded-lg overflow-hidden">
            <div className="px-4 py-2.5 bg-zinc-50 border-b border-zinc-200 flex items-center justify-between">
              <span className="text-[12px] font-semibold text-zinc-700 truncate flex-1">{selectedPost.title}</span>
              <button onClick={() => setSelectedPost(null)} className="ml-2 text-[11px] text-zinc-400 hover:text-zinc-600 flex-shrink-0">✕</button>
            </div>
            {cafeReadState.status === 'loading' && (
              <div className="flex items-center gap-2 p-4 text-zinc-400 text-[12px]"><RefreshCw size={13} className="animate-spin" />본문 로딩 중…</div>
            )}
            {cafeReadState.post && cafeReadState.status === 'done' && (
              <div className="px-4 py-3 space-y-2">
                <div className="text-[11px] text-zinc-400">{cafeReadState.post.author} · {cafeReadState.post.date} · 댓글 {cafeReadState.post.comment_count}개</div>
                <p className="text-[12.5px] text-zinc-700 leading-relaxed whitespace-pre-wrap">{cafeReadState.post.body || '(본문 없음)'}</p>
              </div>
            )}
            {cafeReadState.status === 'error' && <p className="px-4 py-3 text-[12px] text-red-500">{cafeReadState.error}</p>}
          </div>
        )}
      </div>
    </PanelShell>
  )
}

// ── EUM 대시보드 ──────────────────────────────────────────────────────────────
export function EumDashboardPanel() {
  return (
    <PanelShell title="EUM 대시보드" desc="건설근로자공제회 단말기 업무 분석 및 홍보 메일 초안을 생성합니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          'EUM 업무 현황 분석해줘',
          '통신단절 단말기 조치 목록 알려줘',
          '신규 현장 홍보 메일 초안 만들어줘',
          '임대 종료 예정 현장 알려줘',
        ]} />
        <HelpNote>eum_business_dashboard.py 분석 결과를 AI가 해석하여 답변합니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 나라장터 G2B ──────────────────────────────────────────────────────────────
export function G2bPanel() {
  return (
    <PanelShell title="나라장터" desc="조달청 나라장터(G2B) 입찰공고 조회 및 다운로드 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '오늘 전기 입찰공고 조회해줘',
          '통신 관련 공고 검색해줘',
          '입찰공고 첨부파일 다운로드해줘',
          '최근 낙찰 결과 알려줘',
        ]} />
        <HelpNote>입찰·전자서명·투찰은 AI가 자동 실행하지 않습니다. 조회 전용입니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 가비아 ────────────────────────────────────────────────────────────────────
export function GabiaPanel() {
  return (
    <PanelShell title="가비아" desc="가비아 도메인 현황 조회 및 관리 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '도메인 만료일 확인해줘',
          '등록된 도메인 목록 보여줘',
          'DNS 설정 현황 알려줘',
        ]} />
        <HelpNote>도메인 이전·결제는 AI가 자동 실행하지 않습니다. 조회 전용입니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 히웍스 메일 ───────────────────────────────────────────────────────────────
export function HiworksMailPanel() {
  return (
    <PanelShell title="히웍스 메일" desc="히웍스 업무 메일 조회 및 발송 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '오늘 받은 메일 요약해줘',
          '미확인 메일 알려줘',
          '○○에게 메일 초안 작성해줘',
          '메일 수신함 검색: 키워드',
        ]} />
        <HelpNote>메일 발송 전에는 반드시 AI가 내용을 보여주고 사용자 승인을 받습니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 히웍스 캘린더 ─────────────────────────────────────────────────────────────
export function HiworksCalPanel() {
  return (
    <PanelShell title="히웍스 캘린더" desc="히웍스 일정 조회 및 등록 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '이번 주 일정 알려줘',
          '다음 주 회의 일정 보여줘',
          '일정 추가해줘: 6월 1일 오후 2시 팀 회의',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── Gmail ─────────────────────────────────────────────────────────────────────
export function GmailPanel() {
  return (
    <PanelShell title="Gmail" desc="Gmail 수신함 조회 및 메일 작성 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '오늘 Gmail 확인해줘',
          '미읽음 메일 요약해줘',
          '○○에게 Gmail 답장 초안 작성해줘',
        ]} />
        <HelpNote>발송 전에는 반드시 사용자 승인을 받습니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── Google Drive ──────────────────────────────────────────────────────────────
export function GdrivePanel() {
  return (
    <PanelShell title="Google Drive" desc="Google Drive 파일 목록 조회 및 업로드 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '드라이브 최근 파일 보여줘',
          '○○ 폴더 목록 알려줘',
          '파일 검색: 키워드',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── Google Sheets ─────────────────────────────────────────────────────────────
export function GsheetsPanel() {
  return (
    <PanelShell title="Google Sheets" desc="Google 스프레드시트 데이터 조회 및 업데이트 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '○○ 시트 데이터 가져와줘',
          '스프레드시트 특정 셀 값 알려줘',
          '시트에 데이터 추가해줘',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── Google Calendar ───────────────────────────────────────────────────────────
export function GcalendarPanel() {
  return (
    <PanelShell title="Google Calendar" desc="Google 캘린더 일정 조회 및 등록 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '이번 주 구글 캘린더 일정 알려줘',
          '일정 추가: 내일 오전 10시 미팅',
          '이번 달 전체 일정 요약해줘',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── Google Docs ───────────────────────────────────────────────────────────────
export function GdocsPanel() {
  return (
    <PanelShell title="Google Docs" desc="Google 문서 조회 및 편집 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '최근 Google Docs 목록 보여줘',
          '○○ 문서 내용 요약해줘',
          '문서에 내용 추가해줘',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── 네이버 메일 ───────────────────────────────────────────────────────────────
export function NaverMailPanel() {
  return (
    <PanelShell title="네이버 메일" desc="네이버 메일 수신함 조회 및 발송 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '오늘 네이버 메일 확인해줘',
          '미읽음 메일 요약해줘',
          '○○에게 네이버 메일 초안 작성해줘',
        ]} />
        <HelpNote>발송 전에는 반드시 사용자 승인을 받습니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 유튜브 ────────────────────────────────────────────────────────────────────
export function YoutubePanel() {
  return (
    <PanelShell title="유튜브" desc="유튜브 채널 관리 및 동영상 업로드 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '채널 최근 동영상 목록 보여줘',
          '동영상 업로드 준비해줘',
          '채널 통계 알려줘',
        ]} />
        <HelpNote>업로드 전에는 반드시 사용자 승인을 받습니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 스마트스토어 ──────────────────────────────────────────────────────────────
export function SmartstorePanel() {
  return (
    <PanelShell title="스마트스토어" desc="네이버 스마트스토어 주문·재고·상품 관리 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '오늘 주문 현황 알려줘',
          '미처리 주문 목록 보여줘',
          '재고 부족 상품 알려줘',
          '상품 정보 수정해줘',
        ]} />
      </HelpSection>
    </PanelShell>
  )
}

// ── 카카오 ────────────────────────────────────────────────────────────────────
export function KakaoPanel() {
  return (
    <PanelShell title="카카오" desc="카카오 개발자 콘솔 및 카카오톡 채널 관리 자동화입니다.">
      <HelpSection>
        <HelpTitle>사용 방법</HelpTitle>
        <HelpList items={[
          '카카오 앱 현황 확인해줘',
          '카카오톡 채널 메시지 발송 초안 만들어줘',
          'API 키 현황 알려줘',
        ]} />
        <HelpNote>메시지 발송 전에는 반드시 사용자 승인을 받습니다.</HelpNote>
      </HelpSection>
    </PanelShell>
  )
}

// ── 원격 접속 설정 ────────────────────────────────────────────────────────────
export function RemoteAccessPanel() {
  const [info, setInfo] = useState<{enabled?: boolean; token_masked?: string} | null>(null)
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('http://127.0.0.1:8765/remote/status')
      if (r.ok) setInfo(await r.json())
    } catch { setInfo(null) } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  return (
    <PanelShell title="원격 접속" desc="외부 네트워크에서 이 PC에 원격으로 접속하기 위한 설정입니다.">
      <div className="space-y-4">
        {info ? (
          <StatusCard rows={[
            { label: '원격 접속', value: info.enabled ? '활성화됨' : '비활성화', id: 'ra-enabled' },
            { label: '토큰',      value: info.token_masked || '—',               id: 'ra-token' },
          ]} />
        ) : (
          <p className="text-[13px] text-zinc-400">{loading ? '로딩 중…' : '로컬 서버 미연결'}</p>
        )}
        <HelpSection>
          <HelpTitle>원격 접속 활성화 방법</HelpTitle>
          <HelpList items={[
            '트레이 아이콘 우클릭 → 원격 접속 활성화',
            '활성화 후 토큰을 원격 클라이언트에 입력',
            '허용 명령: ping, get_status, get_logs_tail, get_screenshot, open_url',
          ]} />
          <HelpNote>원격 접속은 Bearer 토큰 인증 방식입니다. 토큰은 트레이 메뉴에서 재발급할 수 있습니다.</HelpNote>
        </HelpSection>
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
