# CDP 범용 자동화 + MCP 버튼 트리거 — 기준서 + 구현 결과 (2026-09-28)

> 상태: **구현·실기 검증 완료.** 아래 §5는 최초 기준서 초안이 아니라 실제 구현 내용으로 갱신됨
> (설계 대비 달라진 지점은 각 절에 "**드라이런 대비 변경**"으로 명시).
> 범위: 앱에서 버튼을 눌렀을 때 Claude(MCP)가 실제로 작업을 수행하는 트리거 +
> 처음 방문하는 웹사이트에도 사이트별 코드 없이 자동화되는 범용 CDP 액션 계층 +
> Electron 앱 자신의 창(webview)을 CDP로 제어하는 계층(드라이런 이후 추가 범위, §5.4).
> 원칙: 기존 자산(local_agent WS 큐, Playwright CDP 연결, MCP 서버) 재사용 우선, 신규 중복 금지.

## 배경 (왜 지금 이걸 하는가)

한국은 AI 에이전트를 활발히 소비·분석하는 커뮤니티는 있지만(오픈클로 관련 국내 블로그·강좌·스레드
다수), 원조 플랫폼을 직접 만드는 사례는 드물다 — STEM 전공 학생의 창업 의향이 중국의 1/3 수준으로
낮고([Xinhua, 2026-08-10](https://english.news.cn/asiapacific/20260810/84429e9d65724d9fa84c502b814a259c/c.html)),
기업 AI 도입률은 88%로 높지만 전사 스케일 배포는 7%에 그쳐([KoreaTechDesk](https://koreatechdesk.com/korea-enterprise-ai-poc-selection-ai-agent-scaling))
"쓰기는 쓰되 직접 만들어 내놓지는 않는" 비대칭 구조다. 이 앱을 오픈클로 수준(또는 그 이상)으로
완성하는 것은 이 공백을 메우는 국내 선점 기회이기도 하다.

## 0. 요약

| 항목 | 핵심 발견 |
|---|---|
| 오픈클로(OpenClaw) 비교 | CDP 기반이지만 사이트별 코드 없이 동작하는 이유는 **접근성 트리(AXTree) 스냅샷 → ref 기반 act** 패턴 때문. 이 저장소의 현재 자동화(`scripts/naver/*` 등)는 사이트별 CSS 셀렉터 하드코딩이라 이 패턴이 없음 — 이게 실제 기술 격차 |
| MCP 트리거의 구조적 한계 | MCP 공식 스펙(2026-07-28 개정)상 서버(앱)가 유휴 상태의 클라이언트(Claude)를 능동적으로 깨우는 프리미티브는 없음(sampling조차 deprecated). "버튼→즉시 에이전트 작업"은 MCP 밖의 별도 경로(WS 큐 + 헤드리스 `claude -p` 실행)로 구현 |
| 재사용 가능한 기존 인프라 | 드라이런에서는 신규 `scripts/claude_runner_agent.py`를 상정했으나, 실제로는 **기존 `core/agent_runtime/agent.py` + `local_agent/actions.py` 액션 레지스트리**가 이미 이 용도에 정확히 맞는 인프라였음(§5.1 "드라이런 대비 변경" 참고) — 신규 스크립트도, 신규 REST 엔드포인트도 필요 없었음 |
| 구현 중 실측으로 발견·수정한 버그 2건 | (1) Electron webview용 CDP 세션의 `detach()`가 공유 websocket을 진짜로 닫아버림(§5.4), (2) 헤드리스 `claude -p`의 `--allowedTools`가 뒤따르는 토큰을 계속 삼키는 greedy 옵션이라 `--` 구분자 없이 prompt를 이어 붙이면 "prompt 없음" 오류(§5.1) — 둘 다 실행 기반 검증(ERR-04)으로만 발견 가능했던 것들 |

## 1. 요구사항

| ID | 요구사항 (사용자 발화 원문) |
|---|---|
| REQ-1 | "AI 에이전트 및 웹브라우저를 CDP로 AI를 연동해서 자동화를 하는 도구이고 또한 일렉트론 앱으로 연동해서 처리하게 하는게 목표" |
| REQ-2 | "클로드 mcp로 연결해서 사용하게 설계를 하고 싶어" |
| REQ-3 | "클로드 데스크 앱 또는 클로드 코드와 앱이 연동이 되고 앱에서 버튼을 누르면 사용자가 원하는 에이전트 작업이 되게 하는게 목표" |
| REQ-4 | "현재 앱은 나한테 맞춰진거고 오픈클로우를 조사해서 그것보다 좋게 만들고 처음 방문하는 웹사이트에도 자동화 되게 하고 싶어" |
| REQ-5 (드라이런 이후 추가) | "현재 창에서 앱을 제어하고 연결하려면 플레이 라이트가 필요하지?" → "Electron 앱 창을 말한 거야, 그것도 되게 설계해줘" — 외부 웹사이트가 아니라 **Electron 앱 자신의 창(webview)** 을 CDP로 제어 |

## 2. 근거 (공식 문서)

- **MCP 서버 주도 메시지**: `sampling/createMessage`, `elicitation/create`가 MCP가 정의한 유일한 서버 주도
  메시지. 두 문서 모두 시퀀스 다이어그램에서 "서버가 클라이언트 요청을 처리하는 도중에만" 발행되는
  것으로 명시. ([Sampling](https://modelcontextprotocol.io/specification/2025-06-18/client/sampling),
  [Elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation))
- **2026-07-28 개정(RC)**: Multi Round-Trip Requests(MRTR) 개편으로 "서버 주도 요청은 서버가 클라이언트
  요청을 실제로 처리 중일 때만 발행 가능"이라고 프로토콜 차원에서 못박음. Sampling 자체가 이 버전에서
  deprecated되고 "서버가 직접 LLM 제공자 API와 통합하라"는 가이드로 대체됨.
  ([changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx))
- **Chrome DevTools Protocol**: `Accessibility.getFullAXTree`(파라미터 `depth`/`frameId`, 반환
  `AXNode[]` — `nodeId`/`role`/`name`/`value`/`childIds`/`backendDOMNodeId`), `DOM.resolveNode`
  (`nodeId`|`backendNodeId` → `Runtime.RemoteObject.objectId`), `DOM.getBoxModel`(좌표) +
  `Input.dispatchMouseEvent`(실제 마우스 이벤트 — JS `.click()`보다 커스텀 위젯 호환성 높음).
  (chromedevtools.github.io/devtools-protocol의 Accessibility/DOM/Input 도메인 정의,
  [chromedp/cdproto 바인딩](https://pkg.go.dev/github.com/chromedp/cdproto/accessibility)으로 교차 확인)
- **Playwright**: `BrowserContext.new_cdp_session(page)`(v1.11+, 이 저장소 `requirements.txt`의
  `playwright>=1.40.0`로 충분)로 기존 Playwright `Page` 위에서 새 websocket 연결 없이 raw CDP 명령을
  보낼 수 있음. **단, `connect_over_cdp()`는 "page" 타입 CDP 타깃만 노출하고 "webview" 타입은 노출하지
  않음을 실측으로 확인**(`/json/list` 응답과 `browser.contexts[0].pages` 개수를 대조) — Electron
  webview 제어는 Playwright로 불가능해 raw websocket 클라이언트를 직접 구현(§5.4).
- **Electron**: `app.commandLine.appendSwitch("remote-debugging-port", PORT)`는 `app.whenReady()`
  이전에 호출해야 한다(code.electronjs.org/docs/latest/api/command-line-switches). `<webview>` 게스트
  콘텐츠는 별도 CDP 타깃 타입 `"webview"`로 자신의 `webSocketDebuggerUrl`을 갖는다(실측 확인).
- **Claude Code CLI 헤드리스(`-p`/`--print`)**: `--allowedTools`(공식 `--help` 표기 `<tools...>`)는
  콤마 또는 공백으로 구분한 도구 이름 문자열 하나를 받으며, 뒤따르는 인자를 계속 도구 이름으로 소비하는
  greedy 옵션이다 — `--` 로 옵션 파싱을 끊지 않으면 prompt까지 삼켜 `Input must be provided ...`
  오류가 난다(2026-09-28 실측 확인). `--dangerously-skip-permissions`(`--permission-mode
  bypassPermissions`와 동일)는 전체 권한 우회라 이 저장소의 승인 원칙에 맞지 않아 채택하지 않음 —
  `--allowedTools`로 필요한 MCP 도구만 명시적으로 허용하는 방식을 채택.
  (code.claude.com/docs/en/cli-reference, 2026-09-28 확인)
- **선례**: Google 공식 `chrome-devtools-mcp`, Microsoft 공식 `playwright-mcp`가 이미 "접근성 트리
  스냅샷 → ref/uid로 클릭·입력" 패턴을 유지보수 프로젝트로 구현·배포 중 — 오픈클로보다 더 직접적인 참고 선례.
- **오픈클로(OpenClaw, github.com/openclaw/openclaw)**: `snapshot`(ARIA 접근성 트리 기반, 결정론적)
  → `act`(스냅샷 `ref`로 클릭/입력/드래그/선택, CSS 셀렉터 아님) → `navigate` → `screenshot`(보조,
  텍스트 전용 모델일 때 vision 보강). DOM 참조 기반이 기본. 트리거는 채팅 메시지 기반이 주력이나
  cron/webhook/백그라운드 작업도 지원. MCP는 **클라이언트**로 네이티브 지원(`openclaw.json`에 설정,
  stdio+HTTP/SSE) — 자신을 MCP **서버**로 노출하는 기능은 아직 공식 미지원이고 커뮤니티 브리지
  (`freema/openclaw-mcp` 등)로만 존재, 네이티브 지원 요청 이슈(#53215)가 열려 있는 상태.

## 3. 기존 자산 (재사용, 신규 중복 금지)

| 자산 | 역할 | 처리 |
|---|---|---|
| `scripts/browser/agent/cdp.py` (`open_cdp_session`/`CDPSession.new_tab`) | 사용자 Chrome에 Playwright로 CDP 연결, 새 탭 관리 | 그대로 재사용 — 신규 계층의 진입점 |
| `ai_orchestrator/agent_hub/registry/task_queue.py` / `local_agent_registry_task_lifecycle.py` | 작업 큐 상태전이(`queued→delivered→running→completed/failed`), 이미 구현·테스트됨 | 그대로 재사용 — 버튼 트리거의 큐로 사용 |
| **`core/agent_runtime/agent.py` + `local_agent/actions.py`**(드라이런 대비 변경 — 아래 §5.1 참고) | device_token 인증 + 포맬한 액션 레지스트리로 이미 `/api/v1/local-agents/ws`에 접속하는 상시 클라이언트 | **신규 스크립트 대신 이걸 그대로 재사용.** `run_claude_agent` 액션 1개만 추가 |
| `POST /api/v1/local-agents/{agent_id}/tasks`(기존, 신규 아님 — 드라이런에서는 신규로 오판) | 특정 에이전트에 작업 적재 | 그대로 재사용 — `action: "run_claude_agent"`로 호출 |
| `ai_orchestrator/server/mcp_server.py`의 `list_api_endpoints`/`call_api` | 앱 API 전체를 MCP 도구로 범용 노출하는 기존 패턴 | 패턴 재사용 — `snapshot_page`/`act_on_page`/`navigate_page` 3종 추가 |
| `gates/approval.py` + `services/web_task_approval_service.py` | 쓰기 작업(발행/발송/삭제 등) 승인 플로우 | 그대로 유지 — 무인 파이프라인이어도 승인 없이 우회 금지 |
| Playwright(`page.goto`/`page.keyboard`/`page.mouse`/`page.screenshot`) | 이미 사이트 모듈 20개 이상이 쓰는 브라우저 제어 기반 | 그대로 재사용(웹사이트 대상). Electron webview 대상은 §5.4의 raw CDP 어댑터가 같은 인터페이스를 흉내 냄 |
| `tools/hooks/capability_check.py` | "이 도메인에 기존 구현이 있는가" 확인(CLAUDE.md 필수 절차) | 그대로 재사용 — 기존 사이트 모듈/범용 계층 분기점으로 그대로 씀 |

**명시적으로 확장하지 않은 것**: `scripts/cdp_helper.py`(및 `apps/marketing-standalone/connectors/cdp_helper.py`
중복본) — raw-websocket 레거시 경로. 이 두 파일의 중복 자체(DUP-02 조사에서 발견)는 이 기준서와 별개의
정리 과제로 남긴다(§10).

## 4. 전체 흐름 (구현된 실제 경로)

```
[admin-web 버튼 등]
        │ POST /api/v1/local-agents/{agent_id}/tasks  (기존 엔드포인트, 신규 아님)
        │ {"action": "run_claude_agent", "params": {"prompt": "...", "allowed_tools": [...]}}
        ▼
[작업 큐] ── local_agent_registry_task_queue.py (queued)
        │ 3중 게이트 통과 필요(실기로 발견): ACTION_RISK(local_agent_risk_policy.py) +
        │ AUTO_EXECUTE_VIA_AGENT(ai_orchestrator/contracts/local_agent_actions.py) +
        │ _ACTIONS 레지스트리(local_agent/actions.py) — 셋 중 하나라도 빠지면
        │ UNKNOWN_ACTION 또는 ACTION_NOT_AUTO_EXECUTABLE로 즉시 실패
        ▼ WS 푸시 (local_agent_router_ws.py 채널)
[core/agent_runtime/agent.py]  (기존 상시 클라이언트, 신규 스크립트 아님)
        │ action_run_claude_agent(params) 실행 → delivered→running
        ▼
[claude -p --mcp-config .mcp.json --output-format json --max-budget-usd N
          [--allowedTools "mcp__haehan-orchestrator__snapshot_page,..."] -- "<prompt>"]
        │ Claude Code가 MCP 클라이언트로 haehan-orchestrator에 접속
        ▼
[ai_orchestrator/server/mcp_server.py]
        ├─ 기존 도구 / list_api_endpoints / call_api
        └─ snapshot_page / act_on_page / navigate_page (target: "website" | "app")
                │                                              │
                ▼ target=website                               ▼ target=app
        [universal_actions.py] ── AXTree → ref → act    [electron_target.py 어댑터] ──
        (사용자 Chrome, CDP 9222)                        universal_actions.py를 그대로 재사용
                │                                        (Electron 자체 webview, CDP 9333)
        [기존 사이트 모듈: scripts/naver/*]  ← capability_check.py가 있다고 판단하면 이쪽 우선(빠름)
        ▼
[쓰기 작업이면] gates/approval.py + web_task_approval_service.py (기존 승인 플로우 그대로) → 사람 승인
        ▼
[결과를 task 상태 API로 보고 → completed/failed, result_data에 claude -p JSON 결과 저장]
```

## 5. 구성요소 설계 (구현 결과)

### 5.1 트리거: `run_claude_agent` 액션 (드라이런 대비 크게 변경됨)

**드라이런 대비 변경**: 당초 `scripts/claude_runner_agent.py`(신규 스크립트)와
`POST /api/v1/agent-tasks`(신규 라우터)를 상정했으나, 구현 착수 시 더 깊이 조사한 결과
`core/agent_runtime/agent.py` + `local_agent/actions.py`가 이미 device_token 인증·포맬한 액션 레지스트리로
`/api/v1/local-agents/ws`에 접속하고 있었고, `POST /api/v1/local-agents/{agent_id}/tasks`도 이미
존재했다. 신규 스크립트도 신규 REST 엔드포인트도 만들지 않고 **액션 1개(`run_claude_agent`)만
추가**하는 것으로 끝났다 — 최초 계획 대비 더 단순해진 정정 사례.

- 위치: `local_agent/actions.py::action_run_claude_agent(params)`
- params: `prompt`(필수), `timeout`(선택, 기본 300초, 30~1800 강제), `max_budget_usd`(선택, 기본 2.0,
  공식 `--max-budget-usd`로 그대로 전달, subagent 비용 포함해 초과 시 Claude Code가 스스로 중단),
  `allowed_tools`(선택, `list[str]`, 기본 빈 목록)
- 실행 커맨드: `claude -p --mcp-config .mcp.json --output-format json --max-budget-usd <n> [--allowedTools <콤마조인>] -- <prompt>`
- **실측으로 발견·수정한 버그**: 처음엔 `--allowedTools` 없이 구현 → MCP 도구 호출이 전부
  `permission_denials`로 거부됨(`claude -p`는 헤드리스에서도 도구 사용 승인이 기본값이 `default`라
  자동 허용되지 않음). 공식 문서 확인 후 `--allowedTools`를 추가했더니 이번엔 "prompt 인자가 없다"는
  새 오류 — `--allowedTools`가 `<tools...>` 표기대로 뒤 토큰을 계속 삼키는 greedy 옵션이라 prompt까지
  먹혀버린 것(실측 확인). `--` 구분자를 옵션과 prompt 사이에 넣어 해결.
  기본값은 `allowed_tools=[]` → `--allowedTools` 자체를 안 붙여 **기존처럼 MCP 도구 전부 거부**가
  유지된다 — 이 액션을 호출하는 쪽(버튼 핸들러 등)이 이번 작업에 실제 필요한 MCP 도구만 명시적으로
  골라 넣어야 한다. `--dangerously-skip-permissions`(전체 우회)는 이 프로젝트의 승인 원칙에 맞지
  않아 채택하지 않음.
- **3중 게이트**(전부 있어야 작업이 실제로 실행됨, 실기 테스트로 하나씩 발견):
  1. `ai_orchestrator/agent_hub/policy/risk_policy.py::ACTION_RISK["run_claude_agent"] = "medium"` —
     없으면 `enqueue_task()`가 `UnknownActionError`
  2. `ai_orchestrator/contracts/local_agent_actions.py::AUTO_EXECUTE_VIA_AGENT`에 `"run_claude_agent"` 포함 —
     없으면 `ACTION_NOT_AUTO_EXECUTABLE`로 실패
  3. `local_agent/actions.py::_ACTIONS["run_claude_agent"]` — 실제 실행기 매핑
- **종단 실측 검증**(모킹 없음): 작업 큐 적재 → WS 전달 → `core/agent_runtime/agent.py` 실행 →
  `claude -p` 서브프로세스 → 결과 보고까지 실제 인프라로 확인. 첫 테스트("숫자 1만 답해")는
  `allowed_tools` 없이 15초 내 `"1"` 반환. 이어서 `allowed_tools=["mcp__haehan-orchestrator__snapshot_page"]`로
  `target=app` snapshot_page를 실제 호출해 `permission_denials: []`, `result: "40개"`(Electron
  webview 노드 수와 일치)까지 확인 — 버튼 트리거→MCP 도구 사용까지 전체 경로가 실제로 동작함을 증명.
- 회귀 테스트: `tests/test_local_agent_actions_run_claude_agent.py`(5개, `--allowedTools`/`--`
  구성 자체를 subprocess 모킹으로 검사 — 그리디 옵션 버그 재발 방지).

### 5.2 범용 CDP 액션 계층: `scripts/browser/agent/universal_actions.py`

드라이런 설계대로 구현됨. `cdp.py`의 형제 모듈(같은 L4 Browser Engine 계층).

- `snapshot(page, max_depth=None) -> UniversalSnapshot`
  - `cdp = page.context.new_cdp_session(page)` → `Accessibility.enable` → `Accessibility.getFullAXTree`
  - `ignored=true`이거나 `_STRUCTURAL_ROLES = {"generic", "none", "InlineTextBox", "LineBreak"}`에
    속하거나 이름이 빈 노드를 걸러내 트리 압축
  - 각 노드에 짧은 `ref`(`e1`, `e2`, …) 부여, **CSS 셀렉터가 아니라 `backendDOMNodeId`에 매핑**
  - ref→backendDOMNodeId 매핑은 `WeakKeyDictionary[page, dict[ref, backendId]]`로 페이지별 보관,
    `navigate()` 호출 시 무효화
- `act(page, ref, action, value=None)` (`action ∈ {click, fill, select}`)
  - click: `DOM.scrollIntoViewIfNeeded` + `DOM.getBoxModel`(중심좌표 계산) →
    `Input.dispatchMouseEvent`(mousePressed/mouseReleased)
  - fill: `DOM.resolveNode`+`Runtime.callFunctionOn`으로 포커스 → `page.keyboard.press("Control+A")` /
    `("Backspace")`로 기존 값 제거 → `page.keyboard.type(value)`(Playwright 기존 기능 재사용)
  - select: `Runtime.callFunctionOn`으로 `.value` 설정 + `change` 이벤트 디스패치
- `navigate(page, url, ...)` — `page.goto(url)` + ref 레지스트리 무효화
- `screenshot(page) -> bytes` — `page.screenshot()`
- **실기 검증**: wikipedia.org(한 번도 설정된 적 없는 사이트)에서 185개 노드 스냅샷, 검색창에
  `fill`, "English" 링크 `click` → 실제 페이지 이동, `navigate()` 이후 이전 ref는 올바르게 거부됨.
- 단위 테스트: `tests/test_local_agent_browser_universal_actions.py`(10개, FakeCDPSession 등으로
  필터링/클릭 좌표 계산/에러 케이스까지 커버).

### 5.3 MCP 신규 도구 3종 (`ai_orchestrator/server/mcp_server.py`)

`snapshot_page` / `act_on_page` / `navigate_page` — `list_api_endpoints`/`call_api` 바로 옆에 추가.

**드라이런 대비 추가**: 3종 모두 `target: "website" | "app"` 파라미터를 받는다(§5.4 Electron 창
제어가 나중에 추가되면서 확장). `_get_target_page(target)`이 `target="app"`이면
`_get_electron_page()`(§5.4), 아니면 기존 `_get_universal_page()`(사용자 Chrome, CDP 9222)를 반환.
두 경로 모두 Playwright `connect_over_cdp()` 연결을 MCP 호출 간 캐싱 — ref 레지스트리가
`page` 객체 identity에 매여 있어(§5.2) 매 호출마다 새로 연결하면 ref가 무의미해지기 때문.

### 5.4 Electron 앱 자신의 창(webview) CDP 제어 — 드라이런 이후 추가 범위 (REQ-5)

드라이런에는 없던 범위. 사용자가 "지금 이 Electron 앱 창도 CDP로 제어되게 해줘"라고 명시적으로
요청해 추가됨. §5.2의 `universal_actions.py`는 Playwright `Page` 인터페이스(`.context`,
`.new_cdp_session()`, `.goto()`, `.screenshot()`, `.keyboard`)에만 의존하므로, **그 코드를 전혀
수정하지 않고** 같은 인터페이스를 흉내 내는 raw CDP 어댑터로 Electron 창을 물렸다.

- `admin-web/electron/main.js`: `app.whenReady()` 이전에
  `app.commandLine.appendSwitch("remote-debugging-port", "9333")` 추가. 사용자 Chrome이 쓰는
  9222(§5.2, `scripts/browser/cdp/start_chrome_with_cdp.py`)와 겹치지 않게 별도 포트 사용 —
  "웹사이트 자동화"와 "앱 자체 자동화"를 완전히 분리.
- `scripts/browser/agent/electron_target.py`(신규):
  - `list_electron_targets(port)` — `GET http://127.0.0.1:9333/json/list`
  - `_find_target()` — `type == "webview"`(admin-web 콘텐츠) 우선, 없으면 `type == "page"`로 폴백
  - `_RawCDPSession` — `websocket.create_connection(..., enable_multithread=True)`(공식 문서 확인,
    읽기 스레드와 쓰기 스레드가 분리되므로 필요) 기반 실제 websocket 클라이언트
  - `_CDPSessionHandle` — **실기로 잡은 버그의 수정**: `universal_actions.py`는 매 `snapshot()`/
    `act()` 끝에 `cdp.detach()`를 부르는데(Playwright 실제 동작 기준 "논리 세션 종료"일 뿐 실제
    연결은 안 끊김), 최초 설계는 싱글턴 세션을 그대로 돌려줘서 첫 `detach()`가 진짜 websocket을 닫아
    두 번째 호출이 `WebSocketConnectionClosedException`으로 실패했다. `new_cdp_session()`이 매번
    새 얇은 핸들을 돌려주고 그 핸들의 `detach()`는 아무것도 안 하게(no-op) 고쳐 해결. 진짜 종료는
    `ElectronTargetPage.close()`가 담당.
  - `ElectronTargetPage.screenshot()` — `Page.captureScreenshot` 전에 `Page.enable`을 먼저 호출해야
    타임아웃 없이 동작함(공식 문서에 명시되어 있지 않아 실측으로 확인).
  - `_KeyboardAdapter.press()`는 문서화된 no-op(Control+A 등 조합키 미구현, `Input.dispatchKeyEvent`
    조합키 매핑은 범위 밖으로 남김 — §9 위험 참고). `type()`은 `Input.insertText` 사용.
- **실기 검증**(실행 중인 실제 Electron 앱, mock 없음): snapshot 40개 노드(admin-web 실제 UI 텍스트
  "앱 내 AI 채팅은 제거되었습니다 — AI 작업은 Claude Code(MCP: haehan-orchestrator)로 합니다." 포함
  확인), "AI 콘솔" 링크 실제 클릭 성공, 스크린샷 99,551바이트 PNG. §5.1의 헤드리스 MCP 경로로도
  `target=app` snapshot_page 재검증(`permission_denials: []`, 결과 "40개").
- 단위 테스트: `tests/test_local_agent_browser_electron_target.py`(6개 — 타깃 탐색 우선순위,
  detach no-op 회귀, 세션 공유, close() 시 실제 종료).

### 5.5 Claude Desktop 경로

대화형(사람이 앉아서 직접 쓸 때)만 지원. 무인 트리거(버튼 클릭)는 Claude Code CLI 헤드리스 실행
전용 — Claude Desktop은 서드파티가 새 대화를 프로그래밍적으로 시작시킬 헤드리스 실행 API가 없다.

## 6. 권한/보안 설계

- 쓰기 작업(발행/발송/삭제/결제 등)은 헤드리스 파이프라인에서도 기존 `gates/approval.py` +
  `services/web_task_approval_service.py`(텔레그램 승인)를 그대로 거친다 — 이 저장소 CLAUDE.md의
  "외부 공개 발행/메일 전송/결제/삭제는 매번 재확인" 규칙을 무인 실행이라고 건너뛰지 않는다.
  헤드리스 Claude 실행은 "요청 생성"까지만 자동, 최종 확정은 지금처럼 사람이 승인.
- `run_claude_agent`은 기존 device_token 인증(`core/agent_runtime/agent.py`) 재사용 — 신규 인증 경로 없음.
- MCP 도구 허용은 `allowed_tools` 화이트리스트 방식(§5.1) — `--dangerously-skip-permissions` 같은
  전체 우회는 쓰지 않는다. 이 액션 자체는 작업 큐의 `risk_level=medium` 게이트를 통과해야 실행되고,
  실제 쓰기 작업(발행/삭제 등)은 그 안에서 다시 §6 첫 항목의 승인 플로우를 거친다 — 이중 게이트.
- 헤드리스 실행 시 시크릿(API 키 등)이 프롬프트나 로그에 노출되지 않도록 기존 SEC-02/03 패턴 유지.
- Electron 원격 디버깅 포트(9333)는 `127.0.0.1` 바인딩(Electron 기본값)이라 로컬 프로세스만 접근
  가능 — 외부 네트워크에 노출되지 않음.

## 7. 대안 비교 (버튼 → 에이전트 작업 트리거)

| | (a) 사람이 "큐 확인해" 프롬프트 | (b) `/loop` 예약 폴링 | (c) WS 푸시로 상시 프로세스 깨움 (채택) |
|---|---|---|---|
| 버튼 클릭만으로 무인 실행 | ✗ | △(Claude Code 세션이 켜져 있어야 폴링 루프가 돔) | ✓ |
| Claude Desktop(GUI)에서도 동작 | ✓ | ✗ | △(Desktop은 결국 Claude Code CLI 경유) |
| 반응 지연 | 즉시(사람이 볼 때) | 폴링 주기만큼 | 거의 즉시(이벤트 기반) — 실측 15초 내 완료 |
| 유휴 시 비용 | 0 | 큐가 비어도 매 주기 토큰 소모 | 0 |
| 기존 자산 재사용도 | 낮음 | 낮음(신규 loop 설정만) | **매우 높음**(local_agent WS 채널 신규 코드 0줄로 재사용, 액션 1개만 추가) |
| 구현 난이도 | 없음 | 낮음 | 낮음(드라이런 예상보다 더 단순 — 신규 프로세스도 안 만듦) |

**채택 근거**: (b)는 이 세션에 이미 있는 `/loop` 스킬로 손쉽게 흉내 낼 수 있지만 Claude Code 세션이
열려 있어야 하고 유휴 폴링 비용이 계속 든다는 점에서 "버튼 누르면"이라는 요구와 거리가 있다. (c)는
검증된 인프라(local_agent WS 큐/상태전이/device_token)를 100% 재사용했고, 실제 구현해보니 드라이런
예상(§7 "구현 난이도: 중간(새 프로세스 1개)")보다도 더 단순하게 끝났다 — 새 프로세스조차 안 만들고
기존 `core/agent_runtime/agent.py`에 액션 1개만 얹었다.

## 8. 실행 결과 (드라이런 → 실측 검증으로 갱신)

- `universal_actions.py`: 드라이런 예상대로 동작. wikipedia.org 실측: `[e3] button "..."` 형태
  텍스트 트리 반환 → Claude가 텍스트만 보고 ref로 클릭/입력 → 실제 사이트 반응 확인.
- 트리거: 드라이런에서 예상한 `claude_runner_agent.py`는 만들지 않음(§5.1). 대신 작업 큐에
  `{"action": "run_claude_agent", "params": {"prompt": "...", "allowed_tools": [...]}}` 적재 →
  `core/agent_runtime/agent.py`가 수신 → `claude -p` 실행 → stdout JSON 파싱 → `completed`로 상태 갱신,
  실측 그대로 확인.
- 기존 `scripts/naver/*` 사이트 모듈은 이번 구현으로 전혀 수정되지 않음 — `capability_check.py`가
  도메인을 인식하면 지금처럼 그 모듈이 우선 실행됨(변경 없음, 재확인만 함).
- Electron 창 제어(§5.4, 드라이런에 없던 추가 범위)까지 포함해 전 구성요소 실기 검증 완료.

## 9. 위험

| 위험 | 영향 | 완화 | 상태 |
|---|---|---|---|
| MCP stdio 특성상 앱이 유휴 Claude를 항상 "깨울" 수 없음 | 근본적 프로토콜 제약 | §7에서 WS 푸시로 Claude Code CLI를 새로 실행하는 방식으로 우회(재접속이지 진짜 푸시가 아님을 인지) | 구현·검증 완료 |
| ref가 페이지 변화 후 무효화됨 | act 실패 | act 실패 시 "다시 snapshot" 에러로 Claude가 재시도하게 설계 | 구현됨(단위 테스트로 확인) |
| 헤드리스 Claude 실행 비용/토큰 | 버튼 클릭마다 과금 | `max_budget_usd` 파라미터로 1회 호출 상한 강제(공식 `--max-budget-usd`) | 구현됨 |
| MCP 도구 권한이 헤드리스에서 기본 거부됨 | `run_claude_agent`이 MCP 도구를 전혀 못 씀 | `allowed_tools` 화이트리스트 + `--` 구분자(실측으로 발견·수정, §5.1) | 수정·검증 완료 |
| Electron webview CDP 세션 detach가 공유 연결을 끊음 | 두 번째 호출부터 전부 실패 | `_CDPSessionHandle`로 detach를 no-op화(§5.4) | 수정·검증 완료 |
| Electron 어댑터의 키보드 조합키(Control+A 등) 미구현 | fill 액션의 "기존 값 지우기" 단계가 앱 창 대상일 때는 동작 안 함 | 문서화된 no-op으로 명시, 필요해지면 `Input.dispatchKeyEvent` 조합키 매핑 추가 | **미해결 — §10로 이관** |
| `cdp_helper.py` 중복 미정리 상태로 새 계층 추가 | 레거시 경로와 신규 경로 혼재 | §3에서 명시적으로 확장 안 함으로 격리, 별도 과제로 분리 | 미해결(범위 밖, §10) |

## 10. 다음 세션 후보

1. `scripts/cdp_helper.py` / `apps/marketing-standalone/connectors/cdp_helper.py` 중복 정리(DUP-02
   조사에서 발견된 별개 과제)
2. `electron_target.py`의 `_KeyboardAdapter.press()` — Control+A 등 조합키 CDP 구현(현재 no-op,
   §9). 앱 창 안의 입력 필드를 `fill`로 덮어써야 하는 실사용 사례가 생기면 우선순위 상향
3. ~~기준서 §5.3에서 언급한 `snapshot_page`/`act_on_page`/`navigate_page`의 `target` 파라미터가
   현재 코드에는 있지만, admin-web 쪽에 이 기능을 실제로 트리거하는 버튼 UI는 아직 없음~~
   **2026-09-29 완료.** 사용자 명시 요청("앱 내부에 mcp를 연결해서 ai를 이용해서 작업이 되게
   해줘")으로 REQ-3의 UI 쪽 착수·완료:
   - 신규 `ai_orchestrator/routers/ai_agent_router.py` (`POST /api/v1/ai-agent/run`) — 등록된
     로컬 에이전트를 자동 선택(idle 우선)해 기존 `run_claude_agent` 작업을 큐잉하는 얇은 편의
     계층. 신규 실행 로직·신규 큐·신규 폴링 엔드포인트 없음(기존
     `GET /api/v1/local-agents/{agent_id}/tasks/{task_id}` 그대로 재사용).
   - `admin-web/src/components/chat/UniversalChat.tsx` 재구현 — 2026-09-24에 "AI 작업은 Claude
     Code(MCP)로 합니다"라는 정적 안내로 비워졌던 결정을 사용자 요청으로 뒤집고, 실제 입력창 +
     작업 큐잉 + 폴링 + 결과 표시로 복원(`AiDock`을 통해 smartstore 제외 전 도메인에 노출).
   - **실측 검증**(로컬 에이전트 재연결·재등록 과정에서 수행): `run_claude_agent` 작업 실제 큐잉→
     WS 전달→`claude -p` 실행→완료까지 확인("숫자 7만 답해" → `result_summary:"7"`, 약 21초).
   - **부수 발견·수정 버그 2건**(모두 이 작업 도중 실기로 발견): (a) `local_agent_registry.py`
     facade가 `get_task_count`/`get_completed_task_count`/`get_failed_task_count` 재노출을
     누락해 `GET /local-agents`가 상시 500이었음(에이전트가 1개라도 등록되면 재현) — 수정 완료.
     (b) `scripts/web_connector.py`의 `_connect_browser()`가 `connect_over_cdp()` 실패 시
     Playwright 인스턴스를 정리 안 해 전용 브라우저 스레드가 영구 오염되는 버그 — 별도 커밋으로
     이미 수정(defect_index #91).
   - **남은 것**: `python -m core.agent_runtime.agent --run`을 사람이 별도로 기동해둬야 하며(Electron이
     자동 스폰하는 건 별개의 구 스마트스토어 에이전트, `core/agent_runtime/runtime/local_agent.py`), FastAPI 서버가
     재시작되면 인메모리 레지스트리가 초기화돼 재등록(`--register-with-code`)이 필요함 — 상시
     자동 기동·영속화는 다음 세션 후보로 남김(§10에 신규 항목 4로 추가).
4. ~~로컬 에이전트(`core/agent_runtime/agent.py --run`)를 Electron 앱이 자동 스폰하지 않음~~
   **2026-09-29 완료.** 사용자 요청("자동으로 연결이 되게 해야 하고")으로 착수·완료:
   - **서버 쪽 영속화**: `ai_orchestrator/agent_hub/registry/common.py`에
     `_save_agents_to_disk()`/`_load_agents_from_disk()` 추가 — 등록 정체성(agent_id/
     token_hash 등, device_token 원문 제외)을 `data/local_agent_registry_state.json`에
     저장. FastAPI 프로세스가 재시작돼도(이 세션에서 여러 번 발생) 인메모리 레지스트리가
     디스크에서 복원돼 기존 에이전트가 재등록 없이 재인증됨. 부수 발견: pre-push AI 리뷰가
     `_save_agents_to_disk()`의 락 없는 순회(경쟁조건)를 지적 — 수정하며 `cleanup_agent_and_
     tasks()`가 이미 `_lock`을 쥔 채 호출하고 있어 그대로 락을 추가하면 교착이 났을 것(비
     재진입 `threading.Lock`) — 함수 자체가 짧게 락을 잡아 스냅샷만 뜨고 파일 I/O는 락 밖에서
     수행하도록 재설계, 호출부도 락 블록 밖으로 이동.
   - **클라이언트 쪽 자동 등록**: `core/agent_runtime/agent.py`에 `--auto-connect` 플래그 추가 —
     미등록(keyring에 device_token 없음)이면 `POST /api/v1/local-agents/registration-codes`를
     인증 없이 호출해(AUTH_ENABLED=False 로컬 개발 서버 전제, `tools/gates/auth.py`
     `get_current_user` 확인) 코드를 자동 발급받고 `--register-with-code`로 등록, 이미
     등록돼 있으면 바로 `--run`과 동일하게 연결. 운영(AUTH_ENABLED=True) 서버에서는 자동
     발급이 401로 실패하고 안내 메시지만 출력 — 안전하게 수동 등록으로 폴백.
   - **Electron 자동 기동**: `admin-web/electron/lib/agent.js`에 `startMcpAgent()`/
     `stopMcpAgent()` 추가 — 기존 `startAgent()`(스마트스토어 전용 구 에이전트,
     `/smartstore/agent/ws`)와 완전히 별개 프로세스로 `core.agent_runtime.agent --auto-connect`
     (`/local-agents/ws`)를 `HAEHAN_AGENT_WS_ENABLED=true`로 스폰. 패키징 빌드는 아직
     미지원(별도 exe 번들 파이프라인 필요 — 개발 모드에서만 자동 기동, 로그로 명시).
   - **실측 검증**: (1) 격리된 config 경로(`HAEHAN_AGENT_DESKTOP_CONFIG`)로 "완전 미등록"
     상태를 재현해 `--auto-connect`가 등록코드 자동 발급→등록→WS `auth_ok`까지 성공 확인.
     (2) Electron을 처음부터 재기동해 `[mcp-agent] 시작(auto-connect)` → `auth_ok` 로그로
     자동 스폰 확인. (3) FastAPI를 재시작하고 **아무 조작도 없이** `GET /local-agents`로
     `agent_status:"idle"`, `connected_at`이 재시작 직후 시각임을 확인(완전 자동 재연결).
