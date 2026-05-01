# BROWSER-ARCH-1: Playwright 설치/사용 현황 및 Router 분리 가능성 분석

**Date:** 2026-05-01  
**Stage:** BROWSER-ARCH-1 — Server-side Playwright inventory & router split analysis  
**Baseline:** 3284e1f (test(browser): verify dry-run browser.inspect task flow)

## Executive Summary

**현황:**
- Playwright 1.58.0은 **ai-orchestrator-api 컨테이너 1개에만 설치**됨 (no duplication)
- Browser binaries는 설치되지 않음 (.playwright 디렉토리 미존재)
- **Server-side (playwright_connector.py) vs Local-Agent (browser_controller.py) 두 별도 흐름** 운영 중
- Browser Router 분리가 **기술적으로 가능하고 권장됨** (중복 회피, 확장성 향상)

**권장 방향:**
1. **BROWSER-ARCH-2에서 Browser Router 신규 생성** (ai_orchestrator/browser_router.py)
2. **thin adapter 패턴 유지** (local_agent/browser_actions.py)
3. **server Playwright worker 통합 계획** (향후 멀티 컨테이너 지원)

---

## Repo Boundary Lock Status

| Item | Status |
|------|--------|
| Repo path | /home/ubuntu/apps/haehan-ai-orchestrator |
| Branch | master |
| HEAD before | 3284e1f |
| origin/master | 3284e1f (synced) ✅ |
| Tracked changes | NONE ✅ |
| Other app access | NONE ✅ |

✅ All pre-checks PASSED.

---

## 컨테이너/서비스 조사

### Docker Compose 구성

**파일:** `/home/ubuntu/apps/haehan-ai-orchestrator/docker-compose.yml`

**정의된 서비스:**
```
services:
  ai-orchestrator-api:      (실행 중 - 8400 port)
  admin-web:                (실행 중 - 3000 port)
  api_storage:              (정의만 됨)
  app_web:                  (정의만 됨)
  cad_quantity_default:     (정의만 됨)
```

### 실행 중 컨테이너

| Container Name | Service | Image | Status | Base Image |
|---|---|---|---|---|
| haehan-ai-orchestrator-api | ai-orchestrator-api | haehan-ai-orchestrator-api:local | Up 4h (healthy) | python:3.11-slim |
| haehan-ai-orchestrator-admin-web | admin-web | haehan-ai-orchestrator-admin-web:local | Up 22h | (Node.js) |

---

## Playwright 설치 현황

### 패키지 정의

| 파일 | Playwright | 설치 여부 |
|------|-----------|---------|
| `/home/ubuntu/apps/haehan-ai-orchestrator/requirements.txt` | `playwright>=1.40.0` | ✅ YES |
| `/home/ubuntu/apps/haehan-ai-orchestrator/admin-web/package.json` | NONE | ❌ NO |
| `/home/ubuntu/apps/haehan-ai-orchestrator/mcp_server/requirements.txt` | (미조사) | - |

### 컨테이너별 Playwright 설치

**ai-orchestrator-api 컨테이너:**
```
Name: playwright
Version: 1.58.0
Location: /usr/local/lib/python3.11/site-packages
Depends on: greenlet, pyee
```

**admin-web 컨테이너:**
- Playwright ❌ NOT INSTALLED
- Next.js/React-only web UI

### Browser Binaries 설치

**조사 결과:**
- `.playwright` 디렉토리: ❌ NOT FOUND in running containers
- Playwright install 명령: ❌ NOT FOUND in Dockerfiles
- Browser binary commands (chromium, firefox, webkit): ❌ NOT FOUND

**결론:** Browser binaries are **NOT installed** in the containers.
**Implication:** Playwright can handle page.goto() / screenshot() operations, but actual browser launch will fail at runtime.

---

## Playwright 코드 사용처

### 1. Server-Side: ai_orchestrator/connectors/playwright_connector.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/ai_orchestrator/connectors/playwright_connector.py`

**용도:** Web page fetching for server-side task execution
- `sync_playwright()` context manager 사용 (동기 API)
- `browser.new_page()` → `page.goto()` → HTML 수집

**호출 경로:**
```
ai_orchestrator/executor.py
  └─> playwright_connector.fetch_web_page(req.target)
```

