# 사이트 자동화 가능성 매트릭스 (F-4S-1)

> **상태**: 설계/조사 문서 (코드 변경 없음)
> **선행**: F-4G-3X (홈택스 전략), F-4G-3Y-a/b/c (로컬 에이전트 큐 + observe + 알림), TAX-API-1L (live API 검증 PASS)
> **의도**: 홈택스만 따로 보지 말고, 앞으로 자동화 대상이 될 주요 사이트를 **같은 기준**으로 분류한다. 공식 API 우선, OAuth/API 가능 작업 우선, 브라우저 자동화는 폴백.
> **이번 단계의 산출물**: 본 매트릭스 문서 1개. 코드 수정 없음, 실제 로그인/접속 없음.

---

## 1. 결론 요약

### 1.1 한 줄 결론

자동화 대상 사이트는 **단일 패턴(브라우저 자동화)으로 묶지 않는다.** 사이트별로 (a) 공식 API, (b) OAuth API, (c) 로컬 에이전트 read-only observe, (d) 승인형 click action, (e) 보류/금지 — 5개의 경로 중 하나로 분류해 처리한다.

### 1.2 우선순위 한 눈에

- **API 즉시 가능**: Naver Search OpenAPI, NTS 사업자등록 API (이미 연동), 공공데이터(data.go.kr) API
- **API 신규 PoC 1순위**: YouTube Data API (read-only)
- **OAuth 설계 필요**: Google Drive, YouTube Studio/Analytics, Naver Cafe write
- **로컬 에이전트 observe 폴백**: Hometax (이미 F-4G), G2B 화면 의존 부분
- **승인형 click action**: Naver Cafe 가입/글쓰기 같은 write 조작 (대표님 명시 승인 필수)
- **보류/금지**: Instagram/Facebook/TikTok/Kakao/Coupang/Smartstore 의 일반 사용자측 write — 약관/스팸 정책 충돌

### 1.3 본 단계가 만드는 것 / 만들지 않는 것

만드는 것:
- 사이트별 분류표 (4장)
- 다음 구현 단계 5개 (10장)

만들지 않는 것:
- 코드 변경 0
- 실제 사이트 접속 0
- 실제 로그인/댓글/가입/업로드 0
- API 키/secret 원문 기록 0

---

## 2. 공통 원칙

본 매트릭스가 모든 사이트에 적용하는 단일 정책:

1. **공식 API > OAuth > observe > click > 보류** 의 순서로 시도한다.
2. **AI 가 ID/PW/인증서 비밀번호/OTP/간편인증 값을 입력하거나 저장하지 않는다.**
3. **쿠키 / session / storage_state / localStorage / sessionStorage 를 읽거나 내보내지 않는다.**
4. API 키 / OAuth secret 은 `.env` 또는 환경변수에서만 읽고, 평문 로그/문서/응답에 노출하지 않는다.
5. **write action (가입/댓글/업로드/구매/팔로우 등)** 은 명시적 사용자 승인 토큰 없이는 실행되지 않는다.
6. 캡차/약관/봇 차단을 우회하지 않는다.
7. 한 사이트에 여러 경로가 동시에 가능할 때는 **가장 안전한 경로** 를 채택한다.

---

## 3. 위험도 분류

| 등급      | 의미                                                                                             | 예                                          |
| --------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| `low`     | 공식 API + 비로그인/API 키 + read-only.                                                          | NTS 사업자 상태조회, Naver 검색 (read)      |
| `medium`  | 공식 API + OAuth 또는 사용자 1회 승인 후 read 중심.                                              | Google Drive read, YouTube Analytics read   |
| `high`    | 공식 API write 또는 visible browser + 사용자 본인 인증 직접 수행 + AI 인증값 미접촉.             | Hometax observe, Naver Cafe write (OAuth)   |
| `blocked` | 약관/봇 정책/대량 자동화 금지/세션 우회 위험. 본 시스템에서는 진행하지 않는다.                  | 일반 SNS 의 비OAuth 자동 댓글/팔로우/스팸성 작업 |

