# Google Domain Function Index

Updated: 2026-05-27

This document maps each registered Google/YouTube domain to its function,
purpose, and automation boundary. It is derived from
`data/google_domain_taxonomy_latest.json`,
`data/google_surface_catalog_latest.json`, and
`data/google_work_action_catalog_latest.json`.

## Global Policy

- Entry starts at `https://www.google.com/`.
- Login, MFA, account recovery, CAPTCHA, and credential entry are user-present.
- Read/search/status checks may run through the local browser profile after the
  Google Home and work-mode gates.
- Draft, create, upload, share, save, publish, release, key issue, billing,
  IAM, deploy, campaign, and monetization actions require explicit approval.
- Raw secrets, saved passwords, payment submission, destructive account
  permission changes, and unknown domains fail closed.

## Domain Groups

| Group | Purpose | Primary Boundary |
| --- | --- | --- |
| Search / Entry | Google Home and public entry flow | read-only navigation |
| Identity / Access | account state, security, SSO context | user-present login, no credential replay |
| Workspace / Productivity | Gmail, Drive, Calendar, Docs, Sheets, Slides, Forms, Meet, Chat, Contacts, Keep, Tasks | API preferred; drafts and writes require approval |
| Cloud / Backend | Cloud Console, APIs, credentials, IAM, billing, deploy, data services | read project context; writes/billing/IAM/deploy require approval |
| AI / Model Tools | AI Studio, Gemini, Vertex AI | read/use plans; API keys, deploy, paid use require approval |
| Android App Development | Android docs, Play Console, Firebase | docs read-only; release/configuration requires approval |
| Marketing / SEO / Analytics | Search Console, Business Profile, Analytics, Tag Manager, Ads, Merchant, AdSense, Looker Studio | read reports; publish/spend/configuration requires approval |
| YouTube / Creator | YouTube viewing and Studio channel operations | search/read/summarize; upload/publish/playlist/monetization require approval |
| Personal Media | Google Photos | metadata/read plans; download/share/upload/delete require approval/user-only |
| Developer Tools | Google Developers, Chrome Developers, Apps Script, Colab | docs read-only; scripts/notebooks/deploy require approval |

## Domain Map

