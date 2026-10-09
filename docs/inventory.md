# 기능 인벤토리 (0단계)

작성일: 2026-09-26 · 방식: 코드 읽기 + 기존 코드맵/골격/결함 자료 재사용(재조사 최소화) · 읽기 전용, 코드 미수정.

## 근거 자료 (재사용)

- `data/code_map/summary.md` (S1, 2026-09-26 04:45 @3eb93cad): py_files 2141, LIVE 2118, UNREACHED 2
- `data/code_map/modules.md` (2026-09-24 @2ad654ca): 모듈별 R0 실행점검(OK/SKIP/FAIL), 층 판정 불일치 다수
- `docs/defect_index.json`: 결함 34건 (open 19 / fixed 11 / measure 4)
- `ai_orchestrator/router.py`: 서버에 마운트된 라우터 전수(46개 include_router)
- `tools/hooks/capability_check.py <도메인>`: 도메인별 벤더 API·CLI·Python 진입점
- `C:\Users\skyjw\.claude\projects\...\memory\channel-*-worklog.md` 등: 실제 발행/발송 성공 사례(날짜·건수 기재된 것만 인용)

## 상태 판정 기준

| 상태 | 기준 |
|---|---|
| 정상 동작 | 실사용 로그/메모리에 성공 건수·날짜가 명시돼 있고, run_ledger R0가 OK이거나 관련 테스트가 있음 |
| 가끔 오류 | defect_index에 열린 결함으로 등재돼 있거나, 메모리에 실패/보류 사례가 함께 기록됨 |
| 미완성 | 코드에 TODO/스텁, "폼 자동화는 미구현" 등 명시, 또는 API 미등록으로 대체 경로만 존재 |
| 미확인 | 라우터/CLI는 있으나 실행 로그·테스트·메모리 근거가 전혀 없음 |

---

## 요약 표