**에러 처리:**
- `playwright_not_installed`: Playwright 미설치
- `playwright_timeout`: 페이지 로딩 timeout
- `playwright_error:*`: 기타 Playwright 에러

**제약:**
- read-only (page inspection, HTML fetch only)
- form submission 금지
- 쿠키/storage 접근 금지

### 2. Server-Side: ai_orchestrator/sites/ (session management)

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/ai_orchestrator/sites/session_manager.py`

**용도:** Login probing / session capture
- `sync_playwright()` context manager
- Login form 입력 후 session state capture
- 사용자 interaction 시뮬레이션

**에러 처리:**
- `playwright import 실패` → RuntimeError
- `playwright 미설치` → warning log

### 3. Server-Side: agent/runner.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/agent/runner.py`

**용도:** Browser state probe
- `_playwright_available()`: Playwright 설치 여부 확인 (import only, no launch)
- `sync_playwright()` for page.goto() (actual browser launch attempted)

**상태 조회:**
```python
"playwright_available": _playwright_available(),
"chromium_available": (actual browser launch attempt),
```

### 4. Local Agent: local_agent/browser_controller.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/local_agent/browser_controller.py`

**용도:** Async browser automation for local PC
- `async_playwright()` context manager (비동기 API)
- `browser.new_context()` → `page.goto()` → user interactions
- PC에서 WebSocket으로 수신된 task 실행

**핵심 기능:**
- Browser launch & shutdown
- Page navigation
- Click / type / fill / select / scroll
- Screenshot capture

**에러 처리:**
- `BrowserLaunchError`: Browser 시작 실패
- `Playwright not installed`: 패키지 미설치

### 5. Local Agent: local_agent/browser_actions.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/local_agent/browser_actions.py`

**용도:** Action handler layer for browser.* commands
- Thin wrapper around browser_controller.py
- browser.inspect (dry_run only, current stage)
- browser.plan_click / browser.plan_type (future)
- browser.execute_click / browser.execute_type (future)

**구조:**
```python
def action_browser_inspect(params: dict) -> ActionResult:
    # dry_run=True: mock response (no actual Playwright)
    # dry_run=False: error (ACTUAL_BROWSER_EXECUTION_NOT_ENABLED)
```

### 6. Local Agent: local_agent/browser_reader.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/local_agent/browser_reader.py`

**용도:** Read-only browser page analysis
- `sync_playwright()` context manager
- Page content fetch & DOM analysis
- XPath / CSS selector inspection

**DI pattern:**
- `_playwright_factory` parameter for test injection
- Allows mocking without actual Playwright

### 7. Local Agent: local_agent/browser_login_probe.py

**위치:** `/home/ubuntu/apps/haehan-ai-orchestrator/local_agent/browser_login_probe.py`

**용도:** Login requirement detection
- Read-only probe for login pages
- `sync_playwright()` with factory injection

### 8. Tests

**파일들:**
- `tests/test_browser_execute_integration.py`: async_playwright() 실제 실행 테스트
- `tests/test_browser_task_handler.py`: async_playwright() with real browser
- `tests/test_browser_approval_verifier.py`: async_playwright()
- `tests/test_browser_action_contract.py`: async_playwright()
- `tests/test_fetch_web_page.py`: Fake playwright injection
- `tests/test_browser_login_probe.py`: Fake playwright
- `tests/test_browser_open_observe_fixture.py`: Fake playwright
- `agent/tests/test_login_with_secret.py`: Fake playwright
- `agent/tests/test_agent_readonly.py`: Fake playwright
- `scripts/_probe_kakao_page_structure.py`: sync_playwright() (actual browser)

**패턴:**
- Real browser: integration tests only (test_browser_execute_integration.py, etc.)
- Mock factory: most unit tests use _playwright_factory injection

---

## 중복 설치 분석

### 결과

| Component | Playwright | Count | Duplication |
|-----------|-----------|-------|------------|
| ai-orchestrator-api container | 1.58.0 | 1 | ❌ NO |
| admin-web container | - | 0 | - |
| Other services | - | 0 | - |
| **Total** | - | **1** | **✅ NO DUPLICATION** |

**결론:** Playwright는 **단 1개 컨테이너에만 설치**되어 있음. 중복 제거할 것 없음.

---

