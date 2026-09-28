# CDP 범용 자동화 + MCP 버튼 트리거 — 기준서 + 드라이런 (2026-09-28)

> 상태: 기준서·드라이런만 작성. 코드·설정 미수정, 커밋 없음. 사용자 승인 후 착수.
> 범위: 앱에서 버튼을 눌렀을 때 Claude(MCP)가 실제로 작업을 수행하는 트리거 설계 +
> 처음 방문하는 웹사이트에도 사이트별 코드 없이 자동화되는 범용 CDP 액션 계층 설계.
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
| MCP 트리거의 구조적 한계 | MCP 공식 스펙(2026-07-28 개정)상 서버(앱)가 유휴 상태의 클라이언트(Claude)를 능동적으로 깨우는 프리미티브는 없음(sampling조차 deprecated). "버튼→즉시 에이전트 작업"은 MCP 밖의 별도 경로(WS 큐 + 헤드리스 `claude -p` 실행)로 구현해야 함 |
| 재사용 가능한 기존 인프라 | `local_agent` WS 푸시 채널(큐 적재→기동→상태보고)이 이미 구현·검증돼 있음 — 신규로 만들 건 "그 채널이 CDP 대신 Claude Code CLI를 실행하게" 하는 얇은 변형뿐 |

## 1. 요구사항

| ID | 요구사항 (사용자 발화 원문) |
|---|---|
| REQ-1 | "AI 에이전트 및 웹브라우저를 CDP로 AI를 연동해서 자동화를 하는 도구이고 또한 일렉트론 앱으로 연동해서 처리하게 하는게 목표" |
| REQ-2 | "클로드 mcp로 연결해서 사용하게 설계를 하고 싶어" |
| REQ-3 | "클로드 데스크 앱 또는 클로드 코드와 앱이 연동이 되고 앱에서 버튼을 누르면 사용자가 원하는 에이전트 작업이 되게 하는게 목표" |
| REQ-4 | "현재 앱은 나한테 맞춰진거고 오픈클로우를 조사해서 그것보다 좋게 만들고 처음 방문하는 웹사이트에도 자동화 되게 하고 싶어" |

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
  보낼 수 있음.
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
| `ai_orchestrator/local_agent/browser/cdp.py` (`open_cdp_session`/`CDPSession.new_tab`) | 사용자 Chrome에 Playwright로 CDP 연결, 새 탭 관리 | 그대로 재사용 — 신규 계층의 진입점 |
| `ai_orchestrator/local_agent_registry_task_queue.py` / `local_agent_registry_task_lifecycle.py` | 작업 큐 상태전이(`queued→delivered→running→completed/failed`), 이미 구현·테스트됨 | 그대로 재사용 — 버튼 트리거의 큐로 사용 |
| `ai_orchestrator/local_agent_router_ws.py` + `scripts/local_agent.py` | 서버→로컬 프로세스 WS 푸시 채널의 원형(device_token 인증) | 패턴 재사용 — `scripts/claude_runner_agent.py`(신규)의 템플릿 |
| `ai_orchestrator/mcp_server.py`의 `list_api_endpoints`/`call_api`(462~558행 부근) | 앱 API 전체를 MCP 도구로 범용 노출하는 기존 패턴 | 패턴 재사용 — 신규 도구 3종 추가할 자리 |
| `gates/approval.py` + `services/web_task_approval_service.py` | 쓰기 작업(발행/발송/삭제 등) 승인 플로우 | 그대로 유지 — 무인 파이프라인이어도 승인 없이 우회 금지 |
| Playwright(`page.goto`/`page.keyboard`/`page.mouse`/`page.screenshot`) | 이미 사이트 모듈 20개 이상이 쓰는 브라우저 제어 기반 | 그대로 재사용 |
| `scripts/ops/capability_check.py` | "이 도메인에 기존 구현이 있는가" 확인(CLAUDE.md 필수 절차) | 그대로 재사용 — 기존 사이트 모듈/범용 계층 분기점으로 그대로 씀 |

**명시적으로 확장하지 않는 것**: `scripts/cdp_helper.py`(및 `apps/marketing-standalone/connectors/cdp_helper.py`
중복본) — raw-websocket 레거시 경로. 여기에 AXTree/ref 로직을 얹으면 4번째 병렬 CDP 클라이언트가
생겨 계층이 더 꼬인다. 이 두 파일의 중복 자체(오늘 DUP-02 조사에서 이미 발견)는 이 기준서와 별개의
정리 과제로 남긴다.

## 4. 전체 흐름

