# 실행 위치 정책 설계 문서

작성일: 2026-05-08

## 목적

브라우저 작업의 실행 위치를 중앙에서 결정한다.
사이트별 전용 코드 없이 action + site_category로만 분류한다.

## 분류 기준

### BLOCKED (자동화 전면 금지)

| action | 사유 |
|--------|------|
| cookie_export | 쿠키 수집 금지 |
| session_export | 세션 수집 금지 |
| auto_sign | 자동 서명 금지 |
| auto_bid_submit | 자동 투찰 금지 |
| auto_payment | 자동 결제 금지 |
| auto_transfer | 자동 이체 금지 |
| npki_access | NPKI 파일 접근 금지 |
| bid_submit | 입찰서 제출 (기본 차단) |

### USER_DIRECT_ONLY (사용자 직접 수행)

| action | 사유 |
|--------|------|
| cert_password_input | 인증서 비밀번호 직접 입력 |
| otp_input | OTP 직접 입력 |
| final_submit | 최종 제출 직접 확인 |
| confirm_payment | 결제 직접 확인 |
| sign_document | 문서 서명 직접 수행 |

### LOCAL_REQUIRED (로컬 에이전트 필수)

- action이 login 포함
- action이 cert_auth, otp_wait, security_program, government_auth, financial_auth 포함
- site_category가 financial_banking_auth

### SERVER_FIRST (서버 우선)

- site_category가 public_readonly + action이 read/open
- 위 조건 외 기본값 (fallback 허용)

### SERVER_ONLY (서버 전용)

- action이 db_query, internal_api, backend_only

## fallback_allowed 규칙

| 실행 위치 | fallback_allowed |
|-----------|-----------------|
| SERVER_FIRST | True |
| SERVER_TO_LOCAL_FALLBACK | True |
| SERVER_ONLY | False |
| LOCAL_REQUIRED | False |
| USER_DIRECT_ONLY | False |
| BLOCKED | False |

## 헬퍼 함수

- `is_server_first(task)` → bool
- `is_local_required(task)` → bool
- `is_user_direct_only(task)` → bool
- `should_block(task)` → bool
- `get_execution_reason(task)` → str
