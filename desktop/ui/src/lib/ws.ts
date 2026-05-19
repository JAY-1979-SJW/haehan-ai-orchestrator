export type WsMessage =
  | { type: 'menu'; items: MenuItem[] }
  | { type: 'menu_saved' }
  | { type: 'chat'; role: 'user' | 'assistant' | 'system'; text: string; ts?: number }
  | { type: 'system'; text: string }
  | { type: 'task'; task_id: string; action_type: string; domain?: string; risk_level: string; description?: string; needs_approval?: boolean; execution_location?: string; status?: string; ts?: number }
  | { type: 'browser_status'; port?: string; url?: string; state?: string; active?: boolean }

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
