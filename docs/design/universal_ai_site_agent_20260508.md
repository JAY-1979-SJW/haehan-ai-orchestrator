# Universal AI Site Agent - 설계 문서

작성일: 2026-05-08  
태스크: UNIVERSAL_AI_SITE_AGENT_1

---

## 핵심 패러다임 전환

| 기존 (Universal Site Automation Platform) | 신규 (Universal AI Site Agent) |
|---|---|
| 사용자가 site profile 등록 | AI가 페이지를 관찰하여 자동 인식 |
| selector/workflow 직접 관리 | AI가 selector 발견, workflow 자동 생성 |
| known site만 처리 가능 | 처음 보는 사이트도 처리 가능 |
| 사이트별 코드 존재 | 공통 runner + fallback policy |

---

## AI 인식 구조

### 1. Universal Page Observer (`universal_page_observer.py`)

현재 페이지를 **안전하게** 관찰한다.

**관찰 가능:**
- URL host, title, headings
- visible buttons, links, form_labels
- page type candidates (notice_board, blog, government 등)
- visible actions (search, download, write, publish 등)
- auth signals, risk signals
- download candidates

**절대 읽지 않음:**
- password input value
- OTP value
- cookie/session/localStorage/sessionStorage
- storage_state, token
- 인증서/NPKI

출력 safe fields: `password_value_read=False`, `otp_value_read=False`, `cookie_read=False`, `session_read=False`, `storage_state_read=False`, `server_browser_used=False`

### 2. Intent Parser (`user_intent_parser.py`)

자연어 지시 → 실행 intent 변환.

**15가지 intent:**
READ_PAGE, SEARCH_SITE, FIND_NOTICE, DOWNLOAD_ATTACHMENTS, SUMMARIZE_CONTENT, EXTRACT_TABLE, GENERATE_BLOG_DRAFT, PREPARE_FORM, WRITE_POST, WRITE_COMMENT, PUBLISH_POST, UPDATE_POST, DELETE_POST, SEND_MESSAGE, SUBMIT_FORM

**AUTO_ALLOWED intents:** READ_PAGE, SEARCH_SITE, FIND_NOTICE, DOWNLOAD_ATTACHMENTS, SUMMARIZE_CONTENT, EXTRACT_TABLE, GENERATE_BLOG_DRAFT, PREPARE_FORM

**Permission Required intents:** WRITE_POST, WRITE_COMMENT, PUBLISH_POST, UPDATE_POST, DELETE_POST, SEND_MESSAGE, SUBMIT_FORM

### 3. Site Type Classifier (`site_type_classifier.py`)

처음 보는 사이트도 유형을 추정한다.

판정 순서:
1. Known domain map (confidence: high)
2. `.go.kr` / `.gov` domain (confidence: high)
3. 텍스트 기반 힌트 (confidence: medium)
4. page_type_candidates (confidence: low)

10개 site type: content_platform, blog, cafe_or_forum, notice_board, government, financial, ecommerce, document_portal, form_site, unknown

### 4. Generic Selector Discovery (`generic_selector_discovery.py`)

known selector pack 없이 화면에서 후보를 발견한다.

**발견 가능:**
- search_box, list_items, article_links, download_links
- title_input, body_editor, save_draft_button, preview_button
- publish_button, submit_button, delete_button (발견만)
- risk_buttons_detected (payment/sign/bid/transfer/delete)

**절대 발견하지 않음:**
- password_selector (= False)
- otp_selector (= False)
- cert_password_selector (= False)
- npki_selector (= False)

### 5. Universal Task Planner (`universal_task_planner.py`)

intent + observation + site_type → 실행 계획 생성.

- risk signal(payment/sign/bid) 감지 시 DELEGATED → DIRECT 격상
- permission_map으로 DELEGATED step 실행 가능 여부 결정
- auto_steps / pending_permission / user_direct_required / blocked 분류

---

## 실행 등급

| 등급 | 실행 | 예시 |
|------|------|------|
| AUTO_ALLOWED | 즉시 실행 | 읽기, 검색, 다운로드, 요약, 초안 생성 |
| USER_DELEGATED_PERMISSION_REQUIRED | 권한 부여 후 실행 | 발행, 댓글, 수정, 삭제, 메시지 전송 |
| USER_DIRECT_REQUIRED | 사용자 직접 조작 | 로그인, OTP, 전자서명, 결제, 송금 |
| BLOCKED | 절대 실행 불가 | password 저장, cookie export, captcha 우회 |

---

## Unknown Site Fallback Policy (`unknown_site_fallback_policy.py`)

처음 보는 사이트도 기본 처리 가능.

- unknown site read-only: AUTO_ALLOWED
- unknown site download: AUTO_ALLOWED (download policy 통과 시)
- unknown site 비민감 폼 입력: AUTO_ALLOWED
- unknown site write/publish/delete/send/submit: USER_DELEGATED_PERMISSION_REQUIRED
- unknown site payment/sign/legal: USER_DIRECT_REQUIRED
- credential/session/cookie/captcha: BLOCKED

risk signal 감지 시 DELEGATED → DIRECT 자동 격상.

---

## Learned Site Profile Store (`learned_site_profile_store.py`)

성공한 workflow 구조를 안전하게 저장한다.

**저장 가능:**
- host, site_type, learned_at
- workflow_template_id
- safe_selector_candidates (publish_button, search_box 등)
- capability_hints
- action_risk_mapping
- non_sensitive_labels

**저장 금지:**
- password_value, passwd, otp_value
- cookie_value, session_value, token_value
- storage_state, cert_password
- npki, private_key, account_number, credit_card

---

## Universal Action Verifier (`universal_action_verifier.py`)

실행 후 결과를 검증한다.

검증 항목:
- safe fields (7개) 모두 False
- blocked action 실행 안 됨
- audit log 존재
- status not FAILED
- page 변화 (observation 비교)
- download manifest (download action)
- draft 생성 (generate_draft action)

---

## 안전 경계 (불변)

| 항목 | 보장 방법 |
|------|----------|
| password value 읽기 금지 | page observer에서 False |
| OTP value 읽기 금지 | page observer에서 False |
| cookie/session 읽기 금지 | page observer에서 False |
| server_browser_used | 항상 False |
| learned profile 민감정보 | 저장 전 sanitize + validate |
| BLOCKED action | unknown_site_fallback_policy + universal_task_planner |

---

## 사용자 경험

사용자는 사이트를 등록하지 않는다. 자연어로만 지시한다:

- "이 사이트에서 공지사항 찾아서 요약해줘" → FIND_NOTICE → AUTO_ALLOWED
- "첨부파일 받아서 정리해줘" → DOWNLOAD_ATTACHMENTS → AUTO_ALLOWED
- "이 페이지 내용을 블로그 글로 만들어줘" → GENERATE_BLOG_DRAFT → AUTO_ALLOWED
- "이 글을 발행해줘" → PUBLISH_POST → USER_DELEGATED_PERMISSION_REQUIRED
- "결제해줘" → risk signal "payment" → USER_DIRECT_REQUIRED
