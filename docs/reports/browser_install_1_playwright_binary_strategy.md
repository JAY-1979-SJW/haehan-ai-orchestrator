# BROWSER-INSTALL-1 Playwright browser binary 설치 전략

## 작업 개요
- 목표: ai-orchestrator-api 컨테이너의 Playwright browser binary 설치 전략 조사
- 범위: read-only 조사, 코드/Dockerfile/compose 수정 없음
- 결과물: 단기/장기 설치 권장안 + 다음 단계 지시문

---

## Repo Boundary Lock 준수
| 항목 | 상태 |
|------|------|
| **repo path** | /home/ubuntu/apps/haehan-ai-orchestrator |
| **branch** | master |
| **HEAD before** | c8a0461 |
| **origin/master** | c8a0461 |
| **working tree before** | clean |
| **다른 앱 접근 여부** | None (read-only 조사만) |

---

## 현재 상태

### API Service & Container
| 항목 | 현황 |
|------|------|
| **service name** | haehan-ai-orchestrator-api |
| **container status** | Up 4+ hours (healthy) |
| **image name** | haehan-ai-orchestrator-api:local |
| **container user** | root (default) |

### Dockerfile 현황
| 항목 | 값 |
|------|-----|
| **base image** | python:3.11-slim |
| **Python version** | 3.11 |
| **requirements.txt** | 설치됨 |
| **playwright install 명령** | 없음 ❌ |
| **PLAYWRIGHT_BROWSERS_PATH** | 설정 안 됨 |
| **browser cache volume** | 없음 |

### Playwright Package
| 항목 | 값 |
|------|-----|
| **설치 상태** | pip install -r requirements.txt로 설치됨 |
| **버전** | 1.58.0 |
| **위치** | /usr/local/lib/python3.11/site-packages |
| **browser binary 경로** | /root/.cache/ms-playwright |
| **실제 browser binary** | 없음 ❌ |

### docker-compose.yml 구조
| 항목 | 값 |
|------|-----|
| **volumes** | api_storage: /app/ai_orchestrator/storage |
| **browser cache volume** | 없음 |
| **read-only mount** | ./secrets/api:/run/secrets/api:ro (기존) |
| **restart policy** | unless-stopped |

---

## 설치 방식 후보 비교

### A. Docker Image Build 시 설치 (Dockerfile에 playwright install)
```
방식: Dockerfile RUN python -m playwright install chromium --with-deps
```

**장점:**
- ✓ 재현성 매우 높음 (컨테이너 생성 시 항상 일관된 상태)
- ✓ 클라우드 배포 환경에서도 같은 바이너리 보장
- ✓ 배포 후 런타임 의존성 없음
- ✓ 디버깅 시 환경 복제 용이

**단점:**
- ✗ 이미지 크기 증가 (약 500MB)
- ✗ 빌드 시간 증가 (약 2-3분)
- ✗ 바이너리 업데이트 시 이미지 재빌드 필요

**예상 영향:**
- 현재 이미지: ~200MB (python:3.11-slim + deps)
- 설치 후: ~700-800MB
- Docker registry 저장소 비용 증가 (미미)

---

### B. 런타임 Volume/Cache Install (초기 구동 시 playwright install)
```
방식: docker-compose에 browser cache volume 추가 후 시작 스크립트에서 설치
```

**장점:**
- ✓ 이미지 크기 유지
- ✓ 빌드 시간 유지
- ✓ 바이너리 캐시로 컨테이너 재생성 시 재설치 스킵 가능

**단점:**
- ✗ 초기 시작 시간 증가 (playwright install 대기)
- ✗ 초기화 스크립트 추가 필요 (docker entrypoint 변경)
- ✗ volume 손상 시 수동 재초기화 필요
- ✗ 멀티 노드 배포 시 각 노드마다 초기화 필요
- ✗ 운영 일관성 낮음

---

### C. 별도 Browser-Worker Image 분리
```
방식: haehan-ai-orchestrator-browser-worker 이미지 추가
```

**장점:**
- ✓ API 이미지 크기 유지
- ✓ browser-worker 확장/축소 독립 가능
- ✓ 장기적으로 가장 깔끔한 아키텍처

**단점:**
- ✗ 현재 단계에서 작업량 증가
- ✗ server_playwright_backend 구현 필요
- ✗ 네트워크 호출 오버헤드
- ✗ 배포 관리 복잡도 증가

**추천 시점:** BROWSER-ARCH-2B 이후

---

### D. System Chromium 사용
```
방식: apt-get install chromium-browser (system package)
```

