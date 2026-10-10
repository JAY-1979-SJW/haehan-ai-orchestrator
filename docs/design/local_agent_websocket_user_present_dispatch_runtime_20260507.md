# LOCAL_AGENT_WEBSOCKET_USER_PRESENT_DISPATCH_RUNTIME 설계

date: 2026-05-07

## 목표

routing dry-run 결과가 `DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED`일 때,
서버가 연결된 로컬 Agent로 USER_PRESENT_TASK를 능동적으로 push하고,
로컬 Agent가 WAITING_FOR_USER 상태를 생성한 뒤 ACK/STATUS를 서버로 반환한다.

## 신규 모듈

`ai_orchestrator/agent_hub/user_present_dispatcher.py`

### 핵심 함수

| 함수 | 역할 |
|------|------|
| `build_user_present_dispatch_context(payload)` | dryrun_result + agent 선택 정보 → dispatch context |
| `should_dispatch_user_present_task(dryrun_result)` | DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED 여부 |
| `build_user_present_task_from_dryrun(dryrun_result)` | dryrun_result → USER_PRESENT_TASK message |
| `validate_user_present_dispatch_request(payload)` | 필수 필드 + 정책 검증 |
| `build_user_present_dispatch_response(payload)` | dispatch 결과 응답 구성 |

## dispatch 정책

- `dispatch_decision == DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED`일 때만 dispatch 후보
- API_CONNECTOR / BLOCKED / MANUAL_REVIEW / SERVER_PLAYWRIGHT route → dispatch 금지
- `selected_agent_id` 없으면 → `AGENT_SELECTION_REQUIRED` 오류
- safe_to_execute=False 항상
- raw target_url 금지 → redacted/hash만

## 수정 모듈

- `ai_orchestrator/agent_hub/router/root.py`: dryrun 응답 후 user-present push 경로 추가
- `core/agent_runtime/connection/websocket_client.py`: `user_present_task_push` message_type 확인

## 보안 원칙

- click/type/fill/submit 금지
- cookie/session/token/OTP/인증서 비밀번호 저장·전송 금지
- 실제 브라우저/Playwright 실행 없음
- safe_to_execute=False 항상
