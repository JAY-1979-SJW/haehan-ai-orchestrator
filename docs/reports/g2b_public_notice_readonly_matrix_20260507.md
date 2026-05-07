# G2B 공개 업무 읽기 전용 접근 매트릭스 리포트

작성일: 2026-05-07  
태스크: G2B_PUBLIC_NOTICE_READONLY_MATRIX_1  
상태: 완료

---

## 실행 요약

G2B(나라장터) 공개 화면 10개 후보를 대상으로 읽기 전용 자동화 접근 가능 여부를 정책 모듈로 분류하고 픽스처 및 테스트 18개를 추가 완료.

---

## 분류 결과

| # | 화면명 | verdict | server_allowed | execution_loc |
|---|---|---|---|---|
| 1 | 입찰공고 검색 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 2 | 입찰공고 목록 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 3 | 입찰공고 상세 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 4 | 첨부파일 목록 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 5 | 공고문 파일 다운로드 | DOWNLOAD_MANUAL_ONLY | True | SERVER_BROWSER |
| 6 | 업체정보 공개조회 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 7 | 낙찰결과 조회 | READ_ONLY_ALLOWED | True | SERVER_BROWSER |
| 8 | 로그인 페이지 | BLOCKED_LOGIN_REQUIRED | False | LOCAL_AGENT |
| 9 | 입찰 참가 신청 | BLOCKED_CERT_REQUIRED | False | USER_PRESENT_ONLY |
| 10 | 계약 체결 관리 | BLOCKED_AUTH_REQUIRED | False | USER_PRESENT_ONLY |

---

## 주요 발견사항

### 1. subdomain 불일치 (www.g2b.go.kr vs g2b.go.kr)

`site_compliance_policy.py`의 `ALLOWLIST_SAFE_SITES`에 `g2b.go.kr`(apex domain)만 등록되어 있음.  
`www.g2b.go.kr` 입력 시 allowlist 불일치 → `BLOCK` 반환.  
**정책 적용 시 반드시 apex domain `g2b.go.kr` 사용 필요.**

### 2. server_browser_allowed 판단 기준

`evaluate_server_browser_allowed()`는 `site_category`를 기준으로 판단.  
`g2b_public_readonly` → `server_browser_allowed=True` (도메인 무관).  
`g2b_login` → `server_browser_allowed=False` (로컬 Agent 전용).

### 3. download operation BLOCK

`site_category=g2b_public_readonly`이더라도 `operation_type=download`는 `evaluate_site_compliance()`에서 `BLOCK` 처리.  
공고문 파일 다운로드는 목록 조회만 자동화 허용, 실제 다운로드는 사용자 수동 처리.

### 4. 인증서 요구 화면

`requires_certificate=True` 플래그 → `execution_location_required=USER_PRESENT_ONLY`.  
입찰 참가 신청, 계약 체결은 공인인증서 필요로 서버 브라우저 및 자동 실행 전면 금지.

---

## 테스트 결과

| 파일 | 통과 | 실패 |
|---|---|---|
| test_g2b_public_notice_readonly_matrix_20260507.py | 18 | 0 |
| test_local_agent_user_present_status_observability_20260507.py | 22 | 0 |
| 전체 테스트 스위트 | 2887 | 17 (기존) |

기존 17개 실패는 browser_gate/browser_worker/tenant_scope 관련으로 이번 변경과 무관.

---

## 생성된 파일

- `docs/design/g2b_public_notice_readonly_matrix_20260507.md` — 설계 문서
- `tests/fixtures/g2b_public_notice_readonly_matrix_20260507.json` — 픽스처 10개 케이스
- `tests/test_g2b_public_notice_readonly_matrix_20260507.py` — 테스트 18개
- `docs/reports/g2b_public_notice_readonly_matrix_20260507.md` — 본 리포트