| Domain | 기능 | 용도 | 허용되는 자동화 | 승인/차단 경계 |
| --- | --- | --- | --- | --- |
| `www.google.com` | Google Home, Search entry | Google 작업의 표준 진입점, 공개 검색, 앱 런처 확인 | 홈 진입, 공개 검색/관련 검색 조회, 계정 표시 상태 확인 | 로그인 직접 진입 금지; 상태 변경 없음 |
| `myaccount.google.com` | Google Account | 계정 상태, 보안 상태, 연결 앱 확인 | 비밀 없는 계정 상태/보안 요약, 연결 앱 목록 확인 | 권한 회수, 개인정보/보안 설정 변경, 비밀번호 확인은 사용자 직접 |
| `mail.google.com` | Gmail | 메일 목록, 검색, 본문 요약, 초안 작성 | 목록/검색/요약, 초안 입력 준비 | 최종 발송, 삭제, 설정 저장은 승인 또는 사용자 직접 |
| `drive.google.com` | Google Drive | 파일 목록, 검색, 파일 정보, 업로드/공유 계획 | 목록/검색/메타데이터 읽기, 업로드/공유 계획 작성 | 업로드 실행, 공유 권한 변경, 삭제, 다운로드는 승인 경계 |
| `calendar.google.com` | Google Calendar | 일정 조회, 검색, 일정 생성 준비 | 오늘 일정/검색/상세 읽기, 일정 초안 작성 | 일정 생성/수정/삭제 최종 실행은 승인 |
| `docs.google.com` | Docs, Sheets, Slides, Forms | 문서/시트/발표/폼 조회와 편집 준비 | 최근 문서 조회, 시트/문서 작업 계획, 폼/슬라이드 상태 조회 | 셀 수정, 문서 편집, 공유, 폼 발송/게시 최종 실행은 승인 |
| `meet.google.com` | Google Meet | 회의 생성/참가 준비 | 회의 계획 작성, 링크/상태 확인 | 회의 생성, 참가, 초대 발송은 승인 또는 사용자 직접 |
| `chat.google.com` | Google Chat | 스페이스/DM 조회, 메시지 초안 | 공간 목록, 메시지 초안 작성 | 메시지 최종 발송은 승인 |
| `contacts.google.com` | Google Contacts | 연락처 목록/생성 준비 | 연락처 목록 조회, 생성 계획 작성 | 연락처 생성/수정/삭제는 승인 |
| `keep.google.com` | Google Keep | 메모 목록/초안 | 메모 목록 조회, 노트 초안 작성 | 저장, 보관, 삭제, 라벨 변경은 승인 |
| `tasks.google.com` | Google Tasks | 할 일 목록/초안 | 할 일 목록 조회, 작업 초안 작성 | 작업 생성/수정/삭제 최종 실행은 승인 |
| `photos.google.com` | Google Photos | 사진/앨범 조회, 다운로드/공유/업로드 계획 | 사진/앨범 메타데이터, 승인용 다운로드/공유/업로드 계획 | 원본 다운로드, 공유, 업로드, 삭제, 얼굴/위치/EXIF 출력은 승인 또는 차단 |
| `www.youtube.com` | YouTube | 타인/본인 영상 검색, 자막 기반 요약 준비, 시청 관련 조회 | `google youtube search`로 공식 API 또는 공개 검색 DOM read-only 수집, `google youtube rank`로 상위 영상 점수화 및 visible transcript 파생 요약 분석, `google youtube topic`으로 키워드 묶음별 관측 순위/반복 노출/주제 클러스터 분석 | 댓글, 좋아요, 구독, 플레이리스트 저장 등 계정 상태 변경은 승인. 브라우저 수집은 입력/제출/쿠키·스토리지 export/숨은 endpoint 호출/챌린지 우회 금지. transcript 원문 전체 저장 금지 |
| `studio.youtube.com` | YouTube Studio | 채널 업로드, 게시, 분석, 수익화 설정 | 업로드 계획, 라이브 입력 `--no-final-submit`, 채널 상태 읽기 | 업로드 최종 제출, 게시, 수익화, 채널 설정 변경은 승인 |
| `console.cloud.google.com` | Cloud Console, Maps Platform, APIs/Credentials, IAM, Billing, Cloud Run, Compute Engine, Storage, BigQuery, GKE, Cloud SQL, Pub/Sub, Secret Manager, Logging, Monitoring, Vertex AI | 프로젝트/인프라/데이터/AI 백엔드 운영 | 프로젝트 컨텍스트와 리소스 상태 읽기, 승인용 실행 계획 작성 | API 키/OAuth 발급, IAM, billing, deploy, secret, query/export, resource create/delete는 승인 또는 차단 |
| `aistudio.google.com` | Google AI Studio | Gemini/API 실험, 키/프로젝트 관련 설정 | 무료/사용량 라벨 확인, 모델/도구 정보 조회 | API key 생성, 유료 사용, 프로젝트 설정 변경은 승인 |
| `gemini.google.com` | Gemini | 대화형 AI 앱, 프롬프트 기반 작업 | 사용자가 제공한 프롬프트 작업 계획/요약 | 민감 프롬프트 저장/공유, 외부 실행, 유료 기능은 승인 |
| `colab.research.google.com` | Google Colab | 노트북 실행, 분석/실험 환경 | 노트북 목록/상태 확인, 실행 계획 작성 | 코드 실행, 런타임 연결, 파일/드라이브 접근, 유료 런타임은 승인 |
| `script.google.com` | Apps Script | Workspace 자동화 스크립트 작성/배포 | 스크립트/프로젝트 상태 확인, 배포 계획 작성 | 스크립트 실행, 권한 부여, 배포, 트리거 생성은 승인 |
| `console.firebase.google.com` | Firebase Console | 앱 백엔드, 인증, DB, 호스팅, 분석 | 프로젝트/앱 상태 읽기, 설정 변경 계획 | 인증/DB/호스팅/배포/과금 관련 변경은 승인 |
| `developer.android.com` | Android Developers | Android 개발 문서와 가이드 | 공개 문서 검색/요약 | 계정 상태 변경 없음 |
| `play.google.com` | Google Play Console | Android 앱 출시, 테스트, 스토어 운영 | 앱 상태/출시 준비 보고서, 승인용 릴리스 계획 | 앱 릴리스, 가격/배포/스토어 등록정보 변경은 승인 |
| `developers.google.com` | Google for Developers | Google API/SDK 공식 문서 | 공개 문서 검색/요약, API 사용 전략 정리 | 콘솔 작업은 해당 콘솔 도메인 게이트로 이동 |
| `developer.chrome.com` | Chrome for Developers | Chrome, WebView, PWA 개발 문서 | 공개 문서 검색/요약 | 계정 상태 변경 없음 |
| `search.google.com` | Google Search Console | 사이트 검색 성능, 색인, 사이트맵 | 속성/리포트 읽기, 색인 상태 확인 | URL 색인 요청, 사이트맵 제출, 권한 변경은 승인 |
| `business.google.com` | Google Business Profile | 업체 프로필, 지도/검색 노출 관리 | 프로필 상태/리뷰/노출 정보 읽기 | 업체 정보 수정, 게시글/사진/영업시간 변경은 승인 |
| `analytics.google.com` | Google Analytics | 트래픽/이벤트/전환 분석 | 리포트 조회, 지표 요약 | 속성/이벤트/전환/권한 설정 변경은 승인 |
| `tagmanager.google.com` | Google Tag Manager | 태그/트리거/컨테이너 배포 | 컨테이너 상태 읽기, 변경 계획 작성 | 태그 저장, 버전 게시, 트리거 변경은 승인 |
| `ads.google.com` | Google Ads | 키워드/캠페인/광고비 관련 도구 | 무료 범위/가입 상태/키워드 플래너 접근 계획 | 캠페인 생성, 예산, 결제, 광고 게시, 유료 작업은 승인 또는 차단 |
| `merchants.google.com` | Merchant Center | 상품 피드, 쇼핑 노출, 판매자 정보 | 상품/계정 상태 읽기, 피드 계획 | 상품 피드 제출, 판매자/배송/세금 설정 변경은 승인 |
| `adsense.google.com` | Google AdSense | 사이트 수익화, 광고 단위, 지급 정보 | 수익/상태 리포트 읽기 | 광고 단위 생성, 지급/계정/사이트 설정 변경은 승인 |
| `lookerstudio.google.com` | Looker Studio | 대시보드/리포트 작성과 공유 | 리포트 목록/상태 읽기, 대시보드 계획 | 데이터 소스 연결, 공유, 게시, 권한 변경은 승인 |

