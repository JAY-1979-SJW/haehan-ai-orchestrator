# Browser Submit Execution Gate 설계 문서

**작성일:** 2026-05-06  
**타스크:** BROWSER_SUBMIT_EXECUTION_GATE_DESIGN_1  
**정정:** BROWSER_SUBMIT_EXECUTION_GATE_DESIGN_ALIGNMENT_1  
**상태:** ✓ 설계 완료 (구현 전)

---

## 1. 목적

Browser Submit 시스템의 policy → preview → approval → audit 흐름이 완성된 상태에서,
**실제 production submit 실행 직전**에 통과해야 하는 최종 차단문(Execution Gate)을 설계한다.

이번 단계는 **설계 고정**이며, 실제 제출 실행 기능 구현이 아니다.

---

## 2. 배경: 기존 흐름 요약

```
[Browser Click]
      ↓
[submit_policy.py]  → SubmitPolicyResult (verdict: ALLOW/DENY)
      ↓
[submit_preview.py] → SubmitPreviewBundle (preview_hash, risk_level, layers)
      ↓
[approval UI]       → ApprovalDecisionPayload (approval_status: approved/cancelled)
      ↓
[submit_approval_state.py] → append-only JSONL log
      ↓
[submit_audit_log.py]      → append-only JSONL audit
      ↓
[controlled_submit.py]     → ControlledSubmitResult (submit_result: pending/blocked/success)
      ↓
★ [EXECUTION GATE]  ← 이번 설계 대상
      ├─ controlled_submit_allowed=True  → Controlled/Internal Submit 허용
      └─ production_submit_allowed=True  → Production Submit 허용 (별도 승인 필요)
```

---

## 3. Execution Gate 역할 (정정)

Gate는 두 가지 허용 경로를 **독립적으로 판정**한다.

| 판정 대상 | 설명 |
|----------|------|
| `controlled_submit_allowed` | 핵심 6개 조건(policy~audit) 모두 통과 시 True |
| `production_submit_allowed` | 핵심 6개 조건 + production_submit_enabled=True 시 True |

**중요 원칙:**
- `production_submit_enabled=False`는 production submit만 차단한다.
- **controlled/internal submit 경로는 production_submit_enabled와 독립적이다.**
- Gate는 판정만 반환한다. submit 실행 없음, DB write 없음, network 없음.

---

## 4. Gate Verdict 분리 (정정)

```
gate_verdict:
  "GATE_PASS"             → 핵심 6개 조건 통과 + production_submit_enabled=True
  "GATE_ALLOW_CONTROLLED" → 핵심 6개 조건 통과 + production_submit_enabled=False
  "GATE_BLOCK"            → 핵심 6개 조건 중 하나 이상 실패
```

| Verdict | controlled_submit_allowed | production_submit_allowed | 의미 |
|---------|--------------------------|--------------------------|------|
| `GATE_PASS` | True | True | 모든 조건 충족 |
| `GATE_ALLOW_CONTROLLED` | True | False | production 차단, controlled 허용 |
| `GATE_BLOCK` | False | False | 핵심 조건 하나 이상 실패 |

**현재 기본값:** `production_submit_enabled=False` → `GATE_ALLOW_CONTROLLED` 또는 `GATE_BLOCK`

---

## 5. Gate Input Schema

```python
@dataclass
class ExecutionGateInput:
    # 필수: policy 결과
    policy_verdict: str              # "ALLOW" (다른 값이면 BLOCK)

    # 필수: preview 결과
    preview_hash: str                # 비어 있으면 BLOCK
    validation_id: str               # 비어 있으면 BLOCK
    risk_level: str                  # "low" | "medium" | "high"

    # 필수: approval 상태
    approval_status: str             # "approved" (다른 값이면 BLOCK)

    # 필수: controlled submit 결과
    controlled_submit_result: str    # "success" (다른 값이면 BLOCK)

    # 필수: audit 기록 여부
    audit_logged: bool               # False이면 BLOCK

    # 필수: production 활성화 플래그 (production submit 전용)
    production_submit_enabled: bool  # False이면 production_submit_allowed=False 만 영향

    # 선택: 추가 메타데이터
    submitted_by: str = ""
    site_id: str = ""
    form_id: str = ""
```

---

## 6. Gate Output Schema (정정)

