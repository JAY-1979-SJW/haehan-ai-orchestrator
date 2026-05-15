# Site Engine Phase D Browser & Form Resolver
**날짜**: 2026-05-15
**단계**: SITE_ENGINE_PHASE_D_BROWSER_FORM_RESOLVER_01

---

## 1. 생성/수정 파일

| 파일 | Layer | 역할 |
|---|---|---|
| `scripts/site_engine/adapters/__init__.py` | L4 | adapter public export |
| `scripts/site_engine/adapters/browser.py` | L4 | BrowserActionPlan 생성 함수 |
| `scripts/site_engine/form_resolver.py` | L4 | FormFieldCandidate 분류, 민감값 masking |
| `scripts/site_engine/capability_detector.py` | L4 | DOM snapshot 기반 작업 가능성 감지 |
| `scripts/site_engine/__init__.py` | L4 | 신규 모듈 public export 추가 |
| `tests/test_site_engine_browser_adapter.py` | L11 | browser adapter unit test 12건 |
| `tests/test_site_engine_form_resolver.py` | L11 | form resolver unit test 13건 |
| `tests/test_site_engine_capability_detector.py` | L11 | capability detector unit test 15건 |
| `docs/reports/site_engine_phase_d_browser_form_resolver_20260515.md` | L12 | 이 문서 |

---

## 2. browser adapter 정책

| action | plan | gate 연계 |
|---|---|---|
| NAVIGATE | BrowserActionPlan(READ) | READ_ONLY_ALLOWED |
| CLICK | BrowserActionPlan(FORM_FILL) | SERVER_BROWSER_ALLOWED |
| INPUT (일반) | BrowserActionPlan(FORM_FILL) | SERVER_BROWSER_ALLOWED |
| INPUT (password/otp/session/cookie) | BrowserActionPlan(FORM_FILL, sensitive=True) | USER_DIRECT_REQUIRED |
| DOWNLOAD | BrowserActionPlan(DOWNLOAD) | SERVER_BROWSER_ALLOWED |
| UPLOAD | BrowserActionPlan(UPLOAD) | APPROVAL_REQUIRED |
| SUBMIT | BrowserActionPlan(SUBMIT) | APPROVAL_REQUIRED |

plan 객체에 value 필드 없음 — 실제 값 저장 불가 구조.

---

## 3. form resolver 정책

| field/sensitivity | 처리 | 저장 여부 |
|---|---|---|
| EMAIL, NAME, PHONE, ADDRESS | SAFE | 저장 안 함 (value 필드 없음) |
| PASSWORD, OTP, PASSWORD_CONFIRM | FORBIDDEN | mask_field_value() 강제 REDACTED |
| FILE, SELECT | SAFE | 저장 안 함 |
| type=password → 자동 감지 | FORBIDDEN | REDACTED |

---

## 4. capability detector 정책

| capability | 판단 기준 | gate |
|---|---|---|
| READ | 페이지 존재 시 항상 | READ_ONLY_ALLOWED |
| SEARCH | has_search_input=True | SERVER_BROWSER_ALLOWED |
| FORM_FILL | has_form=True 또는 input_types 존재 | SERVER_BROWSER_ALLOWED |
| DOWNLOAD | 버튼 레이블 '다운로드' 등 | SERVER_BROWSER_ALLOWED |
| UPLOAD | file input 또는 버튼 레이블 '첨부' 등 | APPROVAL_REQUIRED |
| SUBMIT | 버튼 레이블 '저장/상신/확인' 등 | APPROVAL_REQUIRED |
| PUBLISH | 버튼 레이블 '게시/발행' 등 | APPROVAL_REQUIRED |
| SEND | 버튼 레이블 '보내기/발송' 등 | APPROVAL_REQUIRED |
| DELETE | 버튼 레이블 '삭제' 등 | APPROVAL_REQUIRED |
| SIGN | 버튼 레이블 '전자서명/인증서' 등 | USER_DIRECT_REQUIRED |
| LOGIN_REQUIRED | 페이지 텍스트 '로그인 후' 등 | - |

---

## 5. 기존 CDP/form/explorer 영향 없음

- `scripts/cdp_client.py` 변경 없음
- `scripts/form/discovery.py` 변경 없음
- `scripts/explorer/page_classifier.py` 변경 없음
- `scripts/site_access.py` 변경 없음

---

## 6. 테스트 결과

| 테스트 파일 | 결과 | 통과 수 |
|---|---|---|
| test_site_engine_browser_adapter.py | PASS | 12 |
| test_site_engine_form_resolver.py | PASS | 13 |
| test_site_engine_capability_detector.py | PASS | 15 |
| test_site_engine_execution_gate.py | PASS | 30 |
| test_site_engine_profiles.py | PASS | 12 |
| test_site_engine_registry.py | PASS | 10 |
| test_site_engine_audit.py | PASS | 10 |
| test_codebase_layer_audit.py | PASS | 10 |
| **합계** | **PASS** | **112** |

---

## 7. 다음 Phase E 계획

`SITE_ENGINE_PHASE_E_ACTION_WORKFLOW_RUNNER_01`

- `scripts/site_engine/action_planner.py`
  - click/input/download/submit 계획 조합
  - execution_gate decision + browser adapter plan 연결
- `scripts/site_engine/workflow_runner.py`
  - 업무 흐름 단계 조합 실행기
  - 사이트별 workflow를 thin definition으로 교체하는 기반