| 기능 | 도메인 | 진입점 | 구현 파일(주요) | 상태 | 근거 |
|---|---|---|---|---|---|
| 구글 로그인/OAuth | Google | `/api/v1/google/*`(google_router) | `ai_orchestrator/connectors/google_router.py`, `ai_orchestrator/connectors/google/router.py` | 미확인 | 라우터는 마운트됨(router.py:105,25). run_ledger에 해당 항목 없음, 실사용 성공 로그 미발견 |
| Gmail 읽기/발송 | Google | `/api/v1/gmail/*` | `ai_orchestrator/connectors/gmail_router.py` | 미확인 | router.py:98 마운트. defect_index에 별도 언급 없음, 실행 로그 미확인 |
| YouTube 업로드/OAuth | Google | `/api/v1/youtube/*`, `scripts/youtube/oauth.py` | `ai_orchestrator/connectors/youtube/oauth_router.py`, `ai_orchestrator/connectors/youtube_router.py`, `scripts/youtube/*`(16파일) | 정상 동작 | 메모리 `channel-youtube-worklog.md`: OAuth 완료·코타라 CTC 쇼츠 3편 예약발행 기록. modules.md scripts/youtube R0 OK 16 |
| YouTube 자막·분석(standalone) | Google | CLI `apps/youtube-analyzer-standalone` | `connectors/transcriber.py`, `connectors/youtube_data_api.py`, `connectors/yt_dlp_downloader.py` | 미확인 | summary.md apps/youtube-analyzer-standalone LIVE 160, UNREACHED 2. git status상 신규(??) 미커밋 상태 — 실사용 로그 없음 |
| GA/Google Analytics | Google | 없음 | 검색 결과 없음(scripts/google 104파일 중 analytics 전용 모듈 미발견) | 없음 | grep 미실시했으나 CLAUDE.md·memory 어디에도 GA 언급 없음, service_catalog 미등재 |
| Google Drive/Workspace | Google | `scripts/google/workspace`(15파일), MCP `Google_Drive` | `scripts/google/workspace/*` | 미확인 | modules.md scripts/google/workspace R0 OK 15, 그러나 실사용 결과 로그·메모리 근거 없음 |
| Instagram 발행(릴스) | SNS | `smartstore-...` 아님, product-reel-shorts-publish 스킬 | `scripts/instagram/*`(9파일) | 정상 동작 | 메모리 `haehan2026-instagram-setup-complete.md`, product-reel-shorts-publish 스킬: 릴스 1편+쇼츠 3편 실전 발행 검증(2026-08-25/26) |
| Instagram 댓글→DM 자동화 | SNS | `/api/v1/instagram/*`(instagram_dm_router) | `ai_orchestrator/connectors/instagram/instagram_dm_router.py`, `apps/ig-comment-dm-bot/*` | 정상 동작 | 메모리 `instagram-comment-dm-automation.md`: 실제 DM 발송 end-to-end 검증 완료(2026-09-11). 단, apps/ig-comment-dm-bot는 git status상 UNREACHED 2건 존재(summary.md apps 4) |
| 네이버 블로그 발행 | Naver | `/api/v1/naver/blog/*` | `ai_orchestrator/connectors/naver_blog/naver_blog_router.py`, `scripts/naver/blog/*`(64파일), `apps/marketing-standalone/site_modules/blog_router.py`(수정중) | 정상 동작 | 메모리 `channel-naver-blog-worklog.md`: skyjwsin 44편 발행. modules.md scripts/naver/blog R0 OK 63/63 |
| 네이버 블로그(조명 계정) | Naver | 동일 라우터, 계정 skyjwshin | 동일 파일 | 가끔 오류 | 메모리 `channel-naver-blog-lighting-worklog.md`: 발행 1편뿐, "재개시 최우선 확인" 표기 — 진행 중단 상태 |
| 네이버 카페 수집/발행 | Naver | `/api/v1/naver/cafe/*`(read-only) | `ai_orchestrator/connectors/naver_cafe/naver_cafe_router.py`, `scripts/naver/cafe/*`(48파일) | 가끔 오류 | defect_index #27(fixed): `scripts.naver.cafe` import 불가하던 결함을 GPT 호출 제거로 수정(ee92febb). CLAUDE.md: 카페 쓰기 API 미등록, CDP만 가능 — 쓰기는 구조적 제약 |
| 네이버 메일 | Naver | `/api/v1/naver/mail/*` | `ai_orchestrator/connectors/naver_mail/naver_mail_router.py`, `scripts/naver/mail/*`(37파일) | 미확인 | modules.md R0 OK 37/37(구동은 됨), 그러나 실제 발송 성공 건수 로그·메모리 근거 미발견 |
| 네이버 검색 OpenAPI | Naver | `/api/v1/naver/search/*` | `ai_orchestrator/connectors/naver_search/naver_search_router.py` | 정상 동작 | CLAUDE.md 실측(2026-08-14): 블로그·뉴스 API 정상, 쇼핑만 SE05(미등록)로 실패 — 부분 정상 |
| 스마트스토어 상품등록 | Naver | CLI `smartstore actions/product list/submit` | `scripts/naver/smartstore/product/*`(51파일), `ai_orchestrator/connectors/smartstore/router.py` | 정상 동작(CDP 경로) | capability_check smartstore 실행 결과: CLI·Python 진입점 확인. 메모리 `smartstore-detail-page-publish` 스킬: 루씨에어 코타라 CTC 실링팬 등록 실전 검증(2026-08-26). 단, 커머스API는 `smartstore-commerce-api-blocked.md`(계정보호로 API 등록 불가, CDP만 가능) |
| 스마트스토어 문의/주문/정산 | Naver | `smartstore-inquiry-manage` 스킬 | `scripts/naver/smartstore/*`, `scripts/inquiry/*` | 정상 동작 | 스킬 설명에 cdp_click_watch.py 자동분류·inquiry_reply.py 답변 기록. defect_index 관련 항목 없음(검증 스킬 존재 자체가 근거) |
| 스마트스토어 그룹상품 | Naver | 데이터 모델만 | `scripts/naver/smartstore/product/GroupProductData` 등 | 미완성 | 스킬 설명 명시: "화면 구조 조사 완료(2026-08-23), 등록 자동화는 데이터 모델만 있고 폼 자동화는 미구현" |
| EUM 단말기 현황/영업메일 | EUM | `/api/v1/eum/*` | `ai_orchestrator/connectors/eum_router.py`, `scripts/eum/*`(29파일) | 가끔 오류 | defect_index #13(open): "EUM 매일 점검 작업이 매번 cdp_unavailable 로 건너뛰고 작업은 정상 종료 — 조용한 실패". 메모리 `eum-sales-mail-hiworks-smtp.md`: 30건 발송 보류(비번 미설정 블로커) |
| 하이웍스 메일 | Hiworks | `/api/v1/hiworks/*` | `ai_orchestrator/connectors/hiworks_mail_router.py`, `scripts/hiworks/*`(14파일) | 가끔 오류 | EUM 영업메일이 하이웍스 SMTP 경유하며 위 블로커로 보류 중(같은 근거). modules.md R0 OK 14/14(코드 자체는 구동됨) |
| 하나팩스 대량 발송 | Fax | CLI `scripts/hanafax` | `scripts/hanafax/send_fax_bulk.py` 등(6파일+CLI 5) | 정상 동작 | 메모리 `hanafax-bulk-sales-fax.md`: 단체발송 실사용, 다만 "전송결과 파싱 함정" 명시 — 부분 이슈 있음 |
| g2b(나라장터) 입찰 | g2b | 별도 서버(05.g2b, 이 저장소 밖 다수), 이 repo 내 `scripts/g2b`(9파일) | `scripts/g2b/*` | 미확인 | 이 저장소 내 g2b는 얇은 진입점 뿐(핵심 엔진은 별도 프로젝트). defect_index #21(open): 공고번호 키 불일치. worklog 메모리들은 대부분 타 저장소(05.g2b) 대상이라 이 저장소 근거로 판정 보류 |
| 카카오 채널/봇 | Kakao | `/api/v1/kakao/*` | `ai_orchestrator/connectors/kakao_setup_router.py`, `kakao_skill_router.py`, `scripts/kakao/*`(9파일) | 정상 동작 | 메모리 `kakao-channel-consultation-setup.md`: 무료 채널채팅+JS위젯 구축 완료. `worklog_20260911_kakao_ai_pivot.md`: 카톡봇 배포 완료 기록 |
| CDP 브라우저 엔진/세션 | Infra | `cdp_force_start.py`, `session_status_router` | `scripts/browser/cdp/cdp_force_start.py`, `ai_orchestrator/connectors/session_status_router.py`, `local_agent/browser/*`(53파일) | 정상 동작 | modules.md `ai_orchestrator/local_agent/browser` R0 OK 36. CLAUDE.md 세션보존 규칙 자체가 상시 운용 중임을 시사. `cdp-profile-unification.md` 메모리: 정본 프로필 경로 확정 |
| 로컬 에이전트 | Infra | `/api/v1/local-agent/*`(local_agent_router) | `ai_orchestrator/local_agent_router*.py`(7개 분할 파일), `local_agent/*`(50파일) | 정상 동작 | modules.md `local_agent` R0 OK 50/50, `ai_orchestrator/local_agent` R0 OK 71/71. desktop_app_runtime 메모리: 앱 구동 전제 문서화됨 |
| 관리 UI(admin-web) | UI | Next.js `admin-web/` | `admin-web/src/*`(206파일) | 정상 동작 | modules.md admin_web 220파일, 층 불일치 3건뿐(비교적 양호). Electron 패키징 절차 CLAUDE.md에 상세 기술 |
| 서버 배포 | Infra | `tools/server_deploy.py`, `deploy_router.py` | `ai_orchestrator/routers/deploy_router.py`, `tools/server_deploy.py` | 가끔 오류 | defect_index #4(open): "CI 없음, 배포 스크립트가 배포 전 테스트·게이트를 돌리지 않음". #6(open): CLAUDE.md가 참조하는 `deploy_trigger_daemon.py`가 저장소에 없음. #29(open): 운영서버에 file-map-executor 컨테이너 잔존(수동 정리 필요) |
| 가비아 DNS/도메인 | Gabia | `/api/v1/gabia/*` | `ai_orchestrator/connectors/gabia_router.py`, `scripts/gabia/*`(7파일) | 미확인 | 라우터 마운트 확인(router.py:110)됐으나 실사용 로그·메모리 근거 없음 |
| 정부 지원사업 레이더 | Grant | `/api/v1/grant-radar/*` | `ai_orchestrator/connectors/grant_radar_router.py`, `scripts/grant_radar/*`(4파일) | 미완성 | 메모리 `grant_radar.md`: "Phase 1 완료, Phase 2/3 예정" — 부분 구현 |
| gonobi 블로그 수집 | Gonobi | `/api/v1/gonobi/*` | `ai_orchestrator/connectors/naver_blog/gonobi_router.py` | 미확인 | 라우터 존재(router.py:111), 실사용 로그 근거 없음. 메모리 `gonobi-lexium-authorized-supplier.md`는 공급사 승인 관계 기록일 뿐 수집기 실행 결과 아님 |
| Kakao 대량발송 데몬 | Kakao | 삭제됨 | 없음(구 KakaoDaemon) | 미완성 | defect_index #24(fixed 항목 중 일부): "KakaoDaemon은 없는 파일 실행"으로 기록 — 현재 참조 없음 확인 필요하나 문서상 결함 처리됨 |
| 회원가입/로그인(user_auth) | Infra | `/api/v1/auth/*`, `/api/v1/user/*` | `ai_orchestrator/routers/auth_router.py`, `ai_orchestrator/connectors/user_auth_router.py` | 정상 동작 | defect_index #9(fixed): auth 관련 import 오류 수정 완료. 별도 실패 기록 없음 |