---

## 4. 사이트별 매트릭스

표가 길어서 핵심 필드만 inline 으로 표기한다. **이번 단계에서 “구현”** 이 아니라 “분류” 만 한다.

### 4.1 Hometax (홈택스)

- **site_key**: `hometax`
- **service_name**: 국세청 홈택스
- **target_tasks**: 매출/매입 (전자)세금계산서 메뉴, 현금영수증, 사업자 상태조회, 납세증명/소득증명 등
- **official_api_available**: `partial` (자료 일부는 공공데이터 API, 대부분은 화면)
- **api_type**: `public_api` (사업자 상태조회/진위확인) + `browser_only` (그 외 화면)
- **auth_type**: `api_key` (API), `certificate`/`simple_auth`/`user_login` (브라우저)
- **read_only_possible**: 화면 read-only observe 는 이미 F-4G-3Y-b 에 핸들러 등록됨
- **write_action_possible**: ❌ 본 시스템에서는 신고/납부/발행 등 어떤 write 도 자동화하지 않는다 (`sensitive_submission` 분류)
- **browser_observe_needed**: ✅ (사업자 상태/진위확인 외 자료 모두)
- **approval_required**: 사용자가 직접 인증 (인증서/간편인증)
- **risk_level**: `high` (브라우저 경로) / `low` (공공데이터 API 경로)
- **recommended_path**:
  - 사업자 상태/진위확인 → `api_first` (이미 TAX-API-1 PoC 완료)
  - 그 외 → `local_agent_observe` (F-4G-3Y 시리즈)
- **required_secrets**: `NTS_BUSINESS_API_SERVICE_KEY` 또는 `PUBLICDATA_SERVICE_KEY`
- **user_involvement**: 브라우저 경로에서는 매 세션 인증을 사용자가 직접
- **automation_boundary**: 화면 자동 클릭/입력/다운로드 금지. read-only observe + controlled plan 만.
- **notes**: F-4G-3X 전략 문서가 분리 정의. 현재 진행 단계는 F-4G-3Y-c 까지.

### 4.2 Naver Search (네이버 통합 검색)

- **site_key**: `naver_search`
- **service_name**: Naver Search OpenAPI (블로그/뉴스/쇼핑/웹문서/카페글/책/지식iN/이미지 등)
- **target_tasks**: 키워드 검색, 시계열 모니터링, 신규 게시물 알림
- **official_api_available**: `yes` (Naver Open API)
- **api_type**: `public_api`
- **auth_type**: `api_key` (Client ID + Client Secret)
- **read_only_possible**: ✅
- **write_action_possible**: ❌ 본 API 에는 write 가 없음
- **browser_observe_needed**: ❌ (필요 없음)
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first`
- **required_secrets**: `NAVER_OPENAPI_CLIENT_ID`, `NAVER_OPENAPI_CLIENT_SECRET` (`naver_openapi_config.py` 가 이미 처리)
- **user_involvement**: 없음
- **automation_boundary**: rate limit / 일일 호출 한도 준수, query 캐시 권장
- **notes**: `ai_orchestrator/connectors/naver_search_*` 자산이 이미 풍부 (`naver_search_client`, `naver_search_runner`, `naver_search_db`, `naver_blog_collectors`, `naver_shopping_collectors`).

### 4.3 Naver Blog (수집)

- **site_key**: `naver_blog`
- **service_name**: Naver 블로그 검색/수집
- **target_tasks**: 블로그 검색 + 본문 미리보기 메타데이터 (공개 글 한정)
- **official_api_available**: `yes` (Naver Search OpenAPI 의 블로그 카테고리)
- **api_type**: `public_api`
- **auth_type**: `api_key`
- **read_only_possible**: ✅
- **write_action_possible**: ❌
- **browser_observe_needed**: 필요 시 read-only `naver_public_page_reader` 활용 가능 (스크래핑 정책 준수)
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first` (검색)
- **required_secrets**: Naver Open API 키
- **user_involvement**: 없음
- **automation_boundary**: 본문 전체 텍스트 무제한 저장은 피하고, 발췌(메타) 위주
- **notes**: `naver_blog_collectors.py` 이미 존재.

