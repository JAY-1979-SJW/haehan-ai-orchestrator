# BROWSER_ALLOWLIST_POLICY_DESIGN_1 리포트

작성일: 2026-05-06  
기준 HEAD: 1cabc02 (직전 단계 완료)

---

## 작업 목적

browser action URL allowlist 정책을 schema/fixture/test 범위만 설계한다.  
실제 사이트 접속, dispatcher 연결, browser 실행, production submit/type/click은 이번 단계 전면 금지.

---

## 직전 단계 WARN 이력

- 단계: BROWSER_SUBMIT_TYPE_RISK_RECLASSIFICATION_1
- 판정: WARN
- WARN 사유:
  - BROWSER_OPEN_TYPE_CLOSE_CONTROLLED_PREFLIGHT.md untracked 유지
  - allowlist 정책 미설계 TODO (browser.plan_open_url, execute_click, execute_type 등)
  - gate_module / audit_module / approval UI 미구현

---

## allowlist가 필요한 action 목록

| action | operation_type | allowlist_required |
|---|---|---|
| browser.plan_open_url | navigate | true |
| browser.open_url_controlled | open_url | true |
| browser.execute_click | click | true |
| browser.execute_type | type | true |
| browser.open_click_close_controlled | click | true |
| browser.open_type_close_controlled | submit | true |

allowlist 불필요 (read-only):
- browser.inspect (read)
- browser.plan_click (read)

---

## operation_type 분류표

| operation_type | allowlist_required | approval_required | audit_required | production_allowed | dry_run_only | 기본 판정 |
|---|---|---|---|---|---|---|
| read | false | false | false | false | true | ALLOW |
| navigate | true | false | false | false | true | ALLOW_IF_DOMAIN_ALLOWLISTED |
| open_url | true | true | false | false | true | ALLOW_IF_DOMAIN_ALLOWLISTED |
| click | true | true | true | false | true | ALLOW_IF_APPROVED |
| type | true | true | true | false | true | ALLOW_IF_APPROVED_AND_NO_SENSITIVE |
| submit | true | true | true | false | true | DENY_BY_DEFAULT |

---

## allowlist schema 표

fixture 구조 (`browser_allowlist_policy_20260506.json`):

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| policy_name | string | O | 정책 식별자 |
| action_name | string | O | browser action명 |
| operation_type | string | O | read/navigate/open_url/click/type/submit |
| domain | string | 조건부 | allowlist_required=true 시 필수 |
| url_pattern | string | 조건부 | allowlist_required=true 시 필수 |
| allowlist_required | bool | O | URL allowlist 필요 여부 |
| approval_required | bool | O | 사용자 승인 필요 여부 |
| audit_required | bool | O | 감사 로그 필수 여부 |
| production_allowed | bool | O | 운영 실행 허용 (항상 false) |
| dry_run_only | bool | O | dry_run 전용 여부 (항상 true) |
| tenant_scope | string/null | O | null이면 DENY |
| expected_verdict | string | O | ALLOW/DENY/DENY_BY_DEFAULT 등 |

---

## 기본 allow 정책

1. operation_type=read: allowlist 없이 ALLOW
2. operation_type=navigate/open_url: domain이 allowlist에 있으면 ALLOW
3. operation_type=click: approval_required=true + audit_required=true + allowlisted domain → ALLOW
4. operation_type=type: 위 조건 + sensitive_field_block 통과 → ALLOW

---

## 기본 deny 정책

1. wildcard-only domain (`*`, `*.*`) → DENY
2. unknown/미등록 domain → DENY
3. production_allowed=true → DENY (현 단계 전면 금지)
4. dry_run_only=false → DENY (현 단계 전면 금지)
5. tenant_scope=null → DENY
6. audit_required=false (click/type/submit) → DENY
7. password/secret/credential intent → DENY (sensitive_field_block)
8. submit operation → DENY_BY_DEFAULT (gate_module 미구현)

---

## click/type/submit 별 승인 필요 기준

| operation | approval_required | 근거 |
|---|---|---|
| click | true | 클릭 대상이 submit/delete/approve 버튼일 수 있음 |
| type | true | 입력값이 form에 반영됨. 민감 필드 위험 |
| submit | true | 사이트 상태 변경. gate_module 구현 후에만 실행 |

---

## production_allowed=false 유지 근거

- gate_module (submit_execution_gate) 미구현
- audit_module (submit_audit_log) 미구현
- approval UI 미구현
- 위 3개 선행 조건 미충족 상태에서 production 실행 시 bypass 위험

---

## dry_run_only=true 유지 근거

- 실제 브라우저 DOM 조작 없이 정책 검증만 수행
- 향후 gate_module 구현 후 dry_run_only=false 허용 검토

---

## tenant_scope/user_scope 필요 근거

- 멀티 테넌트 환경에서 scope 없이 실행 시 권한 범위 불명확
- tenant_scope 누락 = 누가 요청했는지 불명확 → DENY

---

## audit_required 필요 근거

- click/type/submit은 상태 변경 가능성이 있어 감사 추적 필수
- 감사 로그 없이 실행 시 사후 검증 불가

---

## secret/password 입력 금지 기준

- sensitive_field_block: password/otp/cert/token/session/cookie 패턴 감지 시 차단
- intent에 password/secret/credential 포함 시 차단
- 기존 `local_agent/browser_actions.py`의 `_PASSWORD_HINT_RE` 정책과 일치

---

## 실제 사이트 접속/실행하지 않았다는 확인

- 모든 fixture domain은 `example.com`, `PLACEHOLDER_*`, `localhost`, `*.mock` 사용
- g2b 등 실제 업무 사이트: 정책 필요성 문서화만, 실행 가능한 URL fixture 아님
- 실제 HTTP 요청 없음
- 실제 브라우저 open/click/type/submit 없음

---

## dispatcher/task_executor 미연결 유지 확인

- `agent/action_registry.py` 이번 단계 미수정
- `agent/task_executor.py` 미수정
- browser_worker 미수정
- fixture: `dispatcher_connected=false`, `task_executor_connected=false`

---

## 다음 단계 제안

**BROWSER_GATE_MODULE_DESIGN_1**

submit_execution_gate 모듈 설계 단계.  
submit operation의 DENY_BY_DEFAULT를 조건부 ALLOW로 전환하기 위한  
gate 정책, 검증 로직, hash verification schema를 fixture/test로 고정한다.
