# BROWSER-WORKER-1 Playwright 별도 Browser Worker 도구 골격 구현

## 작업 개요
- 목표: Playwright를 별도 Browser Worker 도구로 분리 가능하도록 구조 설계 및 최소 골격 구현
- 범위: 실제 Playwright 실행, Chromium 설치, 별도 프로세스 실행 금지 (골격만)
- 결과물: Browser Worker service/schemas/backends + Browser Tool worker client + tests

---

## Repo Boundary Lock 준수
| 항목 | 상태 |
|------|------|
| **repo path** | /home/ubuntu/apps/haehan-ai-orchestrator |
| **branch** | master |
| **HEAD before** | 35bcc1c |
| **origin/master** | 35bcc1c |
| **working tree before** | clean |
| **다른 앱 접근 여부** | None (로컬 repo만 사용) |

---

## 기준선 확인
| 항목 | 상태 |
|------|------|
| **BROWSER-ARCH-2A 포함 여부** | YES (refactor(browser): add browser tool router skeleton) |
| **BROWSER-INSTALL-1 포함 여부** | YES (docs(browser): plan playwright browser binary installation) |
| **local/origin/server HEAD 일치** | YES (35bcc1c) |
| **untracked 파일 여부** | NO |

---

## 구현 내용

### 생성 파일 구조
```
browser_worker/
├── __init__.py                          # Package initialization
├── schemas.py                           # Request/Response schemas
├── policy.py                            # Security & execution policies
├── service.py                           # Core service handler
├── app.py                               # FastAPI app skeleton
└── backends/
    ├── __init__.py
    └── mock_playwright_backend.py       # Mock backend (no actual browser)

ai_orchestrator/browser_tool/backends/
└── worker_backend.py                    # Client adapter for Browser Tool Router

tests/
├── test_browser_worker_schemas.py       # Schema validation tests
├── test_browser_worker_mock_backend.py  # Backend logic tests
└── test_browser_tool_worker_backend.py  # Integration tests
```

### 핵심 Schema 정의

**WorkerBrowserRequest**
```python
- action: str (e.g., "browser.inspect")
- url: str
- task_id: str
- dry_run: bool = False
- payload: Optional[dict]
```

**WorkerBrowserResponse**
```python
- success: bool
- action: str
- task_id: str
- browser_started: bool
- backend: str = "mock_playwright_worker"
- title: Optional[str]
- url: Optional[str]
- status: str = "ok"
- error_code: Optional[str]
- error_message: Optional[str]
- metadata: Optional[dict]
```

### 정책 (Policy) 정의

**허용 Action:**
- dry_run=True: browser.inspect만 허용
- dry_run=False: 모두 차단 (actual execution disabled)

**보안 정책:**
1. Task별 browser context 분리
2. Cookies/sessions 메모리 전용 (영속 저장 금지)
3. Screenshots/temp 파일 task 완료 후 삭제
4. 로그인/인증서 작업은 local_agent_backend 우선
5. Chromium만 지원 (Firefox/WebKit 미지원)

### Mock Backend 동작

**browser.inspect (dry_run=True)**
```
Input:  WorkerBrowserRequest(action="browser.inspect", url="https://example.com", dry_run=True)
Output: WorkerBrowserResponse(
  success=True,
  browser_started=False,
  backend="mock_playwright_worker",
  title="DRY_RUN_BROWSER_INSPECT",
  url="https://example.com",
  status="ok"
)
```

**browser.* (dry_run=False) — Actual execution disabled**
```
Input:  WorkerBrowserRequest(action="browser.inspect", dry_run=False)
Output: WorkerBrowserResponse(
  success=False,
  browser_started=False,
  error_code="ACTUAL_BROWSER_EXECUTION_NOT_ENABLED",
  error_message="Browser worker actual execution is not enabled..."
)
```

**Unknown Action**
```
Input:  WorkerBrowserRequest(action="browser.unknown")
Output: WorkerBrowserResponse(
  success=False,
  browser_started=False,
  error_code="UNKNOWN_BROWSER_ACTION",
  error_message="Browser action 'browser.unknown' is not supported"
)
```

---

## 동작 호환성

