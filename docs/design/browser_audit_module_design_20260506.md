# Browser Audit Module 설계

**작성일:** 2026-05-07  
**단계:** BROWSER_AUDIT_MODULE_DESIGN_1  
**기준 HEAD:** 612abfb  
**상태:** 설계 완료 (구현 전)

---

## 1. 목적

browser action(click/type/submit)의 **실행 전/후 감사 기록 정책**을 설계한다.

- click/type/submit 같은 고위험 action은 `audit_context` 없이는 실행 금지
- audit log는 **append-only** 원칙 — 기록 후 수정/삭제 금지
- secret/password/token/raw sensitive input은 저장 금지
- 이번 단계는 설계·fixture·테스트만 작성. 실제 실행 없음.

### 이전 단계와의 관계

```
[AllowlistPolicy]   ← BROWSER_ALLOWLIST_POLICY_DESIGN_1
      ↓ policy_verdict=ALLOW
[SubmitExecutionGate] ← BROWSER_GATE_MODULE_DESIGN_1
      ↓ gate_decision=ALLOW
[AuditModule]       ← 이번 설계 대상 (BROWSER_AUDIT_MODULE_DESIGN_1)
      ↓ audit_event=AUDIT_READY
[Dispatcher]        ← 다음 단계 (미연결)
```

---

## 2. audit event 단계

| 단계 | 코드 | 설명 |
|---|---|---|
| 1 | `REQUEST_RECEIVED` | action 요청 수신. 식별자 부여 |
| 2 | `GATE_EVALUATED` | gate_decision 판정 완료. ALLOW/BLOCK/DENY_BY_DEFAULT 기록 |
| 3 | `APPROVAL_CHECKED` | approval_required=true 시 approval_id/status 검증 결과 기록 |
| 4 | `AUDIT_REQUIRED` | audit_required=true 확인. audit_context 존재 여부 기록 |
| 5 | `AUDIT_READY` | 감사 준비 완료. 실행 전 최종 기록 |
| 6 | `DISPATCH_BLOCKED` | gate_decision=BLOCK 또는 DENY_BY_DEFAULT 시 차단 기록 |
| 7 | `DISPATCH_ALLOWED_DRY_RUN` | gate_decision=ALLOW, safe_to_dispatch=true 시 dry_run 기록 |

### 이번 단계 허용 event 값

```python
AUDIT_EVENT_STAGES = {
    "REQUEST_RECEIVED",
    "GATE_EVALUATED",
    "APPROVAL_CHECKED",
    "AUDIT_REQUIRED",
    "AUDIT_READY",
    "DISPATCH_BLOCKED",
    "DISPATCH_ALLOWED_DRY_RUN",
}
```

---

## 3. AuditEntry 스키마 초안

```python
@dataclass
class AuditEntry:
    audit_id: str           # 고유 ID (UUID)
    action_name: str        # 예: "browser.execute_click"
    operation_type: str     # "read"|"navigate"|"open_url"|"click"|"type"|"submit"
    tenant_scope: str       # 빈 값이면 감사 불가 → DISPATCH_BLOCKED
    submitted_by: str       # 요청자

    event_stage: str        # AUDIT_EVENT_STAGES 중 하나
    gate_decision: str      # "ALLOW"|"BLOCK"|"DENY_BY_DEFAULT"
    audit_context: str      # 감사 맥락 설명 (빈 값이면 AUDIT_REQUIRED 실패)
    approval_id: str        # approval_required=true 시 필수
    approval_status: str    # "approved" (다른 값이면 차단)

    sensitive_input_present: bool   # true이면 raw_input 저장 금지
    raw_input_redacted: bool        # sensitive_input_present=true + false이면 차단
    production_mode: bool           # true이면 이번 단계 전면 차단
    safe_to_dispatch: bool          # true이면 DISPATCH_ALLOWED_DRY_RUN 가능

    recorded_at: str        # ISO 8601 UTC
    stage_id: str           # 현재 단계 식별자 (예: "BROWSER_AUDIT_MODULE_DESIGN_1")
```

---

## 4. AuditLog 스키마 초안 (append-only JSONL)

