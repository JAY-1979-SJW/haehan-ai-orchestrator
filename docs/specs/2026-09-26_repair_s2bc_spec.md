# 구조수리 S2b(선언층 잔여) + S2c(C 6건) 기준서·드라이런 (2026-09-26, 코드 미수정)

측정법: 레지스트리(stage/repair-s2a 의 module_registry.json, 3eb93cad) 층 + allowed_deps, 엣지=data/code_map/map.json import_edges.
재현 스크립트는 scratchpad(v.py/dry.py)이며 읽기 전용. 층 라벨 후보를 얹어 "새 위반이 생기는지"를 파일별로 계산했다(c.py: 후보층별 in/out 위반 수).

**현재(s2a 적용 후) 위반 = 43엣지**(메인 보고 34와 차이는 map.json 이 구버전이라 생긴 것으로 추정 — 실행 직전 `build.py` 재생성 후 재측정 필요).
분류: C 실제 역전 6엣지(5파일군) / B 2 / A 선언층 35.
**드라이런 결과: 아래 라벨 정정만으로 43 → 5** (코드 수정 없이). 남은 5 = C 3건(코드 수정 필요) + site_access·local_agent.py 각 1~2(결정 필요).

allowed_deps: L1→{L1} / L2→{1,2,3,7} / L3→{1,3} / L4→{1,2,3,4,7} / L5→{1..5,7} / L6→{1..7} / L7→{1,7} / L8→{1..8,10}.
핵심 사실: **L7 은 L5 를 못 부르고, L4 는 L5 를 못 부른다.** 그래서 "대상 파일을 하위로 내리는 라벨"이 코드 수정보다 싸다.

---
## 과제 1 — C 6건 (코드가 실제로 거꾸로 부름)

| # | 호출 | 위치 / 이유 | 권장 수정 | 대안 | 위험 |
|---|---|---|---|---|---|
| C1 | site_engine/validators → workflow_runner | validators.py:13 `from ...workflow_runner import WorkflowRunPlan`. 쓰임 = :107 타입 주석 1곳뿐(`from __future__ annotations` 있음, 런타임 사용 0) | `if TYPE_CHECKING:` 안으로 이동(1줄 이동+import 1줄). **동시에 validators·action_planner 를 L2 로 라벨**(C1 해소 + 아래 A-3 의 planner→gate L1→L2 해소) | scanner 가 TYPE_CHECKING import 도 엣지로 세면: `WorkflowRunPlan` 대신 Protocol(`definition`,`steps` 속성만) 을 types.py(L1)에 두고 주석만 교체 | scanner 동작은 실측 필요(worktree 에서 build.py 후 확인). 런타임 영향 0 |
| C2 | local_agent_models → local_agent_registry | models.py:36 `LocalAgent.to_safe()` 안에서 `importlib.import_module("ai_orchestrator.local_agent_registry")` 로 `get_agent_status`/`get_active_task_count` 호출(순환 회피용 late binding) | 의존 주입: models 에 `_registry_hooks` 모듈변수 + `bind_registry(status_fn, active_fn)`; registry 가 import 시점에 `bind_registry(...)` 호출. to_safe 는 hook 사용(미바인딩 시 "unknown"/0 폴백) | to_safe 계산부를 registry_agent 의 `agent_to_safe(rec)` 로 이동 → 호출부 3곳(registry_agent:64, router_registration:172, registration_code_store:712) 교체(더 큼) | 직접 테스트 ai_orchestrator/tests/test_local_agent.py(to_safe), test_local_agent_router_guards.py. 간접 72건. registry 를 안 거치고 models 만 import 하는 경로에서 상태가 폴백값으로 나옴 → 폴백 테스트 필요 |
| C3·C4 | blog_mixin_write → naver/blog selectors, core/writer | :21 `from scripts.naver.blog.page_selectors import (...)`(모듈 top-level), :51·:70 함수 안 lazy import `write_post`/`BlogWriter` | **selectors.py → L1 라벨**(pure 상수, out 0, in = mixin(L4)+writer(L5) → C3 해소, 코드 0). writer 는 L5 유지(out=naver/auth·tag_suggester L5 라 L4 불가): mixin 에 `set_blog_writer_provider(write_post, BlogWriter)` 훅 추가, 부팅 시 L5 쪽(예: scripts/naver/blog/core/__init__ 아닌 local_agent 조립 지점)에서 주입 | blog_mixin_write+blog_mixin(집계) 를 L5 로 라벨하고 상위 조립을 L5/L6 으로 — 상위 importer 가 L4 라 신규 위반 유발(비추) | 직접 테스트: tests/test_module_separation_gate.py(mixin 참조), 간접 114건. 주입 누락 시 blog_write_post 가 실패 → 훅 미주입 예외를 명시 메시지로 |
| C5 | cdp_client → gabia_login_watch | cdp_client.py:582 CLI 분기 `gabia login-watch` 안 lazy import. 사용처 = 이 CLI 한 곳뿐(gabia_login_watch.py 는 자체 argparse `__main__` 보유) | **gabia_login_watch.py → L4 라벨**(out 2 모두 L4 이하, in=cdp_client L4 뿐 → 신규 위반 0, 코드 0) | cdp_client 를 L5 라벨(CLI 디스패처, in=L5 1개) 또는 분기 제거 후 도움말에 `python scripts/gabia_login_watch.py` 안내 | 직접 테스트 tests/test_eum_action_prepare.py, test_eum_router_work.py(둘 다 cdp_client 간접). CLI 문서 문구 유지 |
| C6 | gonobi/db → gonobi/classifier | db.py:144 `reclassify_untagged()` 안 lazy `from .classifier import classify_post`. 호출자 = ai_orchestrator/connectors/gonobi_router.py:124 하나 | **classifier.py → L1 라벨**(순수 키워드 규칙, out 0, in = db L7 + 라우터 L6 → 신규 위반 0, 코드 0) | `reclassify_untagged(conn, limit, classify=None)` 로 분류 함수 주입 후 router 가 넘김(시그니처 확장) | 직접 테스트 없음(gonobi 전용 테스트 미발견) → 라벨 방식이 안전. 간접 34건 |

