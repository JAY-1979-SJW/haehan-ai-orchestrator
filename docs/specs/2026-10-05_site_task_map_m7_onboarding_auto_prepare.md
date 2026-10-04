# 사이트 업무 지도 M7 — 신규 로그인 사이트 등록 · 자동 지도 갱신 · 입력/출력 준비 실행 (기준서, 승인 대기, 코드 없음)

요청(2026-10-05): "처음 로그인한 사이트에서도 일을 할 수 있게 하는 고정 기능을 만들고, 그 사이트의 맵을 만들어 저장하고, 필요하면 자동 탐색되게 하고, AI 가 자동 입력·출력을 하게 하는 기능을 개별로 만들어 API 로 연결해 완성."
전제 문서: `2026-10-03_site_task_map.md`(M1~M4), `2026-10-04_site_task_map_m5_runner.md`(M5), `2026-10-04_site_task_map_m6_business_sites.md`(M6-a; §4 가 M6-b 를 예고).
기존 구현 확인(프로젝트 규칙): `capability_check` 는 키워드로 `site map` 을 못 찾지만 실제로는 `site_task_map*`(domain·persistence·services·routers·scripts/explorer·admin-web)가 있다 — **재사용하고 새로 만들지 않는다.**

## 1. 요구와 현재 상태
| 요구 | 이미 있음 | 비어 있음 |
|---|---|---|
| 처음 로그인한 사이트에서도 일하게 하는 고정 기능 | 지도가 없으면 AI 가 탐색 요청(`sitemap.explore_request`)을 제안하고 사람이 승인 카드를 누르면 읽기 전용 탐색이 시작됨 | 사이트를 **등록하는 고정 절차**가 없다(AI 가 대화 중 제안해야만 시작), 사이트별 정책·상태 기록이 없다 |
| 지도를 만들어 저장 | 호스트별 JSON `data/site_task_map/<host>.json`(구조만 저장, 값 미저장), 분류·위험 등급·검증 상태(`observed/verified/stale`) | — |
| 필요시 자동 탐색 | `stale` 표시와 "재탐색 제안"까지 | **자동으로 다시 탐색**하는 정책·실행이 없다(항상 사람 승인 카드) |
| AI 자동 출력(조회) | M5 `sitemap.run`: read 업무를 지도 절차대로 재생, 결과 표를 요약 | — |
| AI 자동 입력(쓰기·제출) | 없음 — 서버가 read 만 허용 | **최종 버튼 직전까지 입력하고 멈추는 "준비 실행"**(= M6-b) |

## 2. 설계 — 서로 독립인 세 기능(각각 API)
### F1. 사이트 등록(온보딩) — "고정 기능"
**흐름**: 사람이 사이트에 로그인(OTP·인증서·캡차는 사람) → 앱 화면 "사이트 등록"(또는 AI 에게 "이 사이트 등록해")으로 **호스트를 명시** → ① 벤더 공식 API 확인(`vendors.lookup`, 프로젝트 규칙 [0]) ② 등록 레코드 생성 ③ 로그인 상태 읽기 확인(읽기 전용, 브라우저를 시작하지 않음) ④ 최초 탐색 요청 생성(기존 explore request 재사용) ⑤ 승인(등록 때 사람이 한 번 누르면 이 사이트의 최초 탐색 승인으로 갈음) → 지도 저장 → 상태 `ready`.
- 등록 레코드(`data/site_registry/sites.json`, 구조만 — 지도 저장소가 `data/site_task_map/*.json` 전부를 호스트로 취급하므로 별도 폴더): `host`, `auth`, `state`(`registered → exploring → ready → needs_login | blocked`), `auto_explore`(`ask`|`auto`, 기본 `ask`), 한도(일 횟수·페이지 상한), `registered_at`, `last_explored_at`, `last_login_check`.
- **신규 사이트 발견은 사용자 명시 등록으로만 한다.** 백그라운드에서 9222 Chrome 의 탭을 훑어 "새로 로그인한 사이트"를 찾는 방식은 쓰지 않는다(사용자의 다른 탭 열거 금지 원칙, 직전 점검의 Chrome 부작용 사고).
- API(신규, **경로는 `/site-registry`** — `/site-map/{host}` 가 한 단계 경로를 전부 호스트로 받아 같은 접두사를 쓰면 모호): `GET /site-registry`, `POST /site-registry`(등록 + 최초 탐색 요청 + 승인), `GET /site-registry/{host}`, `PATCH /site-registry/{host}/policy`(사람만), `POST /site-registry/{host}/deregister`(등록 해제 — 지도는 지우지 않고 보존).
- AI 허용(읽기): `sites.list`, `sites.get`(`/api/v1/site-registry[/{host}]`). 등록·정책 변경·해제는 AI 에 없다(사람 화면/카드).

