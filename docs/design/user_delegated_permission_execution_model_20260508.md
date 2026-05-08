# 사용자 위임 권한 실행 모델 설계 문서

작성일: 2026-05-08

## 목적

기존 차단 중심 정책을 사용자 위임 권한 기반 실행 모델로 전환한다.
블로그 발행, 카페 글쓰기, 댓글 작성, 수정, 삭제 등 쓰기 작업은
사용자가 명시적으로 권한을 부여한 경우에 한해 실행 가능하다.

## 실행 등급

### 1. AUTO_ALLOWED
권한 없이 자동 실행 가능.

read_page, open_url, search, navigate, detect_login_status,
extract_text, extract_table, extract_list, extract_metadata,
capture_screenshot, summarize, preview,
download_file, fill_search_field, save_draft,
wait_for_user_auth

### 2. USER_DELEGATED_PERMISSION_REQUIRED
사용자가 권한을 명시적으로 위임한 후 실행 가능.

blog_publish, blog_schedule_publish, blog_edit, blog_delete,
blog_set_visibility,
cafe_post_write, cafe_post_edit, cafe_post_delete,
cafe_comment_write, cafe_comment_edit, cafe_comment_delete,
set_visibility, publish_with_attachment,
form_submit, click_submit, file_upload,
send_email, send_message

### 3. USER_DIRECT_REQUIRED
사용자가 직접 수행. 자동화 불가, 위임 불가.

login_password_input, otp_input, cert_password_input,
e_sign, sign_document,
bid_final_submit, confirm_payment, confirm_transfer,
contract_confirm, final_submit,
government_final_submit, legal_final_submit

### 4. BLOCKED (권한 부여 불가, 항상 차단)

password_save, otp_save, cert_password_save,
collect_password, collect_otp, collect_cookie, collect_session,
cookie_export, session_export, cookie_dump, session_dump,
token_export, auth_header_export, storage_state_export,
localStorage_dump, sessionStorage_dump,
cert_file_access, npki_access, read_certificate_file,
auto_sign, auto_bid_submit, auto_payment, auto_transfer,
auto_contract_submit, auto_final_submit, transfer_money,
captcha_bypass, account_restriction_bypass,
bulk_spam_post, bulk_spam_comment, silent_execute

## 권한 객체 구조

```python
{
  "permission_id": "uuid",
  "action": "blog_publish",
  "domain": "blog.naver.com",
  "account": "user1",           # 선택: 특정 계정 한정
  "task_scope": "campaign-001", # 선택: 특정 작업 한정
  "content_preview": "...",     # 승인 내용 미리보기 (최대 200자)
  "granted_by": "user",
  "granted_at": "ISO8601",
  "expires_at": "ISO8601",      # duration_seconds 후 만료
  "max_executions": 1,          # 최대 실행 횟수 (상한 50)
  "execution_count": 0,
  "status": "ACTIVE",           # ACTIVE | REVOKED | EXHAUSTED
  "revoked_at": null
}
```

## 권한 제한 규칙

- action: 권한 생성 시 지정된 action만 허용
- domain: 지정된 도메인만 허용
- account: 지정 시 해당 계정만 허용
- task_scope: 지정 시 해당 scope만 허용
- expires_at: 만료 후 차단 (PERMISSION_EXPIRED)
- max_executions: 초과 시 차단 (PERMISSION_EXHAUSTED), 상한 50
- 1회 권한 재사용: max_executions=1이면 1회 사용 후 EXHAUSTED
- 철회: revoke() 호출 → REVOKED 상태 → 이후 실행 차단

## 실행 흐름

```
evaluate_gate(action, domain, permission_id)
  ↓
BLOCKED? → GATE_BLOCKED → 실행 차단
USER_DIRECT? → GATE_USER_DIRECT → 사용자 직접 수행 안내
AUTO_ALLOWED? → GATE_PASS → 즉시 실행
USER_DELEGATED + permission_id 없음? → GATE_NEED_PERMISSION
USER_DELEGATED + permission 유효? → GATE_PASS
  ↓
콘텐츠 guard (쓰기 action만)
  - content_preview vs actual_content 일치 확인
  - 스팸 감지
  ↓
log_execution_started
  ↓
runner_fn 실행
  ↓
sanitize_write_result (민감값 제거 + safe 필드 강제)
  ↓
log_execution_completed
  ↓
safe result 반환
```

## audit log

모든 권한 기반 실행은 audit log를 남긴다.
이벤트: PERMISSION_GRANTED, PERMISSION_REVOKED, EXECUTION_STARTED,
        EXECUTION_COMPLETED, EXECUTION_BLOCKED

log entry에는 비밀번호/OTP/cookie/session/token/npki 저장 없음.
content_preview는 최대 200자 truncate.

## 콘텐츠 발행 guard

- 스팸: 댓글 최대 20회/권한, 게시글 최대 5회/권한, max_executions 상한 50
- content_preview와 실제 발행 내용 불일치 → CONTENT_REJECTED
- 내용 최소 길이: 5자, 최대: 100,000자

## 절대 불변 원칙

어떠한 권한 부여로도 해제 불가:
1. 비밀번호/OTP/공동인증서 비밀번호 저장·자동입력 없음
2. cookie/session/token/storage_state export 없음
3. 인증서/NPKI 파일 접근 없음
4. 자동 전자서명/투찰/결제/송금 없음
5. 서버 외부 브라우저 실행 없음

## 모듈 구성

```
ai_orchestrator/local_agent/
  action_risk_policy.py              - 4개 등급 분류
  delegated_permission_policy.py     - 권한 객체 빌드/검증
  delegated_permission_store.py      - in-memory 권한 저장소
  delegated_permission_gate.py       - 통합 게이트 평가
  delegated_action_executor.py       - 실행기 (게이트+guard+audit+sanitize)
  approval_audit_log.py              - audit log
  safe_write_result_sanitizer.py     - 쓰기 결과 sanitizer
  content_publish_guard.py           - 발행 콘텐츠 정책 검증
```
