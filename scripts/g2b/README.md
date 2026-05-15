# G2B 세대 (나라장터/조달청)

## 목적

나라장터(G2B) 공개 공고 탐색, 첨부파일 다운로드, 입찰분석 초안 생성 등
Read-Only / Draft 범위 내 업무 자동화를 지원한다.

로그인, 투찰, 전자서명, 최종 제출은 자동화 범위 밖이다.

## 세대 구조

```
scripts/g2b/
├── profile.py        G2B 사이트 프로필 및 action 분류
├── gates.py          실행 판단 게이트 (BLOCKED / USER_DIRECT / LOCAL_AGENT 등)
├── validators.py     페이로드 검증기
├── router.py         command dispatch
├── discover_valid_public_notice_urls.py   공개 공고 URL 탐색
├── download_g2b_direct_attachment_urls.py 첨부파일 배치 다운로드
└── run_public_notice_readonly_live_suite.py Read-Only 라이브 스위트
```

## 허용 작업

| action | 결정 |
|--------|------|
| search_notice | READ_ONLY_ALLOWED |
| read_notice_detail | READ_ONLY_ALLOWED |
| inspect_attachment | READ_ONLY_ALLOWED |
| collect_openapi_notice | READ_ONLY_ALLOWED |
| download_public_attachment | LOCAL_AGENT_REQUIRED |
| create_bid_analysis_draft | DRAFT_ALLOWED |
| create_submit_draft | DRAFT_ALLOWED |

## 금지 작업

| action | 결정 |
|--------|------|
| submit_bid | BLOCKED |
| e_sign | BLOCKED |
| final_send | BLOCKED |
| payment_or_fee_related_action | BLOCKED |
| extract_password/session/cookie/token | BLOCKED |
| server_side_login_browser | BLOCKED |

## Local Agent 필요 작업

- login: Local Agent PC에서만 실행 가능

## 사용자 직접 수행 필요 작업

- certificate_auth: 공동인증서 인증
- otp: OTP 입력

## OpenAPI Collector 분리 원칙

`collect_openapi_notice` action은 READ_ONLY_ALLOWED이나,
OpenAPI collector 구현 자체는 별도 경계를 유지한다.
G2B router에서 OpenAPI collector를 직접 구현하지 않는다.

## 투찰/전자서명 자동화 금지

투찰(submit_bid), 전자서명(e_sign), 최종 전송(final_send)은
시스템 자동화 대상이 아니다. 사용자가 직접 수행해야 한다.

## Evidence/Report Warehouse

- 공개 공고 캐시: `data/g2b/public_notices/`
- 첨부파일 저장소: `data/g2b/attachments/`
- 입찰분석 초안: `data/g2b/bid_analysis/`
- 제출 초안: `data/g2b/submit_drafts/`
- 감사 로그: `data/g2b/audit/`
- 보고서: `docs/reports/g2b_*.md`