라우트 영향: C1~C6 전부 라우트 데코 파일 아님 → 288 유지 예상(변경 후 verify_change 라우트 수로 확인).
C 를 라벨로 푸는 게 정당한가: C3(selectors)·C5(gabia_login_watch)·C6(classifier)는 실제 파일 성격(상수 / 로그인 감시 L4 / 순수 규칙)에 맞는 층이라 "위반 숨기기"가 아니라 선언 정정이다.

---
## 과제 2 — A 잔여 선언층 (~35엣지, 라벨만으로 30 해소)

이미 s2a 에서 정정된 15건과 되돌린 4건(discover_valid_public_notice_urls, error_recovery, bulk 등 — 해당 상승이 새 위반을 유발)은 제외. 아래는 **후보층을 실제로 얹어 검증**한 값(신규 위반 0 확인).

| 파일(또는 묶음) | 현재→제안 | 근거(실제 역할·in/out) | 해소 |
|---|---|---|---|
| scripts/_tmp_full_html, _tmp_html_consts2, _tmp_master | L4→L6 | 임시 스크립트, in 0, out=smartstore product(L5). **삭제 후보(목록만)** | 5 |
| hanafax/send_kras_campaign, send_kras_final_campaign | L4→L6 | 발송 실행 스크립트, in 0, out=sender(L5) | 2 |
| video/_upload_kakao_ep01, kakao_skill_bot_ep01_visuals | L4→L6 | 일회성 영상 스크립트, in 0, out=youtube uploader·instagram(L5) | 2 |
| naver/automation/platform/error_recovery, blog/management/schedule, smartstore/product/bulk, youtube/research_search | L7→**L5** | out=사이트 모듈(L5), in=L5 라우터. **L6 은 in(L5)→L6 위반이라 안 됨(s2a 되돌림 사유)**, L5 가 유일 해 | 6 |
| ai_orchestrator/connectors/naver_blog_router.py | L8→L6 | 라우트 데코 0개(APIRouter 카운트 2 는 import 문자열 — 실 등록 여부 재확인 필수), in=CLI 3(L6)+L8, out 5 모두 ≤L6 | 3 |
| local_agent/browser/approval_server.py | L8→L4 | 라우트 없음(데코 0), out=approval_api_client L2, in=secure_login L8·스크립트 L4 | 2 (minwon_submit, webmail_send) |
| local_agent/browser_approval_verifier.py | L2→L1 | out 0 순수 검증. 이러면 L7 저장소→L2 위반 2건이 **allowed_deps 변경 없이** 해소(B 결정 불필요) | 2 (B) |
| scripts/naver/blog/selectors, gonobi/classifier, gabia_login_watch | (C 참조) | 위 C3/C5/C6 | 3 |
| site_engine/action_planner + validators | L1→L2 | planner→execution_gate(L2), validators→planner. in=L2/L6/L11 뿐이라 L2 가 맞다(planner=정책 판정) | 1 + C1 |
| g2b browser_tool 4파일 (dryrun_adapter, execution_gate, local_live_runner, workflow) | L6→**L5**(묶음) | scripts/g2b 2스크립트(L5)가 호출 + 자기들끼리만 L6 의존 → 4개를 함께 L5 로 내려야 신규 위반 0(개별로는 해 없음). g2b **사이트 모듈** 성격과도 일치 | 5 |
| scripts/site_registry.py | L1→L5 | 실체=사이트 레지스트리(auth 5개·live_probe·login_detector 를 부름) | 7 → 그러나 L4 in(site_access, cdp_client) 2 신규 |
| scripts/cdp_client.py | L4→L5 | CLI 디스패처(21 lazy import), in=L5 1개. site_registry L5 화의 신규 위반 해소용 | 1 |
| scripts/form/orchestrator.py | L6→L4 | out 전부 ≤L4, in=site_access(L4) | 1 |
| smartstore/navigation/cdp_popup_manager.py | L5→L4 | out ≤L4, in=L4·L6·L8 | 1 |

