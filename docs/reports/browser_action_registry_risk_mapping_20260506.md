# BROWSER_ACTION_REGISTRY_RISK_MAPPING_1 보고서

**작성일**: 2026-05-06  
**기준 HEAD**: aae7bfe

---

## 1. 작업 목적

Risk Tier 정책(`BROWSER_ACTION_RISK_TIER_POLICY_1`)을 실제 registry 연결 전에 action별로 매핑한다.  
이번 단계는 설계 및 감사이며, registry/task_executor 수정은 금지.

---

## 2. registry / task_executor read-only 감사 결과

| 항목 | 결과 |
|---|---|
| ACTION_RISK 위치 | `ai_orchestrator/local_agent_risk_policy.py` |
| browser action 등록 수 | 10개 (inspect~open_type_close_controlled) |
| executor.ALLOWED_ACTIONS | `get_server_status`, `fetch_web_page` 2개만 — browser 미등록 |
| browser_tool import (router/executor) | 없음 — 미연결 상태 |
| submit 6개 모듈 외부 연결 | 없음 — 완전 독립 |
| production submit 연결 | 없음 |

---

## 3. Action Mapping Matrix 요약

| action_name | risk_tier | requires_gate | requires_approval | read_only |
|---|---|---|---|---|
| browser.inspect | LOW_READ | false | false | true |
| browser.plan_click | LOW_NAVIGATE | false | false | true |
| browser.plan_type | MEDIUM_TYPE | false | false | true |
| browser.plan_open_url | LOW_NAVIGATE | false | false | true |
| browser.plan_submit | HIGH_STATE_CHANGE | **true** | true | false |
| browser.execute_click | LOW_NAVIGATE | false | true | false |
| browser.execute_type | MEDIUM_TYPE | false | true | false |
| browser.open_url_controlled | LOW_NAVIGATE | false | true | false |
| browser.open_click_close_controlled | LOW_NAVIGATE | false | true | false |
| browser.open_type_close_controlled | CRITICAL_SUBMIT | **true** | true | false |

---

## 4. Risk Tier별 action 수

| Risk Tier | action 수 |
|---|---|
| LOW_READ | 1 |
| LOW_NAVIGATE | 4 |
| MEDIUM_TYPE | 2 |
| HIGH_STATE_CHANGE | 1 |
| CRITICAL_SUBMIT | 1 |
| BLOCKED | 2 (등록 금지) |

---

## 5. GATE 필수 action

- `browser.plan_submit` — HIGH_STATE_CHANGE (현재 ACTION_RISK `low` → `high` 재검토 필요)
- `browser.open_type_close_controlled` — CRITICAL_SUBMIT (현재 `medium` → `high` 재검토 필요)

---

## 6. GATE 미적용 action

- `browser.inspect`, `browser.plan_click`, `browser.plan_type`, `browser.plan_open_url`
- `browser.execute_click`, `browser.execute_type`, `browser.open_url_controlled`, `browser.open_click_close_controlled`

---

## 7. BLOCKED_CRITICAL action (등록 금지)

- `browser.submit.production` — production submit 금지
- `browser.submit.real` — production submit 금지

---

## 8. production submit 금지 유지 확인

- `controlled_submit.py`: `production_submit_enabled=False` 기본값
- executor dispatcher: browser 분기 없음
- `production_submit_allowed=False` 전 action 확인됨

---

## 9. 테스트 결과

| 스위트 | 결과 |
|---|---|
| risk mapping (신규, 23개) | **23 passed** |
| risk tier policy (20개) | PASS |
| execution gate validator | PASS |
| gate controlled smoke | PASS |
| policy validator | PASS |
| **합계** | **141 passed** |

---

## 10. 금지 항목 준수

| 항목 | 결과 |
|---|---|
| action registry 수정 | NONE |
| task_executor 수정 | NONE |
| browser_tool/*.py 수정 | NONE |
| production submit 연결 | NONE |
| 실제 업무 사이트 | NONE |
| DB/docker/package | NONE |
| secret/token 원문 | NONE |
| BROWSER preflight 수정 | NONE (untracked 유지) |
| git diff --check | PASS |
| py_compile | PASS |

---

## 11. 다음 단계 제안

**BROWSER_READ_NAVIGATE_ACTION_REGISTRY_1**

- `executor.ALLOWED_ACTIONS`에 LOW_READ / LOW_NAVIGATE browser action 추가
- `_dispatch_allowed_action`에 `browser_tool.router.dispatch` 분기 연결
- 대상: `browser.inspect`, `browser.plan_click`, `browser.plan_type`, `browser.plan_open_url`
- GATE 없이 read-only 경로로 처리