### browser.inspect dry_run=True 호환성
| 항목 | 상태 |
|------|------|
| **기존 동작 유지** | YES ✓ |
| **결과 형식 호환** | YES (BrowserResult 호환) ✓ |
| **mock_backend 호출** | YES ✓ |
| **네트워크 호출** | NO ✓ |

### browser.inspect dry_run=False (Actual)
| 항목 | 상태 |
|------|------|
| **안전 차단** | YES (ACTUAL_BROWSER_EXECUTION_NOT_ENABLED) ✓ |
| **에러 응답** | YES (success=False) ✓ |
| **기존 테스트 PASS** | YES ✓ |

### Unknown Action 처리
| 항목 | 상태 |
|------|------|
| **안전 차단** | YES (UNKNOWN_BROWSER_ACTION) ✓ |
| **에러 응답** | YES (success=False) ✓ |

### BrowserResult 호환성
```python
# Old schema (browser_tool/schemas.py)
BrowserResult(
  success: bool,
  action: str,
  data: dict,
  error: str,
  error_code: str,
  backend: str = "mock"
)

# Worker backend conversion
return BrowserResult(
  action=task.action,                    # "inspect" (without "browser." prefix)
  success=worker_response.success,
  data={
    "title": worker_response.title,
    "url": worker_response.url,
    "backend": worker_response.backend,  # "mock_playwright_worker"
    "browser_started": False,
  },
  error=worker_response.error_message or "",
  error_code=worker_response.error_code or "",
  backend="worker_playwright",           # New backend type
)
```

### 기존 local_agent dry_run 동작 유지
| 항목 | 상태 |
|------|------|
| **test_browser_tool_router.py** | 24 passed ✓ |
| **test_browser_inspect_action.py** | 10 passed ✓ |
| **test_browser_inspect_task_flow.py** | 9 passed ✓ |
| **test_browser_inspect_approval_policy.py** | 18 passed ✓ |

---

## 실행 제약 (금지 사항)

### Playwright/Browser 금지
| 항목 | 상태 |
|------|------|
| **Playwright import** | NO ✓ (새 파일에) |
| **browser launch** | NO ✓ |
| **playwright install** | NO ✓ |
| **sync/async_playwright** | NO ✓ |

### 운영/배포 금지
| 항목 | 상태 |
|------|------|
| **WebSocket 연결** | NO ✓ |
| **HTTP registration** | NO ✓ |
| **task 서버 생성** | NO ✓ |
| **result 서버 전송** | NO ✓ |
| **approval 변경** | NO ✓ |
| **DB write** | NO ✓ |

### 코드/배포 변경 금지
| 항목 | 상태 |
|------|------|
| **Dockerfile 수정** | NO ✓ |
| **docker-compose 수정** | NO ✓ |
| **requirements 변경** | NO ✓ |

---

## 검증 결과

### Compilation
```
✓ browser_worker/__init__.py
✓ browser_worker/schemas.py
✓ browser_worker/policy.py
✓ browser_worker/service.py
✓ browser_worker/backends/__init__.py
✓ browser_worker/backends/mock_playwright_backend.py
✓ browser_worker/app.py
✓ ai_orchestrator/browser_tool/backends/worker_backend.py
```

### Tests
```
✓ test_browser_worker_schemas.py              7 passed
✓ test_browser_worker_mock_backend.py         5 passed
✓ test_browser_tool_worker_backend.py         5 passed
✓ test_browser_tool_router.py                24 passed (existing)
✓ test_browser_inspect_action.py             10 passed (existing)
✓ test_browser_inspect_task_flow.py           9 passed (existing)
✓ test_browser_inspect_approval_policy.py    18 passed (existing)

Total: 78 tests passed
```

### Playwright Import Check
```
✓ No "sync_playwright" in new files
✓ No "async_playwright" in new files
✓ No "playwright.sync_api" in new files
✓ No "playwright.async_api" in new files
✓ No "chromium.launch" in new files
```

---

## 아키텍처 진화 경로

### BROWSER-WORKER-1 (현재단계)
- ✓ Browser Worker 최소 골격 구현
- ✓ Mock backend으로 dry_run만 지원
- ✓ 실제 프로세스/네트워크 호출 없음

### BROWSER-WORKER-2 (2주 후)
- Dockerfile 작성 (chromium 포함)
- docker-compose.yml에 browser-worker service 추가
- 배포 스크립트 작성

