# 앱 골격 거버넌스 (App Foundation Governance)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_GOVERNANCE_LOCK_01  
상태: LOCKED — 이 문서의 레이어 구조와 의존성 방향은 게이트로 강제된다.

---

## 1. 표준 레이어 정의

| 레이어 | 번호 | 위치 예시 | 책임 |
|--------|------|----------|------|
| UI Layer | L1 | admin-web/, ui/ | 화면·사용자 입력만 담당. 업무 로직 없음. |
| API / Router Layer | L2 | ai_orchestrator/server/, browser_api/ | HTTP request/response dispatch만. SQL·업무로직 없음. |
| Command / Action Registry | L3 | agent/action_registry, scripts/ops/ | 실행 가능한 action 목록·risk metadata만. |
| Permission / Approval Gate | L4 | scripts/site_engine/execution_gate.py, scripts/*/gates.py | 실행 가능 여부 판단만. 실행 없음. |
| Workflow / Task Orchestration | L5 | ai_orchestrator/executor.py, ai_orchestrator/sites/runner.py | 상태 전이·작업 흐름 조합만. |
| Usecase / Service | L6 | ai_orchestrator/sites/adapters/, scripts/*/router.py | 업무 흐름 조합만. 저장소 직접 접근 없음. |
| Domain / Policy | L7 | scripts/site_engine/, scripts/*/profile.py, policies/ | 순수 정책·판정·검증만. 외부 I/O 없음. |
| Adapter / Site Engine | L8 | scripts/gabia/, scripts/hiworks/, scripts/g2b/ | 사이트별 경계만. 다른 사이트 직접 import 금지. |
| Local Agent / Browser Execution | L9 | agent/, local_agent/, ai_orchestrator/local_agent/ | 사용자 PC 실행 필요 작업만. 서버 사이드 금지. |
| Repository / Storage | L10 | ai_orchestrator/storage/, storage/ | 저장소 접근만. 업무 로직 없음. |
| Audit / Report / Evidence | L11 | docs/reports/, data/audit/, data/logs/ | 증거·결과 기록만. 실행 없음. |
| Test / Gate | L12 | tests/, tools/repo_gates/codebase_layer_audit.py | 구조 위반 차단. |

---

## 2. 의존성 방향 (허용)

```
L1 UI
 ↓
L2 API/Router
 ↓
L3 Action Registry
 ↓
L4 Permission/Approval Gate
 ↓
L5 Workflow/Task
 ↓
L6 Usecase/Service
 ↓
L7 Domain/Policy
 ↓
L8 Adapter/Site Engine
 ↓
L9 Local Agent/Browser
 ↓
L10 Repository/Storage
 ↓
L11 Audit/Report/Evidence
```

상위 → 하위만 허용. 하위 → 상위 금지.

---

## 3. 의존성 금지 규칙

| 금지 방향 | 이유 |
|----------|------|
| L7 Domain/Policy → L2 API/Router | 핵심 정책이 HTTP 계층에 의존 금지 |
| L7 Domain/Policy → L10 Repository | 순수 정책이 DB에 의존 금지 |
| L8 Adapter (사이트A) → L8 Adapter (사이트B) | 크로스 도메인 import 금지 (gabia↔hiworks↔eum 등) |
| L6 Usecase → L10 Repository 직접 | 반드시 L10 인터페이스 경유 |
| L2 Router → L10 Storage 직접 | Router에 SQL 작성 금지 |
| L9 Local Agent (서버 실행) | 서버에서 로컬 전용 작업 실행 금지 |

---

## 4. 각 레이어 책임 원칙

### L2 API/Router
- HTTP 처리만
- 업무 산식, DB 쿼리, 정책 판단 금지
- request 수신 → L3/L4로 위임 → response 반환만

### L4 Permission/Approval Gate
- 실행 가능 여부만 판단
- 실행 자체 없음
- gate 결과: ALLOWED / APPROVAL_REQUIRED / USER_DIRECT_REQUIRED / LOCAL_AGENT_REQUIRED / BLOCKED

### L7 Domain/Policy
- 순수 판정·검증·산식
- 환경변수 직접 접근 금지
- 외부 API 호출 금지
- DB 접근 금지

### L8 Adapter/Site Engine
- 사이트별 경계만 담당
- 다른 사이트(L8) 직접 import 금지
- 실제 브라우저/API 호출은 L9에 위임

### L9 Local Agent/Browser
- 사용자 PC에서만 실행 가능한 작업
- 서버 사이드 로그인 브라우저 실행 금지
- session/cookie/token 추출 금지

---

## 5. 현재 앱 골격 인벤토리

| 항목 | 위치 | 상태 |
|------|------|------|
| Frontend/Admin UI | admin-web/ (Next.js), ui/ | 존재 |
| Backend API | ai_orchestrator/server/, browser_api/ | 존재 |
| Site Routers | scripts/gabia/router.py, scripts/hiworks/router.py 등 | 존재 |
| Site Engine (L7/L8) | scripts/site_engine/ | 존재 |
| Local Agent / Browser | agent/, ai_orchestrator/local_agent/ | 존재 |
| Action Registry | agent/action_registry | 존재 |
| Approval Gate | scripts/site_engine/execution_gate.py | 존재 |
| Execution Guard | ai_orchestrator/execution_limits.py | 존재 |
| Workflow/Task | ai_orchestrator/sites/runner.py, executor.py | 존재 |
| Storage/Repository | ai_orchestrator/storage/, storage/ | 존재 |
| Audit/Log | data/audit/, data/logs/ | 존재 |
| Reports | docs/reports/, data/reports/ | 존재 |
| Tests | tests/, agent/tests/, ai_orchestrator/tests/ | 존재 |
| Ops Scripts | scripts/ops/ | 존재 |
| Architecture Docs | docs/architecture/ | 신규 생성 중 |

---

## 6. 강제 사항 (게이트로 구현 필요)

1. FORBIDDEN_IMPORT: 크로스 도메인 import 차단
2. CIRCULAR_IMPORT: 순환 import 차단
3. SECURITY_PATTERN: secret/token/password 출력 차단
4. FAT_SITE: 단일 파일 비대화 차단
5. ROUTER_THINNESS: router에 SQL/업무로직 없음 확인
6. STORAGE_BOUNDARY: repository 직접 접근 차단
7. SERVER_BROWSER_GUARD: 서버 사이드 로그인 브라우저 실행 차단
8. BLOCKED_SECRET_SESSION: session/cookie/token 추출 차단

---

## 7. 다음 기능은 이 골격 위에만 허용

- Gabia subdomain DNS assist
- G2B adapter boundary
- Hiworks workflow
- YouTube upload workflow
- Google Workspace adapter
- CAD/HWPX local agent
- 모든 신규 사이트 기능