## 현재 구조 분석

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  ai-orchestrator-api Container               │
│                     (python:3.11-slim)                        │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Server-Side Browser Operations                       │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ • playwright_connector.py: Web page fetch            │   │
│  │   └─ sync_playwright() for server tasks              │   │
│  │                                                       │   │
│  │ • ai_orchestrator/sites/session_manager.py           │   │
│  │   └─ sync_playwright() for login probe               │   │
│  │                                                       │   │
│  │ • agent/runner.py                                    │   │
│  │   └─ sync_playwright() for availability check        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Local Agent Module (Embedded in Container)           │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ • browser_controller.py: Async browser automation    │   │
│  │   └─ async_playwright() for WebSocket tasks          │   │
│  │                                                       │   │
│  │ • browser_actions.py: Action handlers                │   │
│  │   └─ browser.inspect (dry_run only currently)        │   │
│  │   └─ browser.plan_* (future)                         │   │
│  │   └─ browser.execute_* (future)                      │   │
│  │                                                       │   │
│  │ • browser_reader.py: Read-only analysis              │   │
│  │   └─ sync_playwright() with mock injection           │   │
│  │                                                       │   │
│  │ • browser_login_probe.py: Login detection            │   │
│  │   └─ sync_playwright() with mock injection           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ WebSocket Bridge (local_agent/                       │   │
│  │  browser_websocket_bridge.py)                        │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Connects client PC → server-side browser controller   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Required Package:                                           │
│  • playwright>=1.40.0 (currently 1.58.0)                    │
│  • Browser binaries: ❌ NOT installed                       │
│  └──────────────────────────────────────────────────────────┘
│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  admin-web Container                         │
│                  (Node.js / Next.js)                         │
│                                                               │
│  • React UI for approval workflows                          │
│  • Playwright: ❌ NOT NEEDED                                │
└─────────────────────────────────────────────────────────────┘
```

### 흐름 분석

#### Flow 1: Server-Side Web Task (Traditional)
```
Client API Request
  ↓
ai_orchestrator/executor.py
  ↓
playwright_connector.fetch_web_page()
  ├─ sync_playwright() starts browser
  ├─ page.goto(url)
  ├─ HTML content extraction
  └─ returns result immediately
```
**특징:**
- 동기 (sync_playwright)
- Server 내부에서 완결
- 외부 클라이언트 의존 없음
- Browser binaries 필수 (but not installed)

#### Flow 2: Local Agent Browser Task (New)
```
Client WebSocket (PC)
  ↓
local_agent/browser_websocket_handshake.py
  ↓
local_agent/actions.py::action_browser_inspect()
  ├─ dry_run=True: mock response (no Playwright)
  └─ dry_run=False: ACTUAL_BROWSER_EXECUTION_NOT_ENABLED error
