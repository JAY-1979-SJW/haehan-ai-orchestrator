# Server-Side External Web Execution Guard — 작업 보고

작성일: 2026-05-08
작업 ID: SERVER_SIDE_EXTERNAL_WEB_EXECUTION_GUARD_1

## 신규 모듈 (5개)

| 파일 | 역할 |
|------|------|
| `ai_orchestrator/server/execution_location_guard.py` | enum + classify + assert + handoff 빌더 |
| `ai_orchestrator/server/server_egress_policy.py` | is_internal/external_url + URL sanitize + host category |
| `ai_orchestrator/server/external_url_blocker.py` | block_external_fetch + browser_action guard + playwright invocation guard |
| `ai_orchestrator/server/universal_agent_models.py` | UniversalAgentTask + validate_task_model |
| `ai_orchestrator/server/universal_agent_task_api.py` | create_task (외부 URL → handoff) + list_pending |

## 기존 파일 수정 (1개)

| 파일 | 수정 |
|------|------|
| `ai_orchestrator/browser_tool/unified_execution_router.py` | `runtime_context == "server"` + 외부 URL → 즉시 BLOCKED 가드 추가 |

## 테스트 (4파일, 58 케이스)

| 파일 | 수 | 결과 |
|------|----|------|
| test_server_side_external_web_execution_guard_20260508.py | 23 | PASS |
| test_server_egress_policy_20260508.py | 15 | PASS |
| test_universal_agent_server_location_guard_20260508.py | 14 | PASS |
| test_no_server_playwright_execution_20260508.py | 6 | PASS (정적 검사) |

**전체 회귀: 4679 passed, 7 skipped, 0 failed**

## 정책 grep 결과

- ✅ `ai_orchestrator/server/` 내 sync_playwright/async_playwright import 없음
- ✅ chromium.launch / firefox.launch / webkit.launch 호출 없음
- ✅ selenium webdriver / pyppeteer 사용 없음
- ✅ `server_browser_used = True` 실행 코드 없음
- ✅ 외부 URL fetch 직접 호출 없음 (정책 모듈 제외)
- ✅ password/OTP/cookie/session export 없음

## 핵심 강제 메커니즘

1. **분류:** target_url의 host가 외부면 자동 `LOCAL_AGENT_REQUIRED`
2. **검증:** `validate_task_model`이 `server_browser_used=True` 즉시 거부
3. **차단:** `assert_server_may_not_execute_external_web`이 외부 URL 입력 시 ValueError raise
4. **API:** `create_task`가 외부 URL 받으면 자동 `WAITING_LOCAL_AGENT` + handoff payload 생성
5. **라우터:** `route_browser_task(task={"runtime_context":"server"...})` + 외부 URL → 즉시 `BLOCKED`
6. **정적 검사:** 테스트가 server 디렉터리의 Python 파일을 정규식 스캔하여 위반 시 FAIL

## Local Agent Handoff 출력 예

```json
{
  "task_id": "uuid",
  "execution_location": "LOCAL_AGENT_REQUIRED",
  "target_host": "naver.com",
  "status": "WAITING_LOCAL_AGENT",
  "message_ko": "외부 웹사이트 작업은 사용자 PC 로컬 에이전트에서 실행해야 합니다.",
  "local_agent_required": true,
  "server_browser_used": false,
  "cookie_exported": false,
  ...
}
```

## 안전성 검증

| 위반 시나리오 | 결과 |
|---------------|------|
| `https://naver.com` + open_url | LOCAL_AGENT_REQUIRED handoff |
| `https://g2b.go.kr` + read_page | LOCAL_AGENT_REQUIRED handoff |
| `https://kbstar.com` + download | guard_server_browser_action → BLOCKED |
| `https://example.com` + screenshot | BLOCKED |
| target_url 외부 + execution_location=SERVER_INTERNAL_ONLY | validate 거부 |
| server_browser_used=True 결과 보고 | update_task_result 거부 |
| URL query에 token | sanitize_blocked_url_for_log가 query 제거 |
