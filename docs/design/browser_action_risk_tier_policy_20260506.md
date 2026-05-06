# Browser Action Risk Tier Policy

**문서 ID**: BROWSER_ACTION_RISK_TIER_POLICY_1  
**작성일**: 2026-05-06  
**상태**: ACTIVE

---

## 1. 목적

- 모든 브라우저 행동을 무조건 통제하지 않는다.
- 위험한 행동만 강하게 통제한다.
- GATE는 상태 변경/제출 계열에만 강제한다.

---

## 2. Risk Tier 정의

### LOW_READ

**포함 액션:**
- page_open
- read_text
- extract_table
- screenshot
- inspect_dom
- get_current_url
- check_status

**정책:**
- 승인 불필요
- GATE 불필요
- 간단 audit만 권장
- 실제 업무 사이트도 read-only면 허용 가능

---

### LOW_NAVIGATE

**포함 액션:**
- click_tab
- click_detail
- pagination
- breadcrumb
- open_link_same_origin

**정책:**
- 승인 불필요
- GATE 불필요
- 외부 도메인 이동 시 audit 필요
- 로그인/결제/제출 페이지 이동은 별도 분류

---

### MEDIUM_TYPE

**포함 액션:**
- type_text
- fill_search_keyword
- fill_filter
- fill_date_range
- select_option

**정책:**
- 민감 필드 차단: password / otp / cert / token / session / cookie 필드 차단
- 검색/필터 입력은 승인 불필요 가능
- 업무 폼 입력은 preview 권장
- submit은 절대 자동 연계 금지

---

### MEDIUM_DOWNLOAD

**포함 액션:**
- download_file
- save_attachment
- export_csv
- export_pdf

**정책:**
- 다운로드 경로 allowlist 필요
- 파일명/확장자 검사
- audit 필요
- 실행 파일 다운로드는 차단 (.exe, .bat, .sh, .ps1 등)

---

### HIGH_STATE_CHANGE

**포함 액션:**
- save_form
- form_commit
- approve_request
- mark_complete
- delete_record
- update_status

**정책:**
- 승인 필요
- GATE 필수
- audit 필수
- preview 권장
- 되돌릴 수 없는 상태 변경은 사전 hash 검증 필요

---

### CRITICAL_SUBMIT

**포함 액션:**
- submit_form
- final_submit
- confirm_action
- execute_transaction
- open_type_close_controlled (현재 구현된 controlled submit)

**정책:**
- GATE 필수 (`submit_execution_gate`)
- preview + preview_hash 필수
- 승인 필수 (`user_confirmed=True`)
- audit 필수 (`submit_audit_log`)
- 실행 전 policy_verdict=ALLOW 검증 필수
- production submit 자동 연계 금지 (controlled internal only)

---

## 3. 기존 구현과의 매핑

| 기존 action | Risk Tier | 구현 상태 |
|---|---|---|
| inspect | LOW_READ | 구현됨 |
| plan_click | LOW_NAVIGATE | 구현됨 (plan-only) |
| plan_type | MEDIUM_TYPE | 구현됨 (plan-only, typed=False) |
| plan_submit | HIGH_STATE_CHANGE | 구현됨 (plan-only) |
| execute_click | LOW_NAVIGATE~MEDIUM | 구현됨, requires_approval=True |
| execute_type | MEDIUM_TYPE | 구현됨, requires_approval=True |
| open_type_close_controlled | CRITICAL_SUBMIT | 구현됨, controlled internal only |

---

## 4. GATE 적용 범위

- GATE 강제 대상: `HIGH_STATE_CHANGE`, `CRITICAL_SUBMIT`
- GATE 선택 대상: `MEDIUM_TYPE` (업무 폼 한정), `MEDIUM_DOWNLOAD`
- GATE 불필요: `LOW_READ`, `LOW_NAVIGATE`

---

## 5. 충돌 판정

- production submit 연결: 없음 (controlled_submit.py = "no actual network submit")
- action registry/task_executor 수정: 없음
- 기존 GATE 구조와 충돌: 없음 (submit_execution_gate는 CRITICAL_SUBMIT에만 적용)
- 기존 policy.py requires_approval 설정과 충돌: 없음

**판정: PASS_BROWSER_ACTION_RISK_TIER_POLICY**
