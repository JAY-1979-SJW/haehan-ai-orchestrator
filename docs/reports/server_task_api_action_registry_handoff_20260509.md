# 서버 task API ↔ action_registry / approval_gate / local agent handoff 통합 (2026-05-09)

## 1. 작업 목적
- 서버 task API 진입 지점에서 `ai_orchestrator.local_agent.action_registry`를 단일 조회 지점으로 사용하도록 한다.
- 모든 등록 액션이 동일한 정책 판정(`requires_approval`, `risk_grade`, `implemented`)을 거치게 만든다.
- 사용자 승인 흐름은 `user_approval_gate`를 재사용하며, 승인 토큰은 1회용·만료·`action_name + params_hash` 범위에 묶여 있어야 한다.
- LOCAL_AGENT_REQUIRED 액션에 대해 sanitize된 handoff payload를 생성한다.
- 제출/투찰/전자서명 6개 액션은 ActionSpec 등록 상태를 유지하되, 실제 실행은 차단한다.
- 본 단계의 범위는 “routing + 정책 + handoff metadata”이며, 실제 submit/bid/esign 실행 핸들러는 만들지 않는다.

## 2. 변경 / 신규 파일
- 신규: `ai_orchestrator/server/action_task_handoff.py`
- 추가(공개 helper만): `ai_orchestrator/local_agent/user_approval_gate.py`
  - `sanitize_params(params)`, `compute_params_hash(params)` — 기존 동작 보존, 추가만.
- 신규 테스트:
  - `tests/test_server_task_api_action_registry_handoff_20260509.py`
  - `tests/test_server_task_api_approval_gate_20260509.py`
  - `tests/test_server_task_api_unimplemented_actions_20260509.py`
- 신규 리포트: 본 문서

기존 파일(`server/local_agent_task_api.py`, `task_queue_schema.py`, `task_protocol.py`, `action_registry.py`, `action_schemas.py`, `action_summary_builder.py`, `local_agent_handoff.py`)은 변경하지 않음 — modularization policy에 맞춰 신규 모듈 추가만.

## 3. 연결된 서버 task API 위치
- 진입점: `ai_orchestrator.server.action_task_handoff.prepare_action_task(...)`
- 기존 큐 어댑터(`server.local_agent_task_api`, `server.task_queue_schema`)와 충돌하지 않는다.
- 기존 큐는 단순 verb(`open_url`, `download_file` 등)만 처리했고, 이번 layer는 fully-qualified 액션명(`browser.download_file`, `browser.attach_file`, `bid.*`, `esign.*`)을 처리한다.

## 4. action_registry 통합 방식
`prepare_action_task` 내부 순서:
1. `action_registry.get_action_spec(action_name)` 조회 → 없으면 `UNKNOWN_ACTION`.
2. 입력 params의 민감 키(password/otp/cert_password/cookie/session/storage_state/private_key 등) → `BLOCKED_SENSITIVE_PARAMS`.
3. `user_approval_gate.sanitize_params` → params_safe.
4. `user_approval_gate.compute_params_hash` → 64자 SHA256 hex.
5. `action_summary_builder.build_action_summary` → summary_safe (URL host+path, 파일명만).
6. handler 등록 여부(`has_handler`) 확인 → warning.
7. `requires_user_approval`/`implemented`/`risk_grade`에 따라 verdict 결정.

반환 envelope:
```
action_name, implemented, risk_level, requires_approval, execution_location,
verdict, approval_status, approval_request_id, params_hash, summary,
handoff_required, handoff_target, handoff_payload, blocked_reason, warnings
```

## 5. approval_gate 통합 방식
- 승인 필요 액션 + 토큰 미제공 → `create_approval_request` 호출, `verdict=APPROVAL_REQUIRED`, `approval_status=PENDING_USER_REVIEW`, `approval_request_id` 반환. handoff 없음.
- 토큰 제공 → `verify_and_consume_token`:
  - 실패 → `verdict=APPROVAL_INVALID`, `blocked_reason`에 사유.
  - 성공 → 1회 소비 처리 후 다음 단계.
- 토큰은 1회용, 만료(default 5분, 1~1800초), `action_name + params_hash` 범위에 묶임.
- `action_name` 불일치, `params_hash` 불일치, 만료, 재사용 모두 차단.