```python
@dataclass
class ExecutionGateResult:
    # 최종 판정 (3종)
    gate_verdict: str               # "GATE_PASS" | "GATE_ALLOW_CONTROLLED" | "GATE_BLOCK"

    # 허용 경로 플래그 (독립적)
    controlled_submit_allowed: bool # True: 핵심 6개 조건 모두 통과
    production_submit_allowed: bool # True: 핵심 6개 + production_submit_enabled=True

    # 차단 이유 목록 (GATE_BLOCK일 때 비어 있지 않음)
    block_reasons: list[str]        # BlockReason 코드 목록

    # 메타데이터
    gate_id: str                    # 고유 gate 검증 ID (uuid)
    evaluated_at: str               # ISO 8601 UTC timestamp
    production_submit_enabled: bool # 입력값 그대로 반영
```

---

## 7. Gate Verdict 매핑

| gate_verdict | controlled_submit_allowed | production_submit_allowed | block_reasons |
|-------------|--------------------------|--------------------------|---------------|
| `GATE_PASS` | True | True | [] |
| `GATE_ALLOW_CONTROLLED` | True | False | [] |
| `GATE_BLOCK` | False | False | [1개 이상] |

---

## 8. Block Reason Taxonomy

```python
class BlockReason:
    # Policy 관련
    POLICY_NOT_ALLOW        = "POLICY_NOT_ALLOW"
    # 설명: policy_verdict != "ALLOW"
    # 핵심 차단 조건 — controlled submit도 차단됨

    # Preview 관련
    PREVIEW_HASH_MISSING    = "PREVIEW_HASH_MISSING"
    # 설명: preview_hash 없음 — 미리보기 단계 미통과

    VALIDATION_ID_MISSING   = "VALIDATION_ID_MISSING"
    # 설명: validation_id 없음 — 검증 링크 불가

    # Approval 관련
    APPROVAL_NOT_APPROVED   = "APPROVAL_NOT_APPROVED"
    # 설명: approval_status != "approved"

    # Controlled Submit 관련
    CONTROLLED_SUBMIT_NOT_SUCCESS = "CONTROLLED_SUBMIT_NOT_SUCCESS"
    # 설명: controlled_submit_result != "success"

    # Audit 관련
    AUDIT_NOT_LOGGED        = "AUDIT_NOT_LOGGED"
    # 설명: audit_logged == False — 감사 기록 없음

    # Production 전용 (controlled submit은 차단하지 않음)
    PRODUCTION_DISABLED     = "PRODUCTION_DISABLED"
    # 설명: production_submit_enabled == False
    # 중요: GATE_BLOCK을 일으키지 않음. production_submit_allowed=False 만 의미함.
```

---

## 9. Gate 검증 로직 (정정)

```python
def evaluate_execution_gate(input: ExecutionGateInput) -> ExecutionGateResult:
    """
    Evaluate execution gate.

    핵심 6개 조건 (policy, preview_hash, validation_id, approval, controlled, audit):
      → 하나라도 실패 시 GATE_BLOCK (controlled_submit_allowed=False)
      → 모두 통과 시 controlled_submit_allowed=True

    production_submit_enabled:
      → False이면 production_submit_allowed=False (GATE_BLOCK 아님)
      → True이면 production_submit_allowed=True

    gate_verdict:
      GATE_PASS             ← 핵심 6개 통과 + production_submit_enabled=True
      GATE_ALLOW_CONTROLLED ← 핵심 6개 통과 + production_submit_enabled=False
      GATE_BLOCK            ← 핵심 6개 중 하나 이상 실패

    Never executes production submit.
    """
    block_reasons = []

    # 핵심 6개 조건 (모두 GATE_BLOCK 원인)
    if input.policy_verdict != "ALLOW":
        block_reasons.append(BlockReason.POLICY_NOT_ALLOW)

    if not input.preview_hash:
        block_reasons.append(BlockReason.PREVIEW_HASH_MISSING)

    if not input.validation_id:
        block_reasons.append(BlockReason.VALIDATION_ID_MISSING)

    if input.approval_status != "approved":
        block_reasons.append(BlockReason.APPROVAL_NOT_APPROVED)

    if input.controlled_submit_result != "success":
        block_reasons.append(BlockReason.CONTROLLED_SUBMIT_NOT_SUCCESS)

    if not input.audit_logged:
        block_reasons.append(BlockReason.AUDIT_NOT_LOGGED)

    # 판정
    if block_reasons:
        # 핵심 조건 실패 → GATE_BLOCK
        return ExecutionGateResult(
            gate_verdict="GATE_BLOCK",
            controlled_submit_allowed=False,
            production_submit_allowed=False,
            block_reasons=block_reasons,
            gate_id=f"gate_{uuid.uuid4().hex[:12]}",
            evaluated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            production_submit_enabled=input.production_submit_enabled,
        )

    # 핵심 6개 통과 → controlled submit 허용
    controlled_submit_allowed = True

    # production_submit_enabled 별도 판정
    production_submit_allowed = input.production_submit_enabled

    if production_submit_allowed:
        verdict = "GATE_PASS"
    else:
        verdict = "GATE_ALLOW_CONTROLLED"

    return ExecutionGateResult(
        gate_verdict=verdict,
        controlled_submit_allowed=controlled_submit_allowed,
        production_submit_allowed=production_submit_allowed,
        block_reasons=[],
        gate_id=f"gate_{uuid.uuid4().hex[:12]}",
        evaluated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        production_submit_enabled=input.production_submit_enabled,
    )
```

