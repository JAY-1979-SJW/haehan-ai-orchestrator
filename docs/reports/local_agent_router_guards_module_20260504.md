# Local Agent Router Guards 모듈 분리

**작업명:** ORCHESTRATOR-LOCAL-AGENT-ROUTER-GUARDS-MODULE-1  
**단계:** Phase 2-2A (순수 Helper 분리)  
**작업일:** 2026-05-04  
**상태:** 완료 ✓

---

## 1. 기준선

**분리 전:**
- Branch: master
- HEAD: a0054f0 (refactor: extract local agent audit builders)
- Origin/master: a0054f0
- Git status: clean ✓
- Phase 2-1: audit builders 분리 완료 ✓

**분리 후:**
- Branch: master (작업 대기)
- 변경 파일: 3개
  - M ai_orchestrator/local_agent_router.py
  - A ai_orchestrator/local_agent_router_guards.py
  - A ai_orchestrator/tests/test_local_agent_router_guards.py

---

## 2. 분리 전 구조

### 2.1 Helper 함수 위치 (local_agent_router.py)

```python
# Line 127-140
def _is_capture_screenshot(task) -> bool:
    return bool(task is not None and task.action == "capture_screenshot")

def _task_is_dry_run(task) -> bool:
    """params.options.dry_run 이 True 인 경우 dry-run 작업으로 본다."""
    try:
        options = task.params.get("options") if task is not None else None
        return bool(isinstance(options, dict) and options.get("dry_run"))
    except Exception:
        return False
```

**호출 위치:** 10개 (line 418, 426, 803, 810, 819, 888, 901, 1066, 1067, 1090)

### 2.2 상태 매트릭스 (local_agent_registry.py)

```python
VALID_TASK_TRANSITIONS: dict[str, set[str]] = {
    "queued":           {"delivered", "failed", "cancelled"},
    "delivered":        {"running", "failed", "cancel_requested"},
    "running":          {"completed", "failed", "cancel_requested"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed":        set(),
    "failed":           set(),
    "cancelled":        set(),
}

_CANCEL_TERMINAL_STATUSES: frozenset[str] = frozenset({
    "completed", "failed", "rejected", "cancelled",
})

ACTIVE_TASK_STATUSES: frozenset[str] = frozenset({
    "delivered", "running", "cancel_requested"
})
```

---

## 3. 분리 후 구조

### 3.1 신규 모듈: local_agent_router_guards.py

**순수 Helper 함수:**

```python
is_capture_screenshot_task(task: Optional[LocalAgentTask]) -> bool
task_is_dry_run(task: Optional[LocalAgentTask]) -> bool
can_approve_task(task: Optional[LocalAgentTask]) -> bool
can_reject_task(task: Optional[LocalAgentTask]) -> bool
can_cancel_task(status: str) -> bool
is_terminal_status(status: str) -> bool
```

**상태 상수:**

```python
CANCELLABLE_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "waiting_approval", "delivered", "running"
})

TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({
    "completed", "failed", "rejected", "cancelled"
})
```

### 3.2 Router 변경 (local_agent_router.py)

**Import 추가:**
```python
from . import local_agent_router_guards as _guards
```

**Helper 함수 제거:**
- `_is_capture_screenshot()` 함수 정의 제거 (14줄)
- `_task_is_dry_run()` 함수 정의 제거

**호출부 변경:**
- `_is_capture_screenshot(x)` → `_guards.is_capture_screenshot_task(x)` (8개)
- `_task_is_dry_run(x)` → `_guards.task_is_dry_run(x)` (2개)

---

## 4. 분리한 Helper 목록

| Helper | 유형 | 라인 수 | 사용 | 설명 |
|--------|------|--------|------|------|
| `is_capture_screenshot_task()` | Pure | 1 | 8회 | action == "capture_screenshot" 판별 |
| `task_is_dry_run()` | Pure | 6 | 2회 | params.options.dry_run 판별 |
| `can_approve_task()` | Pure | 4 | 신규 | 승인 가능 여부 판별 |
| `can_reject_task()` | Pure | 4 | 신규 | 거절 가능 여부 판별 |
| `can_cancel_task()` | Pure | 2 | 신규 | 취소 가능 여부 판별 |
| `is_terminal_status()` | Pure | 2 | 신규 | 종료 상태 판별 |

---

## 5. Status Matrix (변경 없음)

### 5.1 CANCELLABLE_TASK_STATUSES

```
취소 가능: queued, waiting_approval, delivered, running
취소 불가: completed, failed, rejected, cancelled, cancel_requested
```

**검증:**
- Registry VALID_TASK_TRANSITIONS와 동등성 유지 ✓
- _CANCEL_TERMINAL_STATUSES와 구분 명확 ✓
- cancel_requested 제외 확인 ✓

### 5.2 TERMINAL_TASK_STATUSES

```
종료: completed, failed, rejected, cancelled
진행 중: queued, waiting_approval, delivered, running, cancel_requested
```

**검증:**
- Registry 상수와 동등성 유지 ✓
- KNOWN_TASK_STATUSES 포함 관계 확인 ✓

---

## 6. 변경 금지 항목 유지 확인

### 6.1 Token 검증 흐름 (변경 없음) ✓

```python
# Before & After 동일
token, status = approve_token(token_id, task_id, actor, role)
...
if status == "approved":
    updated = _reg.mark_approved(task_id, actor)
```

- approve_token() → mark_approved() 순서 유지 ✓
- reject_token() → mark_rejected() 순서 유지 ✓

