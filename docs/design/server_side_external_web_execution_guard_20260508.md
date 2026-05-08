# Server-Side External Web Execution Guard 설계

작성일: 2026-05-08

## 왜 코드 guard가 필요한가

운영 규칙(memory, CLAUDE.md)만으로는 SSH 접속 후 임시로 Playwright/curl 실행 등 우회가 가능하다. 코드 레벨에서 강제하지 않으면:

- Claude Code가 서버 셸에서 외부 사이트 자동화 실행 가능
- 개발자가 디버깅 중 서버에서 외부 URL fetch 실행 가능
- task API가 외부 URL을 받았을 때 미리 title/screenshot을 가져오는 등 부수 호출 발생 가능

이 작업은 **운영 규칙을 코드 강제(enforce-by-code)로 전환**한다.

## 서버 허용 작업

| 작업 | 허용 |
|------|------|
| task 생성 / 상태 관리 / safe result 수신 | ✓ |
| localhost / 127.0.0.1 / docker service 호출 | ✓ |
| 내부 docker network API 호출 | ✓ |
| delegated permission API | ✓ |
| target_url을 task payload에 저장 (실행은 안 함) | ✓ |
| task 상태 조회 | ✓ |

## 서버 금지 작업

| 작업 | 금지 |
|------|------|
| 외부 URL curl/requests/httpx 호출 | ✗ |
| Playwright import / sync_playwright / async_playwright | ✗ |
| Chromium / Firefox / WebKit launch | ✗ |
| Selenium webdriver | ✗ |
| Pyppeteer | ✗ |
| 네이버/G2B/은행/정부/카드/보험 사이트 접속 | ✗ |
| selector discovery on server | ✗ |
| screenshot / form fill / login on server | ✗ |
| `server_browser_used = True` 반환 | ✗ |

## 모듈 구조

```
ai_orchestrator/server/
  execution_location_guard.py       ← 분류 + assert + handoff 빌더
  server_egress_policy.py           ← 내부/외부 URL 판정 + URL sanitize
  external_url_blocker.py           ← block_external_fetch + browser_action guard
  universal_agent_models.py         ← UniversalAgentTask + validate_task_model
  universal_agent_task_api.py       ← create_task (외부 URL → handoff)
ai_orchestrator/browser_tool/
  unified_execution_router.py       ← runtime_context guard 추가
```

## execution_location enum

```
SERVER_INTERNAL_ONLY     = 서버 내부 (localhost, docker service)
LOCAL_AGENT_REQUIRED     = 로컬 PC 에이전트 필수 (외부 웹)
USER_DIRECT_REQUIRED     = 사용자 직접 (결제/송금/투찰/서명)
BLOCKED                  = 차단
```

## blocked_reason enum

```
BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION
BLOCKED_SERVER_PLAYWRIGHT_EXECUTION
BLOCKED_SERVER_BROWSER_LAUNCH
BLOCKED_EXTERNAL_URL_FROM_SERVER
BLOCKED_UNSAFE_EXECUTION_LOCATION
```

## Local Agent Handoff 구조

```python
{
  "task_id": "...",
  "execution_location": "LOCAL_AGENT_REQUIRED",
  "target_url": "...",
  "target_host": "...",
  "action": "...",
  "status": "WAITING_LOCAL_AGENT",
  "message_ko": "외부 웹사이트 작업은 사용자 PC 로컬 에이전트에서 실행해야 합니다.",
  "local_agent_required": True,
  # safe fields 모두 False
}
```

## 정책 강제 메커니즘

1. **`classify_execution_location_for_server(task)`** — 입력 task를 정적 분류
2. **`validate_task_model(task_dict)`** — 모델 검증, server_browser_used=True 거부
3. **`assert_server_may_not_execute_external_web(task)`** — 외부 URL이면 ValueError raise
4. **`block_external_fetch_from_server(url)`** — 외부 URL 시도 시 safe blocked 반환
5. **router runtime_context guard** — `task["runtime_context"]=="server"` + 외부 URL이면 즉시 BLOCKED
6. **테스트 정적 검사** — `tests/test_no_server_playwright_execution_*` 가 import/launch 호출 검사

## 내부 host 판정 기준

- `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`
- 점이 없는 docker service name (예: `nginx`, `haehan-ai-orchestrator-api`)
- `.internal`, `.local`, `.svc.cluster.local` suffix
- private IP: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`

그 외 모든 host는 외부로 판정 → LOCAL_AGENT_REQUIRED.

## 테스트

| 파일 | 수 |
|------|----|
| test_server_side_external_web_execution_guard | 23 |
| test_server_egress_policy | 15 |
| test_universal_agent_server_location_guard | 14 |
| test_no_server_playwright_execution | 6 |

**합계 58 PASS** (정책 grep 정적 검사 6 포함)

## 남은 과제

- runtime import hook 으로 Playwright 모듈을 서버 컨테이너에서 import 자체 차단 검토
- 외부 URL을 fetching하려는 의도가 있는 라이브러리(`httpx`, `aiohttp`) 정책 정의
- nginx 단의 egress firewall로 docker network 외부로 나가는 트래픽 제한 검토