```
[admin-web /ops 버튼]
        │ POST /api/v1/agent-tasks (신규)
        ▼
[작업 큐] ── local_agent_registry_task_queue.py 재사용 (queued)
        │ WS 푸시 (local_agent_router_ws.py 채널 재사용)
        ▼
[scripts/claude_runner_agent.py] (신규, 상시 기동, local_agent.py의 형제)
        │ claude_agent_job 타입 작업 수신 → 상태 delivered→running
        ▼
[claude -p "<지시문>" --mcp-config .mcp.json]  (헤드리스 서브프로세스)
        │ Claude Code가 MCP 클라이언트로 haehan-orchestrator에 접속
        ▼
[ai_orchestrator/mcp_server.py]
        ├─ 기존 도구 / list_api_endpoints / call_api
        └─ 신규: snapshot_page / act_on_page / navigate_page
                │
                ▼ (처음 보는 사이트일 때만)
        [universal_actions.py] (신규) ── AXTree snapshot → ref → act
                │
        [기존 사이트 모듈: scripts/naver/*]  ← capability_check.py가 있다고 판단하면 이쪽 우선(빠름)
        ▼
[쓰기 작업이면] gates/approval.py + web_task_approval_service.py (기존 승인 플로우 그대로) → 사람 승인
        ▼
[결과를 task 상태 API로 보고 → completed/failed]
```

## 5. 구성요소 설계

### 5.1 트리거: `scripts/claude_runner_agent.py`(신규) + `POST /api/v1/agent-tasks`(신규)

- `scripts/local_agent.py`와 동일하게 `/api/v1/local-agents/ws`에 별도 device_token으로 상시 접속.
- `task_type == "claude_agent_job"`인 작업만 처리 — 기존 `local_agent.py`(CDP 도구를 직접 실행하는
  "멍청한 실행기")와 역할이 겹치지 않게 분리.
- 작업을 받으면 프롬프트를 넣어 `claude -p "<프롬프트>" --mcp-config .mcp.json`을 서브프로세스로 실행,
  표준출력을 파싱해 결과를 task 상태 API로 보고.
- Electron이 이미 `local_agent`를 자식 프로세스로 띄우는 관례(`admin-web/electron/lib/agent.js`, 오늘
  `py -3.14` 인터프리터 해석 버그를 수정한 바로 그 파일)가 있으므로, 같은 패턴으로 앱 시작 시 함께
  기동시킨다.

### 5.2 범용 CDP 액션 계층: `ai_orchestrator/local_agent/browser/universal_actions.py`(신규)

`cdp.py`의 형제 모듈(같은 L4 Browser Engine 계층).

- `snapshot(page, max_depth=None) -> UniversalSnapshot`
  - `cdp = page.context.new_cdp_session(page)` → `Accessibility.enable` → `Accessibility.getFullAXTree`
  - `ignored=true`이거나 이름 없는 `generic/none` role 노드를 걸러내 트리 압축
  - 각 노드에 짧은 `ref`(`e1`, `e2`, …) 부여, **CSS 셀렉터가 아니라 `backendDOMNodeId`에 매핑**
    (`nodeId`는 `DOM.getDocument` 호출마다 바뀌지만 `backendDOMNodeId`는 노드 무효화 전까지 안정적)
  - ref→backendDOMNodeId 매핑은 프로세스 내 dict 보관, `navigate()` 호출 시 무효화
- `act(page, ref, action, value=None)` (`action ∈ {click, fill, select}`)
  - ref로 backendNodeId 조회(모르는/오래된 ref면 "다시 snapshot 하라" 에러)
  - `DOM.resolveNode` → `objectId`
  - click: `DOM.getBoxModel` + `DOM.scrollIntoViewIfNeeded` → 중심좌표로 `Input.dispatchMouseEvent`
  - fill: 포커스만 CDP로 주고 **`page.keyboard.type(value)`(Playwright 기존 기능) 재사용** — React
    컨트롤드 인풋과의 호환성은 실키 입력 시뮬레이션이 `.value` 직접 대입보다 안전
  - select: `Runtime.callFunctionOn`으로 `.value` 설정 + `change` 이벤트 디스패치
- `navigate(page, url)` — `page.goto(url)` 그대로 + ref 레지스트리 무효화
- `screenshot(page)` — `page.screenshot()`, vision 보조용(오픈클로처럼 부차 수단으로만)

### 5.3 MCP 신규 도구 3종 (`ai_orchestrator/mcp_server.py`)

`snapshot_page` / `act_on_page` / `navigate_page` — 기존 `list_api_endpoints`/`call_api` 바로 옆에 추가.

### 5.4 Claude Desktop 경로

대화형(사람이 앉아서 직접 쓸 때)만 지원. 무인 트리거(버튼 클릭)는 Claude Code CLI 헤드리스 실행
전용 — Claude Desktop은 서드파티가 새 대화를 프로그래밍적으로 시작시킬 헤드리스 실행 API가 없다.

## 6. 권한/보안 설계

