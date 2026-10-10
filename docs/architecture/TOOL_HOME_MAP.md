# 도구 지도 정본 (TOOL_HOME_MAP) — T0

- 작성: 2026-10-07 (W4) / 브랜치 `stage/t0-tool-home-map` / 기준 통합 HEAD `5f83b90d`
- 상태: **DRAFT — 읽기 전용 조사 + 문서만. 코드 이동·삭제 없음.** 이동은 T1~T5 단계에서 대표님 승인 후 진행한다.
- 지시: "프로그램을 도구별로 폴더·모듈로 나누고 중복을 없앤다"(대표님). 계획서: `C:\work\_coordination\TOOL_MODULARIZATION_PLAN.md` §3 T0.
- 함께 둔 표(전수 목록): 같은 폴더의 `TOOL_HOME_MAP_leaks.tsv`(집 밖 파일 224건), `TOOL_HOME_MAP_dup_groups.tsv`(운영 코드 중복 묶음 367건), `TOOL_HOME_MAP_dup_candidates.tsv`(공용화 후보 67건), `TOOL_HOME_MAP_dated_scripts.tsv`(날짜 박힌 스크립트 5건).

> **정정(2026-10-07, B1 작업 중 발견)**: `scripts/archive/one_off/reclassify_blog_new.py` 는 이름에 `blog` 가 있어 키워드 분류가 블로그 이탈로 잡았으나 실제로는 카탈로그 상품 분류 스크립트(mk_catalog)다. 이동 대상이 아니므로 이탈 목록에서 뺐다(`TOOL_HOME_MAP_leaks.tsv` 에서 1줄 삭제). 이 문서의 숫자는 그만큼 줄어든다: 이탈 224→223, 이동 71→70, naver_blog 이탈 41→40(이동 12→11). 또 youtube 이탈 31건 중 실제 이동 대상은 `yt_upload` 6 + 스모크 1뿐이고 나머지는 google 도메인 하위 탭(정상)·완성형 shim·제외로 재분류했다(아래 youtube 절).

> **정정 2(2026-10-07, G11 도구 집 게이트 작업 중)**: ① 루트 `hiworks_mail_reader.py`·`kakaowork_reader.py` 는 1단계 분리 뒤 `orchestrator_v1/inbox/` 로 간 실제 파일의 **호환 shim** 이다. 이전 표는 이를 실제 파일로 보고 '이동'으로 분류했으나, 이동 대상은 `orchestrator_v1/inbox/` 의 실제 파일이고 루트 shim 은 유지한다(옛 경로의 import·경로 로드·직접 실행 호환 — `tools/devflow/make_shim.py` 형식). ② `scripts/google/audit_gmail_function_contract.py` 는 일회성 감사 스크립트라 `scripts/google/ops/` 로 옮기는 것이 아니라 **archive 후보**(`scripts/archive/`)다. ③ 집 규칙은 이제 게이트로 강제된다: `configs/tool_home.json`(도구 키워드·집·예외+사유) · `configs/tool_home_baseline.json`(기존 집 밖 105건 고정) · `tools/repo_gates/tool_home_gate.py`(pre-commit `--staged`, CI `--check-all`). 이 문서의 224건은 키워드 분류의 전수 조사였고, 게이트 기준선은 예외(시험·archive·apps·층 표준 폴더·google 의 youtube 하위 탭 등)와 이미 이동한 파일을 뺀 현재 실제 집 밖 파일이다.

## 0. 측정 방법과 한계 (숫자를 읽기 전에)
- **파일 분류**: `5f83b90d`의 추적 파일 중 코드(py·ts·tsx·js, 시험·docs·보관(`scripts/archive`)·`admin-web/vendor` 제외) 1,960개를 **경로 이름의 키워드**로 도구에 배정했다(구체적인 도구 먼저: smartstore → hanafax → … → naver_blog). 이름에 도구가 드러나지 않는 파일(예: 공용 CDP 헬퍼)은 배정되지 않는다. 즉 **도구 이름이 경로에 있는 파일만** 센 것이다. 806개가 도구에 배정됐다.
- **import 건수**는 정적 문자열 근사(운영 코드·시험을 구분)다. 동적 import·경로 문자열 참조·JS/TS는 잡지 못한다. 이동 전에 `verify_change`와 `grep`으로 재확인한다.
- **중복**은 지휘창이 `C:\hhwt-integrate`에 돌린 dupscan 보고서(`C:\work\audit-tools\_reports\orchestrator_dupscan_20261007\중복분석.json`)를 근거로 했고, 새 검사기는 만들지 않았다. dupscan 경로는 프로젝트 기준 상대 경로라 전체 경로로 복원했고, `scripts/archive/`(보관 코드)는 뺐다.
- 이동 대상 경로는 **규칙으로 만든 안**이다. 이름 충돌·`__file__` 기준 경로·`sys.path` 의존은 이동 때 파일별로 확인한다.

