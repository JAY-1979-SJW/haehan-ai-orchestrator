# Local Agent User-Present Status Observability 설계

date: 2026-05-07
status: implemented

## 목적

local_agent가 전송한 USER_PRESENT_STATUS 이벤트를 서버가 수신했을 때,
`workflow_run_id` 기준으로 직접 조회 가능한 상태를 저장한다.

## 수신 상태 저장 방식

- 저장소: in-memory dict (`_status_registry`) — 운영 DB write 없음
- 키: `workflow_run_id`
- 덮어쓰기: 동일 workflow_run_id로 재수신 시 최신 상태로 갱신
- 프로세스 재시작 시 초기화 (영구 저장 불필요 — 이벤트 재전송 가능)

## 저장 필드

| 필드 | 설명 |
|------|------|
| workflow_run_id | 이벤트 식별자 |
| agent_id | 수신 에이전트 |
| tenant_id | 테넌트 |
| user_id | 사용자 |
| site_id | 사이트 |
| status | USER_CONFIRMED / CANCELLED / BLOCKED / FAILED / WAITING_FOR_USER |
| status_reason | 선택적 사유 |
| safe_to_execute | 항상 False |
| received_at | 서버 수신 시각 (ISO UTC) |
| message_ko | 상태 메시지 |

## 저장 금지 필드

password, otp, certificate_password, token, cookie, session,
device_token, registration_code, raw target_url, localStorage, sessionStorage

## 조회 API

- `GET /api/v1/local-agents/user-present-status/{workflow_run_id}`
  - 있으면 저장 레코드 반환
  - 없으면 404
- `GET /api/v1/local-agents/{agent_id}/user-present-statuses`
  - agent_id 기준 수신 목록 반환

## Audit/Log 정책

- 수신 성공 시: `[AUDIT] LOCAL_AGENT_USER_PRESENT_STATUS_RECEIVED`
- 민감정보 reject 시: `[AUDIT] LOCAL_AGENT_USER_PRESENT_STATUS_REJECTED`
- safe_to_execute=true reject 시: reject 기록

## 민감정보 Redaction

- 조회 API 응답에 저장 금지 필드 미포함
- handler 수신 단계에서 reject (저장 자체를 안 함)

## 운영 DB Write 금지 기준

현재 단계: in-memory only.
향후 DB 전환 기준:
- 서비스 재시작 후 이전 이벤트 재현 필요 시
- 이벤트 감사 기간 요건 발생 시 (법적 보존 등)
