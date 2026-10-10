# 신규 사이트 온보딩 파이프라인 — 처음 지정한 사이트도 탐색·지도·업무까지 (기준서, 승인 대기, 코드 없음)

요청(2026-10-05, 사용자 최우선): "내가 처음 제시하는 사이트여도 사이트를 탐색하고 맵을 만들고 업무를 할 수 있게 개발… 처음 지정한 사이트여도 탐색하고 일을 해야 해." + "작업한 것을 저장하고 재호출해서 다시 사용되게(Claude 웹처럼)."
전제: `2026-10-03_site_task_map.md`(M1~M4)·`…_m5_runner`·`…_m6_business_sites`·`…_m7_onboarding_auto_prepare`(F1 사이트 등록)·`…_site_map_link_read_tasks`(M8)·`…_site_map_m9_precise_exploration`(M9).
작업 기록 저장소(작업→단계→산출물, 검색·재호출)는 ea 의 `2026-10-05_work_record_store.md` 가 정본 — 이 문서는 **인터페이스만** 정의한다(§6).

## 1. 결론 먼저 — 대부분 이미 있다
실사이트 접촉 없이 코드·문서를 읽어 확인한 현황. **새로 짜지 않고 아래 빈칸만 채운다.**

| 단계 | 이미 있음(재사용) | 비어 있음(이 기준서가 채움) |
|---|---|---|
| 0 사전 조사(공식 API·robots·sitemap) | 등록 시 `vendors.lookup`(읽기, 목록에 없으면 "미조사") | **목록에 없을 때 조사하고 기록하는 절차**, robots.txt·sitemap.xml·약관 링크 판독, `site_compliance_policy`(`browser_tool/`)를 탐색기에 연결 |
| 1 등록 | `POST /site-registry`(M7 F1: 상태 `registered→exploring→ready→needs_login|blocked`, 정책 `ask|auto`) | **로그인 불필요 사이트**(공개 URL) 경로 — 현재 등록은 "사람이 로그인한 사이트" 전제 |
| 2 탐색 | `scripts/explorer`(page_snapshot·auto_explorer·task_mapper·data_sources), 승인 카드, 전용 탭, 읽기 전용, M8 메뉴 색인·M9 데이터 소스·WebMCP 탐지 | robots/sitemap.xml 을 **시작점·허용 범위**로 쓰기, 요청 간격 상한 |
| 3 지도 | `data/site_task_map/<host>.json`(구조만, 값 없음) | **지도 이력·변경 감지(diff)·버전 고정**(현재는 최신 한 벌 + `stale` 표시뿐) |
| 4 업무 후보 | 분류 `read/write/submit`·위험 등급·`site_engine/capability_detector`(키워드) | **DELETE·PAYMENT·전자서명 등 never 분류**를 지도 업무에 부여(현재 3단계) |
| 5 업무 개발 | `sitemap.run`(읽기 재생), M6-b 설계(준비→확정 카드, 사용자 승인 대기) | **"이 사이트에서 할 수 있는 일" 목록 → 업무 명세(task spec) 생성·검토** 흐름 |
| 6 저장·재호출 | `site_task_map_store`·`site_registry_store`, 탐색 요청 저장소 | ea 작업 기록 저장소와 **키·버전 연결** |

## 2. 목표·범위
- 입력: **임의의 URL/호스트 하나**(사용자가 처음 제시). 출력: 지도 + 업무 후보 목록 + 사용자가 고른 업무의 명세·드라이런·승인 후 실행 기록.
- **사이트별 하드코딩 금지** — 자동 프로필(`SiteProfile`)은 탐색 결과로 생성한다. 사이트 전용 셀렉터는 지도에 "후보+신뢰도"로만 둔다.
- 범위 밖: 쓰기·제출의 실제 실행 허용(M6-b, 사용자 명시 승인 별도), 로그인·OTP·캡차(사람), 투찰·전자서명·송금·결제 자동 실행(영구 금지).

