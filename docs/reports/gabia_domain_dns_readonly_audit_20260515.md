# Gabia 도메인 DNS 현황 감사 보고서

작성일: 2026-05-15  
작업 ID: GABIA_DOMAIN_DNS_READONLY_AUDIT_01  
감사 방법: read-only (코드 수정/DNS 변경/로그인 없음)  
데이터 출처: data/manual_visits/dns.gabia.com (2026-05-14 스냅샷) + public DNS 조회

---

## 1. 기준선

| 항목 | 값 |
|------|-----|
| local HEAD | 8edac3f |
| origin HEAD | 8edac3f |
| server HEAD | 8edac3f (ff-only pull 후 동기화) |
| git status | clean (untracked 2건만) |
| HOLD/untracked | close_2_more.py, eum_docs.py |
| session 파일 내용 열람 | 없음 (존재 여부만 확인) |

---

## 2. 기존 Gabia 코드 구조

| 파일 | 주요 내용 |
|------|----------|
| `scripts/gabia/router.py` | status, dns, login, domain, domain-assist, hosting, payment |
| `scripts/gabia/profile.py` | READ/SUBMIT/DELETE/SIGN 정책, SIGN=BLOCKED |
| `scripts/gabia/gates.py` | public_read, account_read, login, dns_change, dns_delete, domain_renew, hosting_change, payment, credential_extract |
| `scripts/gabia/validators.py` | validate_gabia_no_plain_secret |
| `scripts/gabia/domain_assist.py` | normalize_domain_candidate, suggest_tld_candidates, build_domain_registration_draft, build_dns_default_draft, build_registration_summary, evaluate_domain_registration_gate |
| `tests/test_gabia_site_engine.py` | 26개 PASS |
| `tests/test_gabia_domain_registration_assist.py` | 26개 PASS |

session 파일 (존재 여부만):
- `data/sessions/gabia.com.json` — 존재 (내용 읽기 금지)
- `data/sessions/my.gabia.com.json` — 존재 (내용 읽기 금지)
- `data/sessions/www.gabia.com.json` — 존재 (내용 읽기 금지)

---

## 3. manual_visits DNS 스냅샷 (2026-05-14 기준)

출처: `data/manual_visits/dns.gabia.com/dns_internals_total_set__20260514_004838.html`

- 도메인: haehan-ai.kr
- 레코드 개수: 21개
- 최근 업데이트: 2026-03-27 19:20:48
- 네임서버: ns1.gabia.co.kr

---

## 4. DNS 레코드 전체 목록 (스냅샷 기준)

### A 레코드 (TTL 3600, 서버 IP: 1.201.176.236)

| 호스트 | 값 | TTL |
|--------|-----|-----|
| @ (루트) | 1.201.176.236 | 3600 |
| www | 1.201.176.236 | 3600 |
| app | 1.201.176.236 | 3600 |
| support | 1.201.176.236 | 3600 |
| career | 1.201.176.236 | 3600 |
| blog | 1.201.176.236 | 3600 |
| docs | 1.201.176.236 | 3600 |
| status | 1.201.176.236 | 3600 |
| api | 1.201.176.236 | 600 |
| bid | 1.201.176.236 | 600 |
| cloud | 1.201.176.236 | 600 |
| attendance | 1.201.176.236 | 600 |
| cad | 1.201.176.236 | 600 |
| esc | 1.201.176.236 | 600 |
| gongmu | 1.201.176.236 | 600 |

### MX 레코드

| 호스트 | 값 | 우선순위 | TTL |
|--------|-----|---------|-----|
| @ | mailapp.hiworks.co.kr. | 10 | 600 |

### TXT 레코드

| 호스트 | 값 | TTL |
|--------|-----|-----|
| @ | "google-site-verification=FnsmxdpEf0vfwZUw1WWIVjBkSxabPwGhRNUyUpGK4wU" | 3600 |
| @ | "v=spf1 include:_spf.hiworks.co.kr ~all" | 600 |
| _dmarc | "v=DMARC1; p=none; rua=mailto:jay@haehan-ai.kr" | 600 |

### CNAME 레코드

| 호스트 | 값 | TTL |
|--------|-----|-----|
| hiworks | hiworksapp.hiworks.co.kr. | 600 |
| mail | mailapp.hiworks.co.kr. | 600 |

---

## 5. public DNS 조회 결과 (2026-05-15 기준)

| 서브도메인 | 외부 DNS 해석 | IP | 상태 |
|-----------|------------|-----|------|
| haehan-ai.kr | ✔ | 1.201.176.236 | 정상 |
| www | ✔ | 1.201.176.236 | 정상 |
| app | ✔ | 1.201.176.236 | 정상 |
| api | ✔ | 1.201.176.236 | 정상 |
| attendance | ✔ | 1.201.176.236 | 정상 |
| bid | ✔ | 1.201.176.236 | 정상 |
| cad | ✔ | 1.201.176.236 | 정상 |
| docs | ✔ | 1.201.176.236 | 정상 |
| support | ✔ | 1.201.176.236 | 정상 |
| career | ✔ | 1.201.176.236 | 정상 |
| blog | ✔ | 1.201.176.236 | 정상 |
| status | ✔ | 1.201.176.236 | 정상 |
| esc | ✔ | 1.201.176.236 | 정상 |
| cloud | ✔ | 1.201.176.236 | 정상 |
| gongmu | ✔ | 1.201.176.236 | 정상 |
| **admin** | ✘ | - | **미등록 (Non-existent)** |
| **office** | ✘ | - | **미등록 (Non-existent)** |

NS: ns1.gabia.co.kr, ns.gabia.net, ns.gabia.co.kr  
MX: mailapp.hiworks.co.kr (우선순위 10)  
SPF: v=spf1 include:_spf.hiworks.co.kr ~all

