# Browser Submit Execution Gate 설계 문서

**작성일:** 2026-05-06  
**타스크:** BROWSER_SUBMIT_EXECUTION_GATE_DESIGN_1  
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
      ↓
[Production Submit] ← 별도 승인 전까지 항상 BLOCK
```

---

## 3. Execution Gate 역할

Gate는 production submit 직전에 위치하는 **최종 AND 검증기**다.

모든 선행 조건이 충족되어야만 `GATE_PASS`를 반환하며, 하나라도 실패하면 `GATE_BLOCK`이다.

**Gate는 submit을 실행하지 않는다.** PASS/BLOCK 결정만 반환한다.

---

## 4. Gate Input Schema

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

    # 필수: production 활성화 플래그
    production_submit_enabled: bool  # False이면 항상 BLOCK

    # 선택: 추가 메타데이터
    submitted_by: str = ""           # 요청자 식별자
    site_id: str = ""
    form_id: str = ""
```

---

## 5. Gate Output Schema

```python
@dataclass
class ExecutionGateResult:
    # 최종 판정
    gate_verdict: str               # "GATE_PASS" | "GATE_BLOCK"

    # 차단 이유 목록 (GATE_BLOCK일 때 비어 있지 않음)
    block_reasons: list[str]        # BlockReason 코드 목록

    # 메타데이터
    gate_id: str                    # 고유 gate 검증 ID (uuid)
    evaluated_at: str               # ISO 8601 UTC timestamp
    production_submit_enabled: bool # 입력값 그대로 반영
```

---

## 6. Gate Verdict 정의

| Verdict | 의미 | 다음 동작 |
|---------|------|----------|
| `GATE_PASS` | 모든 조건 충족 | production submit 가능 (별도 승인 후) |
| `GATE_BLOCK` | 하나 이상 조건 미충족 | submit 차단, block_reasons 기록 |

**중요:** `GATE_PASS`가 나오더라도, `production_submit_enabled == False`이면 실제 실행 불가.  
현재 기본값은 `production_submit_enabled = False`이며, **별도 승인 없이 True로 변경 금지**.

---

## 7. Block Reason Taxonomy

```python
class BlockReason:
    # Policy 관련
    POLICY_NOT_ALLOW        = "POLICY_NOT_ALLOW"
    # 설명: policy_verdict != "ALLOW"
    # 원인: 정책 검증 실패, 위험 필드, prompt injection 등

    # Preview 관련
    PREVIEW_HASH_MISSING    = "PREVIEW_HASH_MISSING"
    # 설명: preview_hash 없음 — 미리보기 단계 미통과
    
    VALIDATION_ID_MISSING   = "VALIDATION_ID_MISSING"
    # 설명: validation_id 없음 — 검증 링크 불가

    # Approval 관련
    APPROVAL_NOT_APPROVED   = "APPROVAL_NOT_APPROVED"
    # 설명: approval_status != "approved" (pending 또는 cancelled)
    # 원인: 사용자가 승인 전이거나 취소함

    # Controlled Submit 관련
    CONTROLLED_SUBMIT_NOT_SUCCESS = "CONTROLLED_SUBMIT_NOT_SUCCESS"
    # 설명: controlled_submit_result != "success"
    # 원인: blocked, error, pending 상태

    # Audit 관련
    AUDIT_NOT_LOGGED        = "AUDIT_NOT_LOGGED"
    # 설명: audit_logged == False — 감사 기록 없음
    # 원인: audit 단계 미완료

    # Production 관련
    PRODUCTION_DISABLED     = "PRODUCTION_DISABLED"
    # 설명: production_submit_enabled == False
    # 원인: 현재 기본 차단 상태 (별도 승인 필요)

    # 복합 관련
    MULTIPLE_BLOCKS         = "MULTIPLE_BLOCKS"
    # 설명: 2개 이상 block reason이 동시에 존재
```

---

## 8. Gate 검증 로직