**장점:**
- ✓ 이미지 크기 약간만 증가

**단점:**
- ✗ Playwright와 호환성 미확인
- ✗ OS 업데이트 시 버전 변경 가능성
- ✗ 권장도 낮음

**결론:** 미추천

---

## 단기 권장안 (BROWSER-INSTALL-2)

### 선택: A번 (Docker Image Build 시 설치)

**이유:**
1. **재현성:** 이미지만 있으면 어디서나 같은 상태 보장
2. **운영 안정성:** 초기화 스크립트/volume 관리 불필요
3. **MVP 기준:** 지금은 browser-worker 분리 불필요
4. **검증 용이:** 배포 후 setup 문제 없음

### 적용 절차 (BROWSER-INSTALL-2)

**Step 1: Dockerfile 수정**
```dockerfile
FROM python:3.11-slim

# apt dependency 추가 (chromium 필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libxdamage1 libxrandr2 \
    libpango-1.0-0 libpangoft2-1.0-0 libx11-6 libxext6 libxfixes3 \
    && rm -rf /var/lib/apt/lists/*

# ... 기존 내용 ...

# Playwright browser 설치 (chromium only)
RUN python -m playwright install chromium --with-deps
```

**Step 2: docker-compose 변경 없음**
- 기존 volume 유지
- entrypoint 변경 없음

**Step 3: 검증 명령**
```bash
docker build -t haehan-ai-orchestrator-api:local .
docker run --rm haehan-ai-orchestrator-api:local \
  python -c "from playwright.async_api import async_playwright; print('OK')"
```

**Step 4: 배포**
```bash
docker-compose up -d --build
```

### 이미지 크기 예상
| 단계 | 크기 |
|------|------|
| 현재 | ~300MB |
| apt deps 추가 | ~350MB |
| playwright install | ~750-800MB |
| 최종 | ~800MB |

---

## 장기 권장안 (BROWSER-ARCH-2B+)

### Browser Tool Router 체계에 맞춘 아키텍처

```
┌─────────────────────────────────┐
│ Browser Tool Router (완료)      │
│ (ai_orchestrator/browser_tool)  │
└────────────┬──────────────────┬─┘
             │                  │
    ┌────────▼────────┐  ┌──────▼──────────┐
    │ Server         │  │ Local Agent    │
    │ playwright     │  │ backend        │
    │ backend        │  │ (login/auth)   │
    └────────┬────────┘  └───────────────┘
             │
    ┌────────▼──────────────────────┐
    │ Browser Worker               │
    │ (별도 docker image)           │
    │ - chromium binary 포함        │
    │ - WebSocket 연결              │
    │ - task dispatch               │
    └───────────────────────────────┘
```

### 단계별 계획

| Phase | Task | 내용 | 예상 시점 |
|-------|------|------|----------|
| BROWSER-INSTALL-2 | Docker image chromium 설치 | Dockerfile 수정 | 2주 |
| BROWSER-ARCH-2B | server_playwright_backend 구현 | Router + WebSocket 연결 | 3주 |
| BROWSER-TOOL-1 | 기본 navigate/screenshot 지원 | browser.navigate, browser.screenshot | 4주 |
| BROWSER-WORKER | 별도 worker image 분리 | 다중 worker 확장 | 6주 |
| BROWSER-AUTH | 로그인/인증서 지원 | local_agent_backend 우선 | 8주 |

---

## 운영 및 보안 기준

### Task별 Browser Context 분리 원칙
```python
# ✓ 권장: 각 task마다 새로운 browser context
async def execute_browser_task(task_id, actions):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=f"/tmp/profile_{task_id}",
            extra_http_headers={...}
        )
        # task 실행
        await context.close()

# ❌ 금지: context 재사용 또는 공유
global_context = None  # 절대 금지
```

### Cookie/Session 저장 금지
```python
# ❌ 금지: 영속적 저장
context = await launch_persistent_context(user_data_dir="/data/persistent")

# ✓ 권장: 임시 메모리 저장
context = await browser.new_context(
    record_video_dir=None,  # 녹화 금지
    viewport={"width": 1920, "height": 1080}
)
```

### Screenshot/Temp 파일 관리
| 항목 | 경로 | 정책 |
|------|------|------|
| **screenshot** | /app/ai_orchestrator/storage/screenshots/{task_id}.png | task 완료 후 API 응답, 서버 삭제 |
| **temp profile** | /tmp/profile_{task_id} | context close 시 자동 삭제 |
| **DOM snapshot** | /tmp/dom_{task_id}.html | task 완료 후 삭제 |
| **console log** | /tmp/console_{task_id}.log | task 완료 후 삭제 |