---

## 6. 서비스 연결 매핑

| 도메인 | 현재 A 레코드 | 예상 서비스 | 운영 중 |
|--------|------------|-----------|---------|
| haehan-ai.kr | 1.201.176.236 | 루트 웹 | 운영 중 |
| www | 1.201.176.236 | 루트 웹 (www) | 운영 중 |
| app | 1.201.176.236 | 앱 서버 | 운영 중 |
| api | 1.201.176.236 | API 서버 | 운영 중 |
| attendance | 1.201.176.236 | 출퇴근 서비스 | 운영 중 |
| bid | 1.201.176.236 | 입찰 서비스 | 운영 중 |
| cad | 1.201.176.236 | CAD 서비스 | 운영 중 |
| docs | 1.201.176.236 | 문서 서비스 | 운영 중 |
| support | 1.201.176.236 | 고객지원 | 운영 중 |
| career | 1.201.176.236 | 채용 | 운영 중 |
| blog | 1.201.176.236 | 블로그 | 운영 중 |
| status | 1.201.176.236 | 상태 모니터 | 운영 중 |
| esc | 1.201.176.236 | ESC 서비스 | 운영 중 |
| cloud | 1.201.176.236 | 클라우드 서비스 | 운영 중 |
| gongmu | 1.201.176.236 | 공무 서비스 | 운영 중 |
| mail/hiworks | CNAME | Hiworks 메일 | 운영 중 |

서버 IP: **1.201.176.236** (단일 서버, 모든 서브도메인 동일)  
nginx 라우팅으로 서브도메인별 서비스 분기 추정

---

## 7. 서브도메인 후보 분석

### 이미 A 레코드 등록됨 (수정 금지 — 서비스 영향 주의)

```
@, www, app, api, attendance, bid, cad, docs, support, career, blog, status, esc, cloud, gongmu
```

### CNAME 등록됨 (수정 금지)

```
mail, hiworks
```

### 미등록 — 신규 생성 가능

| 후보 | 용도 |
|------|------|
| admin | 관리자 패널 |
| office | 사무 서비스 |
| dev | 개발 환경 |
| staging | 스테이징 환경 |
| dashboard | 대시보드 |
| report | 보고서 |
| portal | 포털 |

### 충돌 위험 없음 (기존 레코드와 독립)

- admin, office: 미등록이므로 신규 A 레코드 추가 가능
- docs: 이미 등록됨 → 기존 서비스 확인 후 수정 여부 결정

### MX/TXT 충돌 주의

- @에 이미 MX, SPF, google-site-verification TXT 존재
- @에 TXT 추가 시 기존 SPF/DMARC와 중복 방지 필요
- _dmarc는 별도 호스트로 단독 존재 (충돌 없음)

### root/www 변경 금지

- @, www는 현재 서비스 운영 중 → APPROVAL_REQUIRED + USER_DIRECT_REQUIRED

---

## 8. DNS 변경 정책

| 작업 | 정책 | 비고 |
|------|------|------|
| DNS 레코드 조회 | READ_ONLY_ALLOWED | 항상 가능 |
| 신규 서브도메인 초안 생성 | DRAFT_ALLOWED | domain_assist.build_dns_default_draft 사용 |
| 신규 A/CNAME 추가 실행 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 가비아 DNS 관리 화면에서 직접 |
| 기존 A/CNAME 수정 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 서비스 영향 사전 확인 필수 |
| A/CNAME 삭제 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 비가역, 승인 필수 |
| root(@) 변경 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 전체 서비스 영향 |
| www 변경 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 전체 서비스 영향 |
| MX 변경 | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | 메일 장애 위험 |
| TXT 추가 (인증 등) | APPROVAL_REQUIRED + USER_DIRECT_REQUIRED | SPF 중복 주의 |
| NS 변경 | BLOCKED (별도 특별 승인) | 전체 DNS 영향 |
| login/session/cookie | BLOCKED | 자동화 금지 |
| 결제/연장/이전 | USER_DIRECT_REQUIRED | 자동화 금지 |

---

## 9. 다음 개발 단계 제안

### SITE_ENGINE_PHASE_G_GABIA_SUBDOMAIN_DNS_ASSIST_01 진행 가능 여부: **YES**

현재 상태에서 안전하게 진행 가능한 작업:

1. **신규 서브도메인 초안 생성 기능** (DRAFT_ALLOWED)
   - admin, office 등 미등록 서브도메인 A 레코드 초안 생성
   - `domain_assist.build_dns_default_draft()` 확장

2. **충돌 감지 로직** (READ_ONLY)
   - 기존 레코드와 신규 후보 간 충돌 여부 자동 분석

3. **서브도메인 gate 판단**
   - 신규: DRAFT_ALLOWED → APPROVAL_REQUIRED
   - 기존 수정: APPROVAL_REQUIRED + 서비스 영향 경고

4. **수정 전 확인 필요 사항**
   - docs, support, career, blog, status, esc, cloud, gongmu 실제 서비스 사용 여부
   - nginx 라우팅 설정에서 각 서브도메인 → 서비스 매핑 확인

---

## 10. 안전 확인

| 항목 | 결과 |
|------|------|
| Gabia 로그인 시도 | 없음 |
| 실제 DNS 변경 | 없음 |
| session/cookie 내용 열람 | 없음 (존재 여부만 확인) |
| 코드 수정 | 없음 |
| DB/schema 변경 | 없음 |
| 서버 재시작/배포 | 없음 |
| 삭제 파일 | 없음 |
| 권한 변경 | 없음 |

---

## 11. 최종 판정

**PASS** — read-only 감사 완료. 기준선 고정. DNS 현황 완전 파악.
