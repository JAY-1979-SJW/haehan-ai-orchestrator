# 로컬 Agent / 서버 브라우저 경계 정책
작성일: 2026-05-07

---

## 1. 목적

- 서버 브라우저(browser_worker/real_playwright_backend)와 로컬 Agent 브라우저(local_agent/browser_reader)의 실행 경계를 명확히 한다.
- 제한 사이트는 서버 브라우저에서 절대 접속하지 않는다.
- 사용자 PC 로컬 Agent 또는 공식 API/OAuth만 허용한다.
- 서버는 작업 지시·승인·감사·상태 수집만 담당한다.
- 사용자의 브라우저/인증/보안프로그램/공동인증서는 사용자 PC에서만 처리한다.

---

## 2. 금지 대상 사이트 카테고리 (서버 브라우저 접속 전면 금지)

| 카테고리 | 예시 | 이유 |
|---|---|---|
| bank | 국민·신한·우리·하나·기업·농협·카카오뱅크 등 | 공동인증서·OTP·보안프로그램 필요 |
| card | 국민카드·신한카드·현대카드 등 | 공동인증서·OTP·보안프로그램 필요 |
| tax | 홈택스·손택스 | 공동인증서·금융인증서·OTP 필요 |
| government | 정부24·민원24 | 공동인증서·보안프로그램 필요 |
| insurance | 4대보험·건강보험·국민연금 | 공동인증서·보안프로그램 필요 |
| certificate | 공동인증서·금융인증서 발급 포털 | 인증서 비밀번호 입력 필요 |
| google_accounts | accounts.google.com | OAuth 전용. 서버 브라우저 로그인 금지 |
| otp_required | OTP 입력 요구 사이트 | 사용자 직접 입력 필요 |
| captcha_required | CAPTCHA/보안문자 요구 사이트 | 자동화 차단 |
| security_plugin | 키보드보안·보안플러그인 요구 사이트 | 원격접속 차단 |
| remote_block | 원격접속 차단 표시 사이트 | 정책 위반 |

---

## 3. 허용 실행 위치

| 사이트 유형 | 서버 브라우저 | 로컬 Agent | API/OAuth | 비고 |
|---|---|---|---|---|
| G2B 공개 공고 read-only | ✅ (readonly) | ✅ | — | 인증 불필요 공개 페이지만 |
| Google 서비스(Gmail/Drive/Calendar/Docs/Sheets) | ❌ | ❌ | ✅ | OAuth + 공식 API만 |
| Google accounts 로그인 | ❌ | ❌ | ✅ OAuth | 서버 브라우저 로그인 금지 |
| 은행/카드/세무/보험/인증서 | ❌ | ✅ (readonly) | — | user-present 필수 |
| 보안프로그램/OTP/CAPTCHA 사이트 | ❌ | ✅ (readonly) | — | user-present 필수 |
| 내부 시스템 | 정책 검토 | VPN/MFA 검토 | — | 별도 정책 적용 |

---

## 4. 서버 역할 (허용)

- 작업 생성 및 관리
- 로컬 Agent로 작업 명령 전달 (WebSocket)
- 상태 수집 (WAITING_FOR_USER, USER_CONFIRMED, CANCELLED 등)
- Approval 처리
- Audit 기록
- 결과 저장
- 제한 사이트 접속 여부 분류·판정

---

## 5. 서버 역할 (금지)

- 제한 사이트(은행/카드/세무/정부/보험/인증서) 브라우저 접속
- 제한 사이트 로그인 페이지 열기
- 인증서/OTP/보안프로그램 필요 사이트 직접 테스트
- 원격접속 차단 사이트 우회 시도
- 비밀번호/OTP/인증서 비밀번호 입력
- 쿠키/session/token/localStorage 추출
- click/type/fill/submit 자동화

---

## 6. 로컬 Agent 역할

- 사용자 PC에서 브라우저 열기 (core/agent_runtime/browser/browser_reader.py)
- 사용자가 직접 인증 수행 (공동인증서, OTP, 비밀번호)
- read-only 상태 확인 (core/agent_runtime/browser/browser_readonly_runtime.py)
- 결과 요약 및 서버 전달
- 민감정보 차단 (sanitize)
- 127.0.0.1 로컬 UI (core/agent_runtime/user_present/user_present_ui_server.py)

---

## 7. server_browser_decision 값

| 결정값 | 의미 |
|---|---|
| SERVER_BROWSER_ALLOWED_READONLY | 서버 브라우저 read-only 접근 허용 (G2B 공개 등) |
| REQUIRE_LOCAL_AGENT | 로컬 Agent 필요 (제한 사이트 read-only 후보) |
| REQUIRE_API_CONNECTOR | 공식 API/OAuth 필요 (Google 서비스 등) |
| REQUIRE_USER_PRESENT | 사용자 직접 인증 필요 (공동인증서·OTP 등) |
| BLOCK | 완전 차단 (CAPTCHA, 정책 금지 등) |

---

## 8. safe_to_execute 정책

- 모든 케이스에서 `safe_to_execute = False`
- 어떤 결정값이더라도 예외 없음

---

## 9. 관련 파일

| 역할 | 경로 |
|---|---|
| 서버 브라우저 경계 정책 | ai_orchestrator/browser_tool/policy/server_browser_boundary_policy.py |
| 사이트 준수 정책 | ai_orchestrator/browser_tool/policy/site_compliance_policy.py |
| 사이트 접근 감사 | ai_orchestrator/browser_tool/policy/site_access_compatibility_auditor.py |
| 로컬 Agent read-only 런타임 | core/agent_runtime/browser/browser_readonly_runtime.py |
| user-present 플로우 | ai_orchestrator/agent_hub/user_present_flow.py |
| user-present 상태 store | core/agent_runtime/user_present/user_present_state_store.py |
| user-present UI 서버 | core/agent_runtime/user_present/user_present_ui_server.py |
| 테스트 | tests/test_local_agent_server_boundary_policy_20260507.py |
| fixture | tests/fixtures/local_agent_server_boundary_policy_20260507.json |
| 이 문서 | docs/design/local_agent_server_boundary_policy_20260507.md |