### 4.4 Naver Cafe Search (공개 카페 글)

- **site_key**: `naver_cafe_search`
- **service_name**: Naver 카페글 검색 (공개)
- **target_tasks**: 공개 카페 게시물 검색
- **official_api_available**: `yes` (Naver Search OpenAPI 의 카페글)
- **api_type**: `public_api`
- **auth_type**: `api_key`
- **read_only_possible**: ✅ (공개 글 한정)
- **write_action_possible**: ❌
- **browser_observe_needed**: ❌ (대부분의 케이스에서 불필요)
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first`
- **required_secrets**: Naver Open API 키
- **user_involvement**: 없음
- **automation_boundary**: 비공개 카페 내부 글은 본 경로에서 다루지 않는다 (별도 권한/카페 운영자 동의 필요)
- **notes**: `ai_orchestrator/sites/adapters/naver_cafe_adapter.py`, `naver_cafe_collection.py` 자산.

### 4.5 Naver Cafe Join / Write (가입·글쓰기·댓글)

- **site_key**: `naver_cafe_join_write`
- **service_name**: Naver 카페 가입/글쓰기/댓글 (write)
- **target_tasks**: 카페 가입, 글쓰기, 댓글, 댓글 수정/삭제
- **official_api_available**: `partial` (Naver 의 Cafe API 는 가입/글쓰기 일부에 OAuth 기반 권한이 필요하며, **시점에 따라 정책/제공 범위가 달라지므로 채택 시 공식 안내 재확인** 필요)
- **api_type**: `oauth_api` (가능 범위), `browser_only` (그 외)
- **auth_type**: `oauth` (Naver 로그인 OAuth, 사용자 동의 필수)
- **read_only_possible**: 가입 여부 등 일부
- **write_action_possible**: ✅ — 단, **본 시스템에서는 대량 가입/반복 댓글/스팸성 작업 금지**. 1건씩 명시 승인.
- **browser_observe_needed**: 가능. 폴백.
- **approval_required**: ✅ (write 마다 별도 승인 토큰)
- **risk_level**: `high` (write), `medium` (read-only)
- **recommended_path**: `oauth_first` + `approval_click` (write 마다)
- **required_secrets**: Naver OAuth Client ID/Secret + 사용자 access_token (사용자 동의 후 발급)
- **user_involvement**: OAuth 동의 1회 + write 시점마다 승인
- **automation_boundary**: 대량/반복 자동화 금지. 캡차/봇 차단 우회 금지.
- **notes**: 본 사이트는 본 매트릭스의 “write 가 가능하지만 매우 보수적” 표본. F-4G-3Y 의 사용자 알림/승인 패턴을 그대로 흡수.

### 4.6 YouTube Search (영상/채널 검색)

- **site_key**: `youtube_search`
- **service_name**: YouTube Data API v3 (search/videos/channels)
- **target_tasks**: 키워드 영상 검색, 영상/채널 메타데이터, 댓글 목록 read
- **official_api_available**: `yes`
- **api_type**: `public_api` (대부분 read 는 API 키만 필요), `oauth_api` (일부 — 본인 채널 분석 등)
- **auth_type**: `api_key` (read), `oauth` (본인 채널 영역)
- **read_only_possible**: ✅
- **write_action_possible**: ❌ (read 한정)
- **browser_observe_needed**: ❌
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first`
- **required_secrets**: `YOUTUBE_API_KEY` (env 권장)
- **user_involvement**: 없음
- **automation_boundary**: 일일 quota 준수. 캡션/transcript 는 `videos.list`/`captions` API 범위 안에서만.
- **notes**: 자막 무단 스크래핑은 위험 분류. 공식 captions API 또는 영상 본문에 자막이 공개된 경우만.

