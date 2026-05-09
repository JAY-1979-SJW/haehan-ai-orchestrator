# SERVER_ACTION_TASK_API_APPROVAL_AUDIT_WIRING_1 작업 보고서

작성일: 2026-05-09  
기준 커밋: afec70b

---

## 1. 작업 목적

이미 구현된 `action_task_handoff.prepare_action_task(...)` layer를 서버 외부 인터페이스에서 호출할 수 있도록
REST/RPC 서비스 함수 진입점을 연결하고, approval request / handoff / evidence / audit 저장 구조의 1차 기반을 구현한다.

실제 제출/투찰/전자서명 핸들러 구현은 이번 작업 범위 밖이다.

---

## 2. 연결된 API/라우터 위치

| 파일 | 역할 |
|---|---|
| `ai_orchestrator/server/action_task_api.py` | 외부 진입점 — `api_prepare_action`, `api_receive_evidence` 등 |
| `ai_orchestrator/server/action_approval_audit_store.py` | approval request JSONL 저장소 |
| `ai_orchestrator/server/action_evidence_store.py` | evidence JSONL 저장소 |

FastAPI 라우터 미연결 (기존 서버에 FastAPI 레이어 없음 확인).  
서비스 함수로 직접 호출 가능한 구조로 구현.

---

## 3. prepare_action_task 연결 방식

`api_prepare_action(...)` → `prepare_action_task(...)` 위임.

- API 계층에서 risk/approval/params_hash 직접 판단 없음
- 정책 판단 100% `action_task_handoff.prepare_action_task`에 위임
- APPROVAL_REQUIRED 판정 시 `action_approval_audit_store`에 기록 추가

---

## 4. approval request 저장 방식

- **저장소**: in-memory dict + JSONL 파일 (`data/audit/action_approval_audit.jsonl`)
- **DB schema 변경 없음**
- **저장 항목**: approval_request_id, action_name, params_hash, requested_by, scope_safe, summary_safe, status, created_at, expires_at, consumed_at, verdict, blocked_reason
- **금지 항목**: raw_params, password, otp, cert_password, private_key, cookie, session, storage_state, 인증서 파일 경로
- **이중 검증**: 저장 전 `_validate_no_forbidden` 호출, 위반 시 ValueError

---

## 5. evidence/audit 저장 방식

- **저장소**: in-memory dict + JSONL 파일 (`data/audit/action_evidence.jsonl`)
- **DB schema 변경 없음**
- **저장 항목**: evidence_id, action_name, approval_request_id, params_hash, result_status, result_fields_safe, evidence_files_ref, local_agent_run_id, occurred_at, stored_at
- **금지 항목**: cookie, session, storage_state, password, otp, cert_password, private_key, localStorage, sessionStorage, raw_browser_storage, 실제 파일 내용
- **파일 evidence**: 경로 ref(`evidence_files_ref`) 허용, 실제 파일 내용 금지
- **이중 검증**: `validate_evidence_fields` → 위반 시 BLOCKED 반환

---

## 6. local agent handoff 응답 구조

`api_prepare_action` 반환값:

```json
{
  "action_name": "browser.download_file",
  "implemented": true,
  "risk_level": "LOW",
  "requires_approval": false,
  "verdict": "HANDOFF_READY",
  "approval_status": "NOT_REQUIRED",
  "approval_request_id": null,
  "params_hash": "...",
  "summary": {...},
  "handoff_required": true,
  "handoff_payload": {
    "action_name": "browser.download_file",
    "params_safe": {...},
    "params_hash": "...",
    "execution_location": "LOCAL_AGENT_REQUIRED",
    "evidence_policy": {...},
    "expires_at": "...",
    "sensitive_data_included": false,
    "cookie_included": false,
    ...
  },
  "dry_run": true
}
```

---

## 7. browser.download_file 처리 결과

- verdict: `HANDOFF_READY`
- requires_approval: false (AUTO_ALLOWED)
- handoff_required: true
- 승인 없이 즉시 local agent handoff 가능

---

## 8. browser.attach_file 처리 결과

- 토큰 없음: verdict `APPROVAL_REQUIRED`, approval_request_id 생성, audit store 기록
- 토큰 제공: verdict `HANDOFF_READY`, handoff_required=true

---

## 9. submit/bid/esign 미구현 액션 처리 결과

| action_name | requires_approval | 토큰 없음 | 토큰 있음 |
|---|---|---|---|
| browser.prepare_submit | False | NOT_IMPLEMENTED | — |
| bid.prepare_bid | False | NOT_IMPLEMENTED | — |
| esign.prepare_signature | False | NOT_IMPLEMENTED | — |
| browser.submit_with_user_approval | True | APPROVAL_REQUIRED | NOT_IMPLEMENTED |
| bid.submit_with_user_approval | True | APPROVAL_REQUIRED | NOT_IMPLEMENTED |
| esign.execute_with_user_approval | True | APPROVAL_REQUIRED | NOT_IMPLEMENTED |

`implemented=False` 유지. 실제 실행 차단 유지.

---

## 10. 보안 차단 기준

| 차단 대상 | 차단 위치 |
|---|---|
| 민감 파라미터 입력 (password/otp/cookie/session/...) | `prepare_action_task` — BLOCKED_SENSITIVE_PARAMS |
| raw params 저장 | `action_approval_audit_store` — ValueError |
| evidence 금지 필드 | `action_evidence_store.validate_evidence_fields` |
| 파일 내용 직접 저장 | `validate_evidence_fields` — file_content 등 차단 |
| handoff payload 민감 플래그 | `validate_handoff_payload` |
| 서버 외부 URL 브라우저 실행 | 코드 없음 (서버에서 Playwright 실행 구조 없음) |
| DB schema 변경 | 없음 |
| 운영 데이터 write | 없음 |

---

## 11. 테스트 결과

| 파일 | 케이스 | 결과 |
|---|---|---|
| test_server_action_task_api_wiring_20260509.py | 14개 | 14 PASS |
| test_server_action_approval_audit_store_20260509.py | 11개 | 11 PASS |
| test_server_action_evidence_store_20260509.py | 11개 | 11 PASS |
| 기존 관련 테스트 (action_registry/approval_gate/handoff) | 203개 | 203 PASS |
| 전체 회귀 | 4912개 | 4912 PASS, 7 skipped, 0 failed |

신규 36/36 PASS. 기존 회귀 0 실패.

---

## 12. 남은 작업

- FastAPI 라우터에 `/api/actions/prepare`, `/api/actions/evidence` 엔드포인트 연결 (서버에 FastAPI 도입 시)
- approval request 만료 처리 자동화 (현재는 in-memory 상태만 추적)
- JSONL audit 파일 로테이션/정리 정책
- `browser.attach_file`, `browser.download_file` 핸들러 실제 서버→local agent 연결 end-to-end 검증
- submit/bid/esign 핸들러 구현 (다음 단계)
