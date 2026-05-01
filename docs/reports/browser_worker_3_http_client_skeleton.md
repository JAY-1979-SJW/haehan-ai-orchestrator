# BROWSER-WORKER-3 Browser Worker HTTP client skeleton 연결

## 작업 개요
- 목표: Browser Tool Router가 향후 별도 browser-worker service를 HTTP로 호출할 수 있는 client skeleton 구현
- 범위: HTTP client skeleton 구현 (실제 네트워크 호출은 테스트에서만 mock으로 검증)
- 결과물: BrowserWorkerClient + router backend 처리 + 17개 추가 테스트

---

## Repo Boundary Lock 준수
| 항목 | 상태 |
|------|------|
| **repo path** | /home/ubuntu/apps/haehan-ai-orchestrator |
| **branch** | master |
| **HEAD before** | 4958fd6 |
| **origin/master** | 4958fd6 |
| **working tree before** | clean |
| **다른 앱 접근 여부** | None (HTTP client skeleton만) |

---

## 구현 내용

### 생성/수정 파일

**수정 파일:**
1. `ai_orchestrator/browser_tool/backends/worker_backend.py`
   - BrowserWorkerClient 클래스 추가 (HTTP client)
   - BrowserWorkerBackend 확장 (worker_client 주입)
   - _call_worker_http 구현

2. `ai_orchestrator/browser_tool/router.py`
   - BrowserWorkerBackend import 추가
   - backend="worker" 요청 처리 로직 추가

3. `tests/test_browser_tool_worker_backend.py`
   - MockTransport 클래스 추가
   - TestBrowserWorkerClient 클래스 추가 (6개 테스트)
   - TestBrowserWorkerBackend 확장 (HTTP 테스트 추가)

**생성 파일:** None (기존 파일만 수정)

### BrowserWorkerClient 구조

```python
class BrowserWorkerClient:
    """HTTP client for Browser Worker service."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
        transport_fn: Optional[Callable] = None,
    ):
        # base_url: http://browser-worker:8500 (default)
        # timeout: 30s (default)
        # transport_fn: test용 mock transport 주입 가능
    
    def call_inspect(request: WorkerBrowserRequest) -> WorkerBrowserResponse:
        # 실제 네트워크 호출 또는 mock transport 사용
    
    def _http_post_inspect(request) -> WorkerBrowserResponse:
        # httpx를 사용한 실제 HTTP POST 구현
    
    @staticmethod
    def _timeout_response(request) -> WorkerBrowserResponse:
    @staticmethod
    def _unavailable_response(request) -> WorkerBrowserResponse:
    @staticmethod
    def _bad_response_error(request) -> WorkerBrowserResponse:
```

### Router backend="worker" 처리

**router.py 수정:**
```python
if selected_backend == "worker":
    worker_backend = BrowserWorkerBackend()
    url = params.get("url", "about:blank")
    task_id = params.get("task_id", f"task-{id(task)}")
    dry_run = params.get("dry_run", True)
    try:
        return worker_backend.execute(task, url, task_id, dry_run)
    except Exception as e:
        return BrowserResult(error_code="BROWSER_WORKER_ERROR", ...)
else:
    # Default to mock backend
    return mock_backend.handle_task(task)
```

**요청 흐름:**
1. BrowserTask(backend="worker", action="inspect", params={...})
2. route_browser_task()
3. BrowserWorkerBackend.execute()
4. BrowserWorkerClient.call_inspect() (HTTP 또는 mock)
5. WorkerBrowserResponse → BrowserResult

### base_url 기본값 및 환경변수

| 항목 | 값 |
|------|-----|
| **기본값** | http://browser-worker:8500 |
| **환경변수** | BROWSER_WORKER_URL |
| **타임아웃** | 30초 (커스터마이징 가능) |

**우선순위:**
1. 생성자 argument base_url (최우선)
2. 환경변수 BROWSER_WORKER_URL
3. 기본값 http://browser-worker:8500