## 6. local agent handoff payload 구조
`build_handoff_payload`가 반환:
- `action_name`
- `params_safe` (민감 키 제거됨)
- `params_hash` (SHA256)
- `execution_location = "LOCAL_AGENT_REQUIRED"`
- `requires_approval`
- `approval_status` (`NOT_REQUIRED` / `APPROVED_AND_CONSUMED` / `PENDING_USER_REVIEW` / `INVALID`)
- `approval_token_required`
- `summary_safe`
- `evidence_policy.allowed_result_fields` (ActionSpec.evidence_fields)
- `evidence_policy.forbidden_fields` (FORBIDDEN_RESULT_FIELDS)
- `created_at`, `expires_at`
- 민감 미포함 플래그: `sensitive_data_included / cookie_included / session_included / password_included / otp_included / cert_info_included / storage_state_included` (모두 False)

`validate_handoff_payload`가 모든 플래그 + params_safe 키 + forbidden_fields 누락을 검증.

## 7. browser.download_file 처리 결과
- 등급: AUTO_ALLOWED, requires_approval=False, implemented=True.
- 흐름: 토큰 없이 즉시 `verdict=HANDOFF_READY`, handoff payload 생성.
- 서버 직접 실행 없음 (`execution_location=LOCAL_AGENT_REQUIRED` 유지).
- summary는 `source_url_safe`(host+path) + `expected_filename` 만 노출 — query string의 token 등은 미노출.

## 8. browser.attach_file 처리 결과
- 등급: USER_DELEGATED_PERMISSION_REQUIRED, requires_approval=True, implemented=True.
- 토큰 미제공 시 `APPROVAL_REQUIRED` + `approval_request_id` 반환, handoff 없음.
- 사용자가 `approve_request`로 토큰 발급 → `prepare_action_task`에 토큰 포함 호출 → `HANDOFF_READY`.
- params 변경 시 `APPROVAL_INVALID` (params_hash 불일치).
- 다른 액션에 토큰 재사용 시 `APPROVAL_INVALID` (action_name 불일치).
- 토큰 재사용·만료 시 차단.

## 9. 미구현 제출/투찰/전자서명 액션 처리 방식
대상 6개:
- `browser.prepare_submit`, `browser.submit_with_user_approval`
- `bid.prepare_bid`, `bid.submit_with_user_approval`
- `esign.prepare_signature`, `esign.execute_with_user_approval`

처리:
- ActionSpec 등록 상태는 유지 (`implemented=False`).
- `register_handler`는 기존대로 `implemented=False` 액션의 핸들러 등록을 거부.
- `prepare_action_task` verdict는 `ACTION_REGISTERED_NOT_IMPLEMENTED`.
- `requires_approval=True` 항목은 승인 요청은 생성될 수 있으나, 토큰을 소비해도 verdict는 `ACTION_REGISTERED_NOT_IMPLEMENTED`로 남고 handoff 미생성 — 실행 차단.
- `blocked_reason`에 “핸들러 미연결” 명시.

## 10. 보안 차단 기준
- 입력 파라미터 키에 `password`, `otp`, `cert_password`, `cookie`, `session`, `storage_state`, `private_key`, `auth_header`, `Authorization`, `npki`, `token` 등이 포함되면 즉시 `BLOCKED_SENSITIVE_PARAMS`.
- handoff payload는 `params_safe`(sanitize), 민감 플래그 모두 False, evidence_policy의 `forbidden_fields`에 모든 민감 result key 포함.
- 외부 URL 브라우저 직접 실행 코드 없음 — 모든 액션이 `LOCAL_AGENT_REQUIRED`.
- DB schema 변경 없음, 운영 데이터 write 없음.
- 승인 토큰 1회용·만료·scope-bound (`action_name + params_hash`).
- 승인 토큰을 소비해도 미구현 액션은 실행 차단.

## 11. 테스트 결과
- 신규 3개 파일 합계 **34/34 PASS**.
- 관련 기존 테스트(`-k "action_registry or user_approval or action_summary or attach_file or download_file or task_protocol or task_queue or local_agent_task_api"`) **236/236 PASS**.
- 전체 회귀 **4876 passed, 7 skipped, 0 failed** (657s).
- `git diff --check`: clean.
- 보안 grep: 신규 모듈의 민감 키 언급은 모두 sanitize/forbidden 목록 — 값 저장/출력 없음.

## 12. 남은 작업
- `browser.attach_file` 외 USER_DELEGATED 액션의 실제 핸들러 연결.
- `browser.prepare_submit / browser.submit_with_user_approval`의 form 미리보기·승인 후 1회 제출 핸들러 구현.
- `bid.*`, `esign.*` 핸들러 — 외부 사이트 보안 정책과 연동.
- 서버 task API 외부 인터페이스(REST/RPC)에서 본 layer를 호출하도록 wiring (현재는 함수 진입점만 노출).
- evidence/audit 저장(`approval_audit_log` 등) 연동.
- 현재 in-memory state(`user_approval_gate._REQUESTS`)의 다중 프로세스 공유 방안.