```
**특징:**
- 비동기 (async Playwright, but not used in current stage)
- Local PC 클라이언트에서 실제 실행
- Playwright는 local PC에 필요 (not on server)
- Current stage (BROWSER-7C): dry_run only (no Playwright call)

### 문제점 분석

#### 문제 1: Server-Side Playwright 사용 목적 불명확
- **playwright_connector.py**는 web page fetching용으로 정의됨
- **agent/runner.py**는 browser availability check용
- **sites/session_manager.py**는 login probe용
- 세 가지 용도가 **동일한 Playwright 패키지** 사용
- Browser binaries 설치 안 되어 있음 → **실제 실행 불가능**

#### 문제 2: Server vs Local Agent 역할 모호
- **Local Agent (browser_controller.py)**는 async_playwright 사용
- **Server-side (playwright_connector.py)**는 sync_playwright 사용
- 두 흐름이 **동일 컨테이너에서 경쟁** 가능
- Future stage에서 browser.execute_* 추가 시 **충돌 위험**

#### 문제 3: Browser Router 부재
- 현재 browser 관련 logic이 **분산됨**:
  - ai_orchestrator/connectors/playwright_connector.py
  - ai_orchestrator/executor.py
  - ai_orchestrator/sites/session_manager.py
  - agent/runner.py
  - local_agent/browser_controller.py
  - local_agent/browser_actions.py
- Unified entry point (router) 없음
- HWP/Excel/CAD 등 다른 로컬 제어 추가 시 **복잡도 증가**

---

## Browser Router 분리 필요성 판단

### 필요성 평가

| 항목 | 현재 | 문제 | 분리 후 |
|------|------|------|--------|
| **Server Web Task** | playwright_connector.py 분산 | 단일 진입점 없음 | browser_router.py 중앙화 |
| **Local Agent Bridge** | browser_controller.py + actions.py | 결합도 높음 | thin adapter 유지 |
| **향후 HWP/Excel/CAD** | 도구별 별도 모듈 | 일관성 부족 | 통합 router 패턴 |
| **Playwright 버전 관리** | 1개 컨테이너, 단순 | - | 동일 (변화 없음) |
| **Browser Binary 설치** | 미설치 상태 | 동작 불가능 | 분리해도 미설치 (별개 문제) |

**결론:** Router 분리가 **강하게 권장됨** (architecturally, not urgently).

---

## 권장 아키텍처

### Option A: Browser Router (권장)

```
┌─────────────────────────────────────────────────┐
│ ai_orchestrator/browser_router.py (NEW)         │
│ - Single entry point for all browser tasks      │
│ - Policy enforcement                            │
│ - Backend selection (server vs local)           │
├─────────────────────────────────────────────────┤
│ Backends:                                       │
│ - server_backend: playwright_connector.py       │
│ - local_agent_backend: thin adapter             │
│ - mock_backend: test fixtures                   │
│ - future: hwp_backend, excel_backend, etc.      │
├─────────────────────────────────────────────────┤
│ ai_orchestrator/browser_policy.py               │
│ - Risk classification (dry_run vs actual)       │
│ - URL validation                                │
│ - Action approval rules                         │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ local_agent/browser_actions.py (ADAPTER ONLY)   │
│ - Thin wrapper around browser_router            │
│ - No direct Playwright calls                    │
│ - WebSocket → router dispatch                   │
└─────────────────────────────────────────────────┘
```

**장점:**
- 단일 진입점으로 정책 적용
- HWP/Excel/CAD 확장성
- Server vs Local 명확한 분리
- 테스트 용이 (mock backend)
- 버전 관리 중앙화

**구현 비용:** 중간 (기존 코드 대부분 재사용)

### Option B: 현상 유지 (not recommended)

```
현재 구조 유지:
- playwright_connector.py 분산
- browser_controller.py 독립
- HWP/Excel/CAD 추가 시마다 새 모듈
```

**단점:**
- 향후 복잡도 증가
- 정책 적용 분산
- 중복 코드 가능성

---

## Local Agent 통합 영향도

### 현재 local_agent 구조

```
local_agent/
├── actions.py (dispatcher)
├── agent.py (main entry)
├── browser_actions.py (handlers)
├── browser_controller.py (async browser control)
├── browser_reader.py (read-only page analysis)
├── browser_login_probe.py (login detection)
├── browser_websocket_bridge.py
├── browser_websocket_handshake.py
├── browser_websocket_schema.py
└── browser_approval_*.py (approval workflow)
```

### Browser Router 도입 시 영향

| 파일 | 변경 | 이유 |
|------|------|------|
| actions.py | 최소 | dispatcher만 유지 |
| browser_actions.py | 최소 | thin adapter로 축소 |
| browser_controller.py | 없음 | internal use 유지 |
| browser_websocket_*.py | 없음 | schema/handshake 동일 |
| browser_approval_*.py | 없음 | approval logic 동일 |

**결론:** Minimum disruption. Backward compatible.

---

## Server-Side 통합 계획

### 현재 분산된 Playwright 사용처

1. **playwright_connector.py** - web fetch (server task)
2. **session_manager.py** - login probe
3. **agent/runner.py** - browser availability check

### 통합 계획 (BROWSER-ARCH-2 후보)

```
ai_orchestrator/browser_router.py
  │
  ├─ server_backend.fetch_web_page(url)
  │  └─ 기존 playwright_connector.py 로직
  │
  ├─ server_backend.probe_login_state(url)
  │  └─ 기존 session_manager.py 로직
  │
  └─ server_backend.check_availability()
     └─ 기존 agent/runner.py 로직