### 4.7 YouTube Studio / Analytics (채널 소유자 영역)

- **site_key**: `youtube_studio`, `youtube_analytics`
- **service_name**: YouTube Analytics & Reporting API + Data API (mine=true)
- **target_tasks**: 채널 분석, 영상 KPI, 업로드/제목·설명 수정/공개범위 변경
- **official_api_available**: `yes`
- **api_type**: `oauth_api`
- **auth_type**: `oauth` (Google OAuth 2.0 — 채널 소유자 동의)
- **read_only_possible**: ✅ Analytics read 가능
- **write_action_possible**: ✅ — 단 본 시스템에서는 **명시 승인형**
- **browser_observe_needed**: Studio UI 브라우저는 **폴백** (가능하면 API)
- **approval_required**: ✅ (write 시 매번)
- **risk_level**: `medium` (read), `high` (write)
- **recommended_path**: `oauth_first` (read), `approval_click` (write)
- **required_secrets**: Google OAuth client + refresh_token
- **user_involvement**: OAuth 동의 1회 + write 시점마다 승인
- **automation_boundary**: 영상 삭제, 수익화 변경 등 비가역 동작은 금지 또는 최상위 승인.
- **notes**: 자산 없음 (신규).

### 4.8 Google Search

- **site_key**: `google_search`
- **service_name**: Google
- **target_tasks**: 키워드 검색
- **official_api_available**: `partial` (Custom Search JSON API 는 별도 등록/CSE 필요. 일반 google.com 스크래핑은 봇 차단 + 약관 충돌)
- **api_type**: `public_api` (CSE), `blocked` (raw scraping)
- **auth_type**: `api_key` (CSE)
- **read_only_possible**: ✅ (CSE 한정)
- **write_action_possible**: ❌
- **browser_observe_needed**: ❌ — google.com 의 일반 검색 자동화는 본 시스템에서 진행하지 않는다 (open-only 정책 + 약관)
- **approval_required**: ❌
- **risk_level**: `low` (CSE), `blocked` (raw)
- **recommended_path**: `api_first` (CSE), 그 외 `blocked`
- **required_secrets**: `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` (사용 시)
- **user_involvement**: 없음
- **automation_boundary**: google.com 의 일반 검색 결과 페이지 자동화 금지 (`browser_launcher.is_google_open_only_url` 정책과 정합)
- **notes**: 본 시스템 정책상 google open-only 흐름이 이미 강제되어 있음.

### 4.9 Google Drive

- **site_key**: `google_drive`
- **service_name**: Google Drive
- **target_tasks**: 파일 메타데이터 조회, 다운로드(소유자 권한), 공유 폴더 읽기
- **official_api_available**: `yes`
- **api_type**: `oauth_api`
- **auth_type**: `oauth` (Google OAuth)
- **read_only_possible**: ✅ (drive.readonly 스코프)
- **write_action_possible**: ✅ — 본 시스템에서는 명시 승인형
- **browser_observe_needed**: ❌
- **approval_required**: ✅ (write)
- **risk_level**: `medium` (read), `high` (write)
- **recommended_path**: `oauth_first`
- **required_secrets**: Google OAuth client + refresh_token
- **user_involvement**: OAuth 동의 1회
- **automation_boundary**: 파일 삭제/이동/공유 변경은 명시 승인.
- **notes**: `ai_orchestrator/sites/adapters/google_dev_reg.py` 가 OAuth dev_reg 일부 흐름을 보유 (개발자 등록 어댑터).

### 4.10 G2B (조달청 나라장터)