### F2. 자동 탐색·갱신
- **트리거(모두 읽기 전용·전용 탭·호스트 고정·한 번에 한 사이트)**: ① 등록 직후 최초 지도 없음 ② 업무가 `stale` 이거나 실패 N회 ③ 마지막 탐색 후 T일 경과 ④ 사용자 "다시 탐색".
- **정책**: 사이트별 `auto_explore` — `ask`(현행: 탐색 요청이 승인 카드로 대기) | `auto`(**사람이 그 사이트에 한해 허용한 경우만** 탐색 요청을 자동 승인, 감사 기록 `actor=auto:policy`). 기본은 `ask`.
- `auto` 에도 지키는 선: 읽기 전용(submit 요소 클릭 금지), 로그아웃·쿠키 삭제 금지, 탐색기는 로그인을 시도하지 않는다 — 로그인이 풀린 것을 읽으면 즉시 중단하고 상태 `needs_login` 으로 두며 사람에게 재로그인을 요청, 캡차·보안 확인 화면을 만나면 즉시 중단(`blocked`), 일일 횟수·페이지 상한·야간 제외 시간은 설정값.
- 구현 방식: **새 백그라운드 루프를 만들지 않는다.** `sitemap.lookup`/`run` 이 부를 때 지연 평가(stale·경과일 판단)하고 정책이 `auto` 면 요청을 만들어 자동 승인한다. 정기 점검이 필요하면 사용자가 기존 예약 작업 화면에 등록한다.
- API(신규): 별도 엔드포인트 없이 기존 `/site-map/explore/requests*` 를 재사용(자동 승인 경로 추가). 정책 변경은 F1 의 `PATCH …/policy`.

### F3. 입력·출력 준비 실행 (M6-b)
- **출력(조회)**: 현행 `sitemap.run`(read) 유지. 입력 매개변수 `{{이름}}` 채우기·결과 표 열 이름 반환도 현행.
- **입력(쓰기·제출)**: `POST /site-map/{host}/prepare` `{task_id, params}` → 전용 새 탭에서 필드를 입력하고 **최종 버튼 직전에서 멈춘다(클릭하지 않는다)**. 입력값은 서버 **메모리에만** 보관(디스크·지도 저장 금지, TTL 30분). 결과: `prepared` 레코드(id, 업무, 입력한 필드 이름과 마스킹된 미리보기, 만료 시각).
- **확정**: 사람이 화면의 **확정 카드**(`[[site-prepare:<id>]]`)에서 `확정`을 눌러야 서버가 같은 입력을 새 전용 탭에서 **재생하고 최종 버튼을 누른다**(상태 유지 의존을 피하려고 재생 방식). 취소·만료는 입력값을 폐기.
- **절대 하지 않는 것(never 목록, 확정 대상에서도 서버가 거부)**: 송금·결제·전자서명·신고 최종 제출·인증서·OTP·비밀번호 입력. 사람이 사이트에서 직접 한다(CLAUDE.md 금지선 유지).
- API(신규): `POST /site-map/{host}/prepare`, `GET /site-map/prepared`, `GET /site-map/prepared/{id}`, `POST /site-map/prepared/{id}/confirm`(사람만), `POST /site-map/prepared/{id}/cancel`(사람만).
- AI 허용: `sitemap.prepare`(준비만)와 `sitemap.prepared`(조회). `confirm`·`cancel` 은 AI 허용 목록에 없다(테스트로 고정).