```

### 주의사항

- **Browser binaries는 여전히 미설치** (별개 문제)
  - Dockerfile 수정 필요 (BROWSER-INSTALL 단계에서 처리)
  - Router 분리와 독립적

- **현재 playwright 1.58.0은 유지**
  - 버전 업그레이드는 별도 계획

---

## 다음 단계 BROWSER-ARCH-2 제안

### Scope

1. **ai_orchestrator/browser_router.py 생성**
   - Server-side entry point
   - Policy enforcement
   - Backend selection

2. **ai_orchestrator/browser_schemas.py**
   - Request/response types
   - Action definitions

3. **ai_orchestrator/browser_backends.py (또는 모듈화)**
   - ServerPlaywrightBackend (기존 playwright_connector.py 재사용)
   - LocalAgentBackend (thin adapter)
   - MockBackend (test fixtures)

4. **local_agent/browser_actions.py 리팩토링**
   - action_browser_inspect → browser_router 위임
   - browser_plan_* / browser_execute_* 추가 (로직은 router에서)

5. **tests 추가**
   - router_unit_tests
   - backend_contract_tests
   - integration_tests (server + local agent)

### Effort Estimate

- Router 설계: 4시간
- 구현: 8시간
- Test coverage: 8시간
- Integration: 4시간
- **Total: ~24시간** (1-2일)

### Prerequisites

- ✅ BROWSER-7C (approval policy verification) COMPLETE
- ✅ Local agent dry_run handler working
- ⏳ Browser binaries installation (separate initiative)

---

## 핵심 판단

### Q1: Playwright가 어느 서비스/컨테이너에 설치되어 있는가?

**A:** ai-orchestrator-api 컨테이너 **1개뿐** (1.58.0, /usr/local/lib/python3.11/site-packages)

### Q2: 중복 설치가 있는가?

**A:** ❌ **NO** — 1개 컨테이너에만 설치됨

### Q3: 실제 코드에서 Playwright를 사용하는 곳은 어디인가?

**A:**
- Server-side: playwright_connector.py, session_manager.py, agent/runner.py (sync API)
- Local-agent: browser_controller.py, browser_actions.py, browser_reader.py (async/sync)
- Tests: integration tests 사용, most unit tests use mocks

### Q4: browser.inspect handler를 local_agent 내부에 직접 붙이면 중복/결합 문제가 생기는가?

**A:** ✅ **약간** — 향후 browser.plan_*/execute_* 추가 시 policy/routing이 분산될 수 있음

### Q5: 별도 browser tool/router로 분리하는 것이 더 안전한가?

**A:** ✅ **YES** — 아키텍처 관점에서 권장

### Q6: 서버 Playwright worker와 local agent Playwright를 분리해야 하는가?

**A:** ✅ **논리적 분리는 YES, 물리적 분리는 현재 NO**
- 현재: 동일 컨테이너에서 sync/async 양쪽 지원
- 권장: Browser Router를 통해 백엔드 선택 지원

### Q7: 향후 HWP/Excel/CAD 로컬 제어와 같은 router 구조로 확장 가능한가?

**A:** ✅ **YES** — Browser Router 도입 시 확장 용이

### Q8: 현재 단계에서 Browser Router를 먼저 만들 필요가 있는가, 아니면 최소 bridge만 만들면 되는가?

**A:** **최소 bridge 권장 (현재), 공식 Router는 BROWSER-ARCH-2에서**
- 현재: browser.inspect (dry_run only) → thin adapter로 충분
- 향후: browser.plan_*/execute_* 추가 → Router 필수

---

## 결론

### 현재 상태 평가

✅ **Playwright 설치 현황 건강함**
- 1개 컨테이너, 중복 없음
- 버전 명확함 (1.58.0)
- Requirements 명시적

⚠️ **Architecture 개선 여지**
- Server vs Local 역할 모호
- 분산된 Playwright 사용
- Router 패턴 부재

### 권장 실행 계획

1. **현재 (BROWSER-7C-ARCH-1):** 현상 유지, Router 설계만 준비
2. **BROWSER-ARCH-2:** Browser Router 구현 (low risk, high benefit)
3. **BROWSER-INSTALL:** Browser binaries 설치 (별개 PR)
4. **BROWSER-7D:** browser.execute_* with approval (Router 사용)

---

**보고서 완료일:** 2026-05-01  
**다음 단계:** BROWSER-ARCH-2 — Browser Router Implementation
