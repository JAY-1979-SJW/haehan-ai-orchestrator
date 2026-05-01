# BROWSER-WORKER-2 Browser Worker Dockerfile/compose 설계

## 작업 개요
- 목표: Browser Worker를 독립 컨테이너로 배포하는 Dockerfile/compose 설계
- 범위: 설계 문서 작성 (실제 수정은 BROWSER-WORKER-4에서)
- 결과물: Docker 배포 아키텍처 설계 + 다음 단계 지시문

---

## Repo Boundary Lock 준수
| 항목 | 상태 |
|------|------|
| **repo path** | /home/ubuntu/apps/haehan-ai-orchestrator |
| **branch** | master |
| **HEAD before** | 3f0bf66 |
| **origin/master** | 3f0bf66 |
| **working tree before** | clean |
| **다른 앱 접근 여부** | None (read-only 분석만) |

---

## 현재 구조 확인

### docker-compose.yml 구조
| 항목 | 값 |
|------|-----|
| **version** | 3.9 |
| **services** | ai-orchestrator-api, admin-web |
| **API service** | haehan-ai-orchestrator-api:8400 |
| **Dockerfile** | ./Dockerfile (root) |
| **volumes** | api_storage (named volume for /app/ai_orchestrator/storage) |
| **networks** | default, app_web (external), cad_quantity_default (external) |
| **restart policy** | unless-stopped |
| **healthcheck** | /api/v1/health (Python urllib) |

### API Dockerfile 현황
| 항목 | 값 |
|------|-----|
| **base image** | python:3.11-slim (~80MB) |
| **Python version** | 3.11 |
| **Playwright package** | 1.58.0 (via requirements.txt) |
| **browser binary** | 미설치 (playwright install 실행 안 됨) |
| **Playwright path** | /usr/local/lib/python3.11/site-packages |
| **EXPOSE port** | 8400 |
| **HEALTHCHECK** | /api/v1/health (Python urllib) |

### browser_worker package 구조
```
browser_worker/
├── __init__.py
├── schemas.py              (WorkerBrowserRequest/Response)
├── policy.py               (dry_run/actual policies)
├── service.py              (handle_browser_request)
├── app.py                  (FastAPI app skeleton)
└── backends/
    ├── __init__.py
    └── mock_playwright_backend.py
```

---

## Browser Worker Service 설계

### 서비스 기본 정보
| 항목 | 값 |
|------|-----|
| **service name** | browser-worker |
| **image name** | haehan-ai-orchestrator-browser-worker:local |
| **container name** | haehan-ai-orchestrator-browser-worker |
| **internal port** | 8500 |
| **external exposure** | NO (내부 docker network만) |
| **restart policy** | unless-stopped |

### Dockerfile 후보 비교

#### 후보 A: python:3.11-slim 기반 (권장)
```dockerfile
FROM python:3.11-slim

# apt dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libxdamage1 libxrandr2 \
    libpango-1.0-0 libpangoft2-1.0-0 libx11-6 libxext6 libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir playwright>=1.40.0

# Install browser binary in BROWSER-INSTALL-2+
# RUN python -m playwright install chromium --with-deps

COPY browser_worker/ ./browser_worker/

EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8500/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "browser_worker.app:app", "--host", "0.0.0.0", "--port", "8500"]
```

**장점:**
- ✓ 최소 크기 (python:3.11-slim 기반)
- ✓ Dockerfile으로 재현성 높음
- ✓ 조직 통일: API와 같은 기본 이미지
- ✓ 커스텀 최소화

**단점:**
- apt deps 관리 필요
- playwright install 시간 (약 2-3분)

#### 후보 B: mcr.microsoft.com/playwright/python 기반
```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.58.0-focal

WORKDIR /app

COPY browser_worker/ ./browser_worker/
COPY requirements.txt .

RUN pip install --no-cache-dir fastapi uvicorn

EXPOSE 8500

# Chromium already pre-installed
# HEALTHCHECK ...
```

**장점:**
- ✓ Playwright deps 이미 포함
- ✓ 빌드 시간 단축
- ✓ 호환성 보장 (공식 이미지)

**단점:**
- ✗ 이미지 크기 더 큼 (~800MB+)
- ✗ Microsoft 의존성 (버전 추적 필요)

