# Local Agent Restart and Status Smoke Report

date: 2026-05-07
task: LOCAL_AGENT_RESTART_AND_STATUS_SMOKE_1
result: PASS

## 기준선

| 항목 | 값 |
|------|-----|
| local HEAD | 2c488d2 |
| origin HEAD | 2c488d2 |
| server HEAD | 2c488d2 |
| tracked dirty | 없음 |

## local_agent 재시작

| 항목 | 내용 |
|------|------|
| 재시작 여부 | YES — 기존 PID 3194771 (구버전) 정상 종료 후 PID 3381787 재시작 |
| 실행 방식 | nohup python3 /tmp/run_combined_agent.py (WS + UI 스레드 통합) |
| UI 포트 | 127.0.0.1:18081 |
| 코드 기준 | 2c488d2 (user_present_status_sender 포함) |

## 연결된 Agent

| 항목 | 값 |
|------|-----|
| agent_id | la-d843d5d3d9c5 |
| host | haehan-mcp (서버 호스트) |
| agent_status | idle (연결 중) |
| connected_at | 2026-05-07T11:36:50+00:00 |

## heartbeat 상태

heartbeat 정상 동작. heartbeat timeout 후 run_user_present_status_send_once() 자동 호출 확인.

## synthetic dispatch 결과

| workflow_run_id | 결과 |
|-----------------|------|
| smoke_auto_status_confirm_20260507_113920 | dispatched=true |
| smoke_auto_status_cancel_20260507_114200 | dispatched=true |

## WAITING_FOR_USER 표시

- `state: WAITING_FOR_USER` 확인
- `safe_to_execute: false` 확인
- password/otp/token/cookie/session 없음

## USER_CONFIRMED 자동 전송

```
[status-sender] USER_PRESENT_STATUS 전송 wf=smoke_auto_status_confirm_20260507_113920 status=USER_CONFIRMED
```

- confirm API 호출 후 heartbeat 주기 내 자동 전송 완료
- flat payload 형식: `{"type": "user_present_status", **event_fields}`
- safe_to_execute=false 유지
- 서버 핸들러 수신 및 USER_CONFIRMED ack 정상

## CANCELLED 자동 전송

```
[status-sender] USER_PRESENT_STATUS 전송 wf=smoke_auto_status_cancel_20260507_114200 status=CANCELLED
```

- cancel API 호출 후 heartbeat 주기 내 자동 전송 완료
- safe_to_execute=false 유지

## 중복 전송 방지

- 각 workflow_run_id/status 조합에 대해 1회만 전송
- sent marker 기록 후 collect_pending에서 제외 확인

## 민감정보 차단 확인

- local_agent 로그에 password/otp/token/cookie/session/registration_code/device_token 없음
- 서버 API 로그에 민감정보 없음
- target_url_redacted만 사용 (raw target_url 없음)

## 브라우저 실행 금지 확인

- playwright 호출 없음
- click/type/fill/submit 없음
- browser_worker/task_executor 호출 없음
- 실제 브라우저 미실행

## 실제 외부 사이트 접속 여부

없음. smoke.local synthetic payload만 사용.

## 테스트 결과

| 테스트 파일 | 결과 |
|------------|------|
| test_local_agent_ws_status_auto_send_20260507.py | 32 PASS |
| test_local_agent_user_present_end_to_end_dryrun_20260507.py | 49 PASS |
| test_local_agent_websocket_user_present_dispatch_runtime_20260507.py | 44 PASS |
| test_local_agent_websocket_user_present_runtime_20260507.py | 40 PASS |
| test_local_agent_websocket_user_present_integration_20260507.py | 52 PASS |
| **합계** | **217 PASS** |

## 금지 항목 준수

- 실제 은행/카드/홈택스/Google 접속 없음
- 실제 브라우저/Playwright 실행 없음
- DB 직접 write 없음
- docker compose down 없음
- reset --hard / rm -rf 없음
- safe_to_execute=true 허용 없음
- 민감정보 로그 출력 없음
