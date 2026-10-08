# Browser Action Registry Preflight 설계

**작성일:** 2026-05-07  
**단계:** BROWSER_ACTION_REGISTRY_PREFLIGHT_1  
**기준 HEAD:** b742316  
**상태:** 설계 완료 (구현 단계)

---

## 1. 목적

browser action을 실행하기 전에, action registry metadata와 gate approval preflight 결과를 조합해 실행 가능성을 사전 판정하는 preflight 모듈을 구현한다.

- action별 operation_type, approval_required, audit_required 정책 검증
- gate approval preflight 결과와 action metadata 정합성 확인
- submit/type 차단 정책 유지 확인
- production_allowed=false 정책 유지 확인
- safe_to_execute=false 정책 유지 확인
- dispatcher/task_executor 연결 없이 "판정만" 수행

---

## 2. Action Registry Preflight 위치

- 모듈: `ai_orchestrator/browser_tool/preflight/action_registry_preflight.py`
- 테스트: `tests/test_browser_action_registry_preflight_20260507.py`
- Fixture: `tests/fixtures/browser_action_registry_preflight_20260507.json`
- 설계 문서: 현재 파일

---

## 3. Action Metadata 필수 필드

action metadata는 action_registry.py의 ActionMeta와 호환하면서도, browser action 실행 전 판정을 위해 다음 필드를 포함해야 한다:

```python
@dataclass
class BrowserActionMetadata:
    action_name: str                      # e.g., "browser.inspect"
    operation_type: str                   # read|navigate|open_url|click|type|submit
    risk_level: str                       # low|medium|high|critical
    approval_required: bool               # approval record 필요 여부
    audit_required: bool                  # audit record 필요 여부
    gate_required: bool                   # gate_approval_preflight 필수 여부
    allowlist_required: bool              # allowlist 검사 필수 여부
    production_allowed: bool              # production mode 허용 여부
    dry_run_only: bool                    # dry-run only
    safe_to_dispatch_allowed: bool        # dry-run dispatch 허용 가능 여부
    safe_to_execute_allowed: bool         # safe_to_execute=true 허용 (모두 false)
    blocked_by_default: bool              # default deny
    block_reason: Optional[str]           # 차단 사유 (SUBMIT_DENY_BY_DEFAULT, TYPE_BLOCKED, etc.)
```

---

## 4. Operation Type별 정책

| Operation Type | 최소 Risk | Approval Required | Audit Required | Safe to Execute |
|---|---|---|---|---|
| read | low | false | false | false |
| navigate | low | false | false | false |
| open_url | medium | true | true | false |
| click | medium | true | true | false |
| type | high | true | true | false |
| submit | critical | true | true | false |

---

## 5. Approval/Gate/Audit 연계 정책

### 5.1 Approval 상태별 판정

| Approval Status | Gate Preflight | Action Preflight | Safe to Dispatch |
|---|---|---|---|
| NOT_REQUIRED | ALLOW_DRY_RUN_DISPATCH | ALLOW_DRY_RUN_DISPATCH | true (read/open_url/click) |
| PENDING | REQUIRE_APPROVAL | REQUIRE_APPROVAL | false |
| APPROVED | ALLOW_DRY_RUN_DISPATCH | ALLOW_DRY_RUN_DISPATCH | true (except submit/type) |
| REJECTED | BLOCK | BLOCK | false |
| EXPIRED | BLOCK | BLOCK | false |
| REVOKED | BLOCK | BLOCK | false |

### 5.2 Operation Type별 Approval 결과

| Operation | Gate Result | Action Result | Block Reason |
|---|---|---|---|
| read/navigate (approval=false) | ALLOW_DRY_RUN_DISPATCH | ALLOW_DRY_RUN_DISPATCH | - |
| open_url (approval=true, status=APPROVED) | ALLOW_DRY_RUN_DISPATCH | ALLOW_DRY_RUN_DISPATCH | - |
| click (approval=true, status=APPROVED) | ALLOW_DRY_RUN_DISPATCH | ALLOW_DRY_RUN_DISPATCH | - |
| type (status=APPROVED) | BLOCK | BLOCK | TYPE_BLOCKED |
| submit (status=APPROVED) | DENY_BY_DEFAULT | DENY_BY_DEFAULT | SUBMIT_DENY_BY_DEFAULT |

---

## 6. Submit/Type 차단 정책

### 6.1 Submit 작업

```python
if operation_type == "submit":
    preflight_decision = "DENY_BY_DEFAULT"
    block_reason = "SUBMIT_DENY_BY_DEFAULT"
    safe_to_dispatch = False
    safe_to_execute = False
    # approval이 있어도 차단 유지
```

### 6.2 Type 작업

```python
if operation_type == "type":
    preflight_decision = "BLOCK"
    block_reason = "TYPE_BLOCKED"
    safe_to_dispatch = False
    safe_to_execute = False
    # approval이 있어도 차단 유지
```

---

## 7. Safe_to_execute 정책

```python
safe_to_execute = False  # 모든 케이스에서 false 유지

# Reason:
# - action registry preflight는 "판정"만 수행한다
# - 실제 실행 허가는 dispatcher/task_executor에서 별도로 승인한다
# - 이번 단계는 dry-run dispatch preflight이므로 safe_to_execute=false 유지
```