## 3. 파이프라인(단계와 게이트)
```
[사용자: URL/호스트 지정]
  ① 사전 조사(읽기, 브라우저 없음)  ─ 공식 API? robots/sitemap/약관? compliance 판정
        ├ 공식 API 있음 → "API 로 개발" 분기(CDP 금지, §4) ─▶ 종료(또는 API 업무로 연결)
        └ blocked(robots·약관 금지) → 중단·보고
  ② 등록(공개/로그인 구분)  ─ 로그인 필요 → 사람이 로그인(필요 시 needs_login)
  ③ 탐색 승인 카드(사람 1회)  ─ 읽기 전용·전용 탭·호스트 고정·속도 제한
  ④ 탐색 → 지도 저장(+ 이력 한 건, 이전 지도와 diff)
  ⑤ 업무 후보 분류(read/write/submit/never) → 사용자에게 "할 수 있는 일" 목록
  ⑥ 사용자가 업무 선택 → 업무 명세 생성(입력·단계·성공/실패 판정·되돌릴 수 없는 지점·승인 지점)
  ⑦ 드라이런(read 만 실제 실행, write·submit 은 입력 직전까지 시뮬레이션 — M6-b 승인 전에는 계획만)
  ⑧ 사용자 승인 → 실행 → 감사 기록(+ 작업 기록 저장소)
```
- read 업무는 ⑥~⑧ 이 지금도 동작(M5). write·submit 의 실제 실행은 M6-b 승인 후에만.

## 4. 안전 정책(필수 — 기존 규칙 그대로, 새 사이트 기본값 포함)
1. **처음 보는 사이트 기본 = 읽기 전용 탐색만.** 클릭은 내비게이션성만(제출·삭제·결제·전송·업로드 금지, submit 요소 클릭 금지 — 현행 탐색기 규칙).
2. **벤더 공식 API 우선(CLAUDE.md [0])**: ① 단계에서 `configs/vendor_apis.json` 조회 → 있으면 API 로 분기. 없고 "미조사"면 **조사 절차**(공식 개발자 문서 검색 → 결과를 `vendor_apis.json` 에 `status: researched|none` 으로 추가, 근거 URL 포함)를 거친 뒤에만 CDP 로 간다. 조사 결과 기록은 **코드 변경 승인 대상**(설정 파일 편집).
3. **로그인은 사용자만**(OTP·캡차·인증서). 탐색기는 로그인을 시도하지 않고, 풀린 것을 읽으면 즉시 중단 `needs_login`. 로그아웃·쿠키 삭제·쿠키/세션 추출 금지, 비밀값(필드 값·토큰) 비수집, 비밀번호·카드·주민번호류 입력란은 지도에 **민감 표시만** 남기고 값·셀렉터 후보 외 정보 없음.
4. **robots.txt·약관(site_compliance)**: 금지 경로는 탐색 대상에서 제외, 사이트 전체 금지면 `blocked`. 요청 간격·일일 페이지 상한을 정책으로(기본값 보수적, 사이트별 조정은 사람만).
5. **위험 capability 는 항상 사람 승인**: write·submit 는 확정 카드, DELETE·PAYMENT·전자서명·송금·투찰·OTP 는 **never**(서버 거부, 사람이 사이트에서 직접).
6. **사용자 Chrome(9222) 보호**: 전용 새 탭만, 호스트 고정, 끝나면 그 탭만 닫음(마지막 탭 보호·창 복원은 `CDP_BROWSER_POLICY` 준수), 사용자의 다른 탭 열거·조작 금지.
7. 캡차·보안 확인·차단(HTTP 403/429)·예외 감지 시 **즉시 중단·보고**, 재시도는 사람이 정한다.
8. 백그라운드 신규 사이트 발견(탭 훑기) 금지 — **사용자 명시 지정으로만 시작**.

## 5. 데이터 모델
- **지도 JSON**(현행 `data/site_task_map/<host>.json`, `version`=스키마 버전)에 **키 추가만**(기존 키·응답 불변): `source`(시작 URL·출처 `robots|sitemap|crawl|manual`), `explored_at`, `map_rev`(정수, 탐색 저장마다 +1), `fingerprint`(구조 해시: 메뉴·업무 목록·폼 필드 이름 — 값 없음), 업무별 `capability`(`read|write|submit|never:<delete|payment|signature|otp|…>`)·`sensitive_fields`(이름만)·`selector_confidence`.
- **이력**: 지도 파일은 최신 한 벌 유지, 이력은 **별도 파일** `data/site_task_map/_history/<host>/<map_rev>.json`(구조만, 용량 상한·최근 N개 보존). 비밀·값 비저장 규칙 동일.
- **변경 감지(diff)**: `diff(map_rev_a, map_rev_b)` → 추가·삭제·변경된 메뉴/업무/폼 필드 이름, 업무별 `stale` 후보. 순수 함수(L1).
- 업무 명세(task spec, 지도 업무에 연결): `task_key`, `map_rev`(**기준 지도 버전 고정**), 입력(이름·유형·민감 여부), 단계, 성공/실패 판정, `irreversible_at`(되돌릴 수 없는 단계), `approval_points`, 위험 등급. 입력 값은 저장하지 않는다(실행 시 메모리 TTL — M7 F3).