```python
def evaluate_execution_gate(input: ExecutionGateInput) -> ExecutionGateResult:
    """
    Evaluate execution gate. Returns GATE_PASS only if ALL conditions met.
    
    AND logic: all checks must pass.
    Returns GATE_BLOCK on first or multiple failures.
    
    Never executes production submit.
    """
    block_reasons = []

    # Check 1: production_submit_enabled (항상 먼저 체크)
    if not input.production_submit_enabled:
        block_reasons.append(BlockReason.PRODUCTION_DISABLED)

    # Check 2: policy_verdict
    if input.policy_verdict != "ALLOW":
        block_reasons.append(BlockReason.POLICY_NOT_ALLOW)

    # Check 3: preview_hash
    if not input.preview_hash:
        block_reasons.append(BlockReason.PREVIEW_HASH_MISSING)

    # Check 4: validation_id
    if not input.validation_id:
        block_reasons.append(BlockReason.VALIDATION_ID_MISSING)

    # Check 5: approval_status
    if input.approval_status != "approved":
        block_reasons.append(BlockReason.APPROVAL_NOT_APPROVED)

    # Check 6: controlled_submit_result
    if input.controlled_submit_result != "success":
        block_reasons.append(BlockReason.CONTROLLED_SUBMIT_NOT_SUCCESS)

    # Check 7: audit_logged
    if not input.audit_logged:
        block_reasons.append(BlockReason.AUDIT_NOT_LOGGED)

    # 판정
    if not block_reasons:
        verdict = "GATE_PASS"
    else:
        verdict = "GATE_BLOCK"

    return ExecutionGateResult(
        gate_verdict=verdict,
        block_reasons=block_reasons,
        gate_id=f"gate_{uuid.uuid4().hex[:12]}",
        evaluated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        production_submit_enabled=input.production_submit_enabled,
    )
```

---

## 9. Gate 상태 전이 매트릭스

| policy | preview_hash | approval | controlled | audit | prod_enabled | 결과 |
|--------|-------------|----------|-----------|-------|-------------|------|
| ALLOW | ✓ | approved | success | ✓ | **True** | **GATE_PASS** |
| ALLOW | ✓ | approved | success | ✓ | **False** | GATE_BLOCK (PRODUCTION_DISABLED) |
| DENY | ✓ | approved | success | ✓ | True | GATE_BLOCK (POLICY_NOT_ALLOW) |
| ALLOW | ✗ | approved | success | ✓ | True | GATE_BLOCK (PREVIEW_HASH_MISSING) |
| ALLOW | ✓ | pending | success | ✓ | True | GATE_BLOCK (APPROVAL_NOT_APPROVED) |
| ALLOW | ✓ | cancelled | success | ✓ | True | GATE_BLOCK (APPROVAL_NOT_APPROVED) |
| ALLOW | ✓ | approved | blocked | ✓ | True | GATE_BLOCK (CONTROLLED_SUBMIT_NOT_SUCCESS) |
| ALLOW | ✓ | approved | success | ✗ | True | GATE_BLOCK (AUDIT_NOT_LOGGED) |
| DENY | ✗ | pending | blocked | ✗ | False | GATE_BLOCK (multiple) |

**현재 단계 기본값:** `production_submit_enabled = False` → 항상 `GATE_BLOCK`

---

## 10. 기존 모듈과의 연결 계획

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

## 11. 구현 예정 파일 (다음 단계)

```
ai_orchestrator/browser_tool/submit_execution_gate.py
  - ExecutionGateInput (dataclass)
  - ExecutionGateResult (dataclass)
  - BlockReason (class with constants)
  - evaluate_execution_gate(input) → ExecutionGateResult

tests/test_browser_submit_execution_gate_20260506.py
  - TestGateBlockReasons (7 tests per reason)
  - TestGatePass (1 test: all conditions met + prod enabled)
  - TestGateProductionDisabled (2 tests)
  - TestMultipleBlocks (2 tests)
  - TestGateNoSideEffects (no network, no DB, no file write)
```

---

## 12. 보안 원칙

| 원칙 | 내용 |
|------|------|
| production_submit_enabled 기본값 | False (별도 승인 없이 True 금지) |
| Gate는 판정만 | submit 실행 없음, DB write 없음, network 없음 |
| 외부 의존성 | 없음 (순수 Python, 표준 라이브러리만) |
| audit_logged 필수 | False이면 GATE_BLOCK — 감사 없는 제출 차단 |
| approval_status 필수 | "approved"만 통과 — pending/cancelled 차단 |

---

## 13. 이번 단계 산출물 목록

| 파일 | 유형 | 상태 |
|------|------|------|
| docs/design/browser_submit_execution_gate_design_20260506.md | 설계 문서 | ✓ 완료 |
| tests/fixtures/browser_submit_execution_gate_fixture_20260506.json | fixture 초안 | ✓ 완료 |
| tests/test_browser_submit_execution_gate_schema_20260506.py | schema/설계 테스트 | ✓ 완료 |
| docs/reports/browser_submit_execution_gate_design_20260506.md | closeout report | ✓ 완료 |

---

**설계 완료 일시:** 2026-05-06 18:30 KST  
**다음 단계:** BROWSER_SUBMIT_EXECUTION_GATE_VALIDATOR_1 (실제 모듈 구현)