---

## 8. Dispatcher 연결 전 남은 조건

action registry preflight에서 판정한 후, dispatcher/task_executor 연결 전 만족해야 할 조건:

1. ✓ Allowlist 검사 (action/domain/url 화이트리스트)
2. ✓ Gate approval preflight 통과
3. ✓ Action registry 정책 통과
4. ⏳ Dispatcher 실행 권한 최종 승인
5. ⏳ Task executor 실행 (dispatcher가 호출)

---

## 9. Browser Action 정책 매트릭스

### Implemented (Registry에 등록됨)

| Action | Op Type | Risk | Approval | Audit | Safe Exec |
|---|---|---|---|---|---|
| browser.inspect | read | low | false | false | false |
| browser.plan_click | read | low | false | false | false |
| browser.plan_open_url | navigate | low | false | false | false |

### Planned (이번 단계 정책 정의, 향후 registry 추가 예정)

| Action | Op Type | Risk | Approval | Audit | Safe Exec |
|---|---|---|---|---|---|
| browser.open_url_controlled | open_url | medium | true | true | false |
| browser.execute_click | click | medium | true | true | false |
| browser.execute_type | type | high | true | true | false |
| browser.open_click_close_controlled | click | medium | true | true | false |
| browser.open_type_close_controlled | submit/type | critical | true | true | false |

---

## 10. API 설계

### build_action_preflight_context

```python
def build_action_preflight_context(payload: dict) -> dict:
    """
    Action preflight 실행에 필요한 context 정보를 빌드한다.
    
    Args:
        payload: {
            "action_name": "browser.inspect",
            "workflow_run_id": "run_123",
            "workflow_id": "g2b_search",
            ...
        }
    
    Returns:
        {
            "action_name": "browser.inspect",
            "action_known": True,
            "registry_policy": {...},
            "gate_preflight": {...},
            ...
        }
    """
```

### evaluate_action_registry_preflight

```python
def evaluate_action_registry_preflight(
    payload: dict,
    approval_store_path: str | Path | None = None,
) -> dict:
    """
    Action registry preflight를 평가한다.
    
    Args:
        payload: action name, operation type, approval status, etc.
        approval_store_path: approval record store path
    
    Returns:
        {
            "action_name": "browser.inspect",
            "action_known": True,
            "action_allowed_by_registry": True,
            "registry_policy": {...},
            "gate_preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "approval_status": "PENDING",
            "approval_required": False,
            "audit_required": False,
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "block_reason": None,
            "safe_to_dispatch": True,
            "safe_to_execute": False,
            "should_write_audit": False,
            "message_ko": "browser.inspect: dry-run dispatch 허용",
        }
    """
```

### validate_action_preflight_result

```python
def validate_action_preflight_result(result: dict) -> list[str]:
    """Validate action preflight result."""
```

### get_browser_action_policy

```python
def get_browser_action_policy(action_name: str) -> dict:
    """Get browser action policy from registry or default policy."""
```

---

## 11. Preflight Decision Values

```python
VALID_PREFLIGHT_DECISIONS = {
    "ALLOW_DRY_RUN_DISPATCH",  # read/open_url/click, approval ok
    "REQUIRE_APPROVAL",         # approval required but missing/pending
    "BLOCK",                    # action unknown, context missing, etc.
    "DENY_BY_DEFAULT",          # submit, type, gate deny
    "UNKNOWN_ACTION",           # action not in registry
}
```

---

## 12. Block Reason Values

```python
VALID_BLOCK_REASONS = {
    "ACTION_UNKNOWN",
    "ACTION_NOT_ALLOWED",
    "OPERATION_TYPE_BLOCKED",
    "TYPE_BLOCKED",
    "SUBMIT_DENY_BY_DEFAULT",
    "APPROVAL_REQUIRED",
    "APPROVAL_MISSING",
    "APPROVAL_PENDING",
    "APPROVAL_REJECTED",
    "APPROVAL_EXPIRED",
    "APPROVAL_REVOKED",
    "PRODUCTION_MODE_BLOCKED",
    "CONTEXT_MISSING",  # tenant/user/site
    "GATE_BLOCKED",
    "GATE_DENY_BY_DEFAULT",
}
```

---

## 13. 다음 단계 연결점

1. **Allowlist Preflight** (ALLOWLIST_PREFLIGHT_1)
   - action/domain/url whitelist 검사
   - action registry preflight 후 실행

2. **Dispatcher Preflight** (BROWSER_DRY_RUN_DISPATCHER_PREFLIGHT_1)
   - action registry preflight + allowlist preflight 통과 후
   - dispatcher 호출 전 최종 승인

3. **Task Executor** (향후)
   - dispatcher가 task_executor 호출
   - safe_to_execute=true 되는 시점 (미정)

---

## 14. 금지 항목

- ❌ task_executor import
- ❌ dispatcher import
- ❌ action_registry.py 실행 연결
- ❌ 실제 browser 실행
- ❌ approval record 수정
- ❌ 실제 업무 사이트 접속

---

## 15. 허용 항목

- ✓ action_registry read-only
- ✓ gate_approval_preflight 결과 조합
- ✓ action metadata fixture 작성
- ✓ preflight 판정만 수행
- ✓ 테스트 작성
- ✓ git commit/push