## 3. 구성(레이어·위치) — 기존 파일을 건드리지 않고 개별 모듈로 추가
| 계층 | 파일(신규) | 역할 |
|---|---|---|
| L1 | `ai_orchestrator/domain/site_registry.py` | 등록 상태 전이·정책 검증·탐색 결과 반영(순수) |
| L1 | `ai_orchestrator/domain/site_task_prepare.py` | 준비 상태(`prepared → confirmed | cancelled | expired`), never 규칙, 마스킹 규칙(순수) |
| L7 | `ai_orchestrator/persistence/site_registry_store.py` | `_sites.json` 원자적 저장 |
| L6 | `ai_orchestrator/services/site_onboarding_service.py` | 등록 절차(공식 API 확인·로그인 읽기 확인·탐색 요청), 자동 탐색 정책 판정(지연 평가) |
| L6 | `ai_orchestrator/services/site_task_prepare_service.py` | 준비·확정·취소·만료(메모리 저장, 실행기는 주입) |
| L3/L4 | `scripts/explorer/task_preparer.py` | 준비/확정 재생 어댑터(전용 탭, 호스트 고정, 최종 버튼 직전 정지) — 기존 읽기 전용 `task_runner.py` 는 수정하지 않는다 |
| L8 | `ai_orchestrator/routers/site_onboarding_router.py`, `site_task_prepare_router.py` | 얇은 HTTP 계층 |
| AI | `mcp_server.API_REGISTRY` | `sites.list/get`, `sitemap.prepare/prepared` 추가(확정·취소·정책·등록은 제외) |
| 화면 | `admin-web/src/app/site-map/` + `components/chat/SitePrepareCard.tsx` | 사이트 등록·정책 토글, 준비 목록, 확정 카드 |
- 새 계층 위반·순환 금지(서비스는 브라우저를 모르고 실행기를 주입), 라우터에 SQL·업무 산식 금지.

## 4. 안전 규칙(직전 앱 실검증의 교훈 반영)
1. **사용자 Chrome(9222)**: 등록·탐색·준비 모두 전용 새 탭만 쓰고 끝나면 그 탭만 닫는다. 사용자의 다른 탭 열거·조작 금지. 상태 확인(등록·`needs_login` 판정)은 **브라우저를 시작하지 않는다**(D7 원칙).
2. 로그인·로그아웃·쿠키·자격증명은 만지지 않는다(읽기 확인만). 로그인이 풀리면 중단하고 사람에게 요청.
3. 저장은 구조만(필드 이름·열 이름·URL 패턴). 입력값·결과 값·개인정보는 지도·로그·감사에 남기지 않는다(준비 값은 메모리 TTL).
4. 호스트 고정(다른 호스트로 이동·리다이렉트 후 조작 금지), 호출 간격·일일 상한, 캡차·보안 확인 감지 시 즉시 중단.
5. 공식 API 가 있으면 화면 조작보다 우선(등록 단계에서 확인). 최종 실행은 사람(확정 카드), never 목록은 확정도 거부.
6. 새 백그라운드 루프·스케줄러를 만들지 않는다.

## 5. 영향
- **새 라우트 약 11개**(등록 5 + 준비 5 + 정책 포함 시 +1): `EXPECTED_RUNTIME_ROUTES`(현재 419)와 라우트 수 기준 시험 6곳(`tests/test_app_*`)을 함께 올려야 한다 — 창 E 가 같은 줄을 고치는 PR 이 있어 병합 순서 조율 필요.
- 기존 API 응답 key·DB·정책 불변(신규 추가만). DB 없음(JSON). 새 .py 약 9개 → `registry_sync --fix`.
- 서버 정책 변경: **쓰기·제출 업무를 사람 확정 하에 실행 가능**(현재는 read 만) — 이 문서의 승인이 곧 그 정책 변경 승인이다.

