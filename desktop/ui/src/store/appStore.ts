import { create } from 'zustand'
import type { MenuItem, WsMessage } from '@/lib/ws'

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
  port?: string
  url?: string
  state?: string
  active?: boolean
}

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
  badgeApproval: number
  badgeTask: number

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
  handleWsMessage: (msg: WsMessage) => void
}

const DEFAULT_MENU: MenuItem[] = [
  // AI 대화
  { id: 'chat',             label: '대화',         icon: '💬', section: 'AI 대화',   visible: true,  min_role: 'any' },
  { id: 'task_queue',       label: '작업 큐',       icon: '📋', section: 'AI 대화',   visible: true,  min_role: 'any' },
  { id: 'approval',         label: '승인 대기',     icon: '✅', section: 'AI 대화',   visible: true,  min_role: 'any' },
  // 업무 조회
  { id: 'news',             label: '뉴스',          icon: '📰', section: '업무 조회', visible: true,  min_role: 'any' },
  { id: 'eum',              label: 'EUM 단말기',    icon: '🏗️', section: '업무 조회', visible: true,  min_role: 'admin' },
  // 관리 대시보드 (admin-web)
  { id: 'admin_dashboard',  label: '관리 대시보드', icon: '🖥️', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_ops',        label: '운영 현황',     icon: '📊', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_approvals',  label: '브라우저 승인', icon: '🔐', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_agents',     label: '로컬 에이전트', icon: '🤖', section: '관리 웹',   visible: true,  min_role: 'admin' },
  { id: 'admin_filemap',    label: '파일맵',        icon: '🗂️', section: '관리 웹',   visible: false, min_role: 'admin' },
  { id: 'admin_cad',        label: 'CAD',           icon: '📐', section: '관리 웹',   visible: false, min_role: 'admin' },
  // 시스템
  { id: 'browser',          label: '브라우저 상태', icon: '🌐', section: '시스템',    visible: true,  min_role: 'admin' },
  { id: 'screenshot',       label: '스크린샷',      icon: '📸', section: '시스템',    visible: false, min_role: 'admin' },
  { id: 'logs',             label: '로그',          icon: '📋', section: '시스템',    visible: true,  min_role: 'admin' },
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
  badgeApproval: 0,
  badgeTask: 0,

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

  handleWsMessage: (msg) => {
    const { addMessage, addTask, setMenuItems, setBrowserStatus } = get()
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
    }
  },
}))
