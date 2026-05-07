# Browser Engine Routing Preflight Chain

날짜: 2026-05-07

## 1. 목적

engine_capability 분류와 routing policy 결정을 기존 preflight chain 앞단에 연결한다.
분류 결과에 따라 필요한 체인 단계만 수행하고, 불필요한 단계는 건너뛴다.

- 무조건 Playwright 먼저 시도하는 구조 금지
- 제한 사이트는 서버 브라우저 preflight 체인으로 진입하지 않음
- API 필요 사이트는 API_CONNECTOR에서 체인 종료
- Local system browser 필요 사이트는 LOCAL_SYSTEM_BROWSER_USER_PRESENT에서 체인 종료
- safe_to_execute는 모든 케이스에서 항상 False

## 2. Chain 순서

```
1. browser_engine_capability_classifier
   → engine_capability, recommended_route 결정

2. browser_engine_routing_policy
   → routing_decision, selected_engine 결정
   → API_CONNECTOR_REQUIRED → [체인 종료: API_CONNECTOR]
   → LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED → [체인 종료: LOCAL_SYSTEM_BROWSER_USER_PRESENT]
   → AUTOMATION_BLOCKED → [체인 종료: BLOCKED]
   → NEEDS_MANUAL_REVIEW → [체인 종료: MANUAL_REVIEW_REQUIRED]

3. site_compliance_policy
   → compliance_decision 확인
   → BLOCK → [체인 종료: BLOCKED]
   → REQUIRE_API_CONNECTOR → [체인 종료: API_CONNECTOR]

4. server_browser_boundary_policy
   → server_browser_decision 확인
   → REQUIRE_USER_PRESENT → [체인 종료: LOCAL_SYSTEM_BROWSER_USER_PRESENT]
   → REQUIRE_API_CONNECTOR → [체인 종료: API_CONNECTOR]
   → BLOCK → [체인 종료: BLOCKED]

5. action_registry_preflight
   → action 정책 확인
   → approval_required=true → [체인 종료: APPROVAL_REQUIRED]
   → domain_allowlist_required=true이고 미확인 → [체인 종료: DOMAIN_VERIFICATION_REQUIRED]
   → BLOCK → [체인 종료: BLOCKED]

6. gate_approval_preflight
   → 승인 상태 확인
   → REQUIRE_APPROVAL → [체인 종료: APPROVAL_REQUIRED]
   → BLOCK → [체인 종료: BLOCKED]

7. allowlist_preflight
   → 도메인/경로 allowlist 확인
   → BLOCK → [체인 종료: BLOCKED]

8. → next_step: SERVER_PLAYWRIGHT_READONLY_PREFLIGHT (dispatcher 연결 대상)
```

## 3. Chain Decision Enum

| 값 | 설명 |
|---|---|
| PROCEED | 다음 단계로 진행 |
| ROUTE_API_CONNECTOR | API connector로 종료 |
| ROUTE_LOCAL_SYSTEM_BROWSER | 로컬 system browser로 종료 |
| BLOCK | 자동화 차단 |
| APPROVAL_REQUIRED | 승인 대기 |
| DOMAIN_VERIFICATION_REQUIRED | 도메인 실사 필요 |
| MANUAL_REVIEW_REQUIRED | 수동 실사 필요 |

## 4. next_step 허용값

| 값 | 설명 |
|---|---|
| SERVER_PLAYWRIGHT_READONLY_PREFLIGHT | 서버 Playwright read-only 대기 (향후 dispatcher 연결) |
| LOCAL_AGENT_PLAYWRIGHT_READONLY | 로컬 Agent Playwright read-only fallback |
| LOCAL_SYSTEM_BROWSER_USER_PRESENT | 사용자 직접 브라우저 접근 필요 |
| API_CONNECTOR | 공식 API/OAuth 경로 |
| APPROVAL_REQUIRED | 승인 절차 시작 필요 |
| DOMAIN_VERIFICATION_REQUIRED | 도메인 실사 및 승인 필요 |
| BLOCKED | 차단 (진행 불가) |
| MANUAL_REVIEW_REQUIRED | 수동 실사 필요 |

## 5. Route별 next_step

| engine_capability | next_step |
|---|---|
| SERVER_PLAYWRIGHT_READONLY_ALLOWED + 체인 통과 | SERVER_PLAYWRIGHT_READONLY_PREFLIGHT |
| SERVER_PLAYWRIGHT_READONLY_ALLOWED + runtime failure | LOCAL_AGENT_PLAYWRIGHT_READONLY |
| LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED | LOCAL_AGENT_PLAYWRIGHT_READONLY |
| LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED | LOCAL_SYSTEM_BROWSER_USER_PRESENT |
| API_CONNECTOR_REQUIRED | API_CONNECTOR |
| AUTOMATION_BLOCKED | BLOCKED |
| NEEDS_MANUAL_REVIEW | MANUAL_REVIEW_REQUIRED |

## 6. Server Playwright 금지 경로

다음 사이트/케이스는 서버 브라우저 preflight 체인(3~7단계)으로 진입하지 않음:
- 은행, 카드사, 홈택스, 정부24, 4대보험, 인증서 포털
- Google accounts, Gmail, Drive, Calendar, Docs, Sheets
- OTP/비밀번호/인증서 필요 사이트
- CAPTCHA 필요 사이트

## 7. Fallback 정책

### 허용 fallback
- SERVER_PLAYWRIGHT_READONLY_ALLOWED 사이트에서 failure_reason이
  `runtime_error` / `network_timeout` / `browser_not_available`인 경우
  → next_step: LOCAL_AGENT_PLAYWRIGHT_READONLY

### 금지 fallback
- failure_reason이 `policy_blocked` / `domain_blocked` / `auth_required` /
  `otp_required` / `certificate_required` / `captcha_required`이면 fallback 금지
- 정책상 제한 사이트는 처음부터 LOCAL_SYSTEM_BROWSER_USER_PRESENT / API_CONNECTOR로 라우팅

## 8. 보안 원칙

- safe_to_execute: 모든 케이스에서 항상 False
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
- 인증서 비밀번호/OTP 입력 코드 없음
- dispatcher/task_executor 실제 연결 없음
- should_write_audit: BLOCK/APPROVAL_REQUIRED 케이스에서 true
