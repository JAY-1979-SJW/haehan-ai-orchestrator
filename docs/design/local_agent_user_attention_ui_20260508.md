# LOCAL_AGENT_USER_ATTENTION_UI 설계 문서

작성일: 2026-05-08  
작업명: LOCAL_AGENT_USER_ATTENTION_UI_1

---

## 개요

인증/로그인/OTP/공동인증서 등 사용자 직접 입력이 필요한 순간,
로컬 에이전트가 안전한 OS 알림을 발송하고 브라우저를 사용자 화면 앞으로 표시 요청한다.
알림은 "사용자 직접 입력 필요"를 알려주는 역할만 한다.

---

## 신규 모듈

| 파일 | 역할 |
|---|---|
| `user_notification_adapter.py` | OS별 토스트 알림 발송. 민감정보 포함 메시지 차단. fallback 메시지 제공 |
| `browser_foreground_adapter.py` | 브라우저 창을 포그라운드로 표시 요청. headed/headless 판정 |
| `user_attention_notifier.py` | 두 adapter를 연결하는 상위 인터페이스. notify_auth_required() 제공 |

---

## 사용자 알림 흐름

```
인증 필요 감지 (playwright_runner)
  ↓
auth_wait_controller.enter_auth_wait()
  ↓
user_attention_notifier.notify_auth_required()
  ├── user_notification_adapter.notify_auth_required()  →  OS 토스트 발송
  └── browser_foreground_adapter.request_foreground()  →  브라우저 포그라운드
  ↓
WAITING_USER_AUTH 결과 반환
  ↓
사용자 직접 인증
  ↓
auth_completion_detector 감지
  ↓
auto_resume_after_auth 자동 재개
```

---

## 브라우저 foreground 흐름

| 조건 | 동작 |
|---|---|
| headed + Windows PID 있음 | SetForegroundWindow 시도 → BROWSER_FOREGROUND_REQUESTED |
| headed + PID 없음 | USER_MANUAL_FOCUS_REQUIRED (직접 클릭 안내) |
| headless | HEADED_BROWSER_REQUIRED 반환 |
| macOS | osascript activate 시도 |
| Linux | USER_MANUAL_FOCUS_REQUIRED |
| 실패 | BROWSER_FOREGROUND_UNAVAILABLE (WARN, 작업 계속) |

---

## headed/headless 전환 기준

- headless 환경에서 인증이 감지되면 `HEADED_BROWSER_REQUIRED` 상태 반환
- headed → headless 강제 전환 없음
- headless → headed 강제 전환 없음 (실행 환경 변경 금지)
- 사용자가 별도로 headed 브라우저를 직접 실행해야 함

---

## 지원 불가 환경 fallback

OS 알림 라이브러리(plyer, win10toast, winotify) 모두 없을 때:
- `FALLBACK_MESSAGE_ONLY` 상태 반환
- 콘솔 메시지로 안내
- 작업은 계속 진행 (알림 실패 = 작업 실패 아님)

---

## 알림 메시지 안전 정책

알림 발송 전 `_is_safe_message()` 검사:
- cookie, session, token, npki, submit, sign, 결제, 투찰 포함 시 → 안전 문구로 강제 대체
- 비밀번호/OTP/인증서 비밀번호는 "자동 입력하지 않는다"는 안내 문구에서만 허용
- 알림 클릭으로 submit/sign/payment/bid가 실행되지 않음

---

## 인증정보 미수집 정책

| 항목 | 상태 |
|---|---|
| password_collected | 항상 False |
| otp_collected | 항상 False |
| certificate_password_collected | 항상 False |
| cookie_exported | 항상 False |
| session_exported | 항상 False |
| storage_state_exported | 항상 False |
| sensitive_data_included | 항상 False |

---

## 자동 재개 연계

- WAITING_USER_AUTH 반환 후 `auth_completion_detector`가 페이지 변화 감지
- 인증 완료 감지 시 `auto_resume_after_auth.resume_after_auth()` 호출
- read_page/search/download/extract만 자동 재개 허용
- submit/sign/payment/bid는 계속 USER_ACTION_REQUIRED

---

## 미구현 항목 (별도 승인 필요)

| 항목 | 상태 | 비고 |
|---|---|---|
| OS 트레이 상주 아이콘 | 미구현 | 별도 승인 후 진행 |
| OS 자동시작 등록 | 미구현 | 별도 승인 후 진행 |
| Linux 포그라운드 전환 | 미구현 | USER_MANUAL_FOCUS_REQUIRED fallback |
| headless → headed 자동 전환 | 미구현 | 실행 환경 변경 금지 원칙 |