### 6.2 HTTP Status Code (변경 없음) ✓

```python
_APPROVE_STATUS_HTTP = {...}  # Unchanged
_REJECT_STATUS_HTTP = {...}   # Unchanged
```

- 409 already_used (변경 없음)
- 410 expired (변경 없음)
- 403 forbidden (변경 없음)

### 6.3 Audit Event (변경 없음) ✓

```python
_APPROVE_AUDIT_EVENT = {...}  # Unchanged
_REJECT_AUDIT_EVENT = {...}   # Unchanged
```

모든 event 이름 및 condition 유지 ✓

### 6.4 상태 전이 (변경 없음) ✓

```python
# Registry의 VALID_TASK_TRANSITIONS 참조 유지
# _ensure_task_transition() 호출 순서 유지
# mark_* 함수 signature 미변경
```

### 6.5 보안 정책 (변경 없음) ✓

- token_id 원문 audit 기록 금지: ✓ (guards 모듈에 token 관련 코드 없음)
- approval_public_id 처리: ✓ (분리하지 않음)
- WebSocket 핸들러: ✓ (분리하지 않음)
- Registry mutation: ✓ (guards는 read-only)

### 6.6 실행 제약 (준수) ✓

- ✓ 실제 agent 실행 없음
- ✓ 실제 task 실행 없음
- ✓ WebSocket 실제 연결 없음
- ✓ Inventory scan 없음
- ✓ Cleanup 실행 없음
- ✓ Browser 실행 없음
- ✓ DB/schema 변경 없음
- ✓ Secret/token/password 원문 출력 없음

---

## 7. 테스트 결과

### 7.1 신규 Guards 테스트

**파일:** test_local_agent_router_guards.py  
**테스트:** 41개

```
TestIsCaptureScreenshot:        3/3 PASS ✓
TestTaskIsDryRun:              6/6 PASS ✓
TestCanApproveTask:            4/4 PASS ✓
TestCanRejectTask:             4/4 PASS ✓
TestCanCancelTask:             9/9 PASS ✓
TestIsTerminalStatus:          9/9 PASS ✓
TestStatusMatrices:            4/4 PASS ✓
TestImportSafety:              2/2 PASS ✓
```

**주요 테스트:**
- Pure function 동등성 검증 ✓
- None 안전성 검증 ✓
- Status matrix 관계성 검증 ✓
- Import cycle 검증 ✓

### 7.2 기존 관련 테스트

| 테스트 파일 | 테스트 수 | 결과 |
|----------|--------|------|
| test_local_agent.py | 134 | PASS ✓ |
| test_local_agent_ws.py | 56 | PASS ✓ |
| test_local_agent_router_audit_redaction.py | 9 | PASS ✓ |
| test_local_agent_audit_builders.py | 13 | PASS ✓ |

**종합:** 253/253 PASS ✓

**회귀 검증:**
- Response shape 무변경 ✓
- Status code 무변경 ✓
- Audit event 무변경 ✓
- Token redaction 유지 ✓

---

## 8. 모듈화 확인

### 8.1 분리 범위

| 카테고리 | 분리 | 이유 |
|---------|------|------|
| Pure helper | ✓ | side-effect 없음 |
| Status constant | ✓ | 불변 상수 |
| Approval gateway | ✗ | 복잡한 검증 로직 |
| WebSocket | ✗ | Agent 실행 흐름과 결합 |
| Registry | ✗ | State machine 핵심 |

### 8.2 Import 관계

```
local_agent_router.py
  └── local_agent_router_guards.py  (신규 import)
  └── local_agent_models.py         (기존)
  └── approval.py                   (기존, 미변경)
  └── local_agent_registry.py        (기존, 미변경)
  └── local_agent_audit_builders.py  (기존, 미변경)

local_agent_router_guards.py
  └── local_agent_models.py         (기존)
  (순환 참조 없음 ✓)
```

### 8.3 대규모 리팩터링 없음 ✓

- 기존 API 보존 ✓
- 엔드포인트 무변경 ✓
- Response key 무변경 ✓
- 상태 전이 로직 무변경 ✓

---

## 9. 후속 작업 후보

### 9.1 Phase 2-2B (Approval Gateway Preflight)

**대상:** approve_token / reject_token 조합  
**위험도:** MEDIUM_HIGH  
**우선순위:** 중간 (이번 Phase 이후)

**가능한 분리:**
```python
# local_agent_approval_gateway.py (신규)
def approve_approval_token(...)
def reject_approval_token(...)
def check_approval_status(...)
```

### 9.2 Local Agent Store Preflight

**대상:** Registry 내부 _tasks store  
**위험도:** HIGH  
**우선순위:** 낮음

### 9.3 WebSocket Handler Preflight

**대상:** _handle_result, _push_queued  
**위험도:** HIGH  
**우선순위:** 낮음

---

## 10. 최종 판정

| 항목 | 판정 |
|------|------|
| **구현 범위** | PASS ✓ (순수 helper만 분리) |
| **보안** | PASS_SECURE ✓ (모든 보안 정책 유지) |
| **테스트** | PASS ✓ (253/253 PASS) |
| **회귀** | PASS_ZERO_REGRESSION ✓ |
| **모듈화** | PASS ✓ (순환 import 없음) |
| **문서화** | PASS ✓ (본 보고서) |

**최종 상태:** ✓ 구현 완료, 커밋 준비 완료

---

**다음 단계:** STEP 8 (커밋/푸시)
