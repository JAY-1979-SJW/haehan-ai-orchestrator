# SERVER_ACTION_FASTAPI_ROUTER_THIN_WIRING_1 작업 보고서

작성일: 2026-05-09  
기준 커밋: 9f11d86

---

## 1. 작업 목적

이미 구현된 `api_prepare_action`, `api_receive_evidence` 서비스 함수를 FastAPI 라우터에 얇게 연결한다.
라우터에서 직접 정책 판단을 재구현하지 않고, 외부 API 진입점만 안전하게 연다.

---

## 2. 추가된 endpoint

| Method | Path | 역할 |
|---|---|---|
| POST | `/api/v1/actions/prepare` | action 실행 준비 (승인 요청 / handoff 생성) |
| POST | `/api/v1/actions/evidence` | evidence safe field 수신 저장 |

기존 `/api/v1` prefix 규칙을 따른다.

---

## 3. 연결된 service 함수

| endpoint | service 함수 |
|---|---|
| `/api/v1/actions/prepare` | `ai_orchestrator.server.action_task_api.api_prepare_action` |
| `/api/v1/actions/evidence` | `ai_orchestrator.server.action_task_api.api_receive_evidence` |

라우터(`action_router.py`)는 요청 body 검증(Pydantic) 후 service 함수 호출만 수행.
risk/approval/params_hash 판단 재구현 없음.

---

## 4. prepare endpoint 결과

- download_file → `HANDOFF_READY`, handoff_payload 포함
- attach_file (토큰 없음) → `APPROVAL_REQUIRED`, approval_request_id 생성
- attach_file (토큰 있음) → `HANDOFF_READY`
- unknown action → `UNKNOWN_ACTION`
- 응답 schema: action_name / verdict / implemented / risk_level / requires_approval / approval_status / approval_request_id / params_hash / summary / handoff_required / handoff_payload / blocked_reason / warnings / dry_run

---

## 5. evidence endpoint 결과

- safe field → accepted=true, evidence_id 반환
- forbidden field (cookie/session/password 등) → accepted=false, evidence_id=null
- 응답에 민감 필드 미포함 (`_strip_forbidden` 이중 제거)

---

## 6. submit/bid/esign 미구현 액션 처리

| action_name | 처리 |
|---|---|
| browser.prepare_submit / bid.prepare_bid / esign.prepare_signature | NOT_IMPLEMENTED, implemented=False |
| browser.submit_with_user_approval / bid.submit_with_user_approval / esign.execute_with_user_approval | APPROVAL_REQUIRED (토큰 없음), NOT_IMPLEMENTED (토큰 있음) |

실제 실행 차단 유지.

---

## 7. JSONL audit/evidence 파일 git 포함 방지

`.gitignore`에 `data/audit/` 경로 추가.
테스트 실행 시 생성되는 `data/audit/action_approval_audit.jsonl`, `data/audit/action_evidence.jsonl` 파일은 git에 포함되지 않는다.

---

## 8. 보안 차단 기준

| 차단 대상 | 차단 위치 |
|---|---|
| 라우터 직접 정책 판단 | 구조적 금지 — 라우터는 service 호출만 수행 |
| 응답 민감 필드 | `_strip_forbidden` — password/otp/cookie/session 등 제거 |
| evidence 금지 필드 | service layer `validate_evidence_fields` → BLOCKED |
| 서버 외부 브라우저 실행 | 코드 없음 |
| raw params 저장 | service layer 차단 |
| DB schema 변경 | 없음 |
| 운영 데이터 write | 없음 |

---

## 9. 테스트 결과

| 파일 | 케이스 | 결과 |
|---|---|---|
| test_server_action_fastapi_router_20260509.py | 14개 | 14 PASS |
| 기존 action_task_api / store 테스트 | 36개 | 36 PASS |
| 기존 관련 테스트 (action_registry/handoff/approval_gate) | 184개 | 184 PASS |
| 기존 server 관련 테스트 | 446개 | 446 PASS |
| 전체 회귀 | 4926개 | 4926 PASS, 7 skipped, 0 failed |

---

## 10. 남은 작업

- 인증 미들웨어 강화 (현재 AUTH_ENABLED=False 환경)
- approval request 조회/목록 API (GET /api/v1/actions/approvals)
- evidence 조회 API (GET /api/v1/actions/evidence/{id})
- approval 만료 자동화
- browser.attach_file / browser.download_file end-to-end 연결 검증
- submit/bid/esign 핸들러 구현 (다음 단계)
