# 나라장터 read-only 로컬 E2E 설계 문서

작성일: 2026-05-08

## 목적

나라장터(g2b.go.kr) 공개 홈페이지를 read-only 방식으로 접근하는 로컬 Playwright E2E 프로토콜을 정의한다.
g2b 전용 자동화 로직 없이 공통 LOCAL_PLAYWRIGHT task protocol만 사용한다.

## 핵심 원칙

- 서버 외부 브라우저 실행 없음 (server_browser_used = false 고정)
- 비밀번호/OTP/인증서 비밀번호 자동 입력 없음
- cookie/session/token/storage_state 서버 전송 없음
- NPKI/인증서 파일 접근 없음
- submit/sign/payment/bid/final_submit 자동 실행 없음
- 로컬 PC Playwright만 사용

## 허용 action

| action | 설명 |
|--------|------|
| read_page | 페이지 HTML 로드 및 기본 정보 추출 |
| extract_text | 본문 텍스트 추출 |
| extract_table | 표 데이터 추출 |
| detect_login_status | 로그인/인증 신호 감지 (값 수집 없음) |
| capture_screenshot | 스크린샷 캡처 |
| search | 검색 실행 |
| download_file | 파일 다운로드 (정책 통과 파일만) |

## 금지 action

cookie_export, session_export, auto_bid_submit, auto_sign, auto_payment,
collect_password, collect_otp, read_certificate_file, npki_access,
submit, sign, payment, bid_submit, final_submit, transfer, contract_submit

## 모듈 구성

```
ai_orchestrator/local_agent/
  task_protocol.py          - EXEC_MODE_LOCAL_PLAYWRIGHT, build_task, build_result
  security_guard.py         - validate_task_before_run, block_forbidden_action
  result_sanitizer.py       - sanitize_result (cookie/session/token/password 제거)
  local_session_boundary.py - enforce_session_boundary (7개 safe 필드 강제)
  auth_wait_controller.py   - enter_auth_wait (WAITING_USER_AUTH / USER_ACTION_REQUIRED)
  auth_completion_detector.py - check_auth_completed_from_page_state
  auto_resume_after_auth.py - can_auto_resume, classify_resume_eligibility, resume_after_auth
  download_policy.py        - check_file, check_files (NPKI > 차단확장자 > 민감명 순)
  download_upload_manifest.py - build_manifest, is_safe_manifest
  playwright_runner.py      - run_task (auth 신호 시 enter_auth_wait 호출)

ai_orchestrator/browser_tool/
  security_signal_detector.py   - detect_from_page_text (SIG_LOGIN_REQUIRED 등)
  domain_profile_registry.py    - get_domain_profile("www.g2b.go.kr")

ai_orchestrator/server/
  local_agent_file_upload_policy.py - validate_upload_manifest (서버측 최종 검증)
```

## 인증 감지 흐름

1. playwright_runner가 페이지 로드 후 body_text/title 검사
2. auth 신호 발견 시 `enter_auth_wait()` 호출 → WAITING_USER_AUTH 반환
3. 사용자가 브라우저에서 직접 인증 완료
4. auth_completion_detector가 페이지 변화로 완료 감지
5. auto_resume_after_auth가 read-only action 재실행

## 다운로드 정책

허용 확장자: .pdf, .hwpx, .hwp, .xlsx, .xls, .docx, .doc, .zip, .txt, .csv, .png, .jpg, .jpeg
차단 확장자: .pfx, .p12, .der, .cer, .crt, .pem, .key, .exe, .msi, .bat, .sh, .ps1, .dll, .so
NPKI 경로 차단: C:/NPKI, /NPKI/, npki/ 포함 경로
민감 파일명 차단: password, 비밀번호, passwd, credential 포함
최대 크기: 50MB

## safe result 구조

```json
{
  "sensitive_data_collected": false,
  "cookie_exported": false,
  "session_exported": false,
  "password_collected": false,
  "otp_collected": false,
  "certificate_password_collected": false,
  "storage_state_exported": false
}
```

7개 필드는 항상 false로 강제. enforce_session_boundary()가 보장.

## E2E 실행 흐름

```
STEP A: read_page → danger check
STEP B: extract_text → danger check  
STEP C: extract_table → danger check
STEP D: detect_login_status
STEP E: download manifest dry-run (실제 다운로드 없음)
→ safe result + manifest 저장
```

중간 인증 감지 시: WARN_AUTH_REQUIRED 반환 (정상 동작)

## g2b 도메인 프로필

```python
{
  "domain": "www.g2b.go.kr",
  "allowed_readonly": True,
  "default_execution": "LOCAL_BROWSER_DEFAULT",
  "blocked_actions": ["auto_bid_submit", "auto_sign", "auto_payment", ...]
}
```
