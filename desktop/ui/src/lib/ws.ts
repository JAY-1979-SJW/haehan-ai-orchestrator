export type WsMessage =
  | { type: 'menu'; items: MenuItem[] }
  | { type: 'menu_saved' }
  | { type: 'chat'; role: 'user' | 'assistant' | 'system'; text: string; ts?: number }
  | { type: 'system'; text: string }
  | { type: 'task'; task_id: string; action_type: string; domain?: string; risk_level: string; description?: string; needs_approval?: boolean; execution_location?: string; status?: string; ts?: number }
  | { type: 'browser_status'; action?: string; count?: number; cdp_alive?: boolean; lock_active?: boolean; tab_count?: number; message_ko?: string; error?: string; port?: string; url?: string; state?: string; active?: boolean }
  | { type: 'browser_quit_result'; ok?: boolean; killed_pids?: number[]; failed_pids?: number[]; error?: string }
  | { type: 'tab_list'; tabs: BrowserTab[]; session?: object }
  | { type: 'tab_close_result'; ok: boolean; tab_id?: string; error?: string; message_ko?: string }
  | { type: 'screenshot_result'; ok: boolean; format?: string; data?: string; error?: string }
  | { type: 'login_watcher_started'; ok: boolean }
  | { type: 'login_watcher_stopped'; ok: boolean }
  | { type: 'target_created';       target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'target_closed';        target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'target_url_changed';   target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'target_title_changed'; target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'auth_popup_detected';  target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'login_state_changed';  target_id: string; sanitized_url?: string; title?: string; extra?: object; ts?: number }
  | { type: 'popup_detected';       added?: string[]; ts?: number }
  | { type: 'blog_status'; status: string; title?: string; tags?: string[]; visibility?: string; body_preview?: string; result_url?: string; error?: string }
  | { type: 'cafe_status'; status: string; title?: string; board?: string; body_preview?: string; result_url?: string; error?: string }
  | { type: 'user_present_task'; task: { task_id: string; action_type: string; domain?: string; risk_level: string; description?: string; workflow_run_id?: string }; ts?: number }
  | { type: 'task_blocked'; task_id?: string; workflow_run_id?: string; reason?: string; message_ko?: string; ts?: number }
  | { type: 'naver_cafe_list'; status: string; cafes?: { cafe_id: string; name: string; url: string }[]; error?: string }
  | { type: 'naver_cafe_posts'; status: string; cafe_url?: string; posts?: { title: string; author: string; date: string; link: string }[]; error?: string }
  | { type: 'naver_cafe_read'; status: string; post?: { title: string; author: string; date: string; body: string; comment_count: number; error?: string } | null; error?: string }

export interface BrowserTab {
  tab_id: string
  url: string
  title: string
}

export interface MenuItem {
  id: string
  label: string
  icon: string
  section: string
  visible: boolean
  min_role?: string
}

type MessageHandler = (msg: WsMessage) => void
type StatusHandler = (status: 'connected' | 'connecting' | 'disconnected') => void

class WsClient {
  private ws: WebSocket | null = null
  private ready = false
  private handlers: MessageHandler[] = []
  private statusHandlers: StatusHandler[] = []
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  connect(url = 'ws://127.0.0.1:8765/ws/ui') {
    if (this.ws) {
      this.ws.onclose = null
      this.ws.onerror = null
      this.ws.close()
    }
    this.notifyStatus('connecting')
    this.ws = new WebSocket(url)

    this.ws.onopen = () => {
      this.ready = true
      this.notifyStatus('connected')
      this.send({ action: 'load_menu', user_id: this.getUserId(), role: this.getRole() })
    }
    this.ws.onclose = () => {
      if (!this.ready) return  // onerror 이미 처리한 경우 중복 방지
      this.ready = false
      this.notifyStatus('disconnected')
      this.reconnectTimer = setTimeout(() => this.connect(url), 3000)
    }
    this.ws.onerror = () => {
      this.ready = false
      this.notifyStatus('disconnected')
      this.reconnectTimer = setTimeout(() => this.connect(url), 3000)
    }
    this.ws.onmessage = (e) => {
      try { this.handlers.forEach(h => h(JSON.parse(e.data))) } catch {}
    }
  }

  send(obj: object) {
    if (this.ready && this.ws) this.ws.send(JSON.stringify(obj))
  }

  onMessage(handler: MessageHandler) { this.handlers.push(handler) }
  onStatus(handler: StatusHandler) { this.statusHandlers.push(handler) }

  private notifyStatus(s: 'connected' | 'connecting' | 'disconnected') {
    this.statusHandlers.forEach(h => h(s))
  }
  private getUserId() { return localStorage.getItem('user_id') || 'default' }
  private getRole()   { return localStorage.getItem('user_role') || 'any' }

  reconnect(url?: string) {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.connect(url || 'ws://127.0.0.1:8765/ws/ui')
  }
}

export const wsClient = new WsClient()