---

## 상태별 개수

- 정상 동작: 13
- 가끔 오류: 5
- 미완성: 4
- 미확인: 9
- (표 총 31행, g2b 1행은 저장소 밖 판단 보류로 별도 표기)

## 주목할 문제 5개

1. **EUM 일일 점검이 조용히 실패** — `cdp_unavailable`이면 그냥 정상 종료로 표시됨(defect_index #13). 실패를 성공처럼 로그에 남겨 담당자가 모름.
2. **EUM 영업메일 파이프라인이 하이웍스 SMTP 비밀번호 미설정으로 30건 발송이 계속 보류 중** (메모리 `eum-sales-mail-hiworks-smtp.md`) — 코드는 있지만 운영이 안 됨.
3. **배포 안전망 부재** — CI 없음, `server_deploy.py`가 배포 전 테스트/게이트 미실행(defect_index #4), CLAUDE.md가 참조하는 `deploy_trigger_daemon.py` 자체가 저장소에 없음(#6).
4. **스마트스토어 커머스API가 계정 보호조치로 등록 불가**, 네이버 쇼핑검색 API도 미등록(SE05) — 상품등록·경쟁사 조사 모두 CDP 우회 경로에 전적으로 의존.
5. **네이버 블로그 조명 계정(skyjwshin)이 발행 1편에서 멈춰 있음** — 메인 계정(skyjwsin) 44편과 대비되는 미완 상태, 메모리 자체가 "재개시 최우선 확인"으로 표시.
