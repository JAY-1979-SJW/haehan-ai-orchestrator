# Site Engine Phase E Action & Workflow Runner
**날짜**: 2026-05-15
**단계**: SITE_ENGINE_PHASE_E_ACTION_WORKFLOW_RUNNER_01

---

## 1. 생성/수정 파일

| 파일 | Layer | 역할 |
|---|---|---|
| `scripts/site_engine/action_planner.py` | L4 | ActionPlan, ActionPlanStep, build/append/summarize |
| `scripts/site_engine/workflow_runner.py` | L4 | WorkflowDefinition, WorkflowRunPlan, build/validate/attach |
| `scripts/site_engine/validators.py` | L4 | 순수 검증 함수 5종 |
| `scripts/site_engine/__init__.py` | L4 | 신규 모듈 export 추가 |
| `tests/test_site_engine_action_planner.py` | L11 | 22건 |
| `tests/test_site_engine_workflow_runner.py` | L11 | 13건 |
| `tests/test_site_engine_validators.py` | L11 | 10건 |
| `docs/reports/site_engine_phase_e_action_workflow_runner_20260515.md` | L12 | 이 문서 |

---

## 2. action planner 정책

| action | gate 필요 | executable 조건 |
|---|---|---|
| READ/SEARCH/NAVIGATE | 불필요 | 즉시 READY |
| FORM_FILL (일반 필드) | 불필요 | 즉시 READY |
| FORM_FILL (password/otp/session/cookie 필드) | USER_DIRECT_REQUIRED | USER_ACTION_REQUIRED — 사용자 직접만 |
| credential extraction (extract/dump + 민감키워드) | BLOCKED | 실행 불가 |
| SUBMIT/PUBLISH/SEND/UPLOAD/DELETE | APPROVAL_REQUIRED | gate_result 없이 READY 불가 |
| SIGN | USER_DIRECT_REQUIRED | USER_ACTION_REQUIRED |

step에 `value` 필드 없음 — 민감값 저장 구조 없음.

---

## 3. workflow runner 정책

| workflow 상태 | 조건 |
|---|---|
| READY | 모든 step이 READY |
| APPROVAL_REQUIRED | 비가역 step이 gate 없이 존재 |
| USER_ACTION_REQUIRED | 민감 입력 또는 SIGN step 존재 |
| BLOCKED | BLOCKED step 존재 |
| NEEDS_PROFILE | site_key, profile_key 모두 없음 |

is_executable() == True는 READY 상태일 때만.

---

## 4. validators 정책

| 검증 함수 | 감지 대상 |
|---|---|
| validate_no_plain_secret | dict에 민감 키 원문 존재 |
| validate_no_executable_sensitive_step_without_gate | APPROVAL_REQUIRED step이 gate 없이 READY |
| validate_no_blocked_step_executable | BLOCKED step에 allowed gate_result 붙어 있음 |
| validate_workflow_has_profile | workflow에 site_key/profile_key 없음 |
| validate_action_plan_steps | GATE_REQUIRED step이 있는데 plan이 READY |

---

## 5. 테스트 결과

| 테스트 파일 | 결과 | 통과 수 |
|---|---|---|
| test_site_engine_action_planner.py | PASS | 22 |
| test_site_engine_workflow_runner.py | PASS | 13 |
| test_site_engine_validators.py | PASS | 10 |
| 기존 site_engine 테스트 | PASS | 104 |
| test_codebase_layer_audit.py | PASS | 10 |
| **합계** | **PASS** | **159** |

---

## 6. 다음 Phase F 계획

`SITE_ENGINE_PHASE_F_THIN_ROUTER_MIGRATION_PLAN_01`

- 현재 사이트별 router 현황 분석 (줄 수, CDP 직접 호출 여부, gate 분산 여부)
- 각 사이트 router를 thin dispatcher로 줄이는 순서 고정
- EUM router (541줄) → thin 150줄 이하
- Naver router (823줄) → thin 150줄 이하
- Hiworks, Smartstore, Google, Youtube 순
- 마이그레이션 중에도 기존 기능 동작 보장
