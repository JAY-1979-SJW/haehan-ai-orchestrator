# Browser Submit Execution Gate Module 설계

**작성일:** 2026-05-06  
**단계:** BROWSER_GATE_MODULE_DESIGN_1  
**기준 HEAD:** 3a43515  
**상태:** 설계 완료 (구현 전)

---

## 1. 목적

submit/type/click 계열 action을 실제 dispatcher에 연결하기 전에,  
**allowlist policy 이후, dispatcher 연결 이전**에 통과해야 하는 최종 차단 계층을 설계한다.

- 기본 원칙: **deny-by-default**
- Gate는 판정만 반환. submit 실행 없음, DB write 없음, network 없음.
- 외부 의존성 없음 (순수 Python, 표준 라이브러리만)

### 이전 단계와의 관계

```
[AllowlistPolicy]     ← BROWSER_ALLOWLIST_POLICY_DESIGN_1 (3a43515)
      ↓ policy_verdict=ALLOW
[SubmitExecutionGate] ← 이번 설계 대상 (BROWSER_GATE_MODULE_DESIGN_1)
      ↓ gate_decision=ALLOW
[Dispatcher]          ← 다음 단계 (미연결)
```

---

## 2. 입력 스키마 초안

```python
@dataclass
class GateModuleInput:
    # 필수: action 식별
    action_name: str          # 예: "browser.open_type_close_controlled"
    operation_type: str       # "read"|"navigate"|"open_url"|"click"|"type"|"submit"

    # 필수: allowlist policy 결과
    policy_verdict: str       # "ALLOW" (다른 값이면 차단)
    allowlist_domain: str     # policy를 통과한 domain

    # 필수: preview 결과
    preview_hash: str         # 비어 있으면 차단
    validation_id: str        # 비어 있으면 차단
    risk_level: str           # "low"|"medium"|"high"

    # 필수: approval 상태
    approval_required: bool   # true이면 approval_id/status 필수
    approval_id: str          # approval_required=true인데 비어 있으면 차단
    approval_status: str      # "approved" (다른 값이면 차단)

    # 필수: audit 상태
    audit_required: bool      # true이면 audit_context 필수
    audit_context: str        # audit_required=true인데 비어 있으면 차단

    # 필수: sensitive input 상태
    contains_sensitive_input: bool  # true이면 redaction 완료 필수
    redaction_complete: bool        # contains_sensitive_input=true + false이면 차단

    # 필수: 실행 모드 플래그
    production_mode: bool     # true이면 safe_to_execute=false (현 단계 전면 금지)
    safe_to_dispatch: bool    # true이면 gate_decision=ALLOW 가능

    # 선택: 메타데이터
    tenant_scope: str = ""    # 비어 있으면 차단 권장
    submitted_by: str = ""
    site_id: str = ""
    form_id: str = ""
```

---

## 3. 출력 스키마 초안

```python
@dataclass
class GateModuleResult:
    gate_decision: str          # "ALLOW"|"BLOCK"|"DENY_BY_DEFAULT"
    safe_to_execute: bool       # 현 단계: 항상 False (dispatcher 미연결)
    safe_to_dispatch: bool      # True이면 dispatcher 연결 준비 완료
    block_reasons: list[str]    # 차단 사유 코드 목록
    gate_id: str                # 고유 ID
    evaluated_at: str           # ISO 8601 UTC
    production_mode: bool       # 입력값 그대로 반영
```

---

## 4. gate_decision 허용값

| gate_decision | 의미 |
|---|---|
| `ALLOW` | 모든 조건 통과. dispatcher 연결 준비 완료 |
| `BLOCK` | 핵심 조건 하나 이상 실패 |
| `DENY_BY_DEFAULT` | operation_type=submit의 기본 차단 상태 |

---

## 5. block_reason 허용값