## 6. 단계와 검증(직렬, 단계마다 기준서→드라이 런→승인→구현→`verify_change`→일반 푸시)
| 단계 | 내용 | 완료 기준(실검증) |
|---|---|---|
| S1 | F1 사이트 등록 + 화면 | 공개 사이트(`www.scrapethissite.com`)를 등록→최초 탐색→지도→AI 가 `sitemap.run`. 로그인 사이트 1곳(사용자 선택)을 사람이 로그인한 뒤 등록→읽기 업무 1건 `verified` |
| S2 | F2 자동 갱신 | 가짜 실행기로 stale·경과일·`needs_login`·`blocked` 시험, 실제 앱에서 `auto` 허용 1곳이 stale 시 자동 재탐색(로그·감사 확인), `ask` 는 카드 대기 |
| S3 | F3 준비 실행 | **가상 양식 사이트(로컬 시험 서버, 외부 영향 0)**에서 준비→확정→입력 반영 확인, never 업무 거부, confirm/cancel 의 AI 비허용 시험. 실사이트는 사용자가 지정한 쓰기 업무 1건을 **최종 버튼 직전까지만**(확정은 사용자가 카드에서) |
- 각 단계 공통: 신규 단위 시험, 영향 시험 기준선 비교(새 실패 0), mypy·ruff·typecheck, 레이어 감사, 실제 앱에서 AI 창으로 지시해 확인, 점검 중 Chrome 프로세스 목록 불변 확인.

## 7. 결정 대기(권장안)
1. **자동 탐색 정책**: 사이트별 기본 `ask`, 사람이 등록 때 `auto` 허용 — 권장. (전 사이트 자동은 사용자 로그인 계정에 반복 접근하므로 비권장.)
2. **신규 사이트 발견**: 사용자 명시 등록 — 권장. (탭 자동 스캔은 사용자 탭 열거 금지 원칙과 충돌.)
3. **입력 실행 범위**: 준비=입력까지, 확정=사람 카드 클릭 시 재생·제출, never 목록 제외 — 권장.
4. **첫 실사이트**: 네이버 카페 / 블로그 / 스마트스토어 중 선택(스마트스토어는 공식 커머스 API 등록이 우선).

## S1 구현 결과 (2026-10-05) — 사이트 등록(F1)
**구현**: L1 `domain/site_registry.py`(`overrides` 로 L1 계약 확정), L7 `persistence/site_registry_store.py`(`data/site_registry/sites.json`), L6 `services/site_onboarding_service.py`(overrides 로 L6 확정), L8 `routers/site_onboarding_router.py`, AI 허용 `sites.list/get`, 화면 `admin-web/src/app/site-map/RegisteredSites.tsx`(사이트 등록·상태·해제, 인라인 2단계 확인 — 브라우저 대화상자 미사용). 기존 `site_task_map*` 파일은 수정하지 않았다(코드 보존).
**라우트**: 5개 추가(GET 2·POST 2·PATCH 1) → `EXPECTED_RUNTIME_ROUTES` 419 → 424, HTTP 417 → 422, POST 193 → 195 와 라우트 수 기준 시험 6곳을 함께 갱신.
**이번 단계에서 하지 않은 것(다음 단계)**: 자동 탐색 `auto`(서비스가 아직 지원하지 않는다고 거부 — 설정만 받고 동작하지 않는 상태를 만들지 않으려는 선택), 로그인 상태 읽기 확인(등록 직후 상태는 탐색 결과로 판정: 로그인 필요 사이트인데 업무 0건이면 `needs_login`(추정), `bot_flagged` 는 `blocked`).
**검증**: 시험 35건(규칙·저장소·서비스·라우터·AI 허용 범위), 린트·mypy·타입체크·ESLint 통과, 레이어 감사 층간 위반 0·순환 80(변화 없음), 계약 audit 424 PASS. 실제 앱: ① API 로 공개 사이트(`www.scrapethissite.com`)를 깊이 1·5쪽으로 등록 → `exploring` → 12초 만에 `ready`(업무 3건) ② 화면에서 인라인 확인으로 해제 → 다시 등록 → `사용 가능`·공식 API 안내 표시 ③ AI 창: `sites.list/get` 로 정확히 답, 등록 요청에는 "등록 도구가 없으니 화면에서 등록하세요"라고 안내, `sitemap.run` 으로 `pages_forms#0` 실행 21행 ④ Chrome 본체 신규 시작 0, 9222 탭 불변, 서버 로그 예외·5xx 0.
**발견**: AI 가 만드는 탐색 요청(`sitemap.explore_request`)에는 `auth` 를 줄 수 없어 로그인 사이트도 `public` 으로 기록된다(기존 한계) — 등록 흐름은 등록할 때 로그인 요건을 선택하므로 해소된다.