---

## 10. Gate 상태 전이 매트릭스 (정정)

| policy | preview_hash | approval | controlled | audit | prod_enabled | gate_verdict | c_allowed | p_allowed |
|--------|-------------|----------|-----------|-------|-------------|-------------|----------|----------|
| ALLOW | ✓ | approved | success | ✓ | **True** | **GATE_PASS** | True | True |
| ALLOW | ✓ | approved | success | ✓ | **False** | **GATE_ALLOW_CONTROLLED** | True | False |
| DENY | ✓ | approved | success | ✓ | True | GATE_BLOCK | False | False |
| ALLOW | ✗ | approved | success | ✓ | True | GATE_BLOCK | False | False |
| ALLOW | ✓ | pending | success | ✓ | True | GATE_BLOCK | False | False |
| ALLOW | ✓ | approved | blocked | ✓ | True | GATE_BLOCK | False | False |
| ALLOW | ✓ | approved | success | ✗ | True | GATE_BLOCK | False | False |
| DENY | ✗ | pending | blocked | ✗ | False | GATE_BLOCK | False | False |

**현재 기본값:** `production_submit_enabled=False` → `GATE_ALLOW_CONTROLLED` (핵심 조건 통과 시)

---

## 11. 기존 모듈과의 연결 계획

```
ExecutionGateInput 필드 → 소스 모듈
─────────────────────────────────────────────────────────
policy_verdict              ← SubmitPolicyResult.verdict
preview_hash                ← SubmitPreviewBundle.audit.preview_hash
validation_id               ← SubmitPreviewBundle.audit.validation_id
risk_level                  ← SubmitPreviewBundle.audit.risk_level
approval_status             ← get_approval_status(latest_approval_state(...))
controlled_submit_result    ← ControlledSubmitResult.submit_result
audit_logged                ← SubmitAuditWriteResult.success
production_submit_enabled   ← 설정값 (현재 항상 False)
```

---

## 12. 구현 예정 파일 (다음 단계)

```
ai_orchestrator/browser_tool/submit/submit_execution_gate.py
  - ExecutionGateInput (dataclass)
  - ExecutionGateResult (dataclass: gate_verdict, controlled_submit_allowed, production_submit_allowed, block_reasons, ...)
  - BlockReason (class with constants)
  - evaluate_execution_gate(input) → ExecutionGateResult

tests/test_browser_submit_execution_gate_20260506.py
  - TestGateBlockReasons (6 tests per core reason)
  - TestGatePass (1 test: all conditions met + prod enabled)
  - TestGateAllowControlled (2 tests: core conditions met + prod disabled)
  - TestGateNoSideEffects (no network, no DB, no file write)
```

---

## 13. 보안 원칙

| 원칙 | 내용 |
|------|------|
| production_submit_enabled 기본값 | False (별도 승인 없이 True 금지) |
| production_submit_enabled=False의 의미 | production submit만 차단. controlled submit은 독립 판정. |
| Gate는 판정만 | submit 실행 없음, DB write 없음, network 없음 |
| 외부 의존성 | 없음 (순수 Python, 표준 라이브러리만) |
| audit_logged 필수 | False이면 GATE_BLOCK — 감사 없는 제출 차단 |
| approval_status 필수 | "approved"만 통과 — pending/cancelled 차단 |

---

## 14. 이번 단계 산출물 목록

| 파일 | 유형 | 상태 |
|------|------|------|
| docs/design/browser_submit_execution_gate_design_20260506.md | 설계 문서 (정정) | ✓ 완료 |
| tests/fixtures/browser_submit_execution_gate_fixture_20260506.json | fixture (정정) | ✓ 완료 |
| tests/test_browser_submit_execution_gate_schema_20260506.py | schema 테스트 (정정) | ✓ 완료 |
| docs/reports/browser_submit_execution_gate_alignment_20260506.md | alignment closeout report | ✓ 완료 |

---

**설계 정정 완료 일시:** 2026-05-06 KST  
**다음 단계:** BROWSER_SUBMIT_EXECUTION_GATE_VALIDATOR_1 (실제 모듈 구현)
