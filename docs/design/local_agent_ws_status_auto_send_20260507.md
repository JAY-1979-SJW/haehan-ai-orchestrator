# Local Agent WS Status Auto-Send 설계

date: 2026-05-07

## 1. 목적

로컬 UI에서 사용자가 "인증 완료" 또는 "중단"을 누른 뒤,
`core/agent_runtime/connection/websocket_client.py`가 상태 변화를 감지하여
`USER_PRESENT_STATUS` 메시지를 서버 WebSocket으로 자동 전송한다.

## 2. 상태 변화 감지 방식

`user_present_status_sender.py`의 `collect_pending_user_present_status_events()` 가
`default_store.list_user_present_tasks()`를 순회하여 FINAL 상태 task를 스캔한다.

```
state_store.list_user_present_tasks()
  └→ filter: state in {USER_CONFIRMED, CANCELLED, BLOCKED, FAILED}
       └→ filter: (workflow_run_id, status) not in _sent_statuses
            └→ build_ws_status_event_from_local_task(task)
```

- 별도 스레드/타이머 없음
- heartbeat timeout → `run_user_present_status_send_once(ws)` 호출
- 동기 방식, 한 번에 pending 전부 전송 시도

## 3. 전송 대상 상태

| 상태 | 전송 여부 | 비고 |
|------|-----------|------|
| USER_CONFIRMED | ✅ | 사용자 인증 완료 |
| CANCELLED | ✅ | 사용자 취소 |
| BLOCKED | ✅ | 정책 차단 |
| FAILED | ✅ | 처리 실패 |
| WAITING_FOR_USER | ❌ | task 수신 ack으로만 처리, 반복 전송 금지 |
| TASK_RECEIVED | ❌ | 중간 상태, 전송 대상 아님 |

## 4. 중복 전송 방지 정책

- `_sent_statuses: dict[str, str]` — `{workflow_run_id: last_sent_status}`
- 전송 성공 시 `_sent_statuses[workflow_run_id] = status` 기록
- `collect_pending_user_present_status_events()`에서 이미 sent인 항목 제외
- 같은 workflow_run_id의 같은 status 반복 전송 없음
- sent marker는 모듈 수준 in-memory (프로세스 재시작 시 초기화 — 재시작 후 재전송 허용)

## 5. 서버 ack 처리

서버 WS 메시지 타입 `user_present_status_ack`:
- `{"type": "user_present_status_ack", "workflow_run_id": "...", "ok": true}` 수신 시 sent 확정
- ack 미수신 / ok=false 시 sent marker 기록하지 않음 → 다음 heartbeat 재전송 가능
- ack 대기 timeout: 5초

## 6. 실패/retry 정책

- 전송 시도 실패 → sent marker 미기록 → 다음 heartbeat에 재시도
- WS 연결 단절 → session 재시작 시 재전송 시도 (sent marker 메모리 유지)
- 연속 실패 시 log만 남기고 agent crash 없음

## 7. 민감정보 미전송 정책

전송 전 event 검사:
- `password`, `otp`, `certificate_password`, `financial_certificate_password`,
  `token`, `access_token`, `refresh_token`, `cookie`, `session`, `localStorage`
  포함 시 전송 거부 + BLOCKED_SENSITIVE_FIELD 오류
- `safe_to_execute: true` 이면 전송 거부
- `target_url` raw (redacted 아님) 포함 금지

## 8. 실제 브라우저 미실행 정책

- `playwright`, `click`, `type`, `fill`, `submit`, `execute_click`, `execute_type` 호출 없음
- `browser_worker`, `task_executor` 호출 없음
- `open_url_execute` 호출 없음

## 9. 운영 등록코드/토큰 취급 주의사항

- `registration_code` 원문은 어떤 로그/이벤트에도 포함 금지
- `device_token` 원문은 어떤 이벤트에도 포함 금지
- `docker exec issue_code` 방식은 smoke 전용, 운영 표준 등록 방식이 아님
- 운영 등록은 admin-web UI 또는 `--register-with-code` CLI 사용

## 10. 구현 범위

### 신규 파일
- `core/agent_runtime/user_present/user_present_status_sender.py`

### 수정 파일
- `core/agent_runtime/connection/websocket_client.py` — heartbeat loop에 `run_user_present_status_send_once()` 연결
