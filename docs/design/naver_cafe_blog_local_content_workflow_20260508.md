# 네이버 카페/블로그 로컬 콘텐츠 workflow 설계

작성일: 2026-05-08

## 목적

USER_DELEGATED_PERMISSION_EXECUTION_MODEL을 네이버 카페/블로그 업무 흐름에 연결한다.
카페 탐색 → 소재 추출 → 블로그 초안 → (권한 있으면) 발행.

## 원칙

- 사이트별 전용 로그인 도구 없음
- 공통 LOCAL_PLAYWRIGHT task protocol만 사용
- 네이버 로그인: 사용자 직접 수행 (WAITING_USER_AUTH)
- 비밀번호/OTP 자동 입력 없음
- cookie/session/storage_state 서버 전송 없음
- 서버에서 네이버 직접 브라우저 실행 금지

## 등록된 네이버 도메인 (7개)

| 도메인 | 카테고리 | 기본 실행 |
|--------|---------|---------|
| naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| www.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| nid.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| cafe.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| m.cafe.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| blog.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |
| m.blog.naver.com | portal_sns | LOCAL_BROWSER_DEFAULT |

## 실행 등급

### AUTO_ALLOWED (권한 불필요)
cafe_search, cafe_read_list, cafe_read_post, cafe_extract_summary,
cafe_extract_keywords, cafe_generate_draft, cafe_generate_comment_candidate,
blog_generate_title, blog_generate_body, blog_generate_tags,
blog_preview, blog_save_draft, read_page, extract_text, search, download_file

### USER_DELEGATED_PERMISSION_REQUIRED
cafe_post_write, cafe_comment_write, cafe_post_edit, cafe_post_delete,
cafe_comment_edit, cafe_comment_delete,
blog_publish, blog_schedule_publish, blog_edit, blog_delete,
blog_set_visibility, publish_with_attachment

### USER_DIRECT_REQUIRED
naver_login, login_password_input, otp_input

### BLOCKED
password_save, otp_save, cookie_export, session_export, storage_state_export,
bulk_spam_post, bulk_spam_comment, auto_like, auto_scrap, auto_follow

## 카페 workflow 흐름

```
search_cafe("검색어") → AUTO_ALLOWED
  ↓
read_cafe_post(url) → AUTO_ALLOWED
  ↓
generate_blog_material_from_post(post) → AUTO_ALLOWED
  ↓
write_cafe_post(domain, content, permission_id) → USER_DELEGATED
write_cafe_comment(domain, content, permission_id) → USER_DELEGATED
```

## 블로그 workflow 흐름

```
generate_blog_draft(topic, source, keywords) → AUTO_ALLOWED
  ↓
publish_blog_post(content, permission_id) → USER_DELEGATED
schedule_blog_publish(content, permission_id) → USER_DELEGATED
edit_blog_post(content, permission_id) → USER_DELEGATED
delete_blog_post(permission_id) → USER_DELEGATED
```

## 통합 runner 흐름

```
STEP A: 카페 탐색/읽기 (AUTO_ALLOWED)
STEP B: 소재 추출 (AUTO_ALLOWED)
STEP C: 블로그 초안 생성 (AUTO_ALLOWED)
STEP D: 발행 (USER_DELEGATED, dry_run=True면 권한 확인만)
```

## safe result 보장

7개 필드 항상 False:
- sensitive_data_collected
- cookie_exported
- session_exported
- password_collected
- otp_collected
- certificate_password_collected
- storage_state_exported
- server_browser_used

## 모듈 구성

```
ai_orchestrator/local_agent/
  content_workflow_policy.py       - action 등급 정의, 네이버 도메인 상수
  naver_cafe_workflow.py           - 카페 탐색/읽기/글쓰기
  naver_blog_workflow.py           - 블로그 초안/발행/수정/삭제
  naver_content_safe_result.py     - 결과 빌더 + sanitizer
  naver_content_workflow_runner.py - 통합 runner

ai_orchestrator/browser_tool/
  domain_profile_registry.py       - 네이버 7개 도메인 등록
```
