# Gabia 집 배정표 (Domain Room Allocation)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_DOMAIN_ROOM_ALLOCATION_01  
상태: LOCKED

cross-domain 직접 import 금지: gabia ↔ g2b ↔ hiworks ↔ eum ↔ google ↔ youtube ↔ cad ↔ hwpx

---

## 1. gabia/domain-registration (도메인 등록 보조)

**목적:** 신규 도메인 등록 초안 생성, 후보 검토, 최종 등록은 사용자 직접 수행  
**현재 구현:** `scripts/gabia/domain_assist.py`

| 항목 | 내용 |
|------|------|
| 허용 action | 후보 도메인 정규화, TLD 추천, 초안 생성, 조회 |
| 금지 action | 실제 등록 자동 실행, 결제 자동화, OTP 입력, session 사용 |
| router | `scripts/gabia/router.py` → `domain-assist` 명령 |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py`, `scripts/gabia/validators.py` |
| usecase/assist | `scripts/gabia/domain_assist.py` |
| storage/report | `data/gabia/domain_candidates/` |
| test | `tests/test_gabia_domain_registration_assist.py` |
| gate decision | draft → DRAFT_ALLOWED / final_register → USER_DIRECT_REQUIRED |
| USER_DIRECT_REQUIRED | ✅ 최종 등록, 결제, DNS 확정 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | session/cookie/OTP/password 자동 입력 |

---

## 2. gabia/dns-management (DNS 레코드 관리 보조)

**목적:** DNS 레코드 현황 조회(read-only), 변경 초안 생성, 실제 변경은 사용자 직접  
**현재 구현:** `data/gabia/dns_baseline_*.json` (스냅샷 저장됨)

| 항목 | 내용 |
|------|------|
| 허용 action | DNS 현황 조회, 변경 초안 생성, nslookup 검증 |
| 금지 action | DNS 레코드 자동 추가/수정/삭제, 서버 사이드 로그인 |
| router | `scripts/gabia/router.py` → `dns` 명령 (미구현) |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py` |
| usecase/assist | `scripts/gabia/dns_assist.py` (미구현) |
| storage/report | `data/gabia/dns_snapshots/` |
| test | `tests/test_gabia_dns_management.py` (미구현) |
| gate decision | read → READ_ONLY_ALLOWED / draft → DRAFT_ALLOWED / apply → USER_DIRECT_REQUIRED |
| USER_DIRECT_REQUIRED | ✅ DNS 레코드 실제 추가/수정/삭제 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | 서버 사이드 브라우저로 가비아 로그인 (SERVER_BROWSER_GUARD) |

---

## 3. gabia/hosting-management (호스팅 관리 보조)

**목적:** 호스팅 상품 현황 조회, 만료일 추적, 갱신 알림 초안 생성

| 항목 | 내용 |
|------|------|
| 허용 action | 호스팅 현황 조회, 만료일 알림 초안 |
| 금지 action | 호스팅 자동 구매/갱신/해지, 결제 자동화 |
| router | `scripts/gabia/router.py` → `hosting` 명령 (미구현) |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py` |
| usecase/assist | `scripts/gabia/hosting_assist.py` (미구현) |
| storage/report | `data/gabia/hosting_snapshots/` |
| test | `tests/test_gabia_hosting_management.py` (미구현) |
| gate decision | read → READ_ONLY_ALLOWED / renew → USER_DIRECT_REQUIRED |
| USER_DIRECT_REQUIRED | ✅ 갱신, 구매, 해지 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | 결제 자동화, session 재사용 |

---

## 4. gabia/mail-management (메일 관리 보조)

**목적:** 가비아 메일 계정 현황 조회, 포워딩 설정 초안 생성

| 항목 | 내용 |
|------|------|
| 허용 action | 메일 계정 목록 조회, 포워딩 초안 생성 |
| 금지 action | 메일 자동 발송, 계정 자동 생성/삭제 |
| router | `scripts/gabia/router.py` → `mail` 명령 (미구현) |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py` |
| usecase/assist | `scripts/gabia/mail_assist.py` (미구현) |
| storage/report | `data/gabia/mail_snapshots/` |
| test | `tests/test_gabia_mail_management.py` (미구현) |
| gate decision | read → READ_ONLY_ALLOWED / configure → USER_DIRECT_REQUIRED |
| USER_DIRECT_REQUIRED | ✅ 메일 계정 설정 변경, 포워딩 실제 적용 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | 메일 자동 발송, session 재사용 |

---

## 5. gabia/account-readonly (계정 조회 전용)

**목적:** 가비아 계정 정보, 계약 목록 read-only 조회

| 항목 | 내용 |
|------|------|
| 허용 action | 계정 정보 조회, 계약 목록 조회, 만료일 목록 |
| 금지 action | 계정 정보 변경, 비밀번호 변경, 결제 수단 변경 |
| router | `scripts/gabia/router.py` → `account` 명령 (미구현) |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py` |
| usecase/assist | `scripts/gabia/account_assist.py` (미구현) |
| storage/report | `data/gabia/account_snapshots/` |
| test | `tests/test_gabia_account_readonly.py` (미구현) |
| gate decision | READ_ONLY_ALLOWED (SERVER_BROWSER_ALLOWED 금지) |
| USER_DIRECT_REQUIRED | ❌ |
| LOCAL_AGENT_REQUIRED | ✅ 가비아 로그인 후 조회 |
| BLOCKED | 서버 사이드 브라우저로 가비아 로그인 |

---

## 6. gabia/payment-billing (결제/청구 보조)

**목적:** 결제 내역 조회, 청구 예정 금액 확인, 실제 결제는 사용자 직접

| 항목 | 내용 |
|------|------|
| 허용 action | 결제 내역 조회, 청구 예정 알림 초안 |
| 금지 action | 결제 자동 실행, 카드 정보 저장/전송 |
| router | `scripts/gabia/router.py` → `payment` 명령 (미구현) |
| profile/gates/validators | `scripts/gabia/site_profile.py`, `scripts/gabia/gates.py` |
| usecase/assist | `scripts/gabia/payment_assist.py` (미구현) |
| storage/report | `data/gabia/payment_snapshots/` |
| test | `tests/test_gabia_payment_billing.py` (미구현) |
| gate decision | read → READ_ONLY_ALLOWED / pay → BLOCKED (자동 결제) |
| USER_DIRECT_REQUIRED | ✅ 실제 결제 |
| LOCAL_AGENT_REQUIRED | ❌ |
| BLOCKED | ✅ 결제 자동화, session/cookie 재사용 |

---

## 7. 현재 구현 현황 요약

| 기능 집 | router | profile | gates | validators | usecase | storage | test |
|---------|--------|---------|-------|------------|---------|---------|------|
| domain-registration | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| dns-management | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ (snapshot) | ❌ |
| hosting-management | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| mail-management | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| account-readonly | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| payment-billing | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