**드라이런 합계: 43 → 5.** 남는 5엣지:
1. blog_mixin_write → writer (C4, 코드 주입)
2. local_agent_models → registry (C2, 코드 주입)
3. validators → workflow_runner (C1, TYPE_CHECKING)
4. site_access(L4) → site_registry(L5) — 결정 필요(아래 D1)
5. core/agent_runtime/runtime/local_agent.py(L4) → smartstore form_runner(L6) — 결정 필요(D2)

삭제 후보(**삭제하지 않음, 목록만**): scripts/_tmp_full_html.py, _tmp_html_consts2.py, _tmp_master.py, scripts/temp_oauth_revoke.py(s2a 에서 L6 선언됨), 참고: scripts/execution_gate.py(in 0·out 0, 사용처 없음 — 사용 여부 별도 확인).

---
## 커밋 단위 / 실행 순서

병합·verify_change 는 메인 쪽 s2a 검증이 끝난 뒤 순차 실행. 각 커밋 후 layer_count.py + verify_change --head.
1. **S2b-라벨 1커밋**: 위 표 라벨 정정 전부(overrides.json 에 reason 포함 + `registry_sync.py --fix` 로 module_registry.json 재생성). 코드 0. 예상 43→5(+C3/C5/C6 포함).
2. **C1 1커밋**: validators TYPE_CHECKING 이동(+scanner 확인). 
3. **C2 1커밋**: bind_registry 훅 + test_local_agent 실행 + 폴백 테스트 추가.
4. **C4 1커밋**: blog writer provider 주입 + 미주입 예외.
5. (D1/D2 결정 후) 남은 라벨 또는 코드 1~2커밋.
게이트: 위 커밋마다 codebase_layer_audit, skeleton_gate(라벨 변경 시 registry_sync --fix), pytest 영향 테스트.

## 예상 위반 수 변화
레지스트리 기준 43 → 5(커밋1) → 4(C1) → 3(C2) → 2(C4) → 0~2(D1/D2). PRIMARY(경로 기준) 지표는 라벨 변경으로 변하지 않음(측정 후 확인).

## 위험
- map.json 이 구버전: 43 vs 메인 34 불일치. 실행 전 build.py 재생성·재측정 필수(라벨 후보 전부 재검증).
- L5 로 내리는 error_recovery 등 4개는 L5 유지 시 L7 저장소가 아니게 되는 의미 변화(이름은 persistence 성격) → role 은 유지, layer 만 변경.
- C2/C4 는 주입 방식이라 부팅 순서(registry·writer 가 먼저 import 되어야 함) 의존. 테스트 없이 배포 금지.
- approval_server L8→L4: 라우트 없음 재확인(FastAPI 등록 여부), 288 유지 확인.
- naver_blog_router L8→L6: 실제로 app 에 include 되는지 확인(되면 L8 유지, CLI 3개 쪽을 손봐야 함).

## 사용자 결정 필요
- D1: site_access(L4)→site_registry(L5). 선택: (a) site_access 를 L5 로(in: L4 site_crawler 1 신규) (b) site_registry 의 auth 호출을 지연 주입으로 바꿔 L1 유지(코드) — 추천 (a)+site_crawler L5.
- D2: core/agent_runtime/runtime/local_agent.py(L4)→form_runner(L6) (스마트스토어 로컬 에이전트 진입점). 선택: local_agent.py 를 L6(in: L4 login_session 1·L5 다수 신규 위반 가능) vs form_runner 호출을 주입. 별도 조사 필요 → 이번 범위 밖 권장.
- D3: C5 를 gabia_login_watch L4 라벨(추천) vs cdp_client L5 vs 분기 삭제.
- D4: _tmp_* 3개·temp_oauth_revoke 삭제 승인(`[allow-delete]`, 태그·백업 후).
