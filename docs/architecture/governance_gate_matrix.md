# 거버넌스 게이트 매트릭스 (Governance Gate Matrix)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_GOVERNANCE_LOCK_01  
상태: LOCKED

---

## 1. 게이트 전체 목록

| 게이트 코드 | 우선순위 | 구현 상태 | 위치 | 설명 |
|------------|---------|----------|------|------|
| FORBIDDEN_IMPORT | P0 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py | 크로스 도메인/레이어 import 차단 |
| CIRCULAR_IMPORT | P0 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py | 순환 import 차단 |
| SECURITY_PATTERN | P0 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py | secret/token/password 출력 차단 |
| FAT_SITE | P0 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py | 단일 파일 비대화 차단 |
| BLOCKED_SECRET_SESSION | P0 | ✅ 구현됨 (gates.py) | scripts/*/gates.py + execution_gate.py | session/cookie/token 추출 차단 |
| APPROVAL_REQUIRED_ACTION | P0 | ✅ 구현됨 (gates.py) | scripts/*/gates.py | 승인 필요 작업 gate 적용 확인 |
| USER_DIRECT_REQUIRED_ACTION | P0 | ✅ 구현됨 (gates.py) | scripts/*/gates.py | 사용자 직접 작업 gate 적용 확인 |
| ROUTER_THINNESS | P1 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py + tests/test_app_foundation_p1_gates.py | router에 SQL/업무로직 없음 (known debt INFO) |
| STORAGE_BOUNDARY | P1 | ✅ 구현됨 | tools/repo_gates/codebase_layer_audit.py + tests/test_app_foundation_p1_gates.py | repository 직접 접근 차단 (known debt INFO) |
| COMMAND_CONTRACT | P1 | ⚠️ 문서만 | docs/architecture/ | command/response key 안정성 |
| RESPONSE_KEY_STABILITY | P1 | ⚠️ 문서만 | docs/architecture/ | API 응답 key 변경 금지 |
| LOCAL_AGENT_REQUIRED_ACTION | P1 | ⚠️ 문서만 | docs/architecture/ | 로컬 에이전트 전용 작업 분류 |
| SERVER_BROWSER_GUARD | P1 | ✅ 구현됨 (보강) | tools/repo_gates/codebase_layer_audit.py + execution_gate.py + gates.py | 서버 사이드 로그인 브라우저 차단 |
| DB_WRITE_GUARD | P2 | ⚠️ 문서만 | docs/architecture/ | 운영 DB write 승인 없이 차단 |
| DESTRUCTIVE_OP_GUARD | P2 | ✅ 구현됨 (quality_gate.py) | tools/quality/quality_gate.py | 파괴적 SQL/명령 차단 |
| ARCHITECTURE_DOC_EXISTS | P2 | 신규 추가 | tests/test_app_foundation_governance.py | 필수 문서 존재 여부 |
| PERMISSION_MODEL_EXISTS | P2 | 신규 추가 | tests/test_app_foundation_governance.py | 권한 모델 문서 존재 여부 |
| WORKFLOW_STATE_EXISTS | P2 | 신규 추가 | tests/test_app_foundation_governance.py | 상태 모델 문서 존재 여부 |
| STORAGE_MODEL_EXISTS | P2 | 신규 추가 | tests/test_app_foundation_governance.py | 저장소 모델 문서 존재 여부 |
| GATE_MATRIX_EXISTS | P2 | 신규 추가 | tests/test_app_foundation_governance.py | 게이트 매트릭스 문서 존재 여부 |

---

## 2. P0 게이트 (STOP 기준 — 0이어야 함)

```
FORBIDDEN_IMPORT      > 0 → STOP
CIRCULAR_IMPORT       > 0 → STOP
SECURITY_PATTERN      > 0 → STOP
FAT_SITE              > 0 → STOP
BLOCKED_SECRET_SESSION > 0 → STOP
```

---

## 3. P1 게이트 (WARN 허용, P0 이후 구현 목표)

```
ROUTER_THINNESS        — router 파일에 SQL/execute/requests.post 없음
STORAGE_BOUNDARY       — router 계층에서 직접 파일 I/O 없음
COMMAND_CONTRACT       — command/response key 변경 감지
RESPONSE_KEY_STABILITY — API response key 목록 고정
SERVER_BROWSER_GUARD   — is_server_forbidden_site=True 강제 여부
LOCAL_AGENT_REQUIRED   — 로컬 전용 action이 서버에서 실행되지 않음 확인
```

---

## 4. P2 게이트 (문서 존재 + 구조 확인)

```
ARCHITECTURE_DOC_EXISTS  — docs/architecture/app_foundation_governance.md 존재
PERMISSION_MODEL_EXISTS  — docs/architecture/permission_approval_model.md 존재
WORKFLOW_STATE_EXISTS    — docs/architecture/workflow_state_model.md 존재
STORAGE_MODEL_EXISTS     — docs/architecture/storage_audit_evidence_model.md 존재
GATE_MATRIX_EXISTS       — docs/architecture/governance_gate_matrix.md 존재
DB_WRITE_GUARD           — 운영 DB 직접 write 코드 감지
DESTRUCTIVE_OP_GUARD     — rm -rf, DROP TABLE 등 파괴적 명령 감지
```

---

## 5. 현재 구현된 게이트 상세

### FORBIDDEN_IMPORT (P0 — 구현됨)
- 위치: `tools/repo_gates/codebase_layer_audit.py` → `check_forbidden_imports()`
- 적용 쌍: gabia↔hiworks, gabia↔eum, gabia↔youtube, gabia↔g2b, gabia↔google, hiworks↔eum, ... (25+ 쌍)
- 테스트: `tests/test_gabia_site_engine.py`, `tests/test_codebase_layer_audit.py`

### SECURITY_PATTERN (P0 — 구현됨)
- 위치: `tools/repo_gates/codebase_layer_audit.py` → `check_security_patterns()`
- 감지: `print(password)`, `print(secret)`, `{password}` f-string 등
- 테스트: `tests/test_codebase_layer_audit.py`

### BLOCKED_SECRET_SESSION (P0 — gates.py로 구현됨)
- 위치: `scripts/*/gates.py` → `gate_*_login()`, `gate_*_credential_extract()`
- 모든 SIGN capability → profile BLOCKED 정책 적용
- 테스트: `tests/test_gabia_site_engine.py::test_gate_login_blocked` 등

### DESTRUCTIVE_OP_GUARD (P2 — quality_gate.py로 구현됨)
- 위치: `tools/quality/quality_gate.py`
- 감지: DROP, TRUNCATE, DELETE FROM 등

---

## 6. 미구현 게이트 구현 계획

| 게이트 | 구현 방법 | 목표 시기 |
|--------|----------|----------|
| ROUTER_THINNESS | codebase_layer_audit.py 확장 — router 파일 내 forbidden pattern | 다음 단계 |
| STORAGE_BOUNDARY | codebase_layer_audit.py 확장 — router 파일에서 open/write 감지 | 다음 단계 |
| SERVER_BROWSER_GUARD | execution_gate 강화 | 다음 단계 |
| DB_WRITE_GUARD | codebase_layer_audit.py 확장 | P2 이후 |
