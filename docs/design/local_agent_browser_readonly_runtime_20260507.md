# 로컬 Agent Read-Only 브라우저 런타임 설계
작성일: 2026-05-07

---

## 1. 목적

- 사용자 PC 로컬 Agent에서 실제 브라우저를 read-only로 실행
- 로그인/입력/제출 없이 페이지 상태(title, url, text snippet)만 확인
- 사용자 직접 인증이 필요한 화면이 감지되면 USER_PRESENT_REQUIRED로 멈춤
- 기존 `core/agent_runtime/browser/browser_reader.py`의 `open_url_readonly()`를 조율하는 정책 계층

---

## 2. 허용 동작

| 동작 | 허용 |
|---|---|
| 브라우저 열기 (headless/headed) | O |
| URL 열기 | O |
| title 읽기 | O |
| current url 읽기 | O |
| body text snippet 읽기 (최대 500자, 민감정보 제거 후) | O |
| 인증 필요 문구 감지 | O |
| 보안프로그램/인증서/OTP/CAPTCHA 문구 감지 | O |
| data: / localhost URL | O |
| 내부 admin-web read-only 페이지 | O |

---

## 3. 금지 동작

| 동작 | 금지 이유 |
|---|---|
| click | 사용자 조작 금지 |
| type / fill | 민감정보 입력 금지 |
| submit | write action 금지 |
| download / upload | write action 금지 |
| cookie/session/token/localStorage 추출 | 민감정보 추출 금지 |
| 인증서 선택 | 사용자 직접 조작 필요 |
| 전자서명 | 사용자 직접 조작 필요 |
| 비밀번호/OTP/인증서 비밀번호 입력 | AI 입력 금지 |
| screenshot 저장 | 민감화면 유출 방지 |
| raw HTML 전체 저장 | 민감정보 유출 방지 |
| CAPTCHA 우회 | 보안 우회 금지 |
| 원격접속 차단 우회 | 보안 우회 금지 |

---

## 4. 상태 enum

| 상태 | 설명 |
|---|---|
| READY | 실행 준비 완료 |
| OPENING_BROWSER | 브라우저 열기 중 |
| PAGE_LOADED | 페이지 로드 완료 |
| USER_PRESENT_REQUIRED | 사용자 직접 인증 감지 - 대기 |
| READONLY_RESULT_READY | read-only 결과 준비 완료 |
| BLOCKED | 차단됨 (CAPTCHA, 금지 operation 등) |
| FAILED | 실패 (브라우저 미설치, 네트워크 오류 등) |
| CANCELLED | 사용자 취소 |
| RUNTIME_NOT_AVAILABLE | Playwright/브라우저 엔진 미설치 |

---

## 5. 결과 schema

```json
{
  "workflow_run_id": "...",
  "site_category": "...",
  "target_url_redacted": "[REDACTED].domain.co.kr/path",
  "target_url_hash": "sha256:...",
  "final_url_redacted": "[REDACTED].domain.co.kr/path",
  "final_url_hash": "sha256:...",
  "page_title": "페이지 제목 (최대 200자)",
  "text_snippet_redacted": "본문 일부 (최대 500자, 민감정보 제거)",
  "detected_auth_methods": ["certificate", "otp"],
  "detected_security_requirements": ["keyboard_security", "security_plugin"],
  "user_present_required": false,
  "local_agent_required": true,
  "blocked_reason": null,
  "runtime_decision": "READONLY_ALLOWED",
  "readonly_execution": true,
  "safe_to_execute": false,
  "created_at": "2026-05-07T..."
}
```

---

## 6. runtime_decision 값

| 값 | 설명 |
|---|---|
| READONLY_ALLOWED | 읽기 전용 실행 허용 |
| REQUIRE_USER_PRESENT | 사용자 직접 인증 필요 |
| REQUIRE_API_CONNECTOR | API 처리 필요 (Google 등) |
| BLOCK | 실행 차단 (CAPTCHA, write op, production_mode) |
| RUNTIME_NOT_AVAILABLE | Playwright/브라우저 미설치 |
| FAILED | 실행 실패 |

---

## 7. 인증/보안 문구 감지 규칙

### auth_method 감지
- 공동인증서, 공인인증서 → certificate
- 금융인증서 → financial_certificate
- 인증서 선택, 인증서 비밀번호, 전자서명 → certificate
- OTP → otp
- 보안카드 → security_card
- 간편인증, PASS, 카카오 인증, 네이버 인증 → simple_auth

### security_requirement 감지
- CAPTCHA, 보안문자 → captcha (→ BLOCK)
- 보안프로그램, 키보드보안, 안전한 브라우저 → security_plugin
- 원격접속, 원격제어, 원격지원 → remote_access_warning
- 설치 필요, 설치 후 → install_required

---

## 8. 보안 정책

- text_snippet: 최대 500자, password/token/otp/cookie/session 포함 시 redaction
- raw HTML 전체: 결과 dict에 포함 금지
- screenshot: 저장/전송 금지
- cookie/session/token/localStorage: 추출/저장/전송 금지
- target_url: hash 처리 후 저장, 원문은 내부 전용
- safe_to_execute: 항상 false

---

## 9. 파일 위치

| 역할 | 경로 |
|---|---|
| 런타임 모듈 | core/agent_runtime/browser/browser_readonly_runtime.py |
| 기존 read-only 브라우저 실행 | core/agent_runtime/browser/browser_reader.py (open_url_readonly) |
| 기존 수동 로그인 감지 | core/agent_runtime/browser/browser_login_probe.py |
| 정책 판정 (실행 위치) | ai_orchestrator/agent_hub/user_present_flow.py |
| 테스트 | tests/test_local_agent_browser_readonly_runtime_20260507.py |
| fixture | tests/fixtures/local_agent_browser_readonly_runtime_20260507.json |
| 이 문서 | docs/design/local_agent_browser_readonly_runtime_20260507.md |
