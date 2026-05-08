# Universal Site Automation Platform - 설계 문서

작성일: 2026-05-08  
태스크: UNIVERSAL_SITE_AUTOMATION_PLATFORM_1

---

## 개요

사이트별 전용 코드 작성 없이, **site profile + workflow template + selector pack + permission policy** 조합만으로 모든 외부 사이트 자동화를 처리하는 범용 플랫폼.

---

## 핵심 원칙

1. **사이트별 코드 금지** — 신규 사이트 온보딩은 profile/selector 등록만으로 처리
2. **로컬 브라우저 전용** — `server_browser_used = False` 불변
3. **7대 safe field 항상 False** — cookie/session/password/otp/cert_password/storage_state/server_browser_used
4. **감사 로그 필수** — 모든 profile `requires_audit_log = True`
5. **BLOCKED action은 실행 불가** — gate에서 차단, 결과에 반영

---

## 구성 요소

### 1. Site Profile Registry (`site_profile_registry.py`)

- 13개 기본 profile 등록 (naver, naver_blog, naver_cafe, g2b_public, hometax_placeholder, bank_placeholder, card_placeholder, insurance_placeholder, generic_* 5종)
- `_COMMON_BLOCKED`: 21개 공통 금지 action (password_save, otp_save, cookie_export, session_export, npki_access, captcha_bypass, auto_esign 등)
- `_COMMON_DIRECT`: 로그인 직접 조작 필요 action
- 모든 profile에 `_COMMON_BLOCKED` 자동 포함 강제

### 2. Site Capability Matrix (`site_capability_matrix.py`)

- 17개 CAP_* 상수 (CAP_READONLY_EXPLORE ~ CAP_BID_DIRECT_ONLY)
- 4-grade 실행 등급:
  - `AUTO_ALLOWED`: readonly/search/extract/download/draft/preview
  - `USER_DELEGATED_PERMISSION_REQUIRED`: publish/comment/message/upload/delete
  - `USER_DIRECT_REQUIRED`: payment/esign/bid
  - `BLOCKED`: 금지 목록

### 3. Workflow Template Engine (`workflow_template_engine.py`)

- 10개 기본 템플릿 (readonly_site_explore, download_documents, blog_publish_with_permission 등)
- 각 step: `{step_id, action, risk_level, optional, description}`
- BLOCKED 스텝 포함 금지

### 4. Selector Pack Registry (`selector_pack_registry.py`)

- 금지 selector key: `password_input, otp_input, cert_password_input, login_id_input, captcha_input, credit_card_input, npki_selector`
- 4개 기본 팩: naver_blog, naver_cafe, g2b_public, generic_content_site
- `generate_skeleton_pack()`: 금지 key 없는 빈 skeleton 생성

### 5. Universal Safe Result (`universal_safe_result.py`)

- 7개 safe field 항상 False 보장
- `build_universal_result()` → 표준 결과 구조
- `validate_universal_result()` → safe field 위반 검사
- `merge_step_results()` → step별 결과 병합

### 6. Universal Workflow Runner (`universal_workflow_runner.py`)

- `run_workflow(site_id, workflow_id, permission_map, runner_fn, task_id, dry_run)`
- `run_single_action(site_id, action, domain, permission_id, content, ...)`
- delegated_permission_gate 통합
- approval_audit_log 통합

### 7. Scenarios Library (`scenarios/`)

- government_readonly, cafe_to_blog, document_download, content_research_to_blog
- financial_readonly, message_send_with_permission, form_submit_with_permission

### 8. Site Onboarding Tools (`scripts/local_agent/`)

- `create_site_profile.py`: profile + selector skeleton 생성
- `validate_site_profile.py`: 보안 정책 준수 검사

---

## 금지 사항 (불변)

| 금지 항목 | 위치 |
|-----------|------|
| password/OTP 자동 입력 | selector_pack_registry._FORBIDDEN_SELECTOR_KEYS |
| cookie/session/token export | _COMMON_BLOCKED, safe_fields=False |
| NPKI/인증서 파일 접근 | _COMMON_BLOCKED |
| captcha 우회 | _COMMON_BLOCKED |
| 서버 측 브라우저 실행 | server_browser_used=False 불변 |
| 스팸 대량 게시 | content_publish_guard |
| 자동 결제/이체/낙찰 | USER_DIRECT_REQUIRED 또는 BLOCKED |

---

## 신규 사이트 온보딩 절차

1. `create_site_profile(site_id, display_name, domains, category)` 실행
2. 생성된 selector skeleton에 안전한 selector 추가
3. `validate_site_profile.py` 실행하여 정책 준수 확인
4. 기존 workflow template 재사용 또는 신규 등록
