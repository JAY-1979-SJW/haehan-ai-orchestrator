# Browser Engine Capability Classification

날짜: 2026-05-07

## 목적

사이트별로 어떤 실행 엔진을 사용할 수 있는지 사전 분류한다.
무조건 Playwright 먼저 시도하는 구조를 금지하고,
정책 기반으로 엔진을 라우팅한다.

## Engine Capability Enum

### 1. SERVER_PLAYWRIGHT_READONLY_ALLOWED

- 서버 Playwright read-only 가능
- 해당 사이트: about:blank, data: URL, example.com, G2B 공개 공고
- click/type/submit 금지
- safe_to_execute: 항상 False

### 2. LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED

- 사용자 PC 로컬 Agent Playwright read-only 가능
- 인증 필요 감지 시 USER_PRESENT_REQUIRED로 전환
- 해당 사이트: 공개 read-only 페이지, 내부 테스트 페이지
- SERVER_PLAYWRIGHT_READONLY_ALLOWED 사이트에서 runtime failure 시 fallback 가능

### 3. LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED

- 사용자 PC의 실제 Chrome/Edge 기본 브라우저 필요
- 사용자가 직접 로그인/인증/OTP/인증서 처리
- 해당 사이트:
  - 은행 (kbstar, shinhan, wooribank, hanabank, ibk, nonghy, kakaobank, tossbank 등)
  - 카드사 (card.kb, shinhancard, hyundaicard, samsungcard, lottec, bccard 등)
  - 홈택스 (hometax.go.kr)
  - 정부24 (gov.kr, mois.go.kr, minwon, egov, g4c)
  - 4대보험 (4insure, nhis.or.kr, nps.or.kr, kcomwel, ei.go.kr)
  - 공동인증서/금융인증서 포털 (yessign, signgate, crosscert, tradesign, npki)
  - OTP/비밀번호/인증서 필요 사이트

### 4. API_CONNECTOR_REQUIRED

- 공식 API/OAuth 필요
- 브라우저 자동화 금지
- 해당 서비스:
  - Gmail (mail.google.com)
  - Google Drive (drive.google.com)
  - Google Calendar (calendar.google.com)
  - Google Docs (docs.google.com)
  - Google Sheets (sheets.google.com)
  - G2B OpenAPI

### 5. AUTOMATION_BLOCKED

- 자동화 금지
- 해당 케이스:
  - CAPTCHA 필요 사이트
  - 보안 우회 요구
  - 이용약관상 자동화 금지
  - 제출/결제/이체 자동화

### 6. NEEDS_MANUAL_REVIEW

- 정책/URL/인증방식 불명
- 실제 접속 전 사용자 승인 및 수동 실사 필요

## 분류 기준 필드

| 필드 | 설명 |
|------|------|
| site_category | 사이트 카테고리 (bank, card, tax, g2b 등) |
| target_domain | 도메인 |
| auth_methods | 인증 방식 목록 |
| requires_certificate | 공동인증서 필요 여부 |
| requires_financial_certificate | 금융인증서 필요 여부 |
| requires_otp | OTP 필요 여부 |
| requires_password | 비밀번호 필요 여부 |
| requires_captcha | CAPTCHA 필요 여부 |
| requires_security_plugin | 보안프로그램 필요 여부 |
| blocks_remote_access | 원격접속 차단 여부 |
| official_api_available | 공식 API 제공 여부 |
| user_present_required | 사용자 직접 참여 필요 여부 |
| local_agent_required | 로컬 Agent 필요 여부 |
| production_mode | 프로덕션 모드 (항상 BLOCK) |

## recommended_route 값

| 값 | 설명 |
|----|------|
| SERVER_PLAYWRIGHT_READONLY | 서버 Playwright read-only |
| LOCAL_AGENT_PLAYWRIGHT_READONLY | 로컬 Agent Playwright read-only |
| LOCAL_SYSTEM_BROWSER_USER_PRESENT | 사용자 기본 브라우저 + user-present |
| API_CONNECTOR | 공식 API/OAuth |
| BLOCK | 자동화 차단 |
| MANUAL_REVIEW | 수동 실사 필요 |

## Fallback 정책

### 허용 fallback

- SERVER_PLAYWRIGHT_READONLY_ALLOWED 사이트에서 runtime failure 발생 → LOCAL_AGENT_PLAYWRIGHT_READONLY fallback 가능

### 금지 fallback

- 정책 차단 사이트는 fallback이 아니라 처음부터 LOCAL_SYSTEM_BROWSER_USER_PRESENT 또는 API_CONNECTOR로 라우팅
- 은행/카드/홈택스/Google 로그인은 server Playwright fallback 시도 자체 금지

## 충돌 방지

- server_browser_boundary_policy.py와 decision 값 일치
- site_compliance_policy.py의 capability 체계와 호환
- site_access_compatibility_auditor.py의 final_verdict와 호환
- local_agent_user_present_flow.py의 DECISION 코드와 호환

## 보안 원칙

- safe_to_execute: 모든 케이스에서 항상 False
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
- 인증서 비밀번호/OTP 입력 코드 없음
- 비밀번호 저장/전송 금지
