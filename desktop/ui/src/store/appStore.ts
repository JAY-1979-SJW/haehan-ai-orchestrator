import { create } from 'zustand'
import type { BrowserTab, MenuItem, WsMessage } from '@/lib/ws'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  ts: number
}

export interface TaskItem {
  task_id: string
  action_type: string
  domain?: string
  risk_level: string
  description?: string
  needs_approval?: boolean
  execution_location?: string
  status?: string
  ts?: number
}

export interface BrowserStatus {
  action?: string
  count?: number
  cdp_alive?: boolean
  lock_active?: boolean
  tab_count?: number
  message_ko?: string
  error?: string
  port?: string
  url?: string
  state?: string
  active?: boolean
}

export interface BrowserTabsState {
  status: 'idle' | 'loading' | 'done' | 'error'
  tabs: BrowserTab[]
  session: object | null
  error: string
  ts: number
}

export interface LoginWatcherEvent {
  type: string
  target_id: string
  sanitized_url: string
  title: string
  extra: Record<string, unknown>
  ts: number
}

export interface LoginWatcherState {
  running: boolean
  events: LoginWatcherEvent[]   // 최근 이벤트 (최대 50개)
  loginStates: Record<string, string>  // target_id → login state
}

export interface ScreenshotState {
  status: 'idle' | 'loading' | 'done' | 'error'
  data: string   // base64 PNG
  format: string
  error: string
  ts: number
}

export type BlogWriteStatus = 'idle' | 'writing' | 'awaiting_approval' | 'confirming' | 'done' | 'error'

export interface BlogState {
  status: BlogWriteStatus
  title: string
  tags: string[]
  visibility: string
  bodyPreview: string
  resultUrl: string
  error: string
}

export type CafeWriteStatus = 'idle' | 'writing' | 'awaiting_approval' | 'confirming' | 'done' | 'error'

export interface CafeState {
  status: CafeWriteStatus
  title: string
  board: string
  bodyPreview: string
  resultUrl: string
  error: string
}

export interface CafeListItem { cafe_id: string; name: string; url: string }
export interface CafePostItem { title: string; author: string; date: string; link: string }
export interface CafePost { title: string; author: string; date: string; body: string; comment_count: number; error?: string }

interface AppState {
  connected: boolean
  connecting: boolean
  panel: string
  sidebarCollapsed: boolean
  menuItems: MenuItem[]
  messages: ChatMessage[]
  tasks: TaskItem[]
  approvalTasks: TaskItem[]
  browserStatus: BrowserStatus
  browserTabsState: BrowserTabsState
  screenshotState: ScreenshotState
  loginWatcherState: LoginWatcherState
  blogState: BlogState
  cafeState: CafeState
  badgeApproval: number
  badgeTask: number
  cafeListState: { status: 'idle' | 'loading' | 'done' | 'error'; cafes: CafeListItem[]; error: string }
  cafePostsState: { status: 'idle' | 'loading' | 'done' | 'error'; cafe_url: string; posts: CafePostItem[]; error: string }
  cafeReadState: { status: 'idle' | 'loading' | 'done' | 'error'; post: CafePost | null; error: string }

  setConnected: (v: boolean) => void
  setConnecting: (v: boolean) => void
  setPanel: (id: string) => void
  setSidebarCollapsed: (v: boolean) => void
  setMenuItems: (items: MenuItem[]) => void
  addMessage: (msg: Omit<ChatMessage, 'id'>) => void
  clearMessages: () => void
  addTask: (task: TaskItem) => void
  removeTask: (id: string) => void
  setBrowserStatus: (s: BrowserStatus) => void
  setBrowserTabsState: (s: Partial<BrowserTabsState>) => void
  setScreenshotState: (s: Partial<ScreenshotState>) => void
  setLoginWatcherRunning: (v: boolean) => void
  addLoginWatcherEvent: (e: LoginWatcherEvent) => void
  clearLoginWatcherEvents: () => void
  setBlogState: (s: Partial<BlogState>) => void
  setCafeState: (s: Partial<CafeState>) => void
  setCafeListState: (s: Partial<AppState['cafeListState']>) => void
  setCafePostsState: (s: Partial<AppState['cafePostsState']>) => void
  setCafeReadState: (s: Partial<AppState['cafeReadState']>) => void
  handleWsMessage: (msg: WsMessage) => void
}