## 1. 원칙
1. **도구마다 층별 집 1곳**: 구현 `scripts/<도구>/`, API `ai_orchestrator/connectors/<도구>/`, 화면 `admin-web/src/app/<도구>/`. 네이버처럼 한 플랫폼 아래 여러 도구가 있으면 `scripts/naver/<도구>/`, 화면 `admin-web/src/app/naver/<도구>/`.
2. **층 표준 위치는 정상**: 도구 전용이라도 서비스·워크플로·영속·게이트·도메인은 층 폴더(`ai_orchestrator/{services,workflows,persistence,gates,domain,sites,contracts}`)에 둔다. 이것은 "집 밖"이 아니다(33개). 폴더 안 도구별 하위 폴더화는 이번 범위가 아니다(결정 3).
3. **집 밖(이탈)의 분류**
   - **이동**: 도구 집으로 옮길 구현 파일.
   - **폴더화**: `connectors/<도구>_*.py`처럼 평면으로 놓인 API 파일, 그리고 `routers/` 안의 도구 라우터를 `connectors/<도구>/`로.
   - **화면이동**: 화면이 다른 경로에 있는 경우(카페).
   - **T4연동**: `ai_orchestrator/local_agent/`·`browser_tool` 안에 있는 도구 전용 믹스인·스크립트. local_agent 3벌 통합(T4) 때 함께 정한다.
   - **독립앱**: `apps/*` 독립 배포 앱의 복사본·자체 구현(결정 1).
   - **archive후보**: `scripts/ops/`의 도구별 감사·스모크 일회성 스크립트(삭제가 아니라 `scripts/archive/`로).
   - **정상**: 플러그인 레지스트리(`scripts/ops/selector_health/sites/`, `write_gates/`) — 도구 이름이 있어도 공용 틀 안의 플러그인이라 유지.
4. **모범 사례(이미 있음)**: 스마트스토어는 `connectors/smartstore/router.py`가 본체이고 옛 경로 `connectors/smartstore_router.py`는 4줄 호환 shim(`from .smartstore.router import smartstore_router`)이다. 다른 도구도 이 형태로 옮긴다(shim → 참조 전환 → shim 제거, 1단계와 같은 방식).

## 2. ① 도구별 집 확정과 현황

