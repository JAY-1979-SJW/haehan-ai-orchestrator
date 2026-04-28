# Stage 12A local-agent control audit

## 1. 목적
local-agent 실제 제어 기능 안정화 전 현재 구현/정책/위험 제어 구조 감사

## 2. 확인한 파일

| 영역 | 주요 파일 | 역할 |
|---|---|---|
| local_agent | `local_agent/agent.py`, `actions.py`, `browser_actions.py`, `browser_login_probe.py`, `browser_reader.py`, `audit.py`, `websocket_client.py` | 로컬 에이전트 실행 측 코드 |
| ai_orchestrator API | `local_agent_router.py`, `local_agent_registry.py`, `approval.py`, `audit_logger.py`, `policy.py`, `policies/default_policy.yaml`, `task_state.py` | 서버 측 큐·승인·감사 |
| admin-web | `src/app/local-agents/LocalAgentsClient.tsx`, `src/lib/api.ts`, `src/types/local-agent.ts` | 운영 UI 및 API 클라이언트 |
| tests | `test_capture_screenshot_*.py`, `test_approval*.py`, `test_browser_*.py`, `test_policy_gate.py`, `test_local_agent.py`, `test_local_agent_ws.py`, `test_executor_policy_flow.py`, `test_admin_ui_capture_screenshot.py` | 기능/정책/승인/감사 테스트 |

## 3. 현재 지원 기능

| 기능 | 구현 여부 | 위치 | 판정 |
|---|---:|---|---|
| agent 목록 조회 | ✓ | `GET /api/v1/local-agents` → `local_agent_registry.list_agents()` | OK |
| heartbeat/status | ✓ | WS heartbeat + `set_agent_last_seen()`, `set_agent_connected/disconnected()` | OK |
| task 생성/조회 | ✓ | `POST /local-agents/{agent_id}/tasks`, `GET /tasks/{task_id}` | OK |
| capture 사전 점검 (dry_run) | ✓ | `CaptureScreenshotRequest.dry_run=True` 기본값, `POST /capture-screenshot` | OK |
| 실제 1회 capture 요청 | ✓ (waiting_approval) | `dry_run=False` 명시 → waiting_approval + 승인 토큰 발행 | OK |
| cancel/stop | ✓ | `POST /tasks/{task_id}/cancel` → `cancel_task()`, `CancelNotAllowedError` 처리 | OK |
| browser open | ✓ | `open_url` action, risk=low, PC agent 실행 | OK |
| URL 접근 | ✓ | `open_url` action via WS dispatch | OK |
| 화면 관찰 | △ | `browser_reader.py`, `browser_observer.py` (로컬 에이전트 측 코드만 존재, API 직접 노출 없음) | WARN |
| 결과 저장/회수 | ✓ | `apply_result()`, `task.result_summary`, `to_safe()` | OK |
| 감사 로그 | ✓ | `audit_logger.log_event()` → `audit_logs.jsonl`, 전 이벤트 커버 | OK |

## 4. 위험 제어 구조

| 항목 | 존재 여부 | 위치 | 판정 |
|---|---:|---|---|
| dry-run / preview-only | ✓ | `CaptureScreenshotRequest.dry_run=True` 기본값, `_task_is_dry_run()`, `CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED` 이벤트 | OK |
| 위험도 분류 | ✓ | `ACTION_RISK` dict: low/medium/high. `default_policy.yaml`에 critical 포함 4단계 | OK |
| 승인 필요 여부 | ✓ | high risk → `issue_token_for_dev_reg()` → `waiting_approval`. WS는 승인 후에만 push | OK |
| 금지 작업 차단 | ✓ | `ACTION_RISK` 미등록 액션 = UNKNOWN_ACTION 400. `policy.py`에 blocked_paths/blocked_commands. critical 기본 차단 | OK |
| secret/cookie/session 차단 | ✓ | `_SENSITIVE_KEYS` frozenset → `_strip_sensitive()` 저장 전 제거. device_token 참조 즉시 초기화 | OK |
| 감사 로그 | ✓ | 등록/큐/대기/승인/거절/취소/완료/실패/WS연결/WS인증실패 전 이벤트 기록 | OK |
| rate/time/count limit | △ | approval token TTL 30분, WS keepalive 30초 timeout. HTTP rate limit 미확인 (API 레이어 별도 확인 필요) | WARN |
| 권한 분리 | ✓ | `require_role()`: admin/owner(쓰기), viewer(읽기). UI에 RoleBadge + 비활성화 처리 | OK |

## 5. admin-web 연동 상태

