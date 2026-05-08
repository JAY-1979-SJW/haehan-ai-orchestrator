# Local Agent Public External Readonly Live Smoke

작성일: 2026-05-08  
작업 ID: LOCAL_AGENT_PUBLIC_EXTERNAL_READONLY_LIVE_SMOKE_1

## 기준선

- local HEAD (시작): `0089f6a` / branch master
- origin/master HEAD (시작): `0089f6a`
- server HEAD (시작): `0089f6a`
- tracked dirty: 0건

## 실행 위치

| 항목 | 값 |
|------|------|
| 실행 호스트 | 해한Ai엔지니어링 / Windows 11 |
| 실행 환경 | **로컬 PC** (Windows desktop, docker container 아님) |
| 서버 외부 접속 | **0건** |
| LOCAL_AGENT 경로 | LOCAL_PLAYWRIGHT (sync_playwright + chromium headless) |
| server_browser_used | **False** (모든 결과) |

## 사전 검증

`server.execution_location_guard.classify_execution_location_for_server`로 3개 URL 분류:

| URL | 서버 분류 | server_browser_used |
|-----|-----------|---------------------|
| https://example.com | LOCAL_AGENT_REQUIRED | False |
| https://www.wikipedia.org | LOCAL_AGENT_REQUIRED | False |
| https://www.python.org | LOCAL_AGENT_REQUIRED | False |

→ **서버 측에서는 절대 실행되지 않음** 확인.

## 대상 URL별 결과

| URL | reachable | title | links | tables | downloads | sensitive 실행 | cookie/session 추출 | verdict |
|-----|-----------|-------|-------|--------|-----------|----------------|---------------------|---------|
| https://example.com | ✅ | "Example Domain" | 1 | 0 | 0 | ❌ | ❌ | OK_READONLY |
| https://www.wikipedia.org | ✅ | "Wikipedia" | 373 | 0 | 0 | ❌ | ❌ | OK_READONLY |
| https://www.python.org | ✅ | "Welcome to Python.org" | 222 | 1 | 0 | ❌ | ❌ | OK_READONLY |

**3/3 reachable**, text excerpt 정상 추출, 다운로드 후보 0개, 모든 safe field False.

## 민감 동작 차단 결과

스크립트 내 `_classify_blocked_action_payloads()` 검증 — **실제 실행 없음**, `action_risk_policy.classify_action`으로 정책 분류만:

| Action | Grade | 결과 |
|--------|-------|------|
| login_password_input | USER_DIRECT_REQUIRED | ✅ 차단 |
| otp_input | USER_DIRECT_REQUIRED | ✅ 차단 |
| cert_password_input | USER_DIRECT_REQUIRED | ✅ 차단 |
| cookie_export | BLOCKED | ✅ 차단 |
| session_export | BLOCKED | ✅ 차단 |
| storage_state_export | BLOCKED | ✅ 차단 |
| token_export | BLOCKED | ✅ 차단 |
| confirm_payment | USER_DIRECT_REQUIRED | ✅ 차단 |
| auto_payment | BLOCKED | ✅ 차단 |
| transfer_money | BLOCKED | ✅ 차단 |
| auto_bid_submit | BLOCKED | ✅ 차단 |
| bid_final_submit | USER_DIRECT_REQUIRED | ✅ 차단 |
| auto_sign | BLOCKED | ✅ 차단 |
| e_sign | USER_DIRECT_REQUIRED | ✅ 차단 |

**14/14 모두 BLOCKED 또는 USER_DIRECT_REQUIRED.**

## 정적 검사 (스크립트 안전성)

- ✅ `requests.get/post`, `httpx.*`, `urllib.request.urlopen` 등 외부 fetch 직접 호출 부재
- ✅ Playwright 사용 (LOCAL_PLAYWRIGHT 경로)
- ✅ `context.cookies()`, `storage_state()` 추출 호출 부재
- ✅ `page.screenshot(...)` 저장 부재
- ✅ `page.fill/type/click` 입력 실행 코드 부재 (read-only 모듈만 사용)

## 안전 정책

| 항목 | 결과 |
|------|------|
| HTML 원문 저장 | ❌ (text excerpt 500자 제한만) |
| screenshot 저장 | ❌ |
| 쿠키 export | ❌ (메모리 전용 context, 종료 시 자동 폐기) |
| storage_state export | ❌ |
| 다운로드 실행 | ❌ (후보 카운트만, 실제 download 미실행) |
| 결과 redaction | ✅ allowlist 필드만 보존 + safe field 강제 False |

## 테스트 결과

| 단계 | 명령 | 결과 |
|------|------|------|
| 1 | `pytest tests/test_local_agent_public_external_readonly_live_smoke_20260508.py` | **34 passed** |
| 2 | 기존 local agent + server guard 6파일 (121건) | 121 passed |
| 3 | live smoke 스크립트 실행 | **3/3 reachable, 14/14 차단 분류** |
| 4 | **전체 회귀 `pytest -q`** | **4776 passed, 7 skipped, 0 failed** |

## 신규 파일

| 파일 | 신규/수정 | 이유 |
|------|-----------|------|
| `scripts/smoke/local_agent_public_external_readonly_live_smoke.py` | 신규 | 로컬 PC live smoke 스크립트 (read-only, allowlist 3개) |
| `tests/test_local_agent_public_external_readonly_live_smoke_20260508.py` | 신규 | 스크립트 정책/구조 검증 34건 (mock, 외부 접속 없음) |
| `data/reports/local_agent/local_agent_public_external_readonly_live_smoke_20260508_221403.json` | 신규 | live smoke 실행 결과 JSON |
| `docs/reports/local_agent_public_external_readonly_live_smoke_20260508.md` | 신규 | 본 문서 |

## 남은 과제

- G2B 공개/비로그인 페이지 별도 단계 (G2B_PUBLIC_READONLY_LIVE_SMOKE)
- 정부24 공개 안내 페이지 별도 단계
- 모바일 앱/공식 API 우선 라우팅 정책 추가 검토