| 도구 | 구현 집 | API 집 | 화면 집 | 파일 | 집 안 | 층 표준 | 이탈 | 이탈 내역 |
|---|---|---|---|---|---|---|---|---|
| video | `scripts/video/` | (없음) | (화면 없음) | 16 | 16 | 0 | 0 | - |
| smartstore | `scripts/naver/smartstore/` | `ai_orchestrator/connectors/smartstore/` | `admin-web/src/app/naver/(legacy)/smartstore/` | 118 | 110 | 0 | 8 | 이동 6, 폴더화 1, 정상 1 |
| hanafax | `scripts/hanafax/` | `ai_orchestrator/connectors/hanafax/` | `admin-web/src/app/hanafax/` | 24 | 17 | 6 | 1 | 폴더화 1 |
| hiworks | `scripts/hiworks/` | `ai_orchestrator/connectors/hiworks/` | (화면 없음) | 21 | 14 | 2 | 5 | 폴더화 4, 이동 1 |
| eum | `scripts/eum/` | `ai_orchestrator/connectors/eum/` | (화면 없음) | 40 | 34 | 0 | 6 | 이동 5, 폴더화 1 |
| gabia | `scripts/gabia/` | `ai_orchestrator/connectors/gabia/` | (화면 없음) | 21 | 8 | 6 | 7 | archive후보 4, 이동 2, 폴더화 1 |
| g2b | `scripts/g2b/` | `ai_orchestrator/connectors/g2b/` | (화면 없음) | 17 | 8 | 0 | 9 | T4연동 8, 이동 1 |
| kakaowork | `scripts/kakaowork/` | `ai_orchestrator/connectors/kakaowork/` | (화면 없음) | 2 | 0 | 1 | 1 | 이동 1 |
| kakao | `scripts/kakao/` | `ai_orchestrator/connectors/kakao/` | (화면 없음) | 11 | 9 | 0 | 2 | 폴더화 2 |
| instagram | `scripts/instagram/` | `ai_orchestrator/connectors/instagram/` | (화면 없음) | 32 | 9 | 0 | 23 | 독립앱 14, 폴더화 7, archive후보 1, 이동 1 |
| youtube | `scripts/youtube/` | `ai_orchestrator/connectors/youtube/` | (화면 없음) | 54 | 22 | 1 | 31 | 이동 17, 독립앱 10, 폴더화 3, archive후보 1 |
| naver_cafe | `scripts/naver/cafe/` | `ai_orchestrator/connectors/naver_cafe/` | `admin-web/src/app/naver/cafe/` | 78 | 48 | 6 | 24 | 화면이동 10, T4연동 10, 이동 3, 폴더화 1 |
| naver_mail | `scripts/naver/mail/` | `ai_orchestrator/connectors/naver_mail/` | `admin-web/src/app/mailbox/` | 118 | 61 | 11 | 46 | 이동 21, archive후보 21, 폴더화 3, T4연동 1 |
| naver_blog | `scripts/naver/blog/` | `ai_orchestrator/connectors/naver_blog/` | `admin-web/src/app/naver/blog/` | 116 | 75 | 0 | 41 | T4연동 18, 이동 12, 폴더화 5, 독립앱 4, 정상 2 |
| naver_search | `scripts/naver/shopping/` | `ai_orchestrator/connectors/naver_search/` | `admin-web/src/app/naver/(legacy)/keywords/` | 30 | 14 | 0 | 16 | 폴더화 15, 이동 1 |
| google | `scripts/google/` | `ai_orchestrator/connectors/google/` | `admin-web/src/app/google/` | 108 | 104 | 0 | 4 | 폴더화 3, archive후보 1 |
| **합계** | | | | **806** | **549** | **33** | **224** | |

비고
- `video`: 에피소드 영상 제작 스크립트(주제가 유튜브·g2b·카카오·인스타여도 영상 제작 도구)라 `scripts/video/`가 집이다. 키워드로는 다른 도구에 걸리므로 별도 도구로 뺐다.
- `kakaowork`는 `kakao`(카카오 채널·스킬)와 다른 제품이라 분리했다(루트 `kakaowork_reader.py`).
- `naver_search`는 검색·쇼핑·OpenAPI 수집을 묶었다. 평면 `connectors/naver_*` 15개가 폴더화 대상이다.
- 화면이 없는 도구(hiworks·eum·gabia·g2b·kakao·instagram·youtube)는 화면 집을 만들지 않는다. 필요해질 때 그 경로를 쓴다.
- 이 표에 없는 도구(gongmu·site_map·scheduled·chat 콘솔·auth·marketing 운영 등)는 이름 키워드로 모이는 구현 스크립트가 없고 층 표준 위치(서비스·영속·라우터)와 화면으로 이뤄져 있어 이번 이탈 목록에서 제외했다.

### 2-1. 도구가 아닌 기반(공용) — 집 정본 제안 (상세는 T1·T4·T5 기준서)
| 기반 | 현재 | 정본 집 제안 | 단계 |
|---|---|---|---|
| CDP·브라우저 | 22개 위치(`ai_orchestrator/local_agent` 47, `browser_tool` 46, 루트 `local_agent` 20, `scripts` 20, `browser_worker`, `browser_api` …) | 엔진은 `ai_orchestrator/browser_tool/`, 공유 연결은 `scripts/web_connector.py`(CLAUDE.md가 이미 정본으로 지정). 도구 전용 믹스인은 각 도구 집으로 | T1(클라이언트 1벌)·T4 |
| local_agent | 3벌(`ai_orchestrator/local_agent` 116, 루트 `local_agent` 51, `scripts/local_agent` 21) | 서버 측은 `ai_orchestrator/local_agent/`, PC 실행체는 루트 `local_agent/`(독립 배포 단위)로 역할을 나누고 `scripts/local_agent/`는 시나리오로 흡수 — **T4 기준서에서 확정**(이번 제안은 방향만) | T4 |
| 게이트·정책 | 26개 위치, 4종 병존(`scripts/common/gate.py`, `scripts/gates/`, `ai_orchestrator/gates/`, `scripts/ops/write_gates/`) | 1종으로 — R2d-2 설계와 함께 | T5 |

