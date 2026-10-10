# Local Agent WebSocket User-Present Runtime

날짜: 2026-05-07

## 1. 목적

USER_PRESENT_TASK / USER_PRESENT_STATUS contract를
실제 core/agent_runtime/connection/websocket_client.py 런타임 흐름에 연결한다.

실제 브라우저 action 실행 없음. safe_to_execute=False 유지.

## 2. 기존 WebSocket 흐름

### 로컬 Client (websocket_client.py)
```
연결 → auth → 메시지 루프
  mtype == "task" → process_task() → result 회신
  mtype == "heartbeat_ack" / "idle" / ... → 무시
  else → 로그
```

### 서버 WS 엔드포인트 (local_agent_router.py /ws)
```
수신 → auth 검증 → 메시지 루프
  mtype == "heartbeat" → heartbeat_ack 송신 + push_queued
  mtype == "pull" → push_queued
  mtype == "running" → _handle_running()
  mtype == "result" → _handle_result()
  else → UNKNOWN_MESSAGE_TYPE 에러
```

## 3. USER_PRESENT_TASK 수신 처리 위치

**로컬 Client (websocket_client.py)**
- `_run_session()` 내 메시지 루프에 `mtype == "user_present_task"` 분기 추가
- `process_user_present_task(task_msg)` 함수 호출
- `user_present_ws_adapter.create_local_user_present_task_from_ws()` 실행
- local state_store에 WAITING_FOR_USER task 생성
- 서버에 `{"type": "user_present_ack", "workflow_run_id": ..., "status": "WAITING_FOR_USER"}` 회신

**연결 위치**: `core/agent_runtime/connection/websocket_client.py` 메시지 루프 `else` 분기 앞에 삽입

## 4. local state_store 등록 흐름

```
1. 서버가 {"type": "user_present_task", "task": {...}} 전송
2. websocket_client가 user_present_task 타입 인식
3. process_user_present_task(task) 호출
4. user_present_ws_adapter.create_local_user_present_task_from_ws(task) 실행
5. user_present_state_store에 workflow_run_id 기준 task 등록
6. 초기 state = TASK_RECEIVED → WAITING_FOR_USER
7. ack 메시지 {"type": "user_present_ack", "workflow_run_id": ..., "status": "WAITING_FOR_USER"} 서버 회신
```

## 5. local UI 인증 완료/중단 후 status event 생성 흐름

```
1. user_present_ui_server를 통해 사용자가 확인/취소 클릭
2. user_present_ws_adapter.mark_local_user_confirmed_and_build_event() 또는
   user_present_ws_adapter.mark_local_user_cancelled_and_build_event() 호출
3. build_waiting/confirmed/cancelled_status_event() 로 USER_PRESENT_STATUS event 생성
4. websocket_client가 {"type": "user_present_status", ...} 서버에 송신
5. 서버 WS 엔드포인트가 handle_user_present_status_event() 로 처리
```

## 6. 서버 USER_PRESENT_STATUS 수신 처리 위치

**서버 WS 엔드포인트 (local_agent_router.py)**
- `mtype == "user_present_status"` 분기 추가
- `_handle_user_present_status(ws, agent_id, msg)` 호출
- `handle_user_present_status_event(event)` 검증 및 응답

**서버 측 handler 위치**:
`ai_orchestrator/agent_hub/user_present_status_handler.py`

## 7. 민감정보 미전송 정책

- user_present_ws_adapter.sanitize_user_present_ws_payload() 적용 필수
- raw target_url 전송 금지 (redacted/hash만)
- password/otp/certificate_password/token/cookie/session 저장/전송 금지
- safe_to_execute=true 포함 event는 서버 reject

## 8. 실제 브라우저 action 미실행 정책

- USER_PRESENT_TASK 수신은 state_store 등록만 수행
- USER_CONFIRMED는 상태 전이만 수행
- click/type/fill/submit 없음
- browser_worker/task_executor 연결 없음

## 9. 테스트 방식

- 실제 WebSocket 서버 없이 `process_user_present_task()` 단위 테스트
- `InMemoryTestTransport` 기반 메시지 흐름 테스트
- 서버 handler는 직접 함수 호출 테스트 (HTTP/WS 연결 없이)