### BROWSER-WORKER-3 (4주 후)
- Browser Worker HTTP client 구현
- worker_backend.py의 _call_worker_http 완성
- Browser Tool Router → Worker 네트워크 연결

### BROWSER-INSTALL-2 (1주 후, 병렬)
- Dockerfile RUN python -m playwright install chromium --with-deps
- 이미지 빌드/테스트
- API 컨테이너에 chromium 설치 (단기 방식)

### BROWSER-7D (6주 후)
- 실제 browser.inspect 실행 활성화
- worker backend에서 actual browser operations 수행
- 스크린샷/DOM 저장 기능

### BROWSER-AUTH (8주 후)
- local_agent_backend로 로그인/인증 지원
- server_playwright_backend는 인증된 세션만 처리

---

## Browser Worker vs API 컨테이너 비교

### 이번 단계까지 (BROWSER-WORKER-1)
```
API Container (ai-orchestrator-api)
├── Browser Tool Router ✓
├── browser.inspect dry_run ✓
├── Worker Backend skeleton ✓
└── Chromium: 없음 (설치 예정)

Browser Worker (별도, 미배포)
├── Service + schemas
├── Mock backend
└── FastAPI app skeleton
```

### BROWSER-WORKER-2+ 이후
```
API Container (ai-orchestrator-api)
├── Browser Tool Router ✓
├── browser.inspect dry_run ✓
├── Worker Backend (HTTP client) ✓
└── Chromium: 없음 (또는 단기 방식)

Browser Worker Container (새로 추가)
├── Service + schemas ✓
├── Real Playwright backend
├── Chromium binary ✓
└── FastAPI app 실행
```

---

## 주요 설계 결정

### 1. Mock Backend 방식
**선택:** WorkerBrowserResponse 생성자를 factory method로 구현
**이유:** 
- 테스트 용이성
- 다양한 응답 타입 (success, actual_disabled, unknown_action) 통일
- 향후 HTTP 응답 변환 시 같은 구조 재사용

### 2. Service 함수 동기화
**선택:** async 대신 sync function 사용
**이유:**
- pytest-asyncio 의존성 추가 불필요
- 초기 단계에서는 네트워크 없으므로 동기만으로 충분
- 향후 HTTP client 추가 시 async 재도입 가능

### 3. BrowserResult 호환성
**선택:** data 필드에 worker 응답 정보 담기
**이유:**
- 기존 schema 수정 없음
- 향후 Router에서 필요한 정보 모두 접근 가능
- 호환성 보장

### 4. Worker Backend 위치
**선택:** ai_orchestrator/browser_tool/backends/worker_backend.py
**이유:**
- Router와 같은 패키지에 위치
- 다른 backend (mock, server_playwright, local_agent 등)과 같은 계층
- 향후 Router가 backend 선택 시 일관성 유지

---

## 보고서 메타데이터

| 항목 | 값 |
|------|-----|
| **보고서 경로** | docs/reports/browser_worker_1_separate_tool_skeleton.md |
| **secret 포함 여부** | No |
| **민감 정보** | None |
| **코드 수정** | No (기존 코드 유지) |
| **Dockerfile 수정** | No |
| **docker-compose 수정** | No |

---

## 최종 판정

### ✓ PASS

**구현 완료:**
1. ✓ Browser Worker schemas 정의 (WorkerBrowserRequest/Response)
2. ✓ Security policy 정의 (dry_run/actual 차단)
3. ✓ Mock Playwright backend 구현 (네트워크/실행 없음)
4. ✓ Browser Worker service 구현
5. ✓ FastAPI app skeleton (배포 미포함)
6. ✓ Browser Tool worker_backend client adapter
7. ✓ 3개 신규 test 파일 + 78개 테스트 모두 통과
8. ✓ 기존 browser.inspect dry_run 호환성 유지
9. ✓ Playwright import 제거 (새 파일에)
10. ✓ 실행/배포/Dockerfile 변경 금지 준수

**다음 단계:**
- BROWSER-WORKER-2: Dockerfile/compose 설계 (2주)
- BROWSER-WORKER-3: Worker HTTP client 구현 (4주)
- BROWSER-INSTALL-2: API 컨테이너 chromium 설치 (1주, 단기 방식)
- BROWSER-7D: 실제 browser 실행 활성화 (6주)