- **site_key**: `g2b`
- **service_name**: 조달청 나라장터 OpenAPI (입찰공고/낙찰/계약)
- **target_tasks**: 입찰공고 검색, 입찰결과 수집, 거래처 검증과 결합한 리스크 점검
- **official_api_available**: `yes` (data.go.kr 공공데이터 카탈로그)
- **api_type**: `public_api`
- **auth_type**: `api_key` (공공데이터 service_key)
- **read_only_possible**: ✅
- **write_action_possible**: ❌ (조달 입찰 자체는 본 시스템 범위 밖)
- **browser_observe_needed**: 폴백 (API 가 안 되는 일부 화면)
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first`
- **required_secrets**: `PUBLICDATA_SERVICE_KEY` (NTS 와 공유 가능)
- **user_involvement**: 없음
- **automation_boundary**: 파라미터 (검색기간/지역코드 등) 는 문서 기준 고정. 자유 형식 자연어 → 파라미터 변환 단계가 명확해야 함.
- **notes**: 신규.

### 4.11 data.go.kr (공공데이터포털 일반)

- **site_key**: `data_go_kr`
- **service_name**: 공공데이터포털 (각종 부처/공공기관 API)
- **target_tasks**: 사업자 상태/진위확인 (NTS), 기상/지리/조달 등 다양
- **official_api_available**: `yes`
- **api_type**: `public_api`
- **auth_type**: `api_key`
- **read_only_possible**: ✅
- **write_action_possible**: ❌
- **browser_observe_needed**: ❌
- **approval_required**: ❌
- **risk_level**: `low`
- **recommended_path**: `api_first`
- **required_secrets**: `PUBLICDATA_SERVICE_KEY` (또는 사용처별 전용 키)
- **user_involvement**: 없음
- **automation_boundary**: 활용 신청/일일 한도 준수.
- **notes**: NTS Business API (TAX-API-1) 가 본 카탈로그의 첫 PoC.

### 4.12 Kakao (Talk/Login/Map/etc)

- **site_key**: `kakao`
- **service_name**: Kakao Developers
- **target_tasks**: 카카오 로그인 (사용자 식별), 알림톡/메시지 (비즈니스 채널 한정)
- **official_api_available**: `partial` (서비스별 상이 — 일부는 비즈니스 계약 필수)
- **api_type**: `oauth_api` (로그인), `private_none` (개인 메시지 자동화는 정책상 차단)
- **auth_type**: `oauth`, 일부 `api_key`
- **read_only_possible**: 사용자 정보 일부
- **write_action_possible**: 알림톡 등 비즈니스 채널 한정
- **browser_observe_needed**: ❌
- **approval_required**: ✅ (write)
- **risk_level**: `medium`~`blocked` (개인 메시지/친구목록 수집은 금지)
- **recommended_path**: `research` 후 `oauth_first`
- **required_secrets**: Kakao REST API 키 등
- **user_involvement**: OAuth 동의
- **automation_boundary**: 개인 KakaoTalk 메시지/친구목록 자동화는 본 시스템에서 진행하지 않는다.
- **notes**: 본 단계에서 구현 대상 아님.

### 4.13 Instagram

- **site_key**: `instagram`
- **service_name**: Instagram Graph API (Business/Creator 계정만)
- **target_tasks**: 본인 계정 게시물 조회/통계 (비즈니스 계정 한정)
- **official_api_available**: `partial` (Business/Creator 계정 + Facebook Graph 연동 필수)
- **api_type**: `oauth_api`
- **auth_type**: `oauth` (Facebook 로그인 + 비즈니스 계정 권한)
- **read_only_possible**: ✅ (본인 비즈니스 계정 한정)
- **write_action_possible**: 게시 가능하나 매우 제한
- **browser_observe_needed**: ❌
- **approval_required**: ✅
- **risk_level**: `high`~`blocked` (개인 계정/타인 데이터/팔로우 자동화는 금지)
- **recommended_path**: `oauth_first` (본인 비즈니스 계정 한정), 그 외 `blocked`
- **required_secrets**: Facebook App + page access token
- **user_involvement**: OAuth + 비즈니스 계정 연결
- **automation_boundary**: 개인 계정 / 타인 게시물 / 팔로우 자동화 금지.
- **notes**: 본 단계 구현 대상 아님.

### 4.14 Facebook

- **site_key**: `facebook`
- **service_name**: Facebook Graph API
- **target_tasks**: 페이지 게시물 조회/게시 (소유 페이지 한정)
- **official_api_available**: `yes` (페이지 한정)
- **api_type**: `oauth_api`
- **auth_type**: `oauth`
- **read_only_possible**: ✅ (소유 페이지)
- **write_action_possible**: 게시 가능 (승인형)
- **browser_observe_needed**: ❌
- **approval_required**: ✅
- **risk_level**: `high`~`blocked` (개인 친구목록/타인 게시물 금지)
- **recommended_path**: `oauth_first` (소유 페이지), 그 외 `blocked`
- **required_secrets**: Facebook App + page access token
- **user_involvement**: OAuth + 페이지 권한
- **automation_boundary**: 개인 친구/그룹 자동화 금지.
- **notes**: 본 단계 구현 대상 아님.

### 4.15 TikTok

- **site_key**: `tiktok`
- **service_name**: TikTok for Developers / TikTok Business API
- **target_tasks**: 본인 계정 영상/통계 조회 (비즈니스), 광고 API
- **official_api_available**: `partial` (대부분 비즈니스 계약 필수)
- **api_type**: `oauth_api`
- **auth_type**: `oauth`
- **read_only_possible**: ✅ (본인 계정/광고 한정)
- **write_action_possible**: 광고 게시 등 (별도 계약)
- **browser_observe_needed**: ❌
- **approval_required**: ✅
- **risk_level**: `high`~`blocked`
- **recommended_path**: `research` 후 `oauth_first`
- **required_secrets**: TikTok App 키
- **user_involvement**: OAuth
- **automation_boundary**: 일반 영상 좋아요/팔로우/댓글 자동화 금지.
- **notes**: 본 단계 구현 대상 아님.

### 4.16 Coupang (셀러/소비자)

- **site_key**: `coupang`
- **service_name**: Coupang Wing (셀러), Coupang 일반 (소비자)
- **target_tasks**: 셀러 — 주문/상품/정산 조회 (Wing API). 소비자 — 일반 검색은 차단/약관 충돌.
- **official_api_available**: `partial` (Wing 셀러 API 만)
- **api_type**: `oauth_api` (Wing) / `blocked` (소비자 측)
- **auth_type**: `api_key` (Wing 인증)
- **read_only_possible**: ✅ (Wing)
- **write_action_possible**: ✅ (상품 등록/주문 처리 등 — 명시 승인형)
- **browser_observe_needed**: ❌ (Wing 대신 API)
- **approval_required**: ✅
- **risk_level**: `medium` (Wing), `blocked` (소비자 측 자동 검색/구매/리뷰)
- **recommended_path**: `oauth_first` (Wing), 그 외 `blocked`
- **required_secrets**: Wing access_key/secret_key
- **user_involvement**: 셀러 계정 인증
- **automation_boundary**: 자동 구매/리뷰/장바구니 작업 금지.
- **notes**: 본 단계 구현 대상 아님.

### 4.17 Smartstore (네이버 스마트스토어)

- **site_key**: `smartstore`
- **service_name**: Naver 커머스 API (네이버 커머스 스마트스토어 셀러)
- **target_tasks**: 셀러 — 주문/상품/정산
- **official_api_available**: `yes` (셀러 한정)
- **api_type**: `oauth_api`
- **auth_type**: `api_key` + 사업자 인증
- **read_only_possible**: ✅
- **write_action_possible**: ✅ (상품 등록/주문 처리 — 명시 승인형)
- **browser_observe_needed**: ❌
- **approval_required**: ✅
- **risk_level**: `medium`~`high`
- **recommended_path**: `oauth_first`
- **required_secrets**: Naver 커머스 API 키
- **user_involvement**: 셀러 인증
- **automation_boundary**: 일반 소비자 자동 구매/리뷰 금지.
- **notes**: 본 단계 구현 대상 아님.

---

## 5. API 우선 대상 (api_first)

다음 사이트는 공식 API 또는 공공데이터 API 가 “지금 즉시 가능” 또는 “단순 PoC 로 가능”:

- **Naver Search** (이미 자산 풍부, `naver_search_*`)
- **Naver Blog 검색** (`naver_blog_collectors`)
- **Naver Cafe 검색** (공개 글, `naver_cafe_*`)
- **Naver Shopping** (이미 collector 존재)
- **NTS 사업자등록 API** (TAX-API-1, live 검증 PASS)
- **공공데이터 일반** (`PUBLICDATA_SERVICE_KEY` 공유)
- **G2B** (data.go.kr 카탈로그 안)
- **YouTube Search** (read-only — 신규 PoC 1순위 후보)
- **Google Custom Search** (CSE 키 등록 필요)

---

## 6. OAuth 우선 대상 (oauth_first)

권한 동의가 필요하지만 합법/안정적으로 read 또는 제한된 write 가 가능:

- **Google Drive** (drive.readonly / drive.file 스코프)
- **YouTube Studio / Analytics** (채널 소유자 본인)
- **Naver Cafe write** (가입/글쓰기 — 매 작업 승인 필수)
- **Smartstore 셀러**, **Coupang Wing** (셀러 한정)
- **Facebook Graph (페이지)**, **Instagram Graph (Business)** — 비즈니스 계정에 한정
- **TikTok Business**, **Kakao 로그인/알림톡** — 비즈니스 계약/리뷰 통과 시

> 본 시스템의 OAuth 흐름은 dev_reg 어댑터 (`naver_dev_reg`, `google_dev_reg`, `hiworks_dev_reg`) 의 패턴을 그대로 확장한다.

---

## 7. 로컬 에이전트 observe 대상 (local_agent_observe)

API 가 없거나 화면 의존이 큰 자료에 한정. visible browser + 사용자 본인 인증 + read-only:

- **Hometax** (이미 F-4G-3Y-c 까지 진행 — 실제 무실행 체인 e2e 는 F-4G-3Y-d 대기)
- **G2B 의 화면 의존 부분** (API 가 커버하지 않는 일부 — 폴백)

---

## 8. 승인형 action 대상 (approval_click)

write 가 가능하지만 매 건마다 사용자 승인이 있어야 실행:

- **Naver Cafe write** (가입 1회/글쓰기 1건/댓글 1건마다)
- **YouTube Studio write** (영상 메타 수정/공개범위 변경 — 영상 삭제는 비가역, 최상위 승인)
- **Google Drive write** (파일 삭제/이동/공유 변경)
- **Facebook 페이지 게시**, **Instagram 비즈니스 게시** — 게시물 1건마다
- **Smartstore 셀러 write**, **Coupang Wing write** — 상품 등록/주문 처리 1건마다

본 카테고리는 본 매트릭스에서 **구현 대상이 아니다**. 후속 단계 별도 설계.

---

## 9. 보류 / 금지 대상

본 시스템에서 **진행하지 않는** 작업:

- 일반 SNS 의 비OAuth 자동 댓글/팔로우/좋아요/DM (Instagram/Facebook/TikTok 의 사용자측 자동화)
- KakaoTalk 개인 메시지/친구목록 수집/자동화
- Coupang 일반 사용자 자동 구매/리뷰/장바구니 조작
- Smartstore 일반 사용자 자동 구매/리뷰
- google.com 의 일반 검색 결과 페이지 스크래핑 (`browser_launcher.is_google_open_only_url` 정책 적용)
- 캡차/봇 차단 우회, 세션 토큰/쿠키 추출, 다계정 활용 회피
- 대량 가입/반복 댓글/스팸성 작업

---

## 10. 다음 구현 순서

본 매트릭스 이후의 권장 단계. 각 단계는 **별도 PoC + 테스트 + 커밋** 단위.

### 10.1 1순위 — Naver Search API live PoC (F-4S-2)

- **대상**: 블로그 / 뉴스 / 카페글 / 쇼핑 / 웹문서 / 책 / 지식iN / 이미지 (Naver Open API 카테고리)
- **인증**: 비로그인. `NAVER_OPENAPI_CLIENT_ID` + `NAVER_OPENAPI_CLIENT_SECRET` (env)
- **자산**: `ai_orchestrator/connectors/naver_search_*` 가 이미 존재 → **live 컨트랙트 점검** + 누락 카테고리 채우기 + 결과 캐시/시계열 시그널 정리.
- **NTS PoC 와 동일 패턴**: 키 redacted, dry-run 우선, `--live` 시 키 없음 → WARN.
- **금지**: 키 원문 출력 금지, 응답 캐시에 키 echo 금지.

### 10.2 2순위 — YouTube Data API read-only PoC (F-4S-3)

- **대상**: 영상 검색, 영상/채널 메타데이터, 댓글 목록 read
- **인증**: API 키 (`YOUTUBE_API_KEY`) — OAuth 없이 가능한 범위만
- **검증**: `mode="live"` 응답 1건 이상 + URL 에 키 마스킹
- **확장**: 자막/transcript 는 별도 검토 (captions API 제약)

### 10.3 3순위 — Naver Cafe OAuth 설계 (F-4S-4)

- **대상**: 가입/글쓰기/댓글 (write — 승인형)
- **인증**: Naver OAuth (사용자 동의)
- **본 단계는 설계만**: 코드 구현 없음. write 마다 승인 토큰 발급 흐름 설계.
- **금지 명시**: 대량 가입 / 반복 댓글 / 스팸성 작업.

### 10.4 4순위 — YouTube Studio / Analytics OAuth 설계 (F-4S-5)

- **대상**: 채널 소유자 분석 데이터 (read), 영상 메타 수정 (write — 승인형)
- **인증**: Google OAuth (refresh_token)
- **본 단계는 설계만**: 영상 삭제/수익화 변경 같은 비가역 동작은 명시 차단.

### 10.5 5순위 — Local Agent Site Smoke Matrix (F-4S-6)

- **대상**: 본 매트릭스의 “API 가 안 되는” 사이트만 visible browser observe
- **흐름**: 사이트 1건씩, F-4G-3Y 의 manual_handoff observer 패턴 그대로 — `login_required` / `reachable` / `blocked` / candidates count 분류
- **출력**: 사이트별 verdict (PASS / WARN / FAIL) + plan 후보 수
- **현재로서는 Hometax 가 유일한 입력**. G2B 는 보류.

---

## 부록 A. 본 단계의 PASS / WARN / FAIL 자가 판정

### PASS
- [x] 사이트별 API / OAuth / observe / 승인형 / 금지 경계가 분리되었다.
- [x] 다음 구현 순서 5개가 명확하게 분리되었다.
- [x] 실제 사이트 접속 / 로그인 / write 0건.
- [x] 코드 변경 0.
- [x] secret/키 원문 기록 0.

### WARN
- [ ] **Naver Cafe 의 OAuth 가능 범위** 는 시점/정책에 따라 변할 수 있어 “채택 시 공식 안내 재확인” 으로 표기.
- [ ] **Kakao / Instagram / Facebook / TikTok** 비즈니스 API 의 구체 가능 범위는 후속 조사 필요 (본 매트릭스는 “보수적 분류” 만).
- [ ] **YouTube transcript / captions** 의 정확한 권한 범위는 PoC 시점에서 확인.
- [ ] **G2B** 는 data.go.kr 카탈로그의 어느 API 를 쓸지 PoC 시 결정.

### FAIL — 모두 회피됨
- [x] 실제 댓글/가입/업로드/구매 0건.
- [x] 인증값/secret 평문 기록 0.
- [x] 쿠키/session/storage 추출 방식 제안 0.
- [x] 봇/캡차 우회 제안 0.

본 문서의 자가 판정은 **PASS (with WARN)** 이다.