## 6. 작업 기록 저장소(ea)와의 인터페이스 — 이 문서는 이 부분만 정의
| 이 파이프라인 산출물 | 저장 단위·키(제안) | ea 저장소가 맡을 것 |
|---|---|---|
| 탐색 결과(지도) | 작업 `site.onboard:<host>` 의 단계 `explore`, 산출물 `map:<host>@<map_rev>` (지도 본문은 기존 저장소, 기록에는 **참조(host,map_rev,fingerprint)만**) | 작업→단계→산출물 모델, 검색, 재호출 목록 |
| 업무 명세 | 산출물 `task_spec:<host>/<task_key>@<map_rev>` | 〃 |
| 드라이런/실행 결과 | 단계 `dry_run`, `run` — 결과 요약·행 수·성공 여부(값 비저장) | 〃, 이어서 하기·재실행 |
- (a) **저장 위치 분담**: 지도·이력·업무 명세는 기존 `site_task_map_store`(L7)에 그대로, 작업 기록은 ea 저장소가 **참조만** 보관 → 중복 저장 없음.
- (b) **"지난번 탐색한 사이트" 재호출**: `host` 로 최신 `map_rev` 조회 → 만든 지 `T`일 이내면 재사용, 지나면 "재탐색 제안"(승인 카드). 재탐색하면 새 `map_rev` + diff 보고(바뀐 업무는 `stale`).
- (c) **재실행·이어서 하기**: 작업 기록이 `map_rev` 를 기억 → 재실행 시 **같은 `map_rev` 로 고정**하고, 현재 최신과 `fingerprint` 가 다르면 "지도가 바뀜 — 재탐색 후 진행?"을 사람에게 묻는다(자동으로 최신을 쓰지 않음).
- ea 기준서 요약이 오면 위 키·참조 형식을 대조해 맞춘다(열린 질문 Q4).

## 7. 구성(레이어·위치) — 기존 파일은 건드리지 않고 모듈 추가
| 계층 | 파일(신규, 제안) | 역할 |
|---|---|---|
| L1 | `ai_orchestrator/domain/site_preflight.py` | 사전 조사 결과 모델·판정(공식 API/robots/sitemap/compliance → `proceed|use_api|blocked`), robots 규칙 해석(순수) |
| L1 | `ai_orchestrator/domain/site_map_history.py` | `map_rev`·fingerprint·diff(순수) |
| L1 | `ai_orchestrator/domain/site_task_spec.py` | 업무 명세 검증·never 분류·승인 지점(순수) |
| L7 | `ai_orchestrator/persistence/site_map_history_store.py` | 이력 파일 저장(원자적, 상한) |
| L3 | `scripts/explorer/preflight_fetch.py` | robots.txt·sitemap.xml 조회(단순 GET, 브라우저 없음, 호스트 고정·간격 제한) |
| L6 | `ai_orchestrator/services/site_preflight_service.py`, `site_task_spec_service.py` | 사전 조사 → 등록 연결, 명세 생성·검토 |
| L8 | 기존 `site_onboarding_router`·`site_task_map_router` 에 라우트 추가(약 5개: preflight, history, diff, spec 생성/조회/승인) | 얇은 HTTP |
| AI | `mcp_server.API_REGISTRY` 에 `sites.preflight`·`sitemap.diff`·`sitemap.spec`(읽기·초안만) | 확정·정책 변경은 제외 |
| 화면 | `admin-web/src/app/site-map/` | 사전 조사 결과·"할 수 있는 일" 목록·diff·명세 검토 |
- 레이어 정본은 `configs/module_registry.json`(+overrides): L1 모듈은 `registry_sync` 가 L4 로 오분류하므로 override 를 함께 추가. 라우터에 SQL·산식 금지, 도메인 간 직접 import 금지(서비스가 어댑터 주입).
- 기존 변경이 필요한 곳(최소): `task_mapper.explore_to_map`(저장 시 `map_rev`·fingerprint·이력 호출), `site_onboarding_service.register`(사전 조사 연결·공개 사이트 `auth: none`), 위험 분류(`never` 부여).

