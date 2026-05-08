# Local Agent External Web Execution Control Closeout

작성일: 2026-05-08  
작업 ID: LOCAL_AGENT_EXTERNAL_WEB_EXECUTION_CONTROL_CLOSEOUT_1

## 목적

서버에서 LOCAL_AGENT_REQUIRED로 분류된 외부 웹 작업을 로컬 PC 에이전트가 안전하게 수신·분류·실행 준비할 수 있는 구조가 코드/테스트로 enforce 되는지 closeout 단위 검증.

**신규 정책 모듈 추가 없음** — 기존 모듈 재사용 + 단위 검증만 추가.

## 정책 enum 매핑

작업 지시문의 enum과 기존 코드 상수 매핑:

| 작업 지시 enum | 기존 모듈 / 상수 |
|----------------|------------------|
| PUBLIC_READONLY_ALLOWED | `action_risk_policy.GRADE_AUTO_ALLOWED` (`_AUTO_ALLOWED` frozenset) |
| LOCAL_AGENT_ALLOWED | `GRADE_AUTO_ALLOWED` 또는 `GRADE_USER_DELEGATED` |
| USER_APPROVAL_REQUIRED | `GRADE_USER_DELEGATED` |
| USER_DIRECT_REQUIRED | `GRADE_USER_DIRECT` |
| SECURITY_PROGRAM_REQUIRED | `security_route_policy.ROUTE_INSTALL_REQUIRED` 등 |
| LOGIN_REQUIRED | `_USER_DIRECT`(`login_password_input`) |
| CERTIFICATE_REQUIRED | `_USER_DIRECT`(`cert_password_input`) |
| OTP_REQUIRED | `_USER_DIRECT`(`otp_input`) |
| PAYMENT_OR_TRANSFER_BLOCKED | `_BLOCKED`(`auto_payment`, `auto_transfer`) + `_USER_DIRECT`(`confirm_payment`) |
| BID_SUBMISSION_BLOCKED | `_BLOCKED`(`auto_bid_submit`) + `_USER_DIRECT`(`bid_final_submit`) |
| ELECTRONIC_SIGNATURE_BLOCKED | `_BLOCKED`(`auto_sign`) + `_USER_DIRECT`(`e_sign`) |
| CREDENTIAL_AUTOMATION_BLOCKED | `_BLOCKED`(`password_save`, `otp_save`, `cert_password_save`, `collect_*`) |
| COOKIE_SESSION_EXTRACTION_BLOCKED | `_BLOCKED`(`cookie_export`, `session_export`, `storage_state_export`, `token_export`) |
| SERVER_BROWSER_BLOCKED | `server.execution_location_guard` + `server.universal_agent_models` |

## 검증 흐름

```
서버 외부 URL → execution_location_guard.classify_execution_location_for_server
  → LOCAL_AGENT_REQUIRED → handoff payload 생성
  → 로컬 에이전트 수신
  → action_risk_policy.classify_action(action) — 4등급 분류
  → site_type_classifier.classify_site(host) — 도메인 분류
  → 등급별 처리:
      AUTO_ALLOWED       → 즉시 실행
      USER_DELEGATED     → 사용자 권한 위임 후 실행
      USER_DIRECT        → 사용자가 직접 수행 (UI 안내)
      BLOCKED            → 절대 실행 안 함
  → 결과 → universal_safe_result.sanitize_universal_result
      → password/cookie/session/token/cert_password/storage_state 키 제거
      → 7개 safe fields 강제 False
```

## 검증 항목 결과