## 3. ② 집 밖 파일 전수와 이동 대상

전체 224건은 `TOOL_HOME_MAP_leaks.tsv`(도구·현재 위치·층·분류·이동 대상·import 건수). 분류별 요약:

| 분류 | 건수 | 위험 | 처리 |
|---|---|---|---|
| 이동 | 71 (참조 0건 35 · 참조 있음 36) | 참조 0 = 낮음, 참조 있음 = 중간 | 아래 배치 B1·B2 |
| 폴더화 | 47 (평면 API 42 · routers/ 5) | 중간(`router.py` include·import 경로) | B3 |
| 화면이동 | 10 | **URL이 바뀐다**(`/assistant/cafe` → `/naver/cafe`) → 리다이렉트 필요 | B4 |
| T4연동 | 37 | T4와 함께 | B5 |
| archive후보 | 28 (참조 0건 15) | 낮음(삭제 아님) | B1 |
| 독립앱 | 28 | 결정 필요 | 결정 1 |
| 정상 | 3 | - | 유지 |

### 3-1. 도구별 대표 이탈과 이동 대상
(전수·경로별 대상은 TSV. 괄호는 운영/시험 import 근사 건수.)

**naver_mail (이탈 46)** — 가장 큼
- `scripts/naver/mail_imap/*`(10) → `scripts/naver/mail/imap/` (`__init__` 운영 9·시험 7, `sender` 6·4, `protocol` 6·1)
- `scripts/naver/mail_read/*`(7) → `scripts/naver/mail/read/` (`__init__` 17·1, `cdp` 13)
- `scripts/naver_mail/{background_runner,settings_panel}.py`(2, 재노출 shim) → `scripts/naver/mail/`
- `scripts/naver/automation/{,integration/}mail_automation.py`(2) → `scripts/naver/mail/` (결함 #39: `NaverMail` 부재 UNREACHED — 이동 전에 폐기 여부 결정)
- `scripts/ops/` 감사·스모크 21개 → archive후보(참조 0건 다수) 또는 `scripts/naver/mail/ops/`
- `ai_orchestrator/connectors/naver_mail/mailbox_router.py`·`naver_mail_bulk_router.py` → `connectors/naver_mail/mailbox_router.py`·`bulk_router.py`, 평면 `connectors/naver_mail_router.py` → `connectors/naver_mail/router.py`(옛 `/naver-mail`, 항상 501 — B 점검)
- `local_agent/browser/mixins/mail_mixin.py` → T4연동

**naver_blog (이탈 41)**
- `scripts/gonobi_*.py` 9개(루트 스크립트, 참조 0건) → `scripts/naver/blog/gonobi/`(이미 `gonobi/` 폴더 존재)
- `scripts/naver/router_blog.py`·`scripts/navigator_blog.py` → `scripts/naver/blog/` (`scripts/archive/one_off/reclassify_blog_new.py` 는 정정으로 제외 — 위 정정 참고)
- `ai_orchestrator/connectors/{gonobi_router,gonobi_scheduler,naver_blog_*}.py`(평면) 및 `routers/blog_automation_router.py` → `connectors/naver_blog/`
- `local_agent/browser/mixins/blog_mixin*.py`(7)·`_js/extract_blog_*.js`(8)·`naver_blog_workflow.py`·`scripts/local_agent/naver/blog_*.py` → T4연동 18건
- `apps/marketing-standalone/connectors/{blog_accounts,blog_images,naver_blog_cdp}.py`·`site_modules/blog_router.py` → 독립앱 4건(결정 1)

**naver_cafe (이탈 24)**
- 화면 `admin-web/src/app/assistant/(legacy)/cafe/*`(10) → `admin-web/src/app/naver/cafe/` (URL 변경, 리다이렉트)
- `scripts/naver/router_cafe.py` → `scripts/naver/cafe/`(운영 3), `scripts/ops/{daily_cafe_marketing_pipeline,export_cafe_keywords_excel}.py` → `scripts/naver/cafe/ops/`
- `local_agent/browser/mixins/cafe_mixin*.py`(7)·`_js/extract_cafe_posts.js`·`naver_cafe_workflow.py`·`scripts/naver/cafe/run_naver_cafe_to_blog_workflow.py` → T4연동 10

**youtube (이탈 31 → 재분류, 정정 2026-10-07 split-youtube)** — 실제 이동 대상은 소수였다
- 이동 완료: `scripts/yt_upload/*`(6, B1 `b4908817`) → `scripts/youtube/upload/`, `scripts/smoke_youtube_manual_login_probe.py` → `scripts/youtube/`(split-youtube `2ce2345e`)
- **정상(옮기지 않음)**: `scripts/google/youtube/*`(7)·`scripts/google/common/youtube_upload.py`·`ai_orchestrator/connectors/google/youtube.py` 는 Google 도메인의 'YouTube 하위 탭'이다. `scripts/google/module_contracts.py`(youtube_creator·youtube_studio 구현 모듈), `tab_registry.py`(owner_package), `scripts/google/youtube/__init__.py`(google 탭 facade가 google taxonomy 를 import), skeleton_gate 의 "google 은 youtube 도메인을 import 하지 않는다" 규칙·baseline, 시험 5곳(모듈 이름 단언)이 소유권을 이미 정했다. 옮기면 규칙을 어기거나 shim 으로 의존을 숨기게 된다.
- **완성형 shim(추가 작업 없음)**: 평면 `connectors/youtube_router.py`·`routers/youtube_{oauth,research}_router.py` — 실구현은 이미 `connectors/youtube/` 패키지(스마트스토어와 같은 형태).
- 제외: `scripts/common/youtube_search_cache.py`(⚠ G5 겹침, §6-1), `tools/hooks/guard_youtube_upload.py`(`.claude/settings.json` 훅), `apps/youtube-analyzer-standalone/*`(10, 독립앱 결정 1)

**instagram (이탈 23)**: 평면 `connectors/instagram_*`(7) → `connectors/instagram/`(⚠ `instagram_dm_db.py`는 G5와 겹침), `scripts/instagram/ig_batch.py` → `scripts/instagram/ops/`, `apps/ig-comment-dm-bot/*`(14) → 독립앱(결정 1; `processed_store.py`는 G5에서 이미 B 분류).
**smartstore (이탈 8)**: `scripts/naver/automation/smartstore/*`(6) → `scripts/naver/smartstore/automation/`(참조 있음, `__init__` 6), 평면 `smartstore_router.py`는 이미 4줄 shim(제거 대상), `tools/selector_health/sites/naver_smartstore.py`는 정상.
**eum (6)**: 루트 `scripts/eum_*.py` 5개 → `scripts/eum/`(이름에서 `eum_` 접두 제거), 평면 `eum_router.py` → `connectors/eum/`.
**gabia (7)**: 루트 `gabia_login_watch.py` 외 → `scripts/gabia/`, `scripts/ops/` 일회성 4개 archive후보.
**g2b (9)**: `ai_orchestrator/browser_tool/g2b_*.py` 8개 → T4연동(엔진 패키지 안의 도구 전용 파일, 집은 `scripts/g2b/`), `scripts/smoke/g2b_*` → `scripts/g2b/smoke/`.
**hiworks (5)**: 루트 `hiworks_mail_reader.py`(+ `orchestrator_v1/inbox/` shim) → `scripts/hiworks/`, 평면 `connectors/hiworks_*.py` 4개 → `connectors/hiworks/`(`hiworks_client`·`collectors`·`config`는 호출처 없는 고아 코드 — B 점검).
**kakao·kakaowork·hanafax·google·naver_search**: 평면 API 파일 폴더화(kakao 2, hanafax 1, google 3, naver_search 15)와 루트 `kakaowork_reader.py` → `scripts/kakaowork/`.

### 3-2. 날짜 박힌 일회성 스크립트 (`scripts/ops/*_2026MMDD.py`)
5개(`TOOL_HOME_MAP_dated_scripts.tsv`), **전부 운영·시험 참조 0건** → T3에서 `scripts/archive/`로 이동 후보(삭제 아님). 도구 이름이 들어간 `scripts/ops/audit_*`·`smoke_*`·`report_*` 등 28개 중 15개도 참조 0건(위 분류의 archive후보).

## 4. ③ 중복 목록 (dupscan 근거)

### 4-1. 전체 규모 (`중복분석.json` 요약)
- 분석 2,429개 파일·함수 15,537개 / 중복 묶음 **구조 동일 727 · 유사 692** / 공용화 후보 **67**(여러 프로젝트에 걸친 것) / 합쳐서 줄일 수 있는 줄 추정 34,254.
- 프로젝트별 중복 함수 비율: tests 37.2%(2,148), apps 39.7%(52), ai_orchestrator 21.8%(825), scripts 18.0%(926), local_agent 8.0%(38), orchestrator_v1 15.4%(20). **시험 코드의 상용구가 가장 크다**(T2 게이트는 새 중복만 차단하는 기준선 방식).
- 파일 단위: 내용이 같은 파일 묶음은 **1건뿐**(`ai_orchestrator/models.py` ≡ `orchestrator_v1/core/models.py`, 1단계 이동 산물). 나머지 182행(60묶음)은 `router.py`(22)·`models.py`(12)·`auth.py`(8) 같은 **동일 파일명일 뿐 내용은 다르다** — 중복으로 세지 않는다.

### 4-2. 운영 코드(시험·보관 제외) 중복 묶음: **367묶음**, 절감 추정 10,072줄 (`TOOL_HOME_MAP_dup_groups.tsv`)
| 구분 | 묶음 | 절감 추정(줄) |
|---|---|---|
| 구조 동일(AST 동일) | 217 | 4,617 |
| 유사 | 150 | 5,455 |
| 서로 다른 프로젝트(패키지)에 걸친 것 | 62 | - |

도구별 묶음 수(한 묶음이 여러 도구에 걸치면 각각 센다): 공용·미분류 224, naver_blog 54, google 42, instagram 31, naver_mail 29, youtube 21, eum 20, kakao 20, hiworks 17, smartstore 17, g2b 14, naver_cafe 13, hanafax 9, naver_search 8, gabia 5.

### 4-3. 중복 패밀리와 정리 방향 (대표 묶음의 근거 위치)
| # | 패밀리 | 근거 | 규모 | 정리 방향 | 단계 |
|---|---|---|---|---|---|
| 1 | persistence 스토어의 연결·스키마 상용구 `_conn`·`_schema_v1` | `agent_dispatch_store`·`fax_authorization_store`·`mail_bulk_store`·`gongmu_store`·`instagram_dm_db` 등 (E701 5함수, E11·S2 `_schema_v1` 8함수) | 절감 약 620줄 | 기존 `persistence/sqlite_schema.py`(`apply_schema`·`set_busy_timeout`)와 `_conn` 표준형으로 모음 — G5 기준서 §4와 같은 부품 | T1③ |
| 2 | 검증기 복사 `validate_*_action_plan` | `scripts/{gabia,google,hiworks,youtube}/validators.py` (E704) | 4개 파일 | 검증기 공용 모듈 1곳 | T1② |
| 3 | 네이버 메일 CDP `_send` 등 | `scripts/naver/mail/read/cdp.py` + `scripts/ops/` 일회성 4개 (E256) | 5개 파일 | 공용 CDP 클라이언트 1벌(T1①), 일회성은 archive | T1①·T3 |
| 4 | CDP 탐색기 상용구 `_visible_ui_snapshot`·`analyze`·`check` | `scripts/eum/workspace.py`, `scripts/hiworks/{explorer,mail}.py`, `scripts/naver/smartstore/…` (E6, 148줄) | 4+ 파일 | 공용 CDP 탐색 부품 | T1① |
| 5 | cdp.db 클러스터의 `_init_db` | `scripts/naver/automation/{platform,smartstore}/…`, `blog/management/…`, `smartstore/product/bulk.py` (S34·E145·E397) | 약 190줄 | **G5 P3에서 저장 계층으로 이동하며 함께 해소** | G5 |
| 6 | 감사 스크립트 상용구 `run_audit`·`audit`·`main`·`print_report` | `scripts/ops/audit_*`(S10 182·S21 142·S22 138·S28 130·E33 115·E39 112 …) | 최상위 묶음 다수 | 감사 상용구 공용 모듈 | T1④ |
| 7 | 품질 게이트 점검 함수 | `scripts/module_quality_gate_checks_{audit,repo}.py` (E12, 208줄) | 2파일 | 점검 함수 공통화 | T5 |
| 8 | 브라우저 엔진 검증기 | `ai_orchestrator/browser_tool/browser_engine_*` (S9, 166줄) | 같은 폴더 내 | 폴더 내 통합 | T4 |
| 9 | 인박스 저장소 `_load_all` | `orchestrator_v1/inbox/{email_task_store,inbox_store}.py`, `tasks/candidate_store.py` (E382) | 3파일 | 저장소 기반 클래스 | T1③ |
| 10 | **apps ↔ scripts 복사본** | `BlogWriter.write_body·set_tags·insert_image·write_mixed_content`, `CDP._reader`, `content_rules.seo_check·_risky_claims·_ai_section_ratio`, `draft_blog_post`, `download_image`, `create_reel_container`, `_post` (E101·E94·E206·E274·E251·E423 등) | 공용화 후보 67 중 **48건**이 apps↔scripts | 결정 1 | 결정 |

공용화 후보 67건(`TOOL_HOME_MAP_dup_candidates.tsv`): 추천이 "공용화 검토(프로젝트 내부 모듈 의존성 분리 필요)" 42건, "haehan_common 이전 추천(독립 코드)" 25건. 절감 추정 1,043줄. 상위는 `BlogWriter.write_body`(46.9점, apps↔scripts, 유사도 0.944)·`CDP._reader`(40.4점)·`content_rules` 5함수다. dupscan이 "독립 코드"로 분류한 25건은 의존성이 없어 `haehan_common`(공용 패키지) 후보다.

## 5. 단계별 이동 대상표 (계획서 §3과 대응, 충돌 피하려 순서 고정)

| 배치 | 내용 | 건수 | 방식 | 선행 |
|---|---|---|---|---|
| **B1** | 참조 0건 이동 35개(gonobi 루트 스크립트 9, eum 루트 5, yt_upload 6, `ops/` 도구별 스크립트, g2b smoke, `kakaowork_reader` 등) + archive후보 중 참조 0건 15개(`scripts/archive/`로) + 날짜 박힌 5개 | 약 55 | `git mv` + `__file__` 보정 + 영향 시험 + `verify_change`. shim 불필요 | T1 후 |
| **B2** | 참조 있는 이동 36개 — `mail_imap`(10)·`mail_read`(7)·`google/youtube`(8)·`automation/smartstore`(6)·`router_cafe` 등 | 36 | **옛 경로에 shim → 참조 전환 → shim 제거**(1단계와 같은 방식). 호출처 많은 `mail_read/__init__`(18)·`mail_imap/__init__`(16)부터 주의 | B1 후 |
| **B3** | 폴더화 47개 — 평면 `connectors/<도구>_*.py` 42, `routers/` 5 | 47 | `connectors/<도구>/`로 이동, `ai_orchestrator/router.py`의 import·include 경로 수정, 옛 경로 4줄 shim. **라우트 개수는 불변**(`configs/route_count_expectation.json` 그대로) | B2와 병행 가능 |
| **B4** | 화면이동 10개(카페 UI) | 10 | `/assistant/cafe` → `/naver/cafe` 이동 + **옛 URL 리다이렉트**, `AssistantNavBar` 링크 | 화면 변경은 실브라우저 확인 필요 |
| **B5** | T4연동 37개(믹스인·`_js`·workflow·g2b 엔진 파일) | 37 | T4(local_agent 3→1) 기준서에서 함께 | T3 후 |
| 결정 | 독립앱 28개와 apps↔scripts 복사본 48건 | 28 | 결정 1 | 대표님 |

각 배치 공통 검증: `verify_change`(base 대비 새 문제 0), 영향 시험을 파일 단위로, 층간 위반·순환 0, `module_registry` 동기화.

## 6. 충돌·주의

### 6-1. G5(저장 경계)와 겹치는 4개 — 한 번만 옮긴다
G5 기준서(`docs/architecture/G5_STORAGE_BOUNDARY_PLAN.md`)가 L7 `persistence/`로 보내기로 한 파일이 이 지도의 이탈 목록에도 있다: `scripts/common/youtube_search_cache.py`(youtube, 이동), `connectors/instagram_dm_db.py`(instagram, 폴더화), `connectors/naver_search_db.py`·`naver_search_queries.py`(naver_search, 폴더화). **저장부는 G5에서 persistence로 가고, 도구 집(`connectors/<도구>/`)에는 라우터·클라이언트만 남긴다.** 이 4개는 T3에서 도구 집으로 옮기지 않고 G5 순서(보류 중)를 따른다.

### 6-2. API 집 = `connectors/` vs CLAUDE.md의 L8 = `routers/`
이번 지시는 API 집을 `connectors/<도구>/`로 정했지만 CLAUDE.md 폴더 구조는 "L8 Server API → `ai_orchestrator/routers`"다. 이미 `connectors/` 직속에 `*_router.py` 27개(직속 `.py` 56개)가 평면으로 있고 `routers/`에는 26개(그중 도구 라우터 5개)가 있다. **폴더는 도구 기준, 층은 `configs/module_registry.json` 정본으로 표시**하면 둘이 충돌하지 않는다(CLAUDE.md도 "레이어 배치의 정본은 레지스트리"라고 적었다). 결정 2.

### 6-3. 진행 중인 다른 작업
- `orchestrator_v1/`로 루트 모듈 이동(W1~W3 통합)이 끝난 구조 기준(`5f83b90d`)으로 작성했다. 루트 `hiworks_mail_reader.py`·`kakaowork_reader.py`는 `orchestrator_v1/inbox/` shim과 같은 이름이 있어 shim 제거와 순서를 맞춘다.
- 라우트 파일을 옮겨도 개수는 불변이므로 `configs/route_count_expectation.json`은 건드리지 않는다. 개수가 바뀌는 변경(예: `stage/pending-reject-2`)과 같은 배치에 섞지 않는다.
- `scripts/` 루트 도구 스크립트의 `__file__` 기준 경로·`sys.path` 삽입이 이동 때 깨지기 쉽다. 1단계의 "위치의존 미조정" 검사(`verify_change` 마지막 항목)를 그대로 쓴다.

### 6-4. 이 지도가 보지 못한 것
- 이름에 도구가 없는 파일(공용 CDP 헬퍼, `scripts/*_login*.py` 등)은 도구에 배정되지 않았다. 기반 정리(T1·T4)에서 다룬다.
- 시험 파일 이동은 범위 밖이다(시험은 대상 모듈 이동에 맞춰 import만 갱신).
- 정적 근사 import 건수는 `scripts/` 루트 스크립트의 `python -m`·`subprocess` 호출을 못 본다.

## 7. 재발 방지 게이트 설계 (T2 입력)
1. **도구 집 게이트**: 도구 이름(위 표의 키워드)이 경로에 들어간 **새 파일**이 그 도구의 집 밖(층 표준 위치 제외)에 생기면 차단. 기존 이탈 224건은 기준선(허용 목록)으로 고정하고 처리될 때마다 줄인다. 구현은 `module_registry`의 도메인 라벨·기존 `skeleton_gate`에 얹는 방식을 권한다(새 검사기를 따로 만들지 않음).
2. **중복 함수 게이트**: dupscan(`C:\work\audit-tools\dupscan`)의 구조 동일(AST 동일) 묶음 217건을 기준선으로 고정하고 **새 묶음만 차단**. 시험 코드는 별도 기준선(상용구가 많아 임계를 달리).
3. 두 게이트 모두 R1(화면↔서버 계약)·라우트 개수 정본과 같은 방식(기준선 + 새 위반만 차단)을 따른다.

## 8. 결정 필요
1. **`apps/*` 독립 배포 앱(28개)의 복사본**: (a) 공용 패키지(`haehan_common`)로 묶어 빌드 시 포함 — dupscan이 "독립 코드"로 분류한 25건부터, (b) 독립 유지(복사 허용, 게이트 예외). 권장: **의존성 없는 순수 함수 25건은 (a), 내부 모듈 의존이 있는 것은 (b)** 로 나누어 시작.
2. **API 집의 층 충돌**(§6-2): 폴더는 도구 기준(`connectors/<도구>/`), 층 라벨은 레지스트리로 — 이 안을 승인할지.
3. **층 표준 폴더의 도구별 하위 폴더화**(`services/<도구>/`, `persistence/<도구>/` 등)를 할지(이번 지도는 하지 않는 것으로 작성).
4. **카페 화면 URL 변경**(`/assistant/cafe` → `/naver/cafe`)과 리다이렉트 기간.
5. **`mail_automation.py`(결함 #39, 존재하지 않는 `NaverMail` import)**: 이동하지 않고 폐기할지.
6. 시작 순서: B1(위험 낮음)부터 승인할지, T1(공용 부품)을 먼저 할지(계획서는 T1 먼저).