## 8. 단계(M번호)·산출물·위험·되돌리기
| M | 내용 | 산출물 | 위험 | 되돌리기 |
|---|---|---|---|---|
| M10 | 사전 조사(공식 API·robots·sitemap·compliance) + 등록 연결 + 공개 사이트 경로 | L1/L3/L6 모듈, 라우트 +2, 화면 카드 | 외부 GET(robots·sitemap)만 — 읽기, 호스트 고정 | 모듈 추가뿐 → 되돌리기 쉬움 |
| M11 | 지도 `map_rev`·이력·diff·버전 고정 + ea 인터페이스 | L1/L7 모듈, 라우트 +2, 저장 키 추가 | 파일 용량(상한으로 제한) | 신규 폴더만 삭제 |
| M12 | never 분류 + "할 수 있는 일" 목록 + 업무 명세 생성·검토(read 는 기존 실행) | L1/L6 모듈, 라우트 +2 | 분류 오판 → never 쪽으로 기울임(보수적) | 분류 규칙 파일 |
| (별개) M6-b | write·submit 준비 실행 — **사용자 명시 승인 후** | 기존 M7 F3 | 서버 정책 변경 | 기능 플래그 |
- 단계마다 기준서 → 드라이런 → 승인 → 코드, 병합 후 다음 단계.

## 9. 영향
- 새 라우트 약 6개(`EXPECTED_RUNTIME_ROUTES`·라우트 수 시험 갱신 필요 — 창 E 와 조율), 새 .py 약 9개(`registry_sync --fix` + L1 override), DB·schema 없음(JSON), 기존 응답 키 불변(추가만), 보안 정책 약화 없음(읽기 전용 기본·never 강화).
- 외부 접촉: ① 사전 조사의 robots.txt/sitemap.xml 단순 GET, ② 공식 API 조사(공식 개발자 문서 검색 — 유료 AI API 아님). 실사이트 탐색은 사용자가 승인한 1곳.

## 10. 검증 계획
- **합성 로컬 사이트**(정적 서버 fixture + 페이지 몇 개: 메뉴·폼·robots.txt·sitemap.xml·금지 경로·로그인 필요 페이지)로 ①→⑦ 전 과정을 시험. 브라우저는 시험 전용 headless(`tests/headless_browser.py` 픽스처 재사용), **9222 무관**(루트 `conftest.py` 가드가 막음).
- 단위: robots 해석·fingerprint·diff·never 분류·명세 검증(순수 함수) — 브라우저 불필요.
- 실사이트: **사용자가 승인한 사이트 1곳에서 읽기 전용으로만**. 이 PC 에서 CDP/browser 계열 영향 시험은 가드 'after' 승인 전까지 실행하지 않는다.
- 게이트: layer/cycle/security audit, audit-kit std, `verify_change`.

## 11. 드라이런(코드 변경 없는 시뮬레이션 — 이번 조사 기준)
- 변경 파일 예상: 신규 약 9개(.py) + 라우터 2개 편집 + `task_mapper`·`site_onboarding_service` 소규모 편집 + 화면 3~4개 + 시험 약 7개 + 문서.
- 게이트 예상: 레이어 — 서비스는 어댑터(`preflight_fetch`)를 주입받으므로 L6→L3 직접 import 없음(위반 0 예상). registry — 신규 L1 모듈 override 필요(과거 동일 사례로 처리 방법 확인됨). 라우트 잠금 — +6 갱신.
- 사이드 이펙트 예상: 없음(읽기 전용 추가). 기존 `data/site_task_map/*.json` 은 `map_rev` 가 없으면 0 으로 간주해 호환.
- 실행한 점검: 기존 구현 목록 대조(위 §1), 기존 지도 9개 호스트 확인(실사이트 접속 없음).

