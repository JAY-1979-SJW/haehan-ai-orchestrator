# Local Agent User-Present E2E Dry-Run 설계

date: 2026-05-07

## 1. 목적

서버→로컬 Agent USER_PRESENT_TASK push 및 USER_PRESENT_STATUS 반환까지의
전체 흐름을 실제 외부 사이트 접속 없이 synthetic payload로 검증한다.

## 2. synthetic task 흐름

```
서버 dryrun result (DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED)
  └→ build_user_present_task_from_dryrun()
       └→ USER_PRESENT_TASK message (safe_to_execute=False)
            └→ 서버 dispatch endpoint or in-memory queue
                 └→ local agent receive handler
                      └→ state_store WAITING_FOR_USER
                           ├→ [user confirm] → USER_CONFIRMED event → 서버 status handler
                           └→ [user cancel]  → CANCELLED event     → 서버 status handler
```

## 3. 서버 → 로컬 Agent dispatch

- `POST /api/v1/local-agents/{agent_id}/user-present-dispatch`
- `build_user_present_dispatch_response()` 검증
- in-memory UP task queue에 저장
- heartbeat/pull 시 WS 경유 전송 (`_push_user_present_tasks()`)

## 4. 로컬 Agent WAITING_FOR_USER 상태 생성

- `websocket_client.process_user_present_task()` 수신
- `create_local_user_present_task_from_ws()` 호출
- `state_store.create_user_present_task()` → `mark_waiting_for_user()`
- ACK: `{type: "user_present_ack", status: "WAITING_FOR_USER", safe_to_execute: false}`

## 5. 로컬 UI 인증 완료/중단 상태 전이

- `user_present_ui_server` - FastAPI 내부 테스트 클라이언트
- `POST /tasks/{workflow_run_id}/confirm` → `mark_user_confirmed()`
- `POST /tasks/{workflow_run_id}/cancel` → `mark_user_cancelled()`
- 응답에 raw URL / password / OTP / 인증서 비밀번호 없음

## 6. 로컬 Agent → 서버 USER_PRESENT_STATUS 반환

- `build_confirmed_status_event()` / `build_cancelled_status_event()`
- WS: `{message_type: "USER_PRESENT_STATUS", status: "USER_CONFIRMED", safe_to_execute: false}`
- 서버 `handle_user_present_status_event()` 수락
- `get_user_present_status(workflow_run_id)` 조회 가능

## 7. 금지 항목

- 실제 은행/카드/홈택스/정부24/Google 접속 금지
- 실제 브라우저/Playwright 실행 금지
- click/type/fill/submit 금지
- password/otp/certificate_password/token/cookie/session 저장·전송 금지
- raw target_url 전송 금지
- safe_to_execute=True 허용 금지
- browser_worker / task_executor 실제 호출 금지

## 8. PASS/WARN/FAIL 기준

- PASS: 전 구간 safe_to_execute=False, 민감정보 없음, 상태 전이 정상
- WARN: 일부 흐름 미연결(WS 실제 연결 없는 경우 in-memory 대체 허용)
- FAIL: safe_to_execute=True 발생, 민감정보 노출, 실제 브라우저 실행

## 9. 실제 운영 연결 전 남은 조건

- 실제 연결된 local agent에 synthetic task push 검증
- UI 실제 렌더링 확인 (HTML form 표시)
- WS 재연결 시 WAITING_FOR_USER 복원
- 타임아웃/만료 처리
