# G2B 도메인 정규화 정책 설계

작성일: 2026-05-07  
태스크: G2B_DOMAIN_NORMALIZATION_POLICY_1

---

## 1. 목적

나라장터(G2B) 공개 read-only 업무에서 apex domain(`g2b.go.kr`)과 www prefix domain(`www.g2b.go.kr`)을
동일하게 정규화하여 allowlist 불일치 문제를 해결하고,
로그인/입찰/투찰/제출/계약/결제/인증서 경로는 계속 차단한다.

---

## 2. 허용 도메인 후보

| 도메인 | 분류 | 정규화 대상 | 근거 |
|---|---|---|---|
| g2b.go.kr | G2B_PUBLIC_READONLY | apex (정규화 기준) | 기존 allowlist |
| www.g2b.go.kr | G2B_PUBLIC_READONLY | www → g2b.go.kr로 정규화 | www prefix 표준 처리 |

---

## 3. 조건부 후보 (검증 필요)

| 도메인 | 분류 | 조건 |
|---|---|---|
| shop.g2b.go.kr | READONLY_CANDIDATE | 공개 read-only 확인 후에만 허용 |
| 기타 *.g2b.go.kr | NEEDS_URL_VERIFICATION | 명시적 허용 전까지 차단 |

> **wildcard 허용 절대 금지**: `*.g2b.go.kr` 전체 허용 없음.

---

## 4. apex/www 정규화 정책

```
normalize_g2b_domain(domain):
  www.g2b.go.kr → normalized_domain = g2b.go.kr
  g2b.go.kr     → normalized_domain = g2b.go.kr (그대로)
  shop.g2b.go.kr → NEEDS_URL_VERIFICATION
  기타 서브도메인  → NEEDS_URL_VERIFICATION
  비 G2B 도메인   → NOT_G2B
```

---

## 5. 공개 read-only 경로 정책

허용 operation: `read`, `navigate`, `open_url`

허용 경로 패턴 (접두사 기반):
- 입찰공고 검색/목록: `/pt/menu/ntn01/pta02/ptb02001l.do`
- 입찰공고 상세: `/pt/menu/ntn01/pta02/ptb02001m.do`
- 업체정보 공개조회: `/pt/menu/ntn01/pta02/ptb03001l.do`
- 낙찰결과 조회: `/pt/menu/ntn01/pta02/ptb04001l.do`
- 그 외 `/pt/menu/ntn01/` 하위 공개 경로

---

## 6. 첨부파일 수동 다운로드 정책

- 첨부파일 **목록 조회** (`read` operation): `READ_ONLY_ALLOWED`
- 첨부파일 **직접 다운로드** (`download` operation): `DOWNLOAD_MANUAL_ONLY`
- `download_auto_allowed = False` 항상

---

## 7. 서버 Playwright / Local Agent / API 라우팅 정책

| 조건 | 실행 위치 | 근거 |
|---|---|---|
| g2b_public_readonly + read/navigate | SERVER_BROWSER | server_browser_boundary_policy |
| g2b_login + submit | LOCAL_AGENT | 로그인 로컬 전용 |
| requires_certificate=True | USER_PRESENT_ONLY | 인증서 서버 금지 |
| download operation | SERVER_BROWSER (파일목록만) | download_auto_allowed=False |

---

## 8. 금지 경로

| 경로 패턴 | 금지 이유 |
|---|---|
| `/co/menu/EgovUserReqstLogin` | 로그인 |
| `/co/menu/` + login | 로그인 관련 |
| `/cert`, `/certificate` | 인증서 |
| `/sign`, `/esign` | 전자서명 |
| `/bid/`, `/bidding/` | 입찰 |
| `/submit`, `/apply` | 제출/신청 |
| `/pay`, `/payment` | 결제 |
| `/contract` | 계약 |
| `/auction` | 경매 |

| operation | 금지 이유 |
|---|---|
| `submit` | 제출 자동화 금지 |
| `type` | 입력 자동화 금지 |
| `fill` | 입력 자동화 금지 |
| `click_submit` | 제출 자동화 금지 |
| `download` | 자동 다운로드 금지 |

---

## 9. 관련 모듈 보강 내역

| 파일 | 보강 내용 |
|---|---|
| `g2b_domain_policy.py` (신규) | 도메인 정규화 + 경로 분류 + URL 분류 |
| `site_compliance_policy.py` | ALLOWLIST_SAFE_SITES에 `www.g2b.go.kr` 추가 |
| `allowlist_preflight.py` | COMMON_ALLOWED_DOMAINS에 `www.g2b.go.kr` 추가 |
