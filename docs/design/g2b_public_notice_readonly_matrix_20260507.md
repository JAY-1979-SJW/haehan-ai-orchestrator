# G2B 공개 업무 읽기 전용 접근 매트릭스 설계

작성일: 2026-05-07  
태스크: G2B_PUBLIC_NOTICE_READONLY_MATRIX_1

---

## 목적

나라장터(G2B) 공개 화면 10개 후보를 대상으로 읽기 전용 자동화 접근 가능 여부를 분류한다.  
정책 기준: `evaluate_site_compliance` + `evaluate_server_browser_allowed` 모듈.

---

## 정책 요약

| site_category | target_domain | operation | compliance_decision | server_allowed | execution_loc |
|---|---|---|---|---|---|
| g2b_public_readonly | g2b.go.kr | read/navigate | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER |
| g2b | g2b.go.kr | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER |
| public_procurement | g2b.go.kr | read | NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL → BLOCK | False | LOCAL_AGENT |
| g2b_login | g2b.go.kr | submit | BLOCK | False | LOCAL_AGENT |
| restricted_financial | ibk.co.kr | read | BLOCK | False | LOCAL_AGENT |
| restricted_government | hometax.go.kr | read | BLOCK | False | LOCAL_AGENT |

> **참고**: `www.g2b.go.kr`(subdomain 포함)는 allowlist `g2b.go.kr`와 불일치로 BLOCK. 정책 적용 시 `g2b.go.kr` 사용.

---

## G2B 공개 화면 10개 후보 분류 매트릭스

| # | 화면명 | URL 패턴 | site_category | operation | compliance_decision | server_allowed | execution_loc | readonly_verdict | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 입찰공고 검색 | /pt/menu/ntn01/pta02/ptb02001l.do | g2b_public_readonly | navigate | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 로그인 불필요 |
| 2 | 입찰공고 목록 | /pt/menu/ntn01/pta02/ptb02001l.do (결과) | g2b_public_readonly | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 검색 결과 목록 |
| 3 | 입찰공고 상세 | /pt/menu/ntn01/pta02/ptb02001m.do | g2b_public_readonly | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 공고 상세 내용 |
| 4 | 첨부파일 목록 | 상세화면 내 첨부파일 영역 | g2b_public_readonly | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 파일명/크기만 조회 |
| 5 | 공고문 파일 다운로드 | 첨부파일 직접 다운로드 | g2b_public_readonly | download | BLOCK (operation_not_allowed) | True | SERVER_BROWSER | DOWNLOAD_MANUAL_ONLY | read/navigate 외 차단 |
| 6 | 업체정보 공개조회 | /pt/menu/ntn01/pta02/ptb03001l.do | g2b_public_readonly | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 공개 업체 정보 |
| 7 | 낙찰결과 조회 | /pt/menu/ntn01/pta02/ptb04001l.do | g2b_public_readonly | read | ALLOW_BROWSER_READONLY | True | SERVER_BROWSER | READ_ONLY_ALLOWED | 계약 결과 공개 |
| 8 | 로그인 페이지 | /co/menu/EgovUserReqstLogin.do | g2b_login | submit | BLOCK | False | LOCAL_AGENT | BLOCKED_LOGIN_REQUIRED | 인증서/아이디 필요 |
| 9 | 입찰 참가 신청 | /pt/menu/ntn01/pta02/ptb05001p.do | g2b_login | submit | BLOCK | False | USER_PRESENT_ONLY | BLOCKED_CERT_REQUIRED | 공인인증서 필요 |
| 10 | 계약 체결 관리 | /ct/menu/ntn02/cta01/ctb01001l.do | g2b_login | submit | BLOCK | False | USER_PRESENT_ONLY | BLOCKED_AUTH_REQUIRED | 로그인 + 인증서 |

---

## readonly_verdict 정의

| verdict | 의미 | 자동화 허용 |
|---|---|---|
| READ_ONLY_ALLOWED | 읽기/탐색 자동화 가능, 서버 브라우저 또는 로컬 agent | O |
| DOWNLOAD_MANUAL_ONLY | 파일 목록 조회만 가능, 실제 다운로드는 수동 | △ (목록만) |
| BLOCKED_LOGIN_REQUIRED | 로그인 화면 진입 자체를 자동화 금지 | X |
| BLOCKED_CERT_REQUIRED | 공인인증서 요구 화면 자동화 금지 | X |
| BLOCKED_AUTH_REQUIRED | 인증 완료 후 접근 화면 자동화 금지 | X |

---

## execution_location 결정 근거

- **SERVER_BROWSER**: `site_category=g2b_public_readonly` + `operation=read/navigate` → `server_browser_allowed=True`
- **LOCAL_AGENT**: `site_category` 분류 불명 또는 `public_procurement` 카테고리 → 기본 로컬 Agent
- **USER_PRESENT_ONLY**: `requires_certificate=True` 또는 `user_present_required=True` → 사용자 직접 인증 필요

---

## 관련 정책 모듈

- `ai_orchestrator/browser_tool/policy/site_compliance_policy.py`: `evaluate_site_compliance()`
- `ai_orchestrator/browser_tool/policy/server_browser_boundary_policy.py`: `evaluate_server_browser_allowed()`
