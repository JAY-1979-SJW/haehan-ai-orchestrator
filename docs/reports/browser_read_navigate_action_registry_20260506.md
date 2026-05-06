# BROWSER_READ_NAVIGATE_ACTION_REGISTRY_1 리포트

작성일: 2026-05-06  
기준 HEAD: 63b77c3  
단계 판정: WARN_READ_NAVIGATE_REGISTERED_WITH_TODO

---

## 작업 목적

browser read/navigate 계열 action을 `agent/action_registry.py`에 안전하게 최소 등록하고,
risk/action metadata 테스트를 고정한다.

executor dispatcher 연결, production 실행, submit/type/click 계열 변경은 이번 단계 제외.

---

## 등록된 read/navigate action 목록

| action | category | risk | tier | read_only | requires_approval | dispatcher_connected |
|---|---|---|---|---|---|---|
| browser.inspect | browser | low | LOW_READ | true | false | false (미연결) |
| browser.plan_click | browser | low | LOW_NAVIGATE | true | false | false (미연결) |
| browser.plan_open_url | browser | low | LOW_NAVIGATE | true | false | false (미연결) |

- 모두 `requires_file_path=False`, `requires_save_as=False`
- `requires_browser=True` (메타데이터만, 실제 실행 미연결)
- `production_submit_possible`: 해당 없음 (ActionMeta 필드 없음 = false 의미)
- `credential_required`: false

---

## 제외한 action 목록

| action | tier | 제외 근거 |
|---|---|---|
| browser.plan_submit | HIGH_STATE_CHANGE | submit 계열, risk high 재검토 TODO |
| browser.execute_click | LOW_NAVIGATE | execute 계열, medium risk |
| browser.execute_type | MEDIUM_TYPE | type/execute 계열 |
| browser.open_url_controlled | LOW_NAVIGATE | controlled 실행 계열 |
| browser.open_click_close_controlled | LOW_NAVIGATE | click+close 실행 계열 |
| browser.open_type_close_controlled | CRITICAL_SUBMIT | CRITICAL, risk high 재검토 TODO |

---

## submit/type/click/file-write 계열 제외 근거

이번 단계는 read-only page observation / navigation 계획 단계 action만 대상.  
실제 DOM mutation(submit/type/click) 계열은 executor dispatcher 연결 및  
risk 재분류 완료 이후 단계에서 별도 등록한다.

---

## TODO/WARN: browser.plan_submit high 재검토

- 현재 risk mapping fixture: `current_risk=low`, `risk_tier=HIGH_STATE_CHANGE`
- `risk_level_needs_review=true`, `recommended_risk=high` 플래그 설정됨
- action_registry.py 미등록 상태 유지
- 다음 단계 `BROWSER_SUBMIT_TYPE_RISK_RECLASSIFICATION_1`에서 처리 필요

---

## TODO/WARN: browser.open_type_close_controlled high 재검토

- 현재 risk mapping fixture: `current_risk=medium`, `risk_tier=CRITICAL_SUBMIT`
- `risk_level_needs_review=true`, `recommended_risk=high` 플래그 설정됨
- action_registry.py 미등록 상태 유지
- CRITICAL_SUBMIT tier gate_module=submit_execution_gate, controlled_internal_only=true
- 다음 단계에서 high 재분류 후 등록 검토

---

## TODO: browser.plan_open_url allowlist_required 정책

- 외부 URL 이동 가능성으로 인해 URL allowlist 정책 설계 필요
- 현재: 정책 없이 low risk metadata만 등록
- 별도 단계 `BROWSER_ALLOWLIST_POLICY_DESIGN_1`에서 처리 권장

---

## executor dispatcher 미연결 유지 확인

- `agent/action_registry.py` 수정 범위: CATEGORY_BROWSER 추가 + 3개 ActionMeta 등록
- `task_executor.py` 미수정
- dispatcher 연결 코드 미추가
- `browser_worker/` 미수정

---

## production submit 미실행 확인

- production submit/type/click 실행 코드 추가 없음
- 실제 브라우저 기동 없음
- 실제 업무 사이트 접근 없음

---

## untracked BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md 유지 확인

- 파일 존재: 유지 (삭제/수정 없음)
- git untracked 상태 유지
- 이번 작업과 경로 충돌 없음

---

## 수정 파일

- `agent/action_registry.py` - CATEGORY_BROWSER 추가, 3개 ActionMeta 등록
- `tests/test_browser_read_navigate_action_registry_20260506.py` - 신규 테스트 (13개 항목)
- `docs/reports/browser_read_navigate_action_registry_20260506.md` - 이 리포트

---

## 다음 단계 제안

**BROWSER_SUBMIT_TYPE_RISK_RECLASSIFICATION_1**

browser.plan_submit(low→high 재분류)과 browser.open_type_close_controlled(medium→high 재분류)를
risk mapping fixture 및 action_registry 동시 반영하는 단계.
