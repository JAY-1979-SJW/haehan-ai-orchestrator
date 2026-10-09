# 로컬 Agent 사용자 직접 인증 UI 런타임 설계
작성일: 2026-05-07

---

## 1. 목적

- 로컬 Agent가 사용자 직접 인증 대기 상태(REQUIRE_USER_PRESENT)를 감지하면
  사용자 PC 로컬 웹 UI에 인증 대기 화면을 표시한다.
- 사용자가 직접 인증을 완료한 뒤 "인증 완료" 버튼을 누르면 USER_CONFIRMED로 전이한다.
- 사용자가 "중단" 버튼을 누르면 CANCELLED로 전이한다.
- AI/Agent는 민감정보(비밀번호, OTP, 인증서 비밀번호)를 입력/수집/저장하지 않는다.
- 로컬 웹은 127.0.0.1 전용으로 바인딩한다.

---

## 2. 상태 enum

| 상태 | 설명 |
|---|---|
| IDLE | 작업 없음 |
| TASK_RECEIVED | 작업 수신됨 |
| OPENING_BROWSER | 브라우저 열기 중 |
| READONLY_CHECKING | read-only 상태 확인 중 |
| WAITING_FOR_USER | 사용자 직접 인증 대기 |
| USER_CONFIRMED | 사용자 인증 완료 |
| CANCELLED | 사용자 중단 |
| BLOCKED | 차단됨 (CAPTCHA, 금지 operation 등) |
| FAILED | 실패 |

---

## 3. 상태 전이 규칙

```
IDLE/TASK_RECEIVED → OPENING_BROWSER → READONLY_CHECKING
READONLY_CHECKING → WAITING_FOR_USER  (USER_PRESENT_REQUIRED 감지 시)
READONLY_CHECKING → BLOCKED           (CAPTCHA 등 차단 시)
WAITING_FOR_USER → USER_CONFIRMED     (사용자가 인증 완료 버튼 클릭)
WAITING_FOR_USER → CANCELLED          (사용자가 중단 버튼 클릭)

CANCELLED → USER_CONFIRMED: 불가
BLOCKED → USER_CONFIRMED: 불가
FAILED → USER_CONFIRMED: 불가
USER_CONFIRMED → 재확인: 불가 (final 상태)
```

---

## 4. 사용자 화면 표시 필드

| 필드 | 설명 |
|---|---|
| workflow_run_id | 현재 사용자 본인 작업 ID만 |
| task_title | 작업명 |
| site_name | 사이트명 (redacted) |
| site_category | 사이트 카테고리 |
| current_step | 현재 상태 |
| auth_method_label | 인증 방식 안내 |
| user_message_ko | 사용자 안내 문구 (한글) |
| blocked_for_ai_input | AI 입력 차단 여부 |
| allowed_user_actions | 사용 가능한 버튼 목록 |
| warning_items | 경고 항목 목록 |
| created_at | 작업 생성 시각 |

---

## 5. 사용자 화면 표시 금지 필드

- password, otp, certificate_password, financial_certificate_password
- token, access_token, refresh_token, api_key
- cookie, session, localStorage, sessionStorage
- secret, raw_audit, audit_raw, internal_policy, full_policy
- cross_tenant_data, other_user_tasks, other_tenant_data
- server_path, system_trace, raw_validation_errors

---

## 6. 버튼 정책

| 상태 | 인증 완료 버튼 | 중단 버튼 |
|---|---|---|
| WAITING_FOR_USER | 활성 | 활성 |
| USER_CONFIRMED | 비활성 (완료) | 비활성 |
| CANCELLED | 비활성 | 비활성 |
| BLOCKED | 비활성 | 활성 |
| FAILED | 비활성 | 활성 |
| IDLE/TASK_RECEIVED | 비활성 | 비활성 |

---

## 7. 보안 정책

- host: 127.0.0.1 전용 바인딩 (0.0.0.0 기본 금지)
- port: 18080 (ai_orchestrator 8400과 충돌 없음)
- 사용자 본인 task만 표시 (user_id 기반 격리)
- 다른 tenant/user task 표시 금지
- raw sensitive 값 미표시 (sanitize_user_present_task_for_user 적용)
- 인증서/OTP/비밀번호 input 필드 HTML에 생성 금지
- 브라우저 자동화 (click/type/submit) 코드 없음

---

## 8. UI 사용자 안내 문구

- "이 단계는 공동인증서/금융인증서/OTP/비밀번호가 필요합니다."
- "AI는 민감정보를 입력하거나 볼 수 없습니다."
- "사용자가 직접 인증을 완료한 뒤 인증 완료 버튼을 눌러주세요."
- "제출/결제/이체는 자동 실행되지 않습니다."
- "현재 화면에는 사용자 본인 작업 정보만 표시됩니다."

---

## 9. HTTP Route 구성

| Method | Path | 설명 |
|---|---|---|
| GET | /health | 헬스체크 |
| GET | / | 작업 목록 HTML |
| GET | /tasks | 작업 목록 JSON |
| GET | /tasks/{workflow_run_id} | 작업 상세 JSON (sanitized) |
| POST | /tasks/{workflow_run_id}/confirm | 인증 완료 상태 전이 |
| POST | /tasks/{workflow_run_id}/cancel | 중단 상태 전이 |

---

## 10. 파일 위치

| 역할 | 경로 |
|---|---|
| 상태 store | core/agent_runtime/user_present/user_present_state_store.py |
| 로컬 웹 UI 서버 | core/agent_runtime/user_present/user_present_ui_server.py |
| 정책 판정 | ai_orchestrator/agent_hub/user_present_flow.py |
| read-only 런타임 | core/agent_runtime/browser/browser_readonly_runtime.py |
| 테스트 | tests/test_local_agent_user_present_ui_runtime_20260507.py |
| fixture | tests/fixtures/local_agent_user_present_ui_runtime_20260507.json |
| 이 문서 | docs/design/local_agent_user_present_ui_runtime_20260507.md |