## 12. 열린 질문(추측하지 않고 사용자 결정 필요)
- Q1. **공개(로그인 불필요) 사이트**도 이 파이프라인 대상인가, 로그인 사이트만인가? (제안: 둘 다, 공개 사이트는 `auth: none`)
- Q2. 사전 조사에서 robots.txt 가 **전체 금지**인 사이트는 사용자 지시가 있어도 `blocked` 로 둘까, 사용자 명시 허용으로 풀 수 있게 할까? (제안: 기본 blocked, 풀기는 사용자 명시 + 사이트 약관 확인 기록)
- Q3. 공식 API 조사 결과를 `configs/vendor_apis.json` 에 **자동 추가**해도 되나(제안: 초안만 만들고 사람이 확정)?
- Q4. 지도 재사용 기한 `T`(제안 7일)와 이력 보존 개수 N(제안 20)은 이 값으로 할까?
- Q5. 업무 명세는 사용자가 **직접 입력 필드·성공 판정을 고치는 화면**이 필요한가, AI 초안을 승인만 하면 되는가?
- Q6. 작업 기록 저장소 키(§6)는 ea 기준서와 대조해 확정 — ea 요약 도착 후.

## 13. 드라이런 결과(2026-10-05, 파일·설정·registry 변경 없음 — 문서에만 기록)
### 13.1 예상 diff와 레이어 정적 확인
`configs/module_registry.json` 정본 `allowed_deps` 기준(L1→L1 / L3→L1,L3 / L7→L1,L7 / L6→L1~L7 / L8→L1~L8·L10). 기존 유사 모듈의 실제 배치: `domain/site_map_menu.py` L1, `persistence/site_task_map_store.py` L7, `services/site_task_map_service.py` L6, `routers/site_onboarding_router.py` L8, `scripts/explorer/task_mapper.py` L6, `scripts/explorer/data_sources.py` L4, `browser_tool/site_compliance_policy.py` **L2**.

| M | 신규 파일 | 레이어 | 책임 | 허용 import(통과 근거) |
|---|---|---|---|---|
| M10 | `ai_orchestrator/domain/site_preflight.py` | L1 | 사전 조사 모델·robots 해석·`proceed/use_api/blocked` 판정 | L1 만 — 표준 라이브러리·다른 domain 만 사용 |
| M10 | `scripts/explorer/preflight_fetch.py` | **L3**(registry 가 L4 로 분류하면 override) | robots.txt·sitemap.xml 단순 GET(호스트 고정·간격 제한) | L3→L1 만 |
| M10 | `ai_orchestrator/services/site_preflight_service.py` | L6 | 공식 API 조회(`vendors`)·compliance(L2)·fetch(L3) 결합, 등록 연결 | L6→L1·L2·L3·L7 허용 |
| M11 | `ai_orchestrator/domain/site_map_history.py` | L1 | `map_rev`·fingerprint·diff(순수) | L1 |
| M11 | `ai_orchestrator/persistence/site_map_history_store.py` | L7 | 이력 파일 원자적 저장·상한 | L7→L1,L7 만(서비스·라우터 import 금지) |
| M12 | `ai_orchestrator/domain/site_task_spec.py` | L1 | 업무 명세 검증·never 분류·승인 지점 | L1 |
| M12 | `ai_orchestrator/services/site_task_spec_service.py` | L6 | 명세 생성·검토·승인 기록(작업 기록 저장소 호출은 best-effort) | L6 |
| M10~12 | 기존 `site_onboarding_router.py`·`site_task_map_router.py` 에 라우트 추가 | L8 | 얇은 HTTP, `require_role` 적용 | L8→L6 |
| M10~12 | 기존 `site_onboarding_service.register`(사전 조사 연결·`auth: none`), `task_mapper.explore_to_map`(저장 시 `map_rev`·fingerprint·이력) 소규모 편집 | L6 | — | 기존 import 유지 |
- 새 라우트 **6개**(preflight 조회·실행 2, 이력 목록·diff 2, 명세 생성/조회·승인 2 → 정확한 수는 구현 때 확정, 잠금값 425→431 예상). 새 .py **7개**(위 표) + 시험 파일 약 7개. 위 표의 모든 import 는 `allowed_deps` 안 → **FORBIDDEN_IMPORT 0 예상**.
- 주의 1: L1 은 L1 만 import 가능하므로 compliance(L2)·`vendors`·fetch 는 **서비스(L6)에서 결합**하고, L1 은 결과를 받아 판정만 한다.
- 주의 2: L7 이력 저장소는 순수 데이터(L1 모델)만 받는다 — 서비스 역방향 import 없음.
- 주의 3: 신규 L1 모듈은 `registry_sync --fix` 가 L4 로 놓을 수 있어 `module_registry.overrides.json` 에 L1/L3 override 를 함께 추가(M8·M9 에서 같은 방식으로 처리한 사례 있음).