- 쓰기 작업(발행/발송/삭제/결제 등)은 헤드리스 파이프라인에서도 기존 `gates/approval.py` +
  `services/web_task_approval_service.py`(텔레그램 승인)를 그대로 거친다 — 이 저장소 CLAUDE.md의
  "외부 공개 발행/메일 전송/결제/삭제는 매번 재확인" 규칙을 무인 실행이라고 건너뛰지 않는다.
  헤드리스 Claude 실행은 "요청 생성"까지만 자동, 최종 확정은 지금처럼 사람이 승인.
- `claude_runner_agent.py`는 기존 device_token 인증 재사용 — 신규 인증 경로 없음.
- 헤드리스 실행 시 시크릿(API 키 등)이 프롬프트나 로그에 노출되지 않도록 기존 SEC-02/03 패턴 유지.

## 7. 대안 비교 (버튼 → 에이전트 작업 트리거)

| | (a) 사람이 "큐 확인해" 프롬프트 | (b) `/loop` 예약 폴링 | (c) WS 푸시로 상시 프로세스 깨움 (채택) |
|---|---|---|---|
| 버튼 클릭만으로 무인 실행 | ✗ | △(Claude Code 세션이 켜져 있어야 폴링 루프가 돔) | ✓ |
| Claude Desktop(GUI)에서도 동작 | ✓ | ✗ | △(Desktop은 결국 Claude Code CLI 경유) |
| 반응 지연 | 즉시(사람이 볼 때) | 폴링 주기만큼 | 거의 즉시(이벤트 기반) |
| 유휴 시 비용 | 0 | 큐가 비어도 매 주기 토큰 소모 | 0 |
| 기존 자산 재사용도 | 낮음 | 낮음(신규 loop 설정만) | **높음**(local_agent WS 채널 이미 검증됨) |
| 구현 난이도 | 없음 | 낮음 | 중간(새 프로세스 1개) |

**채택 근거**: (b)는 이 세션에 이미 있는 `/loop` 스킬로 손쉽게 흉내 낼 수 있지만 Claude Code 세션이
열려 있어야 하고 유휴 폴링 비용이 계속 든다는 점에서 "버튼 누르면"이라는 요구와 거리가 있다. (c)는
이미 검증된 인프라(local_agent WS 큐/상태전이/device_token)를 100% 재사용하면서, 부족한 한 조각
(WS 클라이언트가 CDP를 직접 두드리는 대신 Claude Code CLI를 대신 실행)만 추가하면 되므로 공수 대비
정합성이 가장 높다.

## 8. 드라이런 (예상 결과, 코드 미작성)

- `universal_actions.py`: `snapshot(page)` 호출 → 처음 보는 사이트에서도 role/name/ref로 구성된 텍스트
  트리 반환 예상(예: `[e3] button "장바구니 담기"`, `[e7] textbox "검색어"`) → Claude가 이 텍스트만 보고
  `act(page, "e3", "click")` 호출 → 실제 버튼 클릭.
- `claude_runner_agent.py`: 작업 큐에 `{"task_type": "claude_agent_job", "prompt": "..."}` 적재 →
  프로세스가 `claude -p` 실행 → 표준출력 마지막 JSON 블록을 파싱해 `completed`로 상태 갱신 예상.
- 기존 `scripts/naver/*` 사이트 모듈은 이번 설계로 전혀 수정되지 않는다 — `capability_check.py`가
  도메인을 인식하면 지금처럼 그 모듈이 우선 실행됨.

## 9. 위험

| 위험 | 영향 | 완화 |
|---|---|---|
| MCP stdio 특성상 앱이 유휴 Claude를 항상 "깨울" 수 없음 | 근본적 프로토콜 제약 | §7에서 WS 푸시로 Claude Code CLI를 새로 실행하는 방식으로 우회(재접속이지 진짜 푸시가 아님을 인지) |
| ref가 페이지 변화 후 무효화됨 | act 실패 | act 실패 시 "다시 snapshot" 에러로 Claude가 재시도하게 설계 |
| 헤드리스 Claude 실행 비용/토큰 | 버튼 클릭마다 과금 | 사용 전 사용자에게 비용 고지 필요(별도 승인 사안) |
| `cdp_helper.py` 중복 미정리 상태로 새 계층 추가 | 레거시 경로와 신규 경로 혼재 | §3에서 명시적으로 확장 안 함으로 격리, 별도 과제로 분리 |

## 10. 다음 세션 후보

1. `scripts/cdp_helper.py` / `apps/marketing-standalone/connectors/cdp_helper.py` 중복 정리(오늘
   DUP-02 조사에서 이미 발견된 별개 과제)
2. **실제 구현 착수 여부는 이 기준서 승인 후 별도 승인 필요**(CLAUDE.md 3단계: 기준서→드라이런→**승인**→실행)
