# Browser Engine Routing Policy

날짜: 2026-05-07

## 1. 목적

BROWSER_ENGINE_CAPABILITY_CLASSIFICATION_1의 분류 결과를 기반으로
작업별 실제 실행 경로를 결정한다.

- 무조건 Playwright 먼저 시도하는 구조 금지
- 정책상 허용된 사이트만 Server Playwright 후보
- 제한 사이트는 처음부터 Local System Browser / API Connector로 직접 라우팅
- 이 단계는 라우팅 결정 모듈이며 실제 브라우저 실행 연결 단계가 아님

## 2. Routing Decision Enum

| 값 | 설명 |
|---|---|
| ROUTE_SERVER_PLAYWRIGHT_READONLY | 서버 Playwright read-only |
| ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY | 로컬 Agent Playwright read-only |
| ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT | 사용자 기본 브라우저 + user-present |
| ROUTE_API_CONNECTOR | 공식 API/OAuth |
| BLOCK | 자동화 차단 |
| MANUAL_REVIEW | 수동 실사 필요 |

## 3. Selected Engine Enum

| 값 | 설명 |
|---|---|
| server_playwright | 서버 Playwright |
| local_agent_playwright | 로컬 Agent Playwright |
| local_system_browser | 사용자 기본 브라우저 |
| api_connector | 공식 API/OAuth |
| none | 실행 불가 |

## 4. Routing 입력 기준

| 필드 | 설명 |
|---|---|
| engine_capability | classifier 분류 결과 |
| recommended_route | classifier 추천 경로 |
| site_category | 사이트 카테고리 |
| target_domain | 도메인 |
| target_url | URL |
| operation_type | read / navigate / click / type / submit 등 |
| action_name | 액션명 |
| requires_certificate | 공동인증서 필요 여부 |
| requires_financial_certificate | 금융인증서 필요 여부 |
| requires_otp | OTP 필요 여부 |
| requires_password | 비밀번호 필요 여부 |
| requires_captcha | CAPTCHA 필요 여부 |
| requires_security_plugin | 보안프로그램 필요 여부 |
| official_api_available | 공식 API 제공 여부 |
| oauth_available | OAuth 제공 여부 |
| user_present_required | 사용자 직접 참여 필요 여부 |
| local_agent_required | 로컬 Agent 필요 여부 |
| production_mode | 프로덕션 모드 (항상 BLOCK) |
| failure_reason | runtime failure 원인 (fallback 판정용) |

## 5. Routing 정책

### SERVER_PLAYWRIGHT_READONLY_ALLOWED
- routing_decision: ROUTE_SERVER_PLAYWRIGHT_READONLY
- selected_engine: server_playwright
- server_playwright_first_allowed: True
- local_agent_fallback_allowed: True (runtime failure 시에만)

### LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED
- routing_decision: ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY
- selected_engine: local_agent_playwright
- server_playwright_first_allowed: False

### LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
- routing_decision: ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT
- selected_engine: local_system_browser
- server_playwright_first_allowed: False
- 해당: 은행, 카드, 홈택스, 정부24, 4대보험, 인증서 포털, OTP/비밀번호 필요

### API_CONNECTOR_REQUIRED
- routing_decision: ROUTE_API_CONNECTOR
- selected_engine: api_connector
- server_playwright_first_allowed: False
- 해당: Gmail, Drive, Calendar, Docs, Sheets, G2B OpenAPI

### AUTOMATION_BLOCKED
- routing_decision: BLOCK
- selected_engine: none
- 해당: CAPTCHA 필요, 이용약관상 금지, Google accounts 로그인

### NEEDS_MANUAL_REVIEW
- routing_decision: MANUAL_REVIEW
- selected_engine: none
- 해당: 정책/URL/인증방식 미분류 사이트

## 6. Fallback 정책

### 허용 fallback
- server_playwright_first_allowed=True인 사이트에서
- failure_reason이 runtime_error / network_timeout / browser_not_available인 경우
- → LOCAL_AGENT_PLAYWRIGHT_READONLY fallback 가능

### 금지 fallback
- failure_reason이 아래 중 하나면 fallback 금지:
  - policy_blocked
  - domain_blocked
  - auth_required
  - otp_required
  - certificate_required
  - captcha_required
- 정책상 제한 사이트(은행/카드/홈택스/Google accounts 등)는
  처음부터 LOCAL_SYSTEM_BROWSER_USER_PRESENT / API_CONNECTOR로 라우팅
  (server playwright fallback 시도 자체 금지)

## 7. 금지 라우팅

| 조건 | 금지 경로 |
|---|---|
| 은행/카드/홈택스/정부24/4대보험/인증서 | → SERVER_PLAYWRIGHT_READONLY 금지 |
| Google accounts | → 모든 Playwright 금지 |
| Gmail/Drive/Calendar/Docs/Sheets | → Playwright 금지, API만 허용 |
| CAPTCHA 필요 | → BLOCK |
| production_mode=true | → BLOCK |
| type/submit operation | → 자동 실행 route 금지 |

## 8. 보안 원칙

- safe_to_execute: 모든 케이스에서 항상 False
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
- 인증서 비밀번호/OTP 입력 코드 없음
- 비밀번호 저장/전송 금지
- dispatcher/task_executor 실제 연결 없음