### Transport 분리

**Production (실제 네트워크 호출):**
```python
client = BrowserWorkerClient()
response = client.call_inspect(request)
# httpx를 사용한 실제 HTTP 호출
```

**Testing (Mock transport):**
```python
mock_transport = MockTransport(response)
client = BrowserWorkerClient(transport_fn=mock_transport)
response = client.call_inspect(request)
# mock_transport 함수 호출
```

---

## 동작 정책

### dry_run 정책

| 시나리오 | 처리 |
|---------|------|
| **backend 미지정 + dry_run=True** | 기존 mock backend 사용 ✓ |
| **backend="worker" + dry_run=True** | worker HTTP 호출 (mock response) ✓ |
| **dry_run=False** | actual execution disabled (정책상) ✓ |

### Error Handling

| 에러 | error_code | 메시지 |
|------|-----------|--------|
| **Timeout** | BROWSER_WORKER_TIMEOUT | Request timeout |
| **Unavailable** | BROWSER_WORKER_UNAVAILABLE | Service unavailable |
| **Bad Response** | BROWSER_WORKER_BAD_RESPONSE | Invalid response format |
| **Unknown Action** | UNKNOWN_BROWSER_ACTION | (기존) |
| **Exception** | BROWSER_WORKER_ERROR | (새로운) |

### 기존 Mock Backend 호환성

| 항목 | 상태 |
|------|------|
| **backend 미지정 + dry_run=True** | 기존 동작 유지 ✓ |
| **mock backend 결과** | 변경 없음 ✓ |
| **existing tests** | 모두 통과 ✓ |

---

## 실행 차단 확인

### Playwright/Browser 금지
| 항목 | 상태 |
|------|------|
| **Playwright import** | NO ✓ (새 파일) |
| **browser launch** | NO ✓ |
| **playwright install** | NO ✓ |
| **Chromium install** | NO ✓ |

### 운영/배포 금지
| 항목 | 상태 |
|------|------|
| **실제 HTTP worker 호출** | NO ✓ (테스트에서만 mock) |
| **docker-compose 수정** | NO ✓ |
| **Dockerfile 수정** | NO ✓ |
| **docker build/restart** | NO ✓ |
| **WebSocket 연결** | NO ✓ |

---

## 검증 결과

### py_compile
```
✓ ai_orchestrator/browser_tool/backends/worker_backend.py
✓ ai_orchestrator/browser_tool/router.py
✓ ai_orchestrator/browser_tool/policy.py
✓ browser_worker/schemas.py
✓ browser_worker/service.py
```

### 테스트 결과
```
✓ test_browser_tool_worker_backend.py          12 passed
✓ test_browser_tool_router.py                  24 passed
✓ test_browser_worker_schemas.py                7 passed
✓ test_browser_worker_mock_backend.py           5 passed
✓ test_browser_inspect_action.py               10 passed
✓ test_browser_inspect_task_flow.py             9 passed
✓ test_browser_inspect_approval_policy.py      18 passed

Total: 85 tests passed
```

### Playwright Import Check
```
✓ sync_playwright: NOT FOUND
✓ async_playwright: NOT FOUND
✓ playwright.sync_api: NOT FOUND
✓ playwright.async_api: NOT FOUND
✓ chromium.launch: NOT FOUND
```

### 실제 네트워크 호출 확인
```
✓ 테스트 중 실제 http://browser-worker:8500 호출 없음
✓ 모든 HTTP 호출은 MockTransport 또는 mock로 대체됨
```

---

## 아키텍처 진화

### BROWSER-WORKER-3 (현재)
```
API Container (8400)
├─ Browser Tool Router
│  ├─ backend="mock" → mock_backend (기존)
│  └─ backend="worker" → BrowserWorkerBackend
│      ├─ use_local_service=True → handle_browser_request (로컬)
│      └─ use_local_service=False → BrowserWorkerClient (HTTP)
│          ├─ transport_fn → MockTransport (테스트)
│          └─ httpx → http://browser-worker:8500 (미래)

Browser Worker (미배포)
├─ Service + schemas
└─ FastAPI app skeleton
```

