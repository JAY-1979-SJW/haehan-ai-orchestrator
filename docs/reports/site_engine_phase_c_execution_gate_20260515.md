# Site Engine Phase C Execution Gate
**날짜**: 2026-05-15
**단계**: SITE_ENGINE_PHASE_C_EXECUTION_GATE_01

---

## 1. 생성/수정 파일

| 파일 | Layer | 역할 |
|---|---|---|
| `scripts/site_engine/execution_gate.py` | L4 | ExecutionGateInput/Result, evaluate_execution_gate, 민감 분류 |
| `scripts/site_engine/__init__.py` | L4 | execution_gate public export 추가 |
| `tests/test_site_engine_execution_gate.py` | L11 | unit test 30건 |
| `docs/reports/site_engine_phase_c_execution_gate_20260515.md` | L12 | 이 문서 |

---

## 2. execution gate 정책

| action/risk | decision | reason |
|---|---|---|
| READ/SEARCH capability | ALLOWED | READ_ONLY_ALLOWED |
| WRITE (form_fill 등) | ALLOWED (server browser) | ALLOWED_SERVER_BROWSER |
| SUBMIT/UPLOAD/DELETE/PUBLISH/SEND/SIGN capability | APPROVAL_REQUIRED | APPROVAL_REQUIRED_IRREVERSIBLE |
| 위 + force_approved=True | ALLOWED (requires_approval=True) | POLICY_OVERRIDE |
| extract/get/dump + password/otp/cert/session/cookie | BLOCKED | BLOCKED_SENSITIVE_CREDENTIAL |
| input + password/credential (extract 없음) | USER_DIRECT_REQUIRED | USER_DIRECT_REQUIRED_CREDENTIAL |
| SiteProfile action_policies LOCAL_AGENT_REQUIRED | LOCAL_AGENT_REQUIRED | LOCAL_AGENT_REQUIRED_BY_PROFILE |
| SiteProfile action_policies USER_DIRECT_REQUIRED | USER_DIRECT_REQUIRED | USER_DIRECT_REQUIRED_BY_PROFILE |
| is_server_forbidden_site=True + SERVER location | BLOCKED | BLOCKED_SERVER_FORBIDDEN_SITE |
| profile이 blocked_capabilities에 포함 | BLOCKED | BLOCKED_NOT_IN_ALLOWED |
| profile이 capability 허용 안 함 | BLOCKED | BLOCKED_NOT_IN_ALLOWED |

---

## 3. 기존 scripts/gate.py와의 관계

- `scripts/gate.py`는 변경하지 않았다.
- `scripts/gate.py`는 op_name + RiskLevel 기반의 기존 실행 흐름에서 그대로 사용된다.
- `execution_gate.py`는 SiteProfile + SiteCapability 기반의 신규 site_engine 구조에서만 사용된다.
- Phase C 이후 단계에서 두 gate를 점진적으로 통합하는 방안을 검토한다.

---

## 4. 테스트 결과

| 테스트 파일 | 결과 | 통과 수 |
|---|---|---|
| test_site_engine_execution_gate.py | PASS | 30 |
| test_site_engine_profiles.py | PASS | 12 |
| test_site_engine_registry.py | PASS | 10 |
| test_site_engine_audit.py | PASS | 10 |
| test_codebase_layer_audit.py | PASS | 10 |
| **합계** | **PASS** | **72** |

---

## 5. 다음 Phase D 계획

`SITE_ENGINE_PHASE_D_BROWSER_FORM_RESOLVER_01`

- `scripts/site_engine/form_resolver.py` 공통화
  - 기존 `scripts/form/discovery.py` 흡수
  - 사이트별 form 탐색 중복 제거
- `scripts/site_engine/adapters/browser.py`
  - CDP/Playwright 추상화
  - 사이트별 cdp_client 직접 호출 제거 (Phase D 이후 점진적)