```jsonl
{"audit_id":"...","action_name":"...","operation_type":"click","event_stage":"REQUEST_RECEIVED","gate_decision":"ALLOW","audit_context":"click_board_detail_btn","approval_id":"appr_001","approval_status":"approved","sensitive_input_present":false,"raw_input_redacted":true,"production_mode":false,"safe_to_dispatch":true,"tenant_scope":"internal_test","submitted_by":"test_user","recorded_at":"2026-05-07T00:00:00Z","stage_id":"BROWSER_AUDIT_MODULE_DESIGN_1"}
```

규칙:
- 각 행은 독립된 JSON 객체
- 기존 행 수정/삭제 금지 (append-only)
- 파일명 예: `audit_log_20260507.jsonl`
- secret/password/token은 `[REDACTED]`로 치환 후 저장

---

## 5. 감사 차단 규칙

| 조건 | 결과 |
|---|---|
| `audit_required=true` + `audit_context` 비어 있음 | `DISPATCH_BLOCKED` |
| `sensitive_input_present=true` + `raw_input_redacted=false` | `DISPATCH_BLOCKED` |
| `production_mode=true` | `DISPATCH_BLOCKED` |
| `tenant_scope` 비어 있음 | `DISPATCH_BLOCKED` |
| `gate_decision != "ALLOW"` | `DISPATCH_BLOCKED` |
| `approval_required=true` + `approval_status != "approved"` | `DISPATCH_BLOCKED` |

---

## 6. 저장 금지 필드

다음 필드는 audit log에 평문 저장 금지:

- `raw_input` (type action의 실제 입력값)
- `password`, `secret`, `token`, `credential`, `otp`, `session`, `cookie` 패턴 포함 값
- 스크린샷 raw bytes
- 브라우저 storage state

저장 시 반드시 `[REDACTED]` 치환 후 기록.

---

## 7. operation_type별 감사 요구 수준

| operation_type | audit_required | approval_required | 감사 event 최소 수 |
|---|---|---|---|
| read | false | false | 0 (감사 선택) |
| navigate | false | false | 0 (감사 선택) |
| open_url | false | true | 1 |
| click | true | true | 최소 4 (REQUEST→GATE→APPROVAL→AUDIT_READY 또는 BLOCKED) |
| type | true | true | 최소 4 |
| submit | true | true | DENY_BY_DEFAULT → DISPATCH_BLOCKED만 기록 |

---

## 8. safe_to_execute / safe_to_dispatch 규칙

- 이번 단계에서 `safe_to_execute=true` 허용 안 함 (dispatcher 미연결)
- `safe_to_dispatch=true` + `gate_decision=ALLOW` + 모든 감사 조건 통과 → `DISPATCH_ALLOWED_DRY_RUN` 기록 가능
- `safe_to_dispatch=false` 또는 감사 조건 실패 → `DISPATCH_BLOCKED` 기록

---

## 9. 실제 모듈 import 금지 (설계 단계)

이번 단계에서 아래를 import하거나 호출하지 않는다:
- 실제 브라우저 모듈 (playwright, browser_worker)
- dispatcher 모듈
- task_executor 모듈
- DB write 코드 (SQLAlchemy write, raw SQL INSERT/UPDATE/DELETE)
- production 실행 코드

테스트는 fixture/schema만 검증한다.

---

## 10. 구현 예정 파일 (다음 단계)

```
ai_orchestrator/browser_tool/approval/submit_audit_log.py  (신규)
  → AuditEntry 데이터클래스
  → append_audit_log(entry: AuditEntry, path: Path) -> None
  → audit log JSONL 직렬화
  → sensitive field redaction

tests/test_browser_audit_module_design_20260506.py
  → 이번 단계 신규 테스트 (schema/fixture 검증)
```

---

## 11. 다음 단계 제안

**BROWSER_BUSINESS_WORKFLOW_DESIGN_1**

실제 업무 사이트(g2b 등) 자동화 워크플로우 설계.  
allowlist 정책 + gate module + audit module이 연계되는  
end-to-end 워크플로우 fixture/schema/test를 고정한다.
