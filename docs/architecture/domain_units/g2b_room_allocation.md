# G2B 집 배정표 (Domain Room Allocation)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
상태: LOCKED

cross-domain 직접 import 금지: g2b ↔ gabia ↔ hiworks ↔ eum ↔ google ↔ youtube ↔ cad ↔ hwpx

---

## 1. g2b/public-notice (공개 공고 조회)

**목적:** 나라장터 공개 공고 목록 read-only 수집, 검색, 필터링  
**현재 구현:** `scripts/g2b/router.py`, `scripts/g2b/discover_valid_public_notice_urls.py`

| 항목 | 내용 |
|------|------|
| 허용 action | 공고 목록 조회, 검색, 필터링, 키워드 매핑 |
| 금지 action | 로그인 필요 공고 자동 접근, 결과 자동 제출 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | OpenAPI 연동, read-only HTTP 수집 |
| storage/report | `data/g2b/public_notices/` |
| test | `tests/test_g2b_public_notice_*.py` |
| gate decision | READ_ONLY_ALLOWED |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | 로그인 자동화, session 사용 |

---

## 2. g2b/notice-detail (공고 상세 조회)

**목적:** 개별 공고 상세 정보, 자격 요건, 제출 서류 조회

| 항목 | 내용 |
|------|------|
| 허용 action | 공고 상세 조회, 첨부파일 목록 확인 |
| 금지 action | 로그인 없이 접근 불가 공고 자동 우회 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | OpenAPI 또는 공개 URL 파싱 |
| storage/report | `data/g2b/notice_details/` |
| test | `tests/test_g2b_public_notice_content_validator_20260508.py` |
| gate decision | READ_ONLY_ALLOWED |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ❌ |

---

## 3. g2b/attachment-download (첨부파일 다운로드)

**목적:** 공고 첨부파일 URL 수집 및 다운로드 (로컬 에이전트 경유)  
**현재 구현:** `scripts/g2b/download_g2b_direct_attachment_urls.py`

| 항목 | 내용 |
|------|------|
| 허용 action | 공개 첨부파일 URL 수집, 다운로드 |
| 금지 action | 로그인 필요 파일 자동 다운로드, 대용량 무제한 수집 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | `scripts/g2b/download_g2b_direct_attachment_urls.py` |
| storage/report | `data/g2b/attachments/` |
| test | `tests/test_g2b_readonly_download_manifest_20260508.py` |
| gate decision | READ_ONLY_ALLOWED (공개 파일) / LOCAL_AGENT_REQUIRED (로그인 필요 파일) |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ✅ 로그인 필요 첨부파일 |
| BLOCKED | session 자동 로그인 |

---

## 4. g2b/openapi-collector (OpenAPI 데이터 수집)

**목적:** 나라장터 OpenAPI를 통한 데이터 수집 자동화

| 항목 | 내용 |
|------|------|
| 허용 action | OpenAPI 호출, 응답 파싱, 데이터 저장 |
| 금지 action | API 키 무제한 소진, 결과 자동 제출 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | OpenAPI HTTP 클라이언트 |
| storage/report | `data/g2b/openapi_results/` |
| test | `tests/test_g2b_existing_openapi_bridge_*.py` |
| gate decision | READ_ONLY_ALLOWED |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ❌ |

---

## 5. g2b/login-restricted (로그인 필요 기능)

**목적:** 로그인이 필요한 G2B 기능 — 반드시 로컬 에이전트 + 사용자 직접 로그인

| 항목 | 내용 |
|------|------|
| 허용 action | 로그인 상태 감지, 사용자 로그인 유도, 결과 조회 |
| 금지 action | 서버 사이드 자동 로그인, session/cookie 재사용, OTP 자동 입력 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | 로컬 에이전트 경유 브라우저 |
| storage/report | `data/g2b/login_sessions/` (read-only 증거만) |
| test | 미구현 |
| gate decision | LOCAL_AGENT_REQUIRED |
| USER_DIRECT_REQUIRED | ✅ 로그인 행위 |
| LOCAL_AGENT_REQUIRED | ✅ 브라우저 실행 |
| BLOCKED | 서버 사이드 G2B 자동 로그인 (SERVER_BROWSER_GUARD) |

---

## 6. g2b/bid-analysis (입찰 분석)

**목적:** 입찰 공고 분석, 자격 요건 매핑, 입찰 가능성 초안 생성

| 항목 | 내용 |
|------|------|
| 허용 action | 공고 분석, 자격 요건 매핑, 초안 생성 |
| 금지 action | 입찰 자동 제출, 가격 자동 결정 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | AI 분석 + 데이터 매핑 |
| storage/report | `data/g2b/bid_analysis/` |
| test | `tests/test_g2b_public_notice_workflow_*.py` |
| gate decision | DRAFT_ALLOWED |
| USER_DIRECT_REQUIRED | ✅ 최종 입찰 결정 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | 입찰 자동 제출 |

---

## 7. g2b/bid-submit (입찰 제출)

**목적:** 입찰 제출은 절대 자동화 불가 — 사용자 직접 수행

| 항목 | 내용 |
|------|------|
| 허용 action | 입찰서류 초안 생성, 체크리스트 생성 |
| 금지 action | 투찰 자동 실행, 입찰 가격 자동 입력, 전자서명 자동화 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | 초안 생성만 |
| storage/report | `data/g2b/bid_drafts/` |
| test | 미구현 |
| gate decision | BLOCKED (자동 제출) / DRAFT_ALLOWED (초안) |
| USER_DIRECT_REQUIRED | ✅ 실제 입찰 제출 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ✅ 투찰 자동화, 전자서명 자동화 |

---

## 8. g2b/e-sign (전자서명)

**목적:** 전자서명은 절대 자동화 불가 — 사용자 직접 수행

| 항목 | 내용 |
|------|------|
| 허용 action | 서명 대상 문서 목록 조회, 서명 절차 안내 |
| 금지 action | 전자서명 자동화, 공인인증서 자동 사용 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | 안내 문서 생성만 |
| storage/report | `data/g2b/sign_evidence/` |
| test | 미구현 |
| gate decision | BLOCKED (자동 서명) |
| USER_DIRECT_REQUIRED | ✅ 전자서명 행위 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ✅ 전자서명 자동화 |

---

## 9. g2b/evidence-report (증거/리포트 저장)

**목적:** 입찰 참여 증거, 낙찰 결과, 계약 관련 리포트 저장

| 항목 | 내용 |
|------|------|
| 허용 action | 결과 리포트 저장, 증거 파일 정리, 검색 |
| 금지 action | 원본 문서 삭제, 증거 위조 |
| router | `scripts/g2b/router.py` |
| profile/gates/validators | 미구현 (❌) |
| usecase/adapter | 파일 저장/인덱싱 |
| storage/report | `data/g2b/evidence/`, `data/reports/g2b/` |
| test | `tests/test_g2b_host_proof_schema_20260508.py` |
| gate decision | ALLOWED (저장) / READ_ONLY_ALLOWED (조회) |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ❌ |

---

## 10. 현재 구현 현황 요약

| 기능 집 | router | profile | gates | validators | usecase | storage | test |
|---------|--------|---------|-------|------------|---------|---------|------|
| public-notice | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| notice-detail | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| attachment-download | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| openapi-collector | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| login-restricted | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| bid-analysis | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| bid-submit | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| e-sign | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| evidence-report | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

**필요 작업:** `scripts/g2b/site_profile.py`, `scripts/g2b/gates.py`, `scripts/g2b/validators.py` 생성
