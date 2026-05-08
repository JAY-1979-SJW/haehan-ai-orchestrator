# LOCAL_USER_AUTH_WAIT_AND_AUTO_RESUME 설계 문서

작성일: 2026-05-08  
작업명: LOCAL_USER_AUTH_WAIT_AND_AUTO_RESUME_1

---

## 개요

로컬 Playwright 에이전트가 외부 사이트 작업 중 로그인/공동인증서/OTP/사용자 인증 필요 상태를 감지하면,
자동 입력하지 않고 브라우저를 사용자 화면 앞으로 표시 요청 상태를 반환한다.
사용자가 직접 인증을 완료하면 에이전트가 상태 변화를 감지해 중단된 read-only 작업을 자동 재개한다.

---

## 신규 모듈

| 파일 | 역할 |
|---|---|
| `auth_wait_controller.py` | 인증 대기 상태 진입, 사용자 안내, timeout/cancel 관리 |
| `auth_completion_detector.py` | 페이지 상태 변화로 인증 완료 감지 |
| `auto_resume_after_auth.py` | 인증 완료 후 read-only 작업 자동 재개 |
| `user_attention_notifier.py` | 브라우저 포그라운드 요청, 안내 메시지 생성 |
| `local_session_boundary.py` | 민감정보 서버 전송 차단 경계 강제 |

---

## 인증 필요 감지 흐름

```
playwright_runner.py
  ↓ 페이지 title/body 텍스트 분석
  ↓ _detect_auth_signal() → "login" / "cert" / "otp"
  ↓ auth_wait_controller.enter_auth_wait() 호출
  ↓ WAITING_USER_AUTH 또는 USER_ACTION_REQUIRED 반환
```

감지 신호:
- `login_required`: 로그인, sign in, 로그인이 필요
- `cert_auth_required`: 인증서, certificate, 공인인증, 공동인증, npki
- `otp_required`: otp, 일회용 비밀번호, 보안카드

---

## 사용자 직접 입력 대기

사용자 안내 문구:
```
인증이 필요합니다.
브라우저에서 직접 로그인 또는 인증을 진행해 주세요.
비밀번호, OTP, 인증서 비밀번호는 앱이 저장하거나 입력하지 않습니다.
인증이 완료되면 작업은 자동으로 계속 진행됩니다.
```

- 비밀번호 자동 입력 없음 (`password_auto_input: false`)
- OTP 자동 입력 없음 (`otp_auto_input: false`)
- 인증서 비밀번호 자동 입력 없음 (`cert_password_auto_input: false`)

---

## 인증 완료 감지 기준

`auth_completion_detector.py`:

| 기준 | 판단 |
|---|---|
| 로그인/인증 문구가 현재 페이지에서 사라짐 | 긍정 |
| 마이페이지/로그아웃/대시보드 문구 등장 | 긍정 |
| title 변화 (prev → current) | 긍정 보조 |
| URL 변화 (host 유지) | 긍정 보조 |
| 로그인 문구 여전히 존재 | 미완료 |

금지:
- password input 값 읽기
- OTP input 값 읽기
- cookie/session/localStorage/sessionStorage dump
- 인증서/NPKI 파일 접근

---

## 자동 재개 허용 작업

| action | 자동 재개 |
|---|---|
| read_page | 허용 |
| search | 허용 |
| download_file | 허용 |
| capture_screenshot | 허용 |
| extract_text | 허용 |
| extract_table | 허용 |
| detect_login_status | 허용 |

## 자동 재개 금지 작업

| action | 판정 |
|---|---|
| submit | USER_ACTION_REQUIRED |
| sign | USER_ACTION_REQUIRED |
| payment | USER_ACTION_REQUIRED |
| bid_submit | USER_ACTION_REQUIRED |
| final_submit | USER_ACTION_REQUIRED |
| transfer | USER_ACTION_REQUIRED |
| contract_submit | USER_ACTION_REQUIRED |

---

## 민감정보 차단 경계

`local_session_boundary.py` + `result_sanitizer.py` 이중 적용:

| 항목 | 처리 |
|---|---|
| cookie, cookies | 제거 + cookie_exported=False |
| session, session_token | 제거 + session_exported=False |
| password | 제거 + password_collected=False |
| otp | 제거 + otp_collected=False |
| certificate_password | 제거 + certificate_password_collected=False |
| localStorage, sessionStorage, storage_state | 제거 + storage_state_exported=False |
| npki, npki_data, private_key | 제거 |
| token, access_token, refresh_token | 제거 |
| sensitive_data_collected | 항상 False |

---

## 상태값

```python
STATUS_AUTH_COMPLETED = "AUTH_COMPLETED"
STATUS_AUTH_TIMEOUT = "AUTH_TIMEOUT"
STATUS_AUTH_CANCELLED = "AUTH_CANCELLED"
STATUS_AUTH_FAILED = "AUTH_FAILED"
STATUS_AUTO_RESUME_READY = "AUTO_RESUME_READY"
```

---

## 남은 과제

- OS 트레이/토스트 알림 실제 구현 (현재 contract만 정의)
- 브라우저 포그라운드 표시 OS 레벨 구현
- 다운로드 파일 서버 업로드 정책 결정
- 나라장터 read-only E2E 실제 테스트