const DEFAULT_MENU: MenuItem[] = [
  // AI 대화
  { id: 'chat',            label: '대화',          icon: '💬', section: 'AI 대화',   visible: true,  min_role: 'any' },
  { id: 'task_queue',      label: '작업 큐',        icon: '📋', section: 'AI 대화',   visible: true,  min_role: 'any' },
  { id: 'approval',        label: '승인 대기',      icon: '✅', section: 'AI 대화',   visible: true,  min_role: 'any' },
  // 업무 조회
  { id: 'news',            label: '뉴스',           icon: '📰', section: '업무 조회', visible: true,  min_role: 'any' },
  { id: 'eum',             label: 'EUM 단말기',     icon: '🏗️', section: '업무 조회', visible: true,  min_role: 'admin' },
  { id: 'eum_dashboard',   label: 'EUM 대시보드',   icon: '📊', section: '업무 조회', visible: true,  min_role: 'admin' },
  { id: 'g2b',             label: '나라장터',       icon: '🏛️', section: '업무 조회', visible: true,  min_role: 'admin' },
  { id: 'gabia',           label: '가비아',         icon: '🌐', section: '업무 조회', visible: true,  min_role: 'admin' },
  // 히웍스
  { id: 'hiworks_mail',    label: '히웍스 메일',    icon: '📧', section: '히웍스',    visible: true,  min_role: 'any' },
  { id: 'hiworks_cal',     label: '히웍스 캘린더',  icon: '📅', section: '히웍스',    visible: true,  min_role: 'any' },
  // Google
  { id: 'gmail',           label: 'Gmail',          icon: '📨', section: 'Google',    visible: true,  min_role: 'any' },
  { id: 'gdrive',          label: 'Google Drive',   icon: '🗄️', section: 'Google',    visible: true,  min_role: 'any' },
  { id: 'gsheets',         label: 'Google Sheets',  icon: '🔢', section: 'Google',    visible: true,  min_role: 'any' },
  { id: 'gcalendar',       label: 'Google Calendar',icon: '🗓️', section: 'Google',    visible: true,  min_role: 'any' },
  { id: 'gdocs',           label: 'Google Docs',    icon: '📄', section: 'Google',    visible: false, min_role: 'any' },
  // 네이버
  { id: 'naver_mail',      label: '네이버 메일',    icon: '💌', section: '네이버',    visible: true,  min_role: 'any' },
  // 콘텐츠
  { id: 'blog_write',      label: '블로그 작성',    icon: '✏️', section: '콘텐츠',    visible: true,  min_role: 'any' },
  { id: 'cafe_write',      label: '카페 글쓰기',    icon: '☕', section: '콘텐츠',    visible: true,  min_role: 'any' },
  { id: 'cafe_list',       label: '카페 목록',      icon: '📋', section: '콘텐츠',    visible: true,  min_role: 'any' },
  { id: 'youtube',         label: '유튜브',         icon: '▶️', section: '콘텐츠',    visible: true,  min_role: 'any' },
  { id: 'smartstore',      label: '스마트스토어',   icon: '🛒', section: '콘텐츠',    visible: true,  min_role: 'any' },
  { id: 'kakao',           label: '카카오',         icon: '💛', section: '콘텐츠',    visible: true,  min_role: 'any' },
  // 관리 웹
  { id: 'admin_dashboard', label: '관리 대시보드',  icon: '🖥️', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_ops',       label: '운영 현황',      icon: '📈', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_approvals', label: '브라우저 승인',  icon: '🔐', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_agents',    label: '로컬 에이전트',  icon: '🤖', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_filemap',   label: '파일맵',         icon: '🗂️', section: '관리 웹',   visible: false, min_role: 'admin' },
  { id: 'admin_cad',       label: 'CAD',            icon: '📐', section: '관리 웹',   visible: false, min_role: 'admin' },
  // 시스템
  { id: 'remote_access',   label: '원격 접속',      icon: '🔗', section: '시스템',    visible: true,  min_role: 'admin' },
  { id: 'browser',         label: '브라우저 상태',  icon: '🌐', section: '시스템',    visible: true,  min_role: 'admin' },
  { id: 'screenshot',      label: '스크린샷',       icon: '📸', section: '시스템',    visible: false, min_role: 'admin' },
  { id: 'logs',            label: '로그',           icon: '📜', section: '시스템',    visible: true,  min_role: 'admin' },
]