## Basic Feature Overlay

The `google basic` gate also models common user-facing tasks that may not map
one-to-one to a single public domain:

| Surface | Purpose | Boundary |
| --- | --- | --- |
| `search` | public web search and related queries | read-only; save/bookmark requires approval |
| `youtube` | video search, topic preset research such as SmartStore/shopping mall/purchase agency, and transcript/summary preparation | read-only; playlist/account changes require approval |
| `maps` | place search and route preview | read-only; saved places/location-history output requires approval or block |
| `translate` | text/document translation | text read-only; document upload requires approval |
| `news` | topic news search and briefing | read-only |
| `alerts` | Google Alert creation plan | final alert creation requires approval |
| `shopping` | product search and price comparison | read-only; purchase/payment blocked |
| `account` | security and connected-apps checks | read-only; permission changes user-only |
| `chrome` | bookmarks/history checks | read-only; saved password output user-only/blocked |

## Verification Commands

```powershell
python scripts\entry\cdp_cli.py google domains report
python scripts\entry\cdp_cli.py google subdomains catalog
python scripts\entry\cdp_cli.py google basic catalog
```

Current locked counts:

- domain groups: 10
- surfaces: 50
- hosts: 32
- page tabs: 185
- basic feature surfaces: 22
- basic feature plans: 59
