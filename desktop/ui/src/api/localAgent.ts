/**
 * 로컬 AI Agent API 클라이언트
 *
 * local_server(8765) 의 /local-agent/* 엔드포인트를 호출합니다.
 * 서버 AI (/api/v1/agent/run) 와 병렬로 사용할 수 있는 로컬 실행 경로입니다.
 */

const LOCAL_SERVER = 'http://127.0.0.1:8765'

// ── 타입 정의 ─────────────────────────────────────────────────────────────────

export interface LocalAgentRequest {
  /** 에이전트에게 전달할 프롬프트 */
  prompt: string
  /** Claude 모델 ID (기본: claude-sonnet-4-5) */
  model?: string
  /** MCP 서버 연결 여부 (기본: true) */
  use_mcp?: boolean
}

export interface LocalAgentResponse {
  ok: boolean
  result: string
  provider: 'anthropic_sdk' | 'claude_code_cli' | 'error'
  model: string
  tool_calls: number
}

export interface LocalAgentHealth {
  available: boolean
  anthropic_sdk: boolean
  api_key_set: boolean
  claude_cli: boolean
  mcp_server_found: boolean
  mcp_server_path: string | null
}

// ── API 클라이언트 ────────────────────────────────────────────────────────────

export const localAgentApi = {
  /**
   * 로컬 AI + 로컬 MCP로 에이전트 실행
   *
   * @param req - 프롬프트, 모델, MCP 사용 여부
   * @returns 에이전트 응답 (result 텍스트, provider, ok 여부)
   */
  async run(req: LocalAgentRequest): Promise<LocalAgentResponse> {
    const resp = await fetch(`${LOCAL_SERVER}/local-agent/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    })
    if (!resp.ok && resp.status !== 500) {
      throw new Error(`로컬 에이전트 요청 실패: HTTP ${resp.status}`)
    }
    return resp.json() as Promise<LocalAgentResponse>
  },

  /**
   * 로컬 AI 가용 여부 확인
   *
   * @returns health 정보 (API 키 설정 여부, MCP 경로, CLI 가용 여부 등)
   */
  async health(): Promise<LocalAgentHealth> {
    const resp = await fetch(`${LOCAL_SERVER}/local-agent/health`)
    if (!resp.ok) {
      throw new Error(`로컬 에이전트 health 확인 실패: HTTP ${resp.status}`)
    }
    return resp.json() as Promise<LocalAgentHealth>
  },
}