#### 후보 C: API image 재사용 + browser binary
```dockerfile
FROM haehan-ai-orchestrator-api:base

WORKDIR /app

# Copy only browser_worker package
COPY browser_worker/ ./browser_worker/

# Modify entrypoint to use browser_worker
CMD ["uvicorn", "browser_worker.app:app", "--host", "0.0.0.0", "--port", "8500"]
```

**장점:**
- ✓ 이미지 공유로 저장소 효율
- ✓ 일관된 환경

**단점:**
- ✗ API와 밀접한 결합
- ✗ 유지보수 복잡도 증가
- ✗ 스케일링 시 어려움

### 권장 선택: 후보 A (python:3.11-slim)
**이유:**
1. 최소 크기와 빌드 시간의 균형
2. 재현성과 명확성
3. 향후 커스텀 최적화 가능
4. 별도 서비스로 독립성 보장

---

## Compose 서비스 설계

### browser-worker service 정의 (설계)
```yaml
browser-worker:
  build:
    context: .
    dockerfile: docker/browser-worker.Dockerfile
  image: haehan-ai-orchestrator-browser-worker:local
  container_name: haehan-ai-orchestrator-browser-worker
  working_dir: /app
  command: ["uvicorn", "browser_worker.app:app", "--host", "0.0.0.0", "--port", "8500"]
  
  # 내부 통신만 — 외부 공개 금지
  # ports: (없음 — docker network 내부만)
  
  environment:
    BROWSER_WORKER_MODE: server
    BROWSER_WORKER_ALLOW_EXTERNAL_URLS: "false"
    PLAYWRIGHT_BROWSERS_PATH: /ms-playwright
    PYTHONDONTWRITEBYTECODE: "1"
    PYTHONUNBUFFERED: "1"
  
  volumes:
    # temporary directory for browser cache (not persistent)
    - /dev/shm:/dev/shm:rw
    # DO NOT add persistent volumes for screenshots/cookies
  
  restart: unless-stopped
  
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8500/health',timeout=3).status==200 else 1)"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 10s
  
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
  
  networks:
    - default  # docker-compose 내부 네트워크만
  
  # Resource limits (권장)
  deploy:
    resources:
      limits:
        cpus: "2"
        memory: 2G
      reservations:
        cpus: "1"
        memory: 1G
```

### 네트워크 정책
| 항목 | 정책 |
|------|------|
| **expose** | 내부 docker network만 (default) |
| **external access** | 금지 (API에서만 접근) |
| **API와의 호출** | docker network DNS (browser-worker:8500) |

---

## 통신 설계

### API → Browser Worker 호출 흐름 (BROWSER-WORKER-3+)

```
[Browser Tool Router]
    ↓ (BrowserTask)
[BrowserWorkerBackend.execute()]
    ↓ (WorkerBrowserRequest)
HTTP POST http://browser-worker:8500/v1/browser/inspect
    ↓
[Browser Worker FastAPI]
    ↓
[browser_worker.service.handle_browser_request()]
    ↓
[MockPlaywrightBackend / RealPlaywrightBackend]
    ↓ (WorkerBrowserResponse)
HTTP 200 JSON response
    ↓
[BrowserWorkerBackend._convert_to_browser_result()]
    ↓ (BrowserResult)
[Browser Tool Router] → [local_agent/actions.py]
```

### 엔드포인트 설계

**GET /health**
```
Request: (none)
Response: {"status": "ok", "worker": "browser_worker"}
Timeout: 3s
```

**POST /v1/browser/inspect**
```
Request: {
  "action": "browser.inspect",
  "url": "https://example.com",
  "task_id": "task-001",
  "dry_run": true,
  "payload": {...}
}

Response: {
  "success": true,
  "action": "browser.inspect",
  "task_id": "task-001",
  "browser_started": false,
  "backend": "mock_playwright_worker",
  "title": "DRY_RUN_BROWSER_INSPECT",
  "url": "https://example.com",
  "status": "ok"
}

Timeout: 30s (dry_run), 300s (actual)
```

### 보안 & 검증 정책