| 항목 | 현재 상태 | 판정 |
|---|---|---|
| local-agents API 호출 | `getLocalAgents()`, `getAgentTasks()`, `cancelTask()`, `requestCaptureScreenshot()`, `getCurrentUser()` — 모두 `/orchestrator/api/v1` 기준 | OK |
| capture 버튼 조건 | `isCaptureEnabled(status)`: idle/busy 상태만 활성화. role 확인 후 비활성화 처리. dry_run/real 2단계 모달 | OK |
| cancel 버튼 조건 | `cancelButtonProps(status)`: queued/waiting_approval(취소 가능), delivered/running(취소 요청), 종료 상태(비활성화). viewer는 비활성화 | OK |
| 위험 작업 승인 UI | △ | capture 요청 → waiting_approval 상태 확인 가능. 단 approve/reject 버튼 UI 없음 — API는 구현됨 (`/approve`, `/reject` 엔드포인트 존재) | GAP |
| 오해 가능 문구 | 없음 | 권한 확인 실패 시 "위험 작업 비활성화" 명시. viewer 힌트 안내 표시 | OK |

## 6. 테스트/검증 상태

| 테스트 영역 | 파일 | 판정 |
|---|---|---|
| local-agent API | `test_local_agent.py`, `test_local_agent_ws.py` | OK |
| browser action | `test_browser_actions.py`, `test_browser_login_probe.py`, `test_browser_reader.py` | OK |
| screenshot/capture | `test_capture_screenshot_dry_run.py`, `test_capture_screenshot_approval.py`, `test_capture_screenshot_request_api.py`, `test_capture_screenshot_telegram.py`, `test_admin_ui_capture_screenshot.py` | OK |
| policy/safety | `test_policy_gate.py`, `test_executor_policy_flow.py`, `test_sites_secrets_policy.py`, `test_approval*.py` | OK |
| smoke | `test_sites_import_smoke.py`, `test_web_recording_localhost_smoke.py` | WARN — local_agent 전용 smoke 미확인 |

## 7. GAP 분류

### OK
- ACTION_RISK 기반 low/medium/high 위험도 분류 구현됨
- dry_run 기본값 보호, 실제 capture는 명시적 false + 승인 토큰 필수
- 전 이벤트 감사 로그 (audit_logs.jsonl)
- WS에서 high risk 작업은 승인 전 push 불가 (waiting_approval 상태는 list_pending 제외)
- _SENSITIVE_KEYS 기반 민감값 저장 전 제거
- admin-web에서 viewer 역할 자동 비활성화, 권한 확인 실패 시 위험 작업 잠금

### GAP
- **approve/reject UI 없음**: API 엔드포인트(`/approve`, `/reject`)는 구현됨. admin-web에서 waiting_approval 상태 작업에 대한 승인/거절 버튼 없음. 현재는 API 직접 호출 또는 별도 도구 필요.
- **화면 관찰(browser_observer) API 미노출**: 로컬 에이전트 측 코드(`browser_reader.py`, `browser_observer.py`)는 존재하지만 server API로 직접 노출되지 않음.
- **HTTP rate limit 미확인**: approval token TTL은 있으나 HTTP API 레이어의 rate limiting 설정 확인 필요.
- **local_agent 전용 smoke 테스트 미확인**: import smoke는 있으나 local_agent 에이전트 실행 smoke가 별도 없음.

### RISK
- 없음 (현재 구조에서 치명적 위험 경로 미확인)

### UNKNOWN
- `local_agent/agent.py` 실행 측 코드의 실제 capture 결과 저장 경로/파일명 처리 방식 (서버 API와의 정합성 미확인)
- `ai_orchestrator/approval.py` 의 토큰 만료 후 재사용 방지 구체 로직

## 8. 다음 단계 제안

GAP 항목 기준으로 WARN 판정.

**WARN**: 핵심 안전 구조는 OK. capture dry_run 보호, 승인 게이트, 감사 로그 모두 구현됨. 단 approve/reject UI가 admin-web에 없어 운영자가 waiting_approval 작업을 UI에서 처리할 수 없음.

권장 다음 단계:

- **Stage 12B**: admin-web에 approve/reject UI 추가 — waiting_approval 상태 작업에 승인·거절 버튼 및 token_id 입력 또는 자동 처리 플로우
- **Stage 12C**: capture/cancel E2E smoke 정리 — dry_run=True 경로 smoke 포함
- **Stage 12D**: browser open/observe 안전 실행 경로 정리 — API 노출 범위 결정

## 9. 금지 작업 준수 확인

- 코드 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실제 실행: 없음
- 브라우저 실행: 없음
- POST 실행: 없음
- secret 출력: 없음
- git push: 없음
