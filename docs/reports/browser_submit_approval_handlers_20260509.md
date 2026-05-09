# BROWSER_SUBMIT_APPROVAL_HANDLERS_1 작업 보고서

작성일: 2026-05-09  
기준 커밋: e92aff7

---

## 1. 작업 목적

등록만 되어 있던 `browser.prepare_submit`, `browser.submit_with_user_approval` 액션을 실제 핸들러로 구현한다.
제출 기능의 개발 범위에 포함하되, 사용자 승인 없는 제출 실행은 차단한다.
서버에서의 실제 외부 사이트 제출 클릭은 local agent handoff로만 전달한다.

---

## 2. 구현된 핸들러

| 액션 | 파일 | 역할 |
|---|---|---|
| `browser.prepare_submit` | `ai_orchestrator/local_agent/actions/browser_prepare_submit.py` | 제출 직전 폼 상태 검증 + 요약 생성 |
| `browser.submit_with_user_approval` | `ai_orchestrator/local_agent/actions/browser_submit_with_user_approval.py` | 승인 토큰 검증 후 handoff 생성 |

---

## 3. prepare_submit 동작

입력:
- `page_url`: 제출 페이지 URL
- `page_title`: 페이지 제목
- `submit_selector`: 제출 버튼 CSS selector
- `form_summary`: 폼 요약
- `target_id`: 공고/투찰 번호
- `organization_name`: 기관명
- `amount`: 금액
- `due_date`: 마감일
- 기타 확장 필드

출력:
- `verdict`: PREPARE_SUCCESS 또는 PREPARE_WARN
- `page_url_safe`: URL host+path (쿼리스트링 제외)
- `attached_files_safe`: 파일명 리스트 (경로 제외)
- `form_summary`, `target_id`, `organization_name`, `amount`, `due_date`
- `evidence`: 감사 증거
- `warnings`: submit_selector 없음 등

검증:
- URL은 host+path만 노출 (query string 제외)
- 파일명은 basename만 (경로 제외)
- password/otp/cert_password 포함 시 BLOCKED_SENSITIVE
- cookie/session/storage_state 포함 시 BLOCKED_SENSITIVE
- submit_selector 없음 시 WARN

**중요: 실제 submit 버튼 클릭 안 함**

---

## 4. submit_with_user_approval 동작

입력:
- `page_url`: 제출 페이지 URL
- `submit_selector`: 제출 버튼 selector
- `approval_token`: 사용자 승인 토큰 (필수)
- 기타: target_id, organization_name, amount, due_date 등

출력:
- `verdict`: SUBMIT_HANDOFF_READY 또는 APPROVAL_REJECTED
- `approval_status`: APPROVED_AND_CONSUMED 또는 INVALID
- `handoff_required`: true (local agent 실행 필수)
- `handoff_payload`: local agent가 실행할 정보
  - action_name, page_url_safe, submit_selector, 승인 정보
  - safe fields만 포함 (forbidden field 미포함)
- `evidence`: 감사 증거

검증:
- 토큰 필수 (없으면 APPROVAL_REQUIRED)
- 토큰 1회용 (재사용 차단)
- 토큰 만료 차단
- action_name + params_hash scope 고정

**중요: 서버에서 직접 클릭하지 않고 local agent handoff로만 전달**

---

## 5. FastAPI API 경유 결과

```
POST /api/v1/actions/prepare
{
  "action_name": "browser.prepare_submit",
  "params": {...}
}
→ verdict: HANDOFF_READY (approved_not_required)

POST /api/v1/actions/prepare
{
  "action_name": "browser.submit_with_user_approval",
  "params": {...}
}
→ verdict: APPROVAL_REQUIRED (토큰 없음)

POST /api/v1/actions/prepare
{
  "action_name": "browser.submit_with_user_approval",
  "params": {...},
  "approval_token": "..."
}
→ verdict: HANDOFF_READY (토큰 유효)

POST /api/v1/actions/evidence
{
  "action_name": "browser.submit_with_user_approval",
  "result_status": "SUCCESS",
  "result_fields_safe": {...}
}
→ accepted: true (safe field)
→ accepted: false (forbidden field 포함 시)
```

---

## 6. approval gate 검증 방식

- `user_approval_gate.create_approval_request`: 승인 요청 생성
- `user_approval_gate.approve_request`: 토큰 발급
- `user_approval_gate.verify_and_consume_token`: 토큰 검증 + 1회 소비
  - action_name 일치
  - params_hash (sanitize된 파라미터) 일치
  - 만료 확인
  - 재사용 차단

---

## 7. local agent handoff 구조

```json
{
  "action_name": "browser.submit_with_user_approval",
  "page_url_safe": "https://www.g2b.go.kr/submit/form",
  "submit_selector": "button.submit",
  "target_id": "공고 12345",
  "organization_name": "기관명",
  "amount": "100,000",
  "due_date": "2026-05-31",
  "approval_request_id": "req-...",
  "approval_token": "token-...",
  "expected_result_markers": [],
  "evidence_requirements": {},
  "created_at": "2026-05-09T...",
  "sensitive_data_included": false,
  "cookie_included": false,
  "session_included": false,
  ...
}
```

safe params만 포함. forbidden field 미포함.

---

## 8. 차단된 위험 동작

| 동작 | 차단 방식 | 결과 |
|---|---|---|
| 승인 없는 submit | APPROVAL_REQUIRED → handoff 차단 | 토큰 필요 |
| 토큰 재사용 | verify_and_consume_token (1회용) | 차단 |
| 토큰 만료 | 만료 시간 검증 | 차단 |
| params hash 이탈 | scope-bound 검증 | APPROVAL_INVALID |
| 서버 직접 submit | handoff payload만 생성 | local agent 전달 |
| 민감 필드 입력 | password/otp 차단 | BLOCKED_SENSITIVE |
| handoff에 forbidden field | safe field만 포함 | 자동 제외 |

---

## 9. bid/esign 미구현 유지 결과

다음 액션은 계속 `implemented=False` 유지:
- `bid.prepare_bid`
- `bid.submit_with_user_approval`
- `esign.prepare_signature`
- `esign.execute_with_user_approval`

API 응답: `verdict=ACTION_REGISTERED_NOT_IMPLEMENTED`, `implemented=False`

---

## 10. 테스트 결과

신규 테스트:
- `test_browser_prepare_submit_action_20260509.py`: 9 PASS
- `test_browser_submit_with_user_approval_action_20260509.py`: 6 PASS
- `test_browser_submit_api_flow_20260509.py`: 14 PASS

기존 테스트 수정 및 통과:
- `test_server_action_task_api_wiring_20260509.py`: 14 PASS (unimplemented 액션 목록 수정)
- `test_server_action_fastapi_router_20260509.py`: 14 PASS (unimplemented 액션 목록 수정)
- `test_action_registry_and_schemas_20260508.py`: 20 PASS (phase1 count, pending list 수정)
- `test_server_task_api_unimplemented_actions_20260509.py`: 12 PASS (pending actions 수정)
- `test_phase1_actions_20260508.py`: All PASS (pending actions 제거)

전체 회귀: **4944 passed, 7 skipped, 0 failed**

---

## 11. 남은 작업

- `bid.prepare_bid` / `bid.submit_with_user_approval` 핸들러 구현 (다음 단계)
- `esign.prepare_signature` / `esign.execute_with_user_approval` 핸들러 구현 (다음 단계)
- end-to-end local agent 실행 검증
- 서버 submit 클릭 관련 보안 감시 강화
