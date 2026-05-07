# 로컬 Playwright 에이전트 task bridge 설계 문서

작성일: 2026-05-08

## 목적

LOCAL_BROWSER_DEFAULT 구조를 실제 실행 구조로 연결한다.
서버는 외부 사이트에 직접 접속하지 않고, 작업만 생성한다.
사용자 PC 로컬 에이전트가 서버 작업을 받아 로컬 Playwright로 실행한다.

## 서버 / 로컬 역할 분리

| 역할 | 서버 | 로컬 에이전트 |
|------|------|--------------|
| task 생성 | ✅ | - |
| safe payload 생성 | ✅ | - |
| 외부 사이트 브라우저 접속 | ❌ 금지 | ✅ |
| Playwright 실행 | ❌ 금지 | ✅ |
| 인증/OTP/인증서 자동 처리 | ❌ 금지 | ❌ 사용자 직접 |
| 결과 수신·검증 | ✅ | - |
| 민감값 저장 | ❌ 금지 | ❌ 금지 |
| 상태 관리 | ✅ | - |
| 리포트/알림 | ✅ | - |

## 모듈 구조

```
ai_orchestrator/
  local_agent/
    task_protocol.py      # 공통 task/result schema
    task_client.py        # 서버에서 task 가져와 실행하는 polling client
    playwright_runner.py  # 로컬 Playwright 실행 엔진
    security_guard.py     # 위험 작업 차단 guard
    result_sanitizer.py   # 결과 민감값 제거
  server/
    task_queue_schema.py  # in-memory task 큐 (DB schema 변경 없음)
    local_agent_task_api.py  # 서버 API/adapter
```

## 공통 task protocol

### task schema

```json
{
  "task_id": "uuid",
  "task_type": "browser_task",
  "execution_mode": "LOCAL_PLAYWRIGHT",
  "action": "open_url | read_page | search | download_file | capture_screenshot | extract_text | extract_table | wait_for_user_auth | detect_login_status",
  "target_url": "string",
  "domain": "string",
  "readonly": true,
  "requires_user_presence": false,
  "timeout_seconds": 300,
  "created_at": "iso datetime",
  "metadata": {}
}
```

### result schema

```json
{
  "task_id": "uuid",
  "ok": true,
  "execution_used": "LOCAL_PLAYWRIGHT",
  "status": "COMPLETED | WAITING_USER_AUTH | USER_ACTION_REQUIRED | FAILED | BLOCKED | CANCELLED",
  "current_url_host": "string",
  "title_hint": "string",
  "extracted_data": {},
  "downloaded_files": [],
  "sensitive_data_collected": false,
  "cookie_exported": false,
  "session_exported": false,
  "password_collected": false,
  "otp_collected": false,
  "certificate_password_collected": false,
  "message_ko": "string"
}
```

### 금지 필드 (task/result에 절대 포함 불가)

```
cookie, session, Authorization, password, otp,
certificate_password, certificate_file_path,
localStorage, sessionStorage, token, npki, private_key
```

## polling 방식

```
로컬 에이전트 → get_pending_local_agent_task() → task 수신
           → validate_task() → security_guard.validate_task_before_run()
           → mark_task_assigned()
           → playwright_runner.run_task()
           → result_sanitizer.sanitize_result()
           → receive_local_agent_result()
```

WebSocket 실시간 방식은 이후 단계에서 추가 가능. 현재는 polling.

## local Playwright runner

지원 action 9종:

| action | 설명 |
|--------|------|
| open_url | URL 열기. 인증 신호 감지 시 WAITING_USER_AUTH |
| read_page | 페이지 텍스트 읽기 (body_text_sample, max 1000자) |
| search | 검색 페이지 이동 |
| download_file | 파일 다운로드 (메타만 반환, 바이너리 미전송) |
| capture_screenshot | 스크린샷 (파일명만 반환) |
| extract_text | CSS selector 기반 텍스트 추출 |
| extract_table | 첫 번째 table 행 추출 (max 50행) |
| wait_for_user_auth | 인증 대기 안내 반환 (브라우저 실행 없음) |
| detect_login_status | 로그인 신호 감지 (값 수집 없음) |

## 보안 guard

차단 대상 (실행 전 BLOCK):
- collect_password, collect_otp, collect_cookie, collect_session
- read_certificate_file, auto_bid_submit, auto_sign, auto_payment
- auto_final_submit, transfer_money, contract_submit
- cookie_export, session_export, token_export, npki_access

사용자 직접 수행 (USER_DIRECT_REQUIRED):
- cert_password_input, otp_input, final_submit
- confirm_payment, sign_document, bid_final_submit

## result sanitizer

제거 대상:
- cookie, session, token, password, otp
- certificate_password, npki_data, private_key
- localStorage, sessionStorage

고정 필드 (항상 False):
- sensitive_data_collected, cookie_exported, session_exported
- password_collected, otp_collected, certificate_password_collected

## 사용자 인증 처리 방식

1. Playwright가 인증 신호(로그인/인증서/OTP) 감지
2. page.fill로 자동 입력하지 않음
3. WAITING_USER_AUTH 또는 USER_ACTION_REQUIRED 반환
4. 사용자 안내 문구 표시:
   > 이 작업은 사용자 PC에서 실행됩니다.
   > 브라우저가 열리면 필요한 경우 직접 인증해 주세요.
   > 비밀번호, OTP, 인증서 비밀번호는 앱이 저장하지 않습니다.

## 금지 작업

- 사이트별 전용 로그인 도구 생성
- 서버 브라우저로 나라장터/홈택스/은행/카드/보험 접속
- page.fill로 비밀번호/OTP/인증서 비밀번호 자동 입력
- cookie/session dump
- localStorage/sessionStorage dump
- NPKI 파일 접근
- 자동 투찰/전자서명/결제/최종제출

## 테스트 결과

| 파일 | 테스트 수 |
|------|----------|
| test_local_agent_task_protocol_20260508.py | 18 |
| test_local_agent_task_client_20260508.py | 6 |
| test_local_playwright_runner_20260508.py | 3 (3 skipped) |
| test_local_agent_security_guard_20260508.py | 21 |
| test_local_agent_result_sanitizer_20260508.py | 14 |
| test_server_local_agent_task_api_20260508.py | 11 |
| test_unified_local_playwright_bridge_20260508.py | 18 |
| 기존 LOCAL_BROWSER_DEFAULT 회귀 | 155 |
| **합계** | **246 pass, 3 skip** |

## 남은 과제

- 실제 로컬 PC agent 실행 smoke test
- 브라우저 headed/headless 전환 옵션
- 사용자 알림 UI (토스트/트레이)
- 다운로드 파일 서버 업로드 정책
- 나라장터 read-only 실사용 task end-to-end
- WebSocket 실시간 연결 (현재 polling)
- 로컬 에이전트 자동 재시작 정책
