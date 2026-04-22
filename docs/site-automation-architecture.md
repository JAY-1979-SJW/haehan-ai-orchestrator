# 사이트 자동화 아키텍처 (1단계 골격)

## 앱의 새 역할
haehan-ai-orchestrator 는 기존의 "승인형 AI 오케스트레이터" 역할을 유지한 채,
여러 외부 사이트에 대해 브라우저 기반 작업(조회/체크/다운로드/업로드)을
안전하게 수행할 수 있는 **운영 플랫폼**으로 확장된다.

이번 단계(1단계)는 실제 다양한 사이트 자동화를 붙이는 단계가 아니라,
**확장 가능한 최소 골격**을 만드는 단계다.

## 4계층 구조

| 계층 | 책임 | 주요 구성 |
|------|------|----------|
| A. Control Layer       | 사용자/권한/승인/감사 | FastAPI router, `auth.py` (RBAC), `audit_logger.py`, 기존 `/tasks`, `/approve`, `/reject`, `/webhooks/telegram` |
| B. Planning Layer      | 자연어 → 구조화 task | (이번 단계는 구조만, OpenAI 연동은 기존 유지) `target_site`, `action`, `params`, `risk_level`, `requires_approval` 필드 생성 |
| C. Browser Execution   | 사이트별 실제 브라우저 동작 | `ai_orchestrator/sites/` 패키지 — connector + Playwright wrapper (골격) |
| D. Security & Audit    | 자격증명/세션/로그 | `secrets_policy.py`, 감사 로그 확장 이벤트 타입 |

## Connector 구조

- 베이스: `ai_orchestrator/sites/connector.py` → `SiteConnector` ABC
  - `name` (class attr)
  - `supported_actions` (class attr)
  - `health_check() -> SiteHealthStatus`
  - `login_check() -> SiteHealthStatus` (기본은 health_check 재사용)
  - `dry_run(task) -> SiteExecutionResult`
  - `execute(task) -> SiteExecutionResult` (1단계는 `NOT_IMPLEMENTED` 반환이 기본)
- Registry: `ai_orchestrator/sites/registry.py` (모듈 로드 시 샘플 커넥터 자동 등록)
- 샘플 커넥터 2개:
  - `DummyConnector` — 외부 의존 없음, 구조 smoke 용
  - `ExamplePortalConnector` — 자격증명/세션 파일 존재 여부만 점검 (외부 접속 없음)

### 새 커넥터 추가 방법 (예정)
1. `ai_orchestrator/sites/connectors/<site>.py` 에 `SiteConnector` 구현
2. `registry._load_builtin` 에 등록 또는 런타임에서 `registry.register(instance)` 호출
3. 필요한 경우 `secrets/sites/<site>.env`, `secrets/browser_state/<site>.json` 준비 (커밋 금지)

## Site Health 개념

- `SiteHealthService.check_all()` / `check_one(name)` 으로 안전한 읽기성 점검 수행
- 필드: `state`, `configured`, `credentials_present`, `session_state_present`,
  `browser_launch_ok`, `login_check_status`, `latency_ms`, `warning`, `error`
- 상태 체계: `healthy | degraded | unavailable | unconfigured`
- **절대로 제출/수정/삭제 같은 상태 변경 동작을 수행하지 않는다.**

## 권한 정책

| 엔드포인트 | 허용 role |
|-----------|----------|
| `GET  /api/v1/connectors`        | admin, owner |
| `GET  /api/v1/site-health`       | admin, owner |
| `GET  /api/v1/site-health/{name}`| admin, owner |
| `POST /api/v1/site-tasks/dry-run`| operator, admin, owner |

- body 의 `role` / `requested_by` 등은 서버가 신뢰하지 않는다. 기존 스푸핑 방어 원칙 유지.
- 기존 `/tasks`, `/approve`, `/reject` 권한 게이트는 변경하지 않는다.

## 상태 모델 (승인형 통제 ↔ 브라우저 작업)

```
TaskRequest (기존)  ───▶  risk 평가 ───▶  (requires_approval이면) 토큰 발급 ───▶
     │
     └─▶ (사이트 연관) SiteTask(target_site, action, params, ...)
                               │
                               ├─ dry_run  → SiteExecutionResult(dry_run)
                               └─ execute  → (1단계는 NOT_IMPLEMENTED)
```

- 이번 단계에서는 Control Layer 와 Browser Layer 가 **명시적 상태 머신으로는 연결되지 않는다.**
  두 계층 사이 "dry_run 흐름" 만 우선 연결하고, 실제 execute 는 향후 단계에서 결합한다.
- 향후 durable execution / interrupt / resume 지원을 염두에 두고,
  모델은 재직렬화 가능한 단순 dataclass 로 둔다.

## 향후 로드맵 (5~10줄)

1. ExamplePortalConnector 외에 실제 운영 사이트별 커넥터 점진적 추가
2. `execute()` 에 대해 저위험 조회성 action 부터 허용 (read-only 우선)
3. 승인 토큰 ↔ SiteTask 연동: `requires_approval=true` 이면 `/approve` 통과 후에만 `execute` 허용
4. MFA/CAPTCHA/수동 개입 "대기 상태" 표현 (status=pending_user, resume 엔드포인트)
5. 스크린샷/로그 아티팩트를 audit 와 연동해 승인자에게 텔레그램으로 전달
6. 장기적으로 durable execution (LangGraph / 자체 상태 머신) 도입 검토 — 이번 단계에선 도입하지 않음