export const useAppStore = create<AppState>((set, get) => ({
  connected: false,
  connecting: true,
  panel: 'chat',
  sidebarCollapsed: localStorage.getItem('sb_collapsed') === '1',
  menuItems: DEFAULT_MENU,
  messages: [],
  tasks: [],
  approvalTasks: [],
  browserStatus: {},
  browserTabsState: { status: 'idle', tabs: [], session: null, error: '', ts: 0 },
  screenshotState: { status: 'idle', data: '', format: 'png', error: '', ts: 0 },
  loginWatcherState: { running: false, events: [], loginStates: {} },
  blogState: { status: 'idle', title: '', tags: [], visibility: 'public', bodyPreview: '', resultUrl: '', error: '' },
  cafeState: { status: 'idle', title: '', board: '', bodyPreview: '', resultUrl: '', error: '' },
  badgeApproval: 0,
  badgeTask: 0,
  cafeListState: { status: 'idle', cafes: [], error: '' },
  cafePostsState: { status: 'idle', cafe_url: '', posts: [], error: '' },
  cafeReadState: { status: 'idle', post: null, error: '' },

  setConnected: (v) => set({ connected: v, connecting: false }),
  setConnecting: (v) => set({ connecting: v }),
  setPanel: (id) => set({ panel: id }),
  setSidebarCollapsed: (v) => {
    localStorage.setItem('sb_collapsed', v ? '1' : '0')
    set({ sidebarCollapsed: v })
  },
  setMenuItems: (items) => set({ menuItems: items }),

  addMessage: (msg) => set((s) => ({
    messages: [...s.messages, { ...msg, id: crypto.randomUUID() }]
  })),
  clearMessages: () => set({ messages: [], badgeApproval: 0, badgeTask: 0 }),

  addTask: (task) => set((s) => {
    const needsApproval = task.needs_approval === true
    return {
      tasks: [...s.tasks, task],
      approvalTasks: needsApproval ? [...s.approvalTasks, task] : s.approvalTasks,
      badgeTask: s.badgeTask + 1,
      badgeApproval: needsApproval ? s.badgeApproval + 1 : s.badgeApproval,
    }
  }),
  removeTask: (id) => set((s) => ({
    tasks: s.tasks.filter(t => t.task_id !== id),
    approvalTasks: s.approvalTasks.filter(t => t.task_id !== id),
    badgeApproval: Math.max(0, s.badgeApproval - 1),
    badgeTask: Math.max(0, s.badgeTask - 1),
  })),

  setBrowserStatus: (s) => set({ browserStatus: s }),
  setBrowserTabsState: (s) => set((prev) => ({ browserTabsState: { ...prev.browserTabsState, ...s } })),
  setScreenshotState: (s) => set((prev) => ({ screenshotState: { ...prev.screenshotState, ...s } })),
  setLoginWatcherRunning: (v) => set((prev) => ({ loginWatcherState: { ...prev.loginWatcherState, running: v } })),
  addLoginWatcherEvent: (e) => set((prev) => {
    const events = [...prev.loginWatcherState.events, e].slice(-50)
    const loginStates = e.type === 'login_state_changed' && e.extra && typeof (e.extra as Record<string, unknown>).state === 'string'
      ? { ...prev.loginWatcherState.loginStates, [e.target_id]: (e.extra as Record<string, string>).state }
      : prev.loginWatcherState.loginStates
    return { loginWatcherState: { ...prev.loginWatcherState, events, loginStates } }
  }),
  clearLoginWatcherEvents: () => set((prev) => ({ loginWatcherState: { ...prev.loginWatcherState, events: [], loginStates: {} } })),
  setBlogState: (s) => set((prev) => ({ blogState: { ...prev.blogState, ...s } })),
  setCafeState: (s) => set((prev) => ({ cafeState: { ...prev.cafeState, ...s } })),
  setCafeListState: (s) => set((prev) => ({ cafeListState: { ...prev.cafeListState, ...s } })),
  setCafePostsState: (s) => set((prev) => ({ cafePostsState: { ...prev.cafePostsState, ...s } })),
  setCafeReadState: (s) => set((prev) => ({ cafeReadState: { ...prev.cafeReadState, ...s } })),

  handleWsMessage: (msg) => {
    const { addMessage, addTask, setMenuItems, setBrowserStatus, setBrowserTabsState, setScreenshotState,
            setLoginWatcherRunning, addLoginWatcherEvent,
            setBlogState, setCafeState,
            setCafeListState, setCafePostsState, setCafeReadState } = get()
    switch (msg.type) {
      case 'menu':
        if (msg.items?.length) setMenuItems(msg.items)
        break
      case 'menu_saved':
        break  // 저장 확인 — 별도 처리 불필요
      case 'chat':
        addMessage({ role: msg.role, text: msg.text, ts: msg.ts ?? Date.now() / 1000 })
        break
      case 'system':
        addMessage({ role: 'system', text: msg.text, ts: Date.now() / 1000 })
        break
      case 'task': {
        const taskItem: TaskItem = {
          task_id: msg.task_id,
          action_type: msg.action_type,
          domain: msg.domain,
          risk_level: msg.risk_level,
          description: msg.description,
          needs_approval: msg.needs_approval,
          execution_location: (msg as TaskItem).execution_location,
          status: (msg as TaskItem).status ?? '수신 대기',
          ts: (msg as TaskItem).ts,
        }
        addTask(taskItem)
        addMessage({ role: 'system', text: `새 작업 수신: ${msg.action_type}`, ts: Date.now() / 1000 })
        break
      }
      case 'browser_status':
        setBrowserStatus(msg)
        break
      case 'login_watcher_started':
        setLoginWatcherRunning(true)
        break
      case 'login_watcher_stopped':
        setLoginWatcherRunning(false)
        break
      case 'target_created':
      case 'target_closed':
      case 'target_url_changed':
      case 'target_title_changed':
      case 'auth_popup_detected':
      case 'login_state_changed':
        addLoginWatcherEvent({
          type: msg.type,
          target_id: msg.target_id,
          sanitized_url: msg.sanitized_url ?? '',
          title: msg.title ?? '',
          extra: (msg.extra as Record<string, unknown>) ?? {},
          ts: msg.ts ?? Date.now() / 1000,
        })
        break
      case 'tab_list':
        setBrowserTabsState({
          status: 'done',
          tabs: msg.tabs ?? [],
          session: msg.session ?? null,
          error: '',
          ts: Date.now(),
        })
        break
      case 'screenshot_result':
        setScreenshotState({
          status: msg.ok ? 'done' : 'error',
          data: msg.data ?? '',
          format: msg.format ?? 'png',
          error: msg.error ?? '',
          ts: Date.now(),
        })
        break
      case 'user_present_task': {
        const t = msg.task
        const item: TaskItem = {
          task_id: t.task_id,
          action_type: t.action_type,
          domain: t.domain,
          risk_level: t.risk_level,
          description: t.description,
          needs_approval: true,
          status: '사용자 확인 요청',
          ts: msg.ts,
        }
        addTask(item)
        addMessage({ role: 'system', text: `🔔 사용자 확인 요청: ${t.action_type}`, ts: Date.now() / 1000 })
        break
      }
      case 'task_blocked':
        addMessage({
          role: 'system',
          text: msg.message_ko || `작업 차단됨: ${msg.reason || '정책 위반'}`,
          ts: Date.now() / 1000,
        })
        break
      case 'blog_status':
        setBlogState({
          status: msg.status as BlogWriteStatus,
          title: msg.title ?? '',
          tags: msg.tags ?? [],
          visibility: msg.visibility ?? 'public',
          bodyPreview: msg.body_preview ?? '',
          resultUrl: msg.result_url ?? '',
          error: msg.error ?? '',
        })
        break
      case 'cafe_status':
        setCafeState({
          status: msg.status as CafeWriteStatus,
          title: msg.title ?? '',
          board: msg.board ?? '',
          bodyPreview: msg.body_preview ?? '',
          resultUrl: msg.result_url ?? '',
          error: msg.error ?? '',
        })
        break
      case 'naver_cafe_list':
        setCafeListState({
          status: msg.status === 'done' ? 'done' : msg.status === 'error' ? 'error' : 'loading',
          cafes: msg.cafes ?? [],
          error: msg.error ?? '',
        })
        break
      case 'naver_cafe_posts':
        setCafePostsState({
          status: msg.status === 'done' ? 'done' : msg.status === 'error' ? 'error' : 'loading',
          cafe_url: msg.cafe_url ?? '',
          posts: msg.posts ?? [],
          error: msg.error ?? '',
        })
        break
      case 'naver_cafe_read':
        setCafeReadState({
          status: msg.status === 'done' ? 'done' : msg.status === 'error' ? 'error' : 'loading',
          post: msg.post ?? null,
          error: msg.error ?? '',
        })
        break
    }
  },
}))