| 항목 | 정책 |
|------|------|
| **URL validation** | http/https scheme만 (file:// 금지) |
| **URL allowlist** | 기본값: 모두 허용. 추후 denylist 추가 가능 |
| **request_id/task_id** | 로깅/추적용으로 전달 |
| **secret/token** | request payload에 포함 금지 (policy.py에서 차단) |
| **cookies** | request/response에 포함 금지 |
| **session** | 메모리 전용 (영속 저장 금지) |

---

## 보안 & 운영 정책

### Browser Context 분리
```python
# Task별 독립 context (권장)
async def execute_inspect(task_id, url):
    browser_context = await browser.new_context(
        user_data_dir=f"/tmp/profile_{task_id}",
    )
    # 작업 수행
    await browser_context.close()  # 자동 삭제
```

### Screenshot/Temp 파일 정책
| 항목 | 정책 |
|------|------|
| **screenshot 저장** | /tmp/screenshot_{task_id}.png (임시) |
| **응답 후** | base64 인코딩 → response.data |
| **파일 삭제** | task 완료 직후 자동 삭제 |
| **persistent volume** | 절대 금지 |

### Cookie/Session 정책
| 항목 | 정책 |
|------|------|
| **persistent profile** | 금지 |
| **cookie jar** | 메모리 전용 |
| **session storage** | 메모리 전용 |
| **로그인 필요 작업** | local_agent_backend 우선 |

### 리소스 제한 (권장)
```yaml
deploy:
  resources:
    limits:
      cpus: "2"
      memory: 2G
    reservations:
      cpus: "1"
      memory: 1G
```

**이유:**
- Chromium은 메모리 사용량이 높음 (500MB~1GB per context)
- CPU: inspect/DOM parsing (2-core 충분)
- 여러 task 동시 실행 시 resource starvation 방지

---

## 구현 계획 및 타이밍

### BROWSER-WORKER-2 (현재단계)
- ✓ 설계 문서 작성
- ✓ 아키텍처 확정
- ✓ 보고서 작성

### BROWSER-WORKER-3 (3주 후)
- Worker HTTP client 구현 (BrowserWorkerBackend._call_worker_http)
- timeout/retry 정책
- error handling

### BROWSER-WORKER-4 (4주 후)
- Dockerfile 생성 (docker/browser-worker.Dockerfile)
- docker-compose.yml에 service 추가
- healthcheck 엔드포인트 구현

### BROWSER-INSTALL-2 (병렬, 1주 후)
- **API 컨테이너 (보류/비권장):**
  - python -m playwright install chromium (API Dockerfile에)
  - 이미지 크기: 800MB
  - 단기방식: MVP 검증용만
  
- **Browser Worker (권장):**
  - python -m playwright install chromium (worker Dockerfile에)
  - 이미지 크기: 700MB (API와 분리)
  - 장기방식: 운영 표준

### BROWSER-7D (6주 후)
- Real Playwright backend 구현
- browser.inspect 실제 실행
- screenshot/DOM snapshot 기능

---

## 아키텍처 다이어그램

### 현재 (BROWSER-WORKER-1)
```
API Container (8400)
├─ Browser Tool Router ✓
├─ browser.inspect (dry_run) ✓
├─ WorkerBackend (mock) ✓
└─ Playwright package (1.58.0, binary 미설치)

Browser Worker (skeleton)
├─ Service + schemas ✓
├─ Mock backend ✓
└─ FastAPI app (미배포)
```

### BROWSER-WORKER-4 이후
```
API Container (8400, default + app_web + cad_quantity networks)
├─ Browser Tool Router ✓
├─ browser.inspect (request → HTTP)
├─ WorkerBackend (HTTP client) ✓
└─ Playwright (package only, no binary)

Browser Worker Container (8500, default network only)
├─ Service + schemas
├─ Real/Mock Playwright backend
├─ Chromium binary ✓
└─ FastAPI app (실행중)

[docker network: default]
    API ←→ Browser Worker
    
[external: app_web, cad_quantity_default]
    API ←→ nginx, CAD backend
```

---

## 다음 단계 지시문 후보

### BROWSER-WORKER-3 지시문
```
[BROWSER-WORKER-3 Worker HTTP Client]

목표: BrowserWorkerBackend._call_worker_http 구현

구현:
1. BrowserWorkerBackend.use_local_service = False로 전환
2. _call_worker_http 메서드 구현
   - httpx.AsyncClient 사용 (또는 requests sync)
   - timeout: dry_run=30s, actual=300s
   - retry: exponential backoff (3 retries)
3. health check endpoint 호출
4. error handling: ConnectionError, Timeout, HTTP error

테스트:
- mock worker에 HTTP 요청 (uvicorn 테스트 서버)
- timeout 검증
- error response 검증

금지:
- worker container 실제 실행 금지
- docker build/up 금지
- uvicorn 실제 포트 바인딩 금지 (테스트 서버만)
```

### BROWSER-WORKER-4 지시문
```
[BROWSER-WORKER-4 Docker Deploy Setup]

목표: Dockerfile/compose 실제 추가

구현:
1. docker/browser-worker.Dockerfile 생성
   - python:3.11-slim base
   - apt deps (chromium sandbox)
   - browser_worker 패키지만 COPY
   - healthcheck: GET /health
   - CMD: uvicorn ...
   
2. docker-compose.yml에 browser-worker service 추가
   - image: haehan-ai-orchestrator-browser-worker:local
   - port 8500 (expose, 외부 공개 금지)
   - environment: BROWSER_WORKER_MODE, PLAYWRIGHT_BROWSERS_PATH
   - volume: /dev/shm only (cookies 영속 금지)
   - network: default only
   - resource limits: 2CPU, 2GB memory
   
3. docker build 테스트
   - 이미지 크기 확인 (700MB 예상)
   - healthcheck 엔드포인트 확인
   - API와의 docker network 연결 확인

금지:
- playwright install은 BROWSER-INSTALL-2에서
- chromium 설치는 BROWSER-INSTALL-2에서
- docker-compose up은 테스트 단계에서만
```

### BROWSER-INSTALL-2 지시문
```
[BROWSER-INSTALL-2 Browser Binary Installation]

목표: Chromium 설치

권장안 (선택):
A. Browser Worker image만 설치
   - docker/browser-worker.Dockerfile에 playwright install
   - RUN python -m playwright install chromium --with-deps
   - 이미지 크기: 700MB + 200MB = 900MB
   - 권장도: ★★★★★ (최고)

B. API 컨테이너도 설치 (비권장)
   - Dockerfile에 playwright install
   - 이미지 크기: 300MB + 500MB = 800MB
   - 이유: browser-worker 분리 정책 위배
   - 권장도: ★☆☆☆☆ (미권장)

선택: A 권장 (browser-worker image만)
```

---

## 설계 검토 체크리스트

### 아키텍처
- ✓ Browser Worker는 독립 컨테이너
- ✓ API와는 docker network으로만 통신
- ✓ 외부 포트 공개 금지
- ✓ 다른 서비스와 독립성

### 보안
- ✓ cookie/session persistent volume 없음
- ✓ task별 context 분리
- ✓ screenshot/temp 자동 삭제
- ✓ URL allowlist/denylist 가능
- ✓ 로그인은 local_agent 우선

### 운영성
- ✓ healthcheck 엔드포인트
- ✓ resource limits 설정
- ✓ 로깅 정책 통일
- ✓ restart policy 통일

### 확장성
- ✓ 다중 worker 인스턴스 가능
- ✓ 로드 밸런싱 가능 (향후)
- ✓ 독립적 스케일링

---

## 보고서 메타데이터

| 항목 | 값 |
|------|-----|
| **보고서 경로** | docs/reports/browser_worker_2_docker_compose_design.md |
| **secret 포함 여부** | No |
| **민감 정보** | None |
| **코드 수정** | No |
| **Dockerfile 수정** | No |
| **docker-compose 수정** | No |

---

## 최종 판정

### ✓ PASS

**설계 완료:**
1. ✓ Browser Worker Dockerfile 후보 3개 제시
2. ✓ 권장안 선택 (python:3.11-slim)
3. ✓ docker-compose.yml browser-worker service 설계
4. ✓ 네트워크/포트/healthcheck 정책
5. ✓ 통신 구조 설계 (API → worker HTTP)
6. ✓ 보안/운영 정책 확정
7. ✓ 구현 계획 수립
8. ✓ 다음 단계 지시문 초안 작성

**다음 단계:**
- BROWSER-WORKER-3: Worker HTTP client 구현 (3주)
- BROWSER-WORKER-4: Dockerfile/compose 실제 추가 (4주)
- BROWSER-INSTALL-2: Chromium 설치 (병렬, 1주)
- BROWSER-7D: 실제 browser 실행 (6주)