| 검증 항목 | 결과 |
|-----------|------|
| LOCAL_AGENT_REQUIRED 수신 | ✅ `server.universal_agent_task_api.create_task` |
| 공개/비로그인 조회 | ✅ `read_page`, `extract_text`, `search` → AUTO_ALLOWED |
| 로그인 필요 작업 | ✅ `login_password_input` → USER_DIRECT |
| 보안프로그램 필요 작업 | ✅ `security_route_policy` 8 enum |
| 은행/정부/카드/보험 사이트 | ✅ `site_type_classifier` (g2b.go.kr, hometax.go.kr, gov.kr → SITE_GOVERNMENT) |
| 비밀번호 자동화 차단 | ✅ `password_save`, `collect_password` → BLOCKED |
| OTP 자동화 차단 | ✅ `otp_save`, `collect_otp` → BLOCKED |
| 공동인증서 차단 | ✅ `cert_password_save`, `cert_file_access`, `npki_access` → BLOCKED |
| 쿠키/session 추출 차단 | ✅ `cookie_export`, `session_export`, `storage_state_export`, `token_export`, `localStorage_dump` → BLOCKED |
| 결제/송금 차단 | ✅ `auto_payment`, `auto_transfer`, `transfer_money` → BLOCKED, `confirm_payment` → USER_DIRECT |
| 투찰/전자서명 차단 | ✅ `auto_bid_submit`, `auto_sign` → BLOCKED, `bid_final_submit`, `e_sign` → USER_DIRECT |
| 사용자 직접 조작 모드 | ✅ USER_DIRECT 등급으로 분리 |
| 결과 redaction | ✅ `_REMOVE_FIELDS`로 password/cookie/session/token/cert_password/npki/storage_state 제거 |
| server_browser_used 강제 False | ✅ `_FIXED_SAFE_FIELDS`에 항상 False |
| UAC 사용자 직접 | ✅ `ROUTE_USER_UAC_REQUIRED` → grade USER_DIRECT_REQUIRED |
| 우회/스팸 차단 | ✅ `captcha_bypass`, `account_restriction_bypass`, `bulk_spam_post` → BLOCKED |

## 정적 감사 결과

- `chromium.launch / firefox.launch / webkit.launch`: 정의(frozenset)만, 실행 호출 0건
- `async_playwright`: 정의만
- `requests/httpx/aiohttp/urllib`: 서버 디렉터리 0건
- `selenium / pyppeteer`: 정의만
- `server_browser_used = True` 실행 대입: 0건 (모두 거부 검증 코드)
- 외부 URL 실접속 테스트 코드: 0건 (모두 mock 문자열만)

## 신규 테스트

### `tests/test_local_agent_external_web_execution_control_20260508.py`

총 **52개 케이스, 모두 PASS**:

- 1~3: 공개 조회 → AUTO_ALLOWED (3)
- 4~6: 정부 도메인 분류 (3)
- 7~9: 비밀번호/OTP/인증서 입력 → USER_DIRECT (3)
- 10~14: 결제/송금/투찰/서명 → USER_DIRECT (5)
- 15~18: credential 저장 → BLOCKED (4)
- 19~23: cookie/session/storage/token export → BLOCKED (5)
- 24~26: 인증서/NPKI 파일 → BLOCKED (3)
- 27~31: 자동 결제/송금/투찰/서명 → BLOCKED (5)
- 32~34: security_route UAC/승인/대체경로 (3)
- 35~38: redaction (password/cookie/token/storage_state) (4)
- 39~42: execution_location_guard handoff (4)
- 43~46: 사용자 직접 조작 모드 (form_submit, blog_publish, send_email, file_upload → USER_DELEGATED) (4)
- 47~49: 우회/스팸 → BLOCKED (3)
- 50~51: server_browser_used False 강제 (2)
- 52: 그 외

## 테스트 실행 결과

| 단계 | 명령 | 결과 |
|------|------|------|
| 1 | `pytest tests/test_local_agent_external_web_execution_control_20260508.py` | 52 passed |
| 2 | `pytest tests/test_server_*_guard*.py tests/test_unified_router*.py` (관련 67) | 67 passed |
| 3 | `pytest -k "browser_tool or unified_execution_router or sanitize or redact"` | 212 passed |
| 4 | **전체 `pytest -q`** | **4740 passed, 7 skipped, 0 failed** |

## 결론

이번 closeout에서 신규 정책 모듈 추가 없음. **기존 4단계 등급(`action_risk_policy`) + 도메인 분류(`site_type_classifier`) + 보안프로그램 흐름(`security_route_policy`) + 결과 sanitize(`universal_safe_result`) + 서버 측 가드(`execution_location_guard`)** 가 작업 지시의 모든 필수 enum 시나리오를 cover하는 것을 52개 단위 테스트로 검증.

mock/local fixture만 사용 → 외부 URL 실접속 0건.