### 로그인/인증서 필요 작업 처리
```
Rule: 로그인, 인증서, 세션 쿠키가 필요한 작업
      → local_agent_backend 우선
      → server_playwright_backend는 로그인 완료된 상태만 받음

예시:
✓ "G-Suite 파일 목록 조회" → local agent (로그인) → server playright (조회)
✓ "HWP 다운로드" → local agent (로그인 + CAD backend) → 파일 저장
❌ "로그인" → server playwright에서 직접 수행 금지
```

### Chromium만 설치 (Firefox/WebKit 제외)
```
이유:
- 기업 주요 서비스: Chrome 기반 테스트
- 메모리/이미지 크기: chromium만 ~200MB (full 설치 ~600MB)
- dependency 최소화: 보안 업데이트 부담 감소

playwright install chromium --with-deps  # ✓
playwright install                       # ❌ (firefox/webkit 불필요)
```

---

## 보안 고려사항

### Sandbox 의존성
```
Chromium 실행 환경 (Linux container):
- seccomp sandbox: 필수
- user namespace: root 실행 가능 (현재 상태)
- /dev/shm: 필요 (512MB 권장)
```

### Rootless 실행 가능성
```
현재: root 실행
향후: non-root 전환 검토
- 요구사항: playwright install 시 --with-deps 필수
- 영향: 컨테이너 보안 향상, 추가 setup 불필요
```

### 민감 정보 보호
| 항목 | 정책 |
|------|------|
| **API key** | task payload에 포함 금지 → secrets 별도 관리 |
| **Cookie** | context 메모리 전용 → 영속 저장 금지 |
| **Screenshot** | 개인정보 포함 가능 → task 완료 후 삭제 |
| **console log** | 민감 정보 노출 가능 → 암호화 저장 검토 |

---

## 다음 단계 제안

### Option 1: Docker Image 설치 → Backend 구현
**흐름:** BROWSER-INSTALL-2 → BROWSER-ARCH-2B

**BROWSER-INSTALL-2 (1주)**
- Dockerfile에 chromium 설치
- 이미지 빌드/푸시
- 배포

**BROWSER-ARCH-2B (2주)**
- server_playwright_backend 구현
- router와 backend 연결
- WebSocket task dispatch

### Option 2: Backend 먼저 구현 (Binary는 나중)
**흐름:** BROWSER-ARCH-2B (skeleton) → BROWSER-INSTALL-2

**장점:**
- Router와 backend 구조 먼저 검증
- Integration test 먼저 작성

**단점:**
- 실제 browser 테스트는 BROWSER-INSTALL-2 이후

---

## 검증 체크리스트 (BROWSER-INSTALL-2 예정)

```bash
# 빌드 확인
docker build -t haehan-ai-orchestrator-api:test .

# 이미지 크기 확인
docker images | grep haehan-ai-orchestrator-api

# Playwright import 확인
docker run --rm haehan-ai-orchestrator-api:test \
  python -c "import playwright; print('OK')"

# Chromium 존재 확인
docker run --rm haehan-ai-orchestrator-api:test \
  python -c "from playwright.async_api import async_playwright; print('OK')"

# 컨테이너 시작 후 헬스체크
docker-compose up -d --build
sleep 5
curl http://127.0.0.1:8400/api/v1/health

# 로그 확인
docker-compose logs ai-orchestrator-api | tail -20
```

---

## 보고서 메타데이터

| 항목 | 값 |
|------|-----|
| **보고서 경로** | docs/reports/browser_install_1_playwright_binary_strategy.md |
| **secret 포함 여부** | No |
| **민감 정보** | None |
| **코드 수정** | No |
| **Dockerfile 수정** | No |
| **docker-compose 수정** | No |

---

## 최종 판정

### ✓ PASS

**조사 결과 요약:**
1. ✓ Python Playwright 1.58.0 설치됨
2. ✓ Browser binary 미설치 (예상대로)
3. ✓ 현재 Dockerfile/compose 구조 파악
4. ✓ 단기 권장안 수립 (Docker image build install)
5. ✓ 장기 아키텍처 설계 (Browser Tool Router 연계)
6. ✓ 보안/운영 기준 정의
7. ✓ 다음 단계 명확화

**다음 작업:**
- BROWSER-INSTALL-2: Dockerfile 기반 chromium 설치
- BROWSER-ARCH-2B: server_playwright_backend 구현
