# Browser Submit Gate — Controlled Integration Smoke 보고서

**문서 ID**: BROWSER_SUBMIT_GATE_CONTROLLED_INTEGRATION_SMOKE_1  
**작성일**: 2026-05-06  
**범위**: policy → preview → controlled_submit(mock) → audit → gate_evaluation 통합 검증

---

## STEP 0. 승인 문구 HEAD / origin/master / server HEAD 일치 여부 [최종 판정]

| 항목 | SHA | 상태 |
|------|-----|------|
| LOCAL HEAD | `7460a15ff0b79c19c20f4eda0c43956880db28f2` | ✅ |
| origin/master | `7460a15ff0b79c19c20f4eda0c43956880db28f2` | ✅ 일치 |
| server HEAD (haehan-app) | `7460a15ff0b79c19c20f4eda0c43956880db28f2` | ✅ 일치 |
| 미추적 파일 | `BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md` | ⚠️ 비차단 .md |

**사유**: 세 HEAD 모두 동일 SHA. 미추적 파일 1건 존재하나 `.md` 문서 파일로 비차단.

### 🟡 최종 판정: `WARN_GATE_CONTROLLED_INTEGRATION_WITH_NONBLOCKING_UNTRACKED`

---

## 테스트 결과

**파일**: `tests/test_browser_submit_gate_controlled_integration_smoke_20260506.py`  
**실행 결과**: **25 passed / 0 failed**

| 클래스 | 항목 수 | 결과 |
|--------|---------|------|
| TestStep0GitAlignment | 6 | ✅ 전통과 |
| TestModuleImport | 5 | ✅ 전통과 |
| TestGateAllowControlledIntegration | 5 | ✅ 전통과 |
| TestGateBlockIntegration | 4 | ✅ 전통과 |
| TestAuditIntegration | 3 | ✅ 전통과 |
| TestProductionSubmitSeparation | 2 | ✅ 전통과 |

---

## 통합 검증 범위

### 통과 경로 (GATE_ALLOW_CONTROLLED)

- internal.mock origin → `controlled_submit_result=success`
- 핵심 6개 조건 통과 + `production_submit_enabled=False`
- gate_verdict = `GATE_ALLOW_CONTROLLED`
- `controlled_submit_allowed=True`, `production_submit_allowed=False`

### 차단 경로 (GATE_BLOCK)

| 시나리오 | block_reason |
|----------|-------------|
| external origin → controlled_submit=blocked | `CONTROLLED_SUBMIT_NOT_SUCCESS` |
| preview_hash 없음 | `PREVIEW_HASH_MISSING` |
| approval_status=pending | `APPROVAL_NOT_APPROVED` |
| audit_logged=False | `AUDIT_NOT_LOGGED` |

### Audit 연계

- `build_submit_audit_event` → `append_submit_audit_event` → `read_submit_audit_events` 체인 정상
- audit 저장 완료 후 gate 통과 (end-to-end) 검증 완료

### production_submit 분리 원칙

- `production_submit_enabled=False` → `GATE_BLOCK` 유발하지 않음
- `PRODUCTION_DISABLED`가 `block_reasons`에 포함되지 않음

---

## 제약 사항

- 실제 브라우저 실행 없음 (mock bundle 사용)
- DB write 없음 (tmp_path 사용)
- 네트워크 없음
- production submit 실행 없음

---

## 수정 금지 파일

이번 작업에서 수정하지 않은 파일 (지시문 준수):

- `submit_execution_gate.py`
- `controlled_submit.py`
- `submit_policy.py`
- `submit_preview.py`
- `submit_audit_log.py`
- `submit_approval_state.py`
- 기타 지시문 지정 수정 금지 파일 전체

---

## 신규 생성 파일

| 파일 | 설명 |
|------|------|
| `tests/test_browser_submit_gate_controlled_integration_smoke_20260506.py` | 통합 스모크 테스트 (25 tests) |
| `docs/reports/browser_submit_gate_controlled_integration_smoke_20260506.md` | 본 보고서 |