| block_reason | 조건 |
|---|---|
| `POLICY_NOT_ALLOW` | policy_verdict != "ALLOW" |
| `PREVIEW_HASH_MISSING` | preview_hash 비어 있음 |
| `VALIDATION_ID_MISSING` | validation_id 비어 있음 |
| `APPROVAL_ID_MISSING` | approval_required=true + approval_id 비어 있음 |
| `APPROVAL_NOT_APPROVED` | approval_required=true + approval_status != "approved" |
| `AUDIT_CONTEXT_MISSING` | audit_required=true + audit_context 비어 있음 |
| `SENSITIVE_INPUT_NOT_REDACTED` | contains_sensitive_input=true + redaction_complete=false |
| `PRODUCTION_MODE_BLOCKED` | production_mode=true (현 단계 전면 금지) |
| `TENANT_SCOPE_MISSING` | tenant_scope 비어 있음 |
| `SUBMIT_DENY_BY_DEFAULT` | operation_type=submit (gate_module 미구현 상태) |

---

## 6. 차단 규칙 (핵심)

```
1. operation_type=submit           → gate_decision=DENY_BY_DEFAULT (무조건)
2. production_mode=true            → PRODUCTION_MODE_BLOCKED + safe_to_execute=false
3. policy_verdict != "ALLOW"       → POLICY_NOT_ALLOW
4. preview_hash 비어 있음          → PREVIEW_HASH_MISSING
5. validation_id 비어 있음         → VALIDATION_ID_MISSING
6. approval_required=true 이고
   approval_id 비어 있음           → APPROVAL_ID_MISSING
7. approval_required=true 이고
   approval_status != "approved"   → APPROVAL_NOT_APPROVED
8. audit_required=true 이고
   audit_context 비어 있음         → AUDIT_CONTEXT_MISSING
9. contains_sensitive_input=true 이고
   redaction_complete=false        → SENSITIVE_INPUT_NOT_REDACTED
10. tenant_scope 비어 있음         → TENANT_SCOPE_MISSING
```

---

## 7. safe_to_execute 규칙

- **이번 단계(BROWSER_GATE_MODULE_DESIGN_1)에서 safe_to_execute=true는 허용하지 않는다.**
- dispatcher 연결 전까지 safe_to_execute는 항상 False.
- safe_to_dispatch=true이면 gate_decision=ALLOW (dispatcher 연결 준비만 완료).

---

## 8. 현재 단계 기본값

| 필드 | 기본값 | 이유 |
|---|---|---|
| production_mode | false | 현 단계 production 실행 전면 금지 |
| safe_to_execute | false | dispatcher 미연결 |
| operation_type=submit | DENY_BY_DEFAULT | gate_module 미구현 상태 |

---

## 9. 실제 모듈 import 금지 (설계 단계)

이번 설계 단계에서는 아래를 import하거나 호출하지 않는다:
- 실제 브라우저 모듈 (playwright, browser_worker 등)
- dispatcher 모듈
- task_executor 모듈
- production 실행 코드

테스트는 fixture/schema만 검증한다.

---

## 10. 구현 예정 파일 (다음 단계)

```
ai_orchestrator/browser_tool/submit/submit_execution_gate.py (기존 v1.0 확장)
  → action_name, operation_type 필드 추가
  → allowlist_domain 필드 추가
  → DENY_BY_DEFAULT 판정 추가 (submit operation)
  → PRODUCTION_MODE_BLOCKED 차단 추가
  → TENANT_SCOPE_MISSING 차단 추가
  → safe_to_execute 항상 False 보장

tests/test_browser_gate_module_design_20260506.py
  → 이번 단계 신규 테스트 (schema/fixture 검증)
```

---

## 11. 다음 단계 제안

**BROWSER_AUDIT_MODULE_DESIGN_1**

audit_module(submit_audit_log) 설계 단계.  
gate_decision=ALLOW 이후 감사 로그 기록 정책,  
append-only JSONL schema, audit_context 구조를 fixture/test로 고정.