### 13.2 합성 로컬 사이트 fixture 와 시험 목록(설계만 — 작성·실행 금지)
- **fixture**(정적 서버, 시험 프로세스 안에서 `127.0.0.1:임의포트`, 실사이트·9222 접속 없음): `/`(공개 메뉴: 소개·목록·문의), `/list`(표), `/contact`(폼: 이름·이메일·**메시지** + 제출 버튼), `/admin`(로그인 필요 → 로그인 폼으로 리다이렉트), `/private/…`(robots.txt 가 금지), `/danger`(삭제 버튼·결제 버튼 포함), `/robots.txt`, `/sitemap.xml`.
- 브라우저는 시험 전용 headless(`tests/headless_browser.py` 의 `browser` 픽스처), 순수 함수 시험은 브라우저 없음.

| 시험(제안 이름) | 검증 항목 | 브라우저 |
|---|---|---|
| `test_preflight_decisions` | 공식 API 있음→`use_api`, robots 전체 금지→`blocked`, 일부 금지→`proceed`+제외 경로, 미조사→"조사 필요" | 없음 |
| `test_robots_parser` | Disallow·Allow·와일드카드·Crawl-delay 해석, sitemap.xml 주소 추출 | 없음 |
| `test_preflight_fetch_host_pinned` | 다른 호스트로 리다이렉트하면 중단, 간격 제한, 응답 크기 상한 | 없음(로컬 서버) |
| `test_explore_respects_robots` | `/private/…` 를 방문하지 않음, sitemap 주소를 시작점으로 사용 | 있음 |
| `test_explore_readonly_never_clicks_submit` | 제출·삭제·결제 버튼 클릭 0(서버 요청 로그로 확인) | 있음 |
| `test_map_marks_login_required_and_sensitive_fields` | `/admin` 은 로그인 필요 표시, 민감 필드는 이름만 | 있음 |
| `test_task_capability_never_for_delete_payment` | 삭제·결제 버튼 업무가 `never`, 폼 제출은 `submit`, 목록은 `read` | 있음 |
| `test_map_rev_and_diff` | 재탐색 시 `map_rev`+1, 메뉴 추가·폼 필드 삭제를 diff 가 보고, 값은 저장 안 됨 | 있음 |
| `test_rerun_pins_map_rev` | 지도가 바뀌면(fingerprint 불일치) 실행 전에 "지도가 바뀜" 반환, 자동으로 최신 사용 안 함 | 없음 |
| `test_task_spec_requires_approval_points` | 명세에 `irreversible_at`·`approval_points` 없으면 거부, never 업무는 명세 생성 불가 | 없음 |
| `test_public_site_registration` | `auth: none` 등록, 상태 전이 | 없음 |
| `test_router_requires_role_and_additive_keys` | 신규 라우트 `require_role`, 기존 응답 키 불변·추가만 | 없음 |
- 기존 시험 재사용: `tests/test_site_map_menu.py`·`test_site_map_sources.py`(합성 SPA 서버 패턴)·`test_task_runner.py`.

### 13.3 기존 시험·API·DB 영향(없음 근거)
- **DB·schema**: 없음 — JSON 파일만(`data/site_task_map/…`, 새 폴더 `_history`). 지도 스키마 `version` 불변, 키 추가만 → `site_task_map.load` 는 `map_rev` 가 없으면 0 으로 간주(구 지도 9개 호환).
- **기존 응답 key**: `site_task_map_service.lookup`·`/site-map`·`/site-registry` 응답은 키 **추가만**(기존 키 이름·의미 불변) — 기존 시험이 키 존재만 확인하므로 영향 없음(구현 때 `test_site_task_map_service.py`·`test_site_task_map_router*` 재실행으로 증명).
- **영향 받는 시험**: 라우트 수 기준 시험(`tools/audits/backend/audit_backend_runtime_contract.py` 의 `EXPECTED_RUNTIME_ROUTES` 와 `tests/test_app_*` 에 하드코딩된 값 — 창 E 가 조율 중인 3건과 같은 줄) — 구현 PR 에서 함께 갱신. 그 외 영향 없음.
- **보안 정책**: 완화 없음 — 읽기 전용 기본, never 강화. 외부 접촉은 robots.txt/sitemap.xml 단순 GET 뿐.