### S1 실사이트 검증 — 네이버 카페(로그인 사이트, 2026-10-05)
- **전제 확인**: 읽기 전용 점검으로 `skyjwsin` 로그인(`in`, 계정 확인됨)을 먼저 확인.
- **1차(루트 주소 `cafe.naver.com`, 깊이 1·5쪽)**: 8초에 끝났으나 사이트가 `section.cafe.naver.com` 으로 넘겨 5쪽 중 1쪽만 읽고 업무 0건 — 그런데 등록 상태는 **"사용 가능"** 이었다(등록 호스트의 옛 지도 업무 1건을 보고 판정). 실검증이 잡은 설계 결함 → **수정**: ① 새 상태 `incomplete`(탐색 불완전, 업무 0건) 추가, 실제로 탐색한 호스트(`explored_host`)의 지도로 판정하고 화면에 이동한 호스트의 업무 수를 함께 표시 ② 입력창이 "호스트 또는 사이트 주소"를 받는다고 안내하면서 경로를 버리고 루트로 탐색하던 것을 고쳐, 경로가 있는 주소는 그 경로에서 탐색 시작.
- **2차(실제 카페 주소 `https://cafe.naver.com/0moo`, 깊이 1·5쪽)**: 20초, 업무 **17건**(전부 읽기 등급: 이동·검색), 4쪽 읽음, 캡차·봇 감지 없음.
- **AI 실행(전체 연쇄)**: AI 창이 `sites.get` 으로 상태·업무 수를 정확히 답하고, 검증된 조회 업무 `0moo#0_frmboardsearch` 를 검색어 "공무" 로 실행해 열 5개(제목·제목(2)·작성자·작성일·조회수)와 15행을 반환 — **입력(검색어)과 출력(결과 표)을 로그인한 네이버 카페에서 AI 가 수행**.
- **안전**: 탐색·실행 중 Chrome 본체 신규 시작 0, 9222 탭 불변, 서버 로그 예외·5xx 0, 로그인 유지(실행 직후 첫 확인만 `unknown` 이고 곧 `in` — 자동화 직후의 일시적 읽기 실패이므로 **S2 는 `unknown` 한 번으로 `needs_login` 을 판정하면 안 된다**).
- **알려진 한계(후속)**: ① 17건 중 실질 업무는 2~3건 — 같은 상단 메뉴 버튼이 하위 화면마다 "(전체글보기,…)" 접미사로 반복 저장되고 이름에 줄바꿈·화면 수치("362만 인용")가 섞인 항목이 있다(탐색기의 이름 정리·중복 제거 필요) ② 글쓰기 같은 **입력 업무는 발견되지 않았다**(편집기가 iframe·별도 주소) — S3(준비 실행) 전에 글쓰기 화면 주소로 탐색 범위를 지정해야 한다.