### BROWSER-WORKER-4 이후
```
API Container (8400)
└─ Browser Tool Router
   └─ backend="worker" → HTTP POST http://browser-worker:8500

Browser Worker Container (8500)
├─ FastAPI app
├─ browser_worker.service
├─ Real/Mock backend
└─ Playwright (이후 Chromium 포함)
```

---

## 다음 단계

### BROWSER-WORKER-4 (4주)
```
목표: Dockerfile/compose 실제 추가

구현:
1. docker/browser-worker.Dockerfile 생성
2. docker-compose.yml에 browser-worker service 추가
3. docker build / docker-compose up 테스트
4. healthcheck 엔드포인트 확인
```

### BROWSER-INSTALL-2 (병렬, 1주)
```
목표: Chromium 설치

선택: Browser Worker image (권장)
- docker/browser-worker.Dockerfile에 playwright install
- RUN python -m playwright install chromium --with-deps
```

### BROWSER-7D (6주)
```
목표: 실제 browser.inspect 실행

구현:
1. Real Playwright backend 추가
2. browser.inspect dry_run=False 활성화
3. screenshot/DOM 저장 기능
4. smoke test 추가
```

---

## 주요 설계 결정

### 1. HTTP Client Framework 선택: httpx
**이유:**
- 이미 dependencies에 포함 (httpx>=0.27.0)
- 동기/비동기 모두 지원 (향후 확장 가능)
- error handling 명확함

### 2. Transport 분리
**이유:**
- 테스트에서 실제 네트워크 호출 차단
- mock transport 쉽게 주입 가능
- production과 test mode 깔끔하게 분리

### 3. Router backend 필드 처리
**이유:**
- BrowserTask.backend 필드 활용 (이미 설계됨)
- 기존 동작 변경 없음 (backward compatible)
- 명시적 요청에만 worker 사용

### 4. Error 코드 추가
**새로운 error_code:**
- BROWSER_WORKER_TIMEOUT
- BROWSER_WORKER_UNAVAILABLE
- BROWSER_WORKER_BAD_RESPONSE
- BROWSER_WORKER_ERROR

**기존 코드 유지:**
- UNKNOWN_BROWSER_ACTION
- ACTUAL_BROWSER_EXECUTION_NOT_ENABLED
- BROWSER_ACTION_BLOCKED

---

## 보고서 메타데이터

| 항목 | 값 |
|------|-----|
| **보고서 경로** | docs/reports/browser_worker_3_http_client_skeleton.md |
| **secret 포함 여부** | No |
| **민감 정보** | None |
| **코드 수정** | Yes (2개 파일) |
| **테스트 추가** | Yes (12개 새 테스트) |
| **Dockerfile 수정** | No |
| **docker-compose 수정** | No |

---

## 최종 판정

### ✓ PASS

**구현 완료:**
1. ✓ BrowserWorkerClient HTTP client skeleton
2. ✓ httpx 기반 _http_post_inspect() 구현
3. ✓ timeout/unavailable/bad_response error handling
4. ✓ BrowserWorkerBackend.execute() HTTP 지원
5. ✓ router.py backend="worker" 처리
6. ✓ 12개 신규 테스트 추가
7. ✓ 85개 전체 테스트 통과
8. ✓ 기존 mock backend 호환성 유지
9. ✓ 실제 HTTP 호출 차단 (mock transport)
10. ✓ Playwright import 제거

**다음 단계:**
- BROWSER-WORKER-4: Dockerfile/compose 실제 추가 (4주)
- BROWSER-INSTALL-2: Chromium 설치 (병렬 1주)
- BROWSER-7D: 실제 browser 실행 (6주)