### 13.4 게이트 통과 예상
| 게이트 | 예상 | 근거 |
|---|---|---|
| layer audit(FORBIDDEN_IMPORT·CIRCULAR·SECURITY) | 0·0·0 | §13.1 import 는 모두 `allowed_deps` 안, 서비스가 L2·L3 결합 |
| quality gate(--staged --enforce) | errors 0 | 새 코드, 비밀 출력·docker·DB 접근 없음, SECURITY_PATTERN 문자열 없음(쿠키·세션 미접근) |
| skeleton gate(지도↔골격) | override 추가 후 PASS | `registry_sync --fix` 로 정본 맞춤 |
| audit-kit std | 새 문제 0 | 새 모듈 크기·복잡도 분리, M8·M9 때와 같은 규칙 준수 |
| verify_change | PASS 예상 | 영향 시험 중 라우트 수만 갱신 필요 |
- 구현 시 코드 길이: 함수 분리(C901)·모듈 전역 대입 금지·시험 픽스처 공용 사용 — 기존 지적 정리 때 확인한 패턴 적용.

### 13.5 열린 질문별 권장 답안(사용자가 "권장대로"만 답해도 되게)
| 질문 | 권장 |
|---|---|
| Q1 공개(로그인 불필요) 사이트도 대상? | **예** — 공개 사이트는 `auth: none` 으로 같은 파이프라인(읽기 전용) |
| Q2 robots.txt 가 사이트 전체를 금지? | **기본 `blocked`**, 풀려면 사용자 명시 + 약관 확인 기록(자동 해제 없음) |
| Q3 공식 API 조사 결과를 `vendor_apis.json` 에 자동 추가? | **초안만 만들고 사람이 확정**(설정 파일은 승인 대상) |
| Q4 지도 재사용 기한·이력 보존? | **7일 / 최근 20개**(설정값, 사이트별 조정은 사람만) |
| Q5 업무 명세 편집 화면? | **1단계는 AI 초안을 승인만**, 편집 화면은 후속 단계(M12 이후) |
| Q6 작업 기록 저장소 키 | ea 기준서 대조 후 확정 — 6a 쪽 제안: `map:<host>@<rev>`, `task_spec:<host>/<task_key>@<rev>`, 지도 스냅샷 중복 저장 없이 이력 파일 경로+sha256 참조 |

## 14. 확정 사항(2026-10-05, 사용자 승인 "권장대로 승인하니 진행해" · 창 E 조율)
- Q1~Q5 는 §13.5 권장 답안대로 확정. Q6: 작업 기록 저장소(WRS, ea) 키는 job `site.onboard:<host>`·step `explore|dry_run|run`·산출물 `map:<host>@<map_rev>`·`task_spec:<host>/<task_key>@<map_rev>` 로 확정.
- 업무 식별자는 문서·WRS 에서 **`task_key`** 로 통일한다(감사 로그의 `task_id` 와 의미가 달라 혼동 방지). 지도 JSON 안의 기존 필드 이름은 바꾸지 않는다(응답 키 불변) — `task_key` 는 그 값(지도 업무의 기존 식별자)을 가리키는 문서·저장소 쪽 이름이다.
- compliance(L2 `site_compliance_policy`) 해석: 미지의 사이트 기본 정책이 `NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL` 이라 이를 **하드 차단으로 쓰면 신규 사이트가 전부 막힌다.** 사용자가 사이트를 명시 지정·등록하는 것이 승인이므로, 사전 조사에서 compliance 는 **안내(advisory)** 로 싣고, 하드 차단은 `AUTOMATION_BLOCKED` 로 명시된 경우와 robots 전체 금지뿐이다.
- robots.txt 조회 실패: 404 는 "제한 없음", 5xx·접속 불가는 RFC 9309 에 따라 **판정 보류(blocked, 재시도 안내)**.
