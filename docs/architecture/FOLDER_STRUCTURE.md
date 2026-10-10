# 프로그램 폴더 구조 설계서 (목표 구조 + 실행 순서)

- 작성: 지휘창 skyjw-64 · 2026-10-07 19:50 · 지시: 대표님 "프로그램 폴더 설계를 해서 구조 변경해"
- 측정 기준: stage/integrate-3 `45c6c811` (PR 3 = 도구 분리 반영본)
- 관계: 도구별 집은 `docs/architecture/TOOL_HOME_MAP.md`(G11 게이트로 강제) — **이미 확정**. 이 설계서는 그 위의 **기반(공용) 코드와 최상위 폴더**를 정한다.

## 0. 현재 문제 (실측)
| 위치 | 상태 | 문제 |
|---|---|---|
| `scripts/` 최상위 | `.py` **109개** 평면 | 브라우저·CDP(12)·navigator(8)·page_helper(7)·popup(4)·로그인·품질 게이트(8)·설정·로그가 한 폴더에 섞임 |
| `ai_orchestrator/` 최상위 | `.py` **58개** 평면 | 그중 `local_agent_*` **33개**(서버 쪽 에이전트 관리)가 평면, LLM·MCP·텔레그램·작업 실행이 섞임 |
| 저장소 루트 | shim **30개** + `app.py`·`conftest.py` | 1단계 분리(orchestrator_v1) 후 남은 호환 파일 |
| 최상위 소형 패키지 | `adapters/`3 `agent/`5 `browser_api/`3 `browser_worker/`8 `notice_radar/`8 `services/`(빈 폴더) | 소속 불명, 일부 미사용 의심 |
| local_agent 3벌 | `local_agent/`51 · `ai_orchestrator/local_agent/`116 · `scripts/local_agent/`21 | 이름 같고 역할 겹침 (T4) |
| 도구 집 | `scripts/<도구>/` · `connectors/<도구>/` · 화면 | G11 게이트로 관리 중(기준선 103건, 줄이기만) |

## 1. 목표 구조
```
(repo)
├─ ai_orchestrator/            서버(API·승인·작업·감사) — 진입점 asgi.py·router.py·config.py·app.py 만 최상위
│  ├─ core/                    models, task_state, execution_limits, logging_setup (공용 기반)
│  ├─ llm/                     app_llm, openai_client, openai_guard, planner
│  ├─ mcp/                     mcp_server, mcp_tool_names
│  ├─ notify/                  telegram_notifier, telegram_webhook, alert_classifier
│  ├─ tasks/                   executor, web_task_templates, external_work_registry, inbox, chat_sessions, registration_codes
│  ├─ agent_hub/               (서버 쪽 에이전트 관리) local_agent_router*·registry*·*_policy·diagnostics 33개 → router/·registry/·policy/  ※ T4 결정과 함께
│  ├─ audit/                   감사 로그 정본(잎) — audit_logger + orchestrator_v1 사본 통합 (T1, 내일)
│  ├─ paths/  gates/  routers/  connectors/<도구>/  services/  workflows/  persistence/  domain/  sites/  contracts/  server/  (유지)
├─ scripts/                    도구 구현 + 기반
│  ├─ common/                  config, logger, op_log, critical_logger, realtime_audit, security, schemas, gate, publish_guard, app_paths(+migrate), runtime_temp
│  ├─ browser/                 브라우저 기반 한 곳
│  │  ├─ cdp/                  cdp_* 12, chrome_ui_monitor·watcher, browser_tab_monitor
│  │  ├─ session/              browser_lifecycle, browser_paths, browser_rpc_*, browser_task_session, browser_*_gate, session_tracker
│  │  ├─ page/                 page_helper* 7, page_analyzer, web_connector, human_input, user_action_monitor
│  │  ├─ navigator/            navigator* 8
│  │  └─ popup/                popup_* 4
│  ├─ auth/                    login_*, auth_session, credentials, local_user_secret_store, known_login_urls, check_login_status
│  ├─ site_engine/             (기존) + site_access, site_base, site_registry*, site_session_safety, site_watch
│  ├─ <도구>/                  naver/·google/·eum/·hiworks/ … (TOOL_HOME_MAP 그대로)
│  ├─ ops/                     운영·감사 + quality/ (module_quality_gate* 8, quality_gate, required_quality_gate, install_*, py_compile_no_cache, log_code_change)
│  └─ archive/                 일회성(temp_* 3, 날짜 박힌 감사 등) — 삭제 아님
├─ local_agent/                PC 실행 에이전트 정본 (T4: 3벌 → 1벌, 내일)
├─ apps/                       독립 배포 앱(ig-comment-dm-bot 등) — 공용 패키지 포함 빌드(T6)
├─ admin-web/                  화면 + Electron
├─ orchestrator_v1/            레거시 v1 (루트 shim 은 참조 0 되는 대로 삭제)
├─ tests/  docs/  configs/
└─ (정리 대상) adapters/ agent/ browser_api/ browser_worker/ notice_radar/ services/ → 참조 조사 후 소속 폴더로 이동 또는 archive
```

## 2. 규칙 (구조로 강제)
1. **최상위 평면 금지 게이트(G15, 신규)**: `scripts/*.py`·`ai_orchestrator/*.py`·루트 `*.py` 에 **새 파일 추가 차단**. 허용 목록 = 진입점(`asgi.py`·`router.py`·`config.py`·`app.py`·`__init__.py`·`conftest.py`·`sitecustomize.py`) + 기준선(현재 남은 파일, 줄이기만). G11 과 같은 방식(pre-commit `--staged`, CI `--check-all`).
2. **이동 = 참조 직접 수정 + 옛 파일 삭제가 기본**. shim 은 문자열 참조·외부 실행 경로(bat·스케줄러·Electron)가 있어 즉시 못 바꾸는 경우만, `make_shim` 형식으로, 목록에 기록 후 다음 단계에서 제거.
3. 이동마다: `move_preflight` 0 → `registry_sync --fix` → 순환·층 역전·금지 import **+0** → 영향 시험 → CI. 지표 회피(지연 import·숨김) 금지.
4. 번들(PyInstaller spec)·Electron 이 경로 문자열로 부르는 파일은 spec·main.js 동시 수정 + 빌드 산출물 E2E 로 확인.
5. 층 표준 폴더(persistence·gates·routers 등)는 도구별 하위 폴더화 안 함(결정 3 유지).

## 2-1. 순환의 구조적 원인 (W3 shim 정리 1차에서 실측, 19:55)
- `ai_orchestrator/router.py`(최상위)가 `connectors/<도구>` 를 직접 import 하고, `connectors/<도구>` 는 최상위 공용 모듈(config·audit_logger·models 등)을 import → **폴더 단위 순환(ai_orchestrator ↔ connectors/x)**. 옛 경로 shim 이 우연히 완충 역할을 해 왔음(kakao shim 삭제 시 67→68).
- 해법(지표 회피 아님, 구조): ① **라우터 등록을 최상위에서 빼서** `ai_orchestrator/routers/registry.py`(등록 전용 모듈)로 이동, `asgi.py` 는 그것만 import ② 최상위 공용 모듈은 `core/`(잎)로 이동. ①이 작고 효과가 커서 먼저(S3a).

- (20:10 W2 실측) `scripts/__init__.py` 가 critical_logger·gate·logger·op_log·schemas 를 **재수출**(실행 코드) → scripts.* 어느 하위 모듈을 import 해도 이 5개가 끌려와, 하위 폴더로 옮기는 순간 `scripts/<하위> ↔ scripts` 순환이 생김. 해법: init 을 docstring 만 남기고 재수출 제거, 호출부는 실제 모듈 직접 import(S1 유닛 0, S2 의 선행 조건).
- 기반이 운영 도구를 import 하는 역방향(cdp_daemon → scripts/ops/browser_watch.py)은 해당 런타임 코드를 기반 폴더로 옮겨 단방향화.
- 판정 기준: 단위 커밋은 일시 증가 허용, **통합(W1)에 넘기는 브랜치 head 는 기준 대비 +0 이하 필수**.

## 3. 실행 순서 (충돌 피하려 고정)
| 단계 | 내용 | 담당 | 기준 | 시점 |
|---|---|---|---|---|
| S0 | 이 설계서를 `docs/architecture/FOLDER_STRUCTURE.md` 로 + G15 게이트(기준선 고정) | W1 | integrate-3 | 오늘 |
| S3a | 라우터 등록 이동(`router.py` → `routers/registry.py`, 최상위 router.py 는 진입점 호환만) + router.py 가 쓰던 옛 경로 shim 2차 정리 | W3 | shim-cleanup-1 e5cc6ab5 | 오늘 |
| S1 | `scripts/browser/` (cdp·session·page·navigator·popup ≈40개) | W2 (감사로그 점검 도구 뒤) | integrate-3 | 오늘 |
| S2 | `scripts/common/`·`scripts/auth/`·`site_engine/` 흡수·`ops/quality/`·archive(temp_*) | W4 (scripts 데이터 경로 1차 뒤 — 같은 파일 충돌 방지) | integrate-3 | 오늘~내일 |
| S3 | `ai_orchestrator/{core,llm,mcp,notify,tasks}/` (agent_hub·audit 제외) | W3 (S3a 뒤) | S3a | 내일 |
| S4 | T4: local_agent 3벌 → 1벌 + `ai_orchestrator/agent_hub/` | 2창 | S1~S3 병합 후 | 내일 |
| S5 | `ai_orchestrator/audit/` 정본 + orchestrator_v1 사본 통합 (T1) | 1창 | S3 후 | 내일 |
| S6 | 최상위 소형 패키지 6개 정리, 루트 shim 제거(참조 0부터) | 1창 | S4 후 | 내일 |
- 병합: 각 단계 브랜치 → W1 이 **stage/integrate-4**(integrate-3 위)로 묶어 PR 4' — PR 2 → PR 3 → (M12 PR) → 구조 PR 순서. 오늘 배포판(PR 2)과 첫 빌드에는 영향 없음.
- 서로 다른 폴더만 건드리므로 S1·S2·S3 병렬 가능. 겹치는 호출부(같은 파일의 import 줄)는 나중 병합 쪽이 registry_sync 와 함께 해결.

## 4. 완료 판정
- `scripts/` 최상위 `.py` 109 → 10 이하, `ai_orchestrator/` 최상위 58 → 진입점 4~5개 + 기준선
- 순환 증가 0(감소 목표), G11·G12·G15 PASS, 빌드 산출물 E2E PASS

## 5. 관련 문서·게이트
- 도구별 집(구현·API·화면): [TOOL_HOME_MAP.md](TOOL_HOME_MAP.md) — G11 도구 집 게이트(`tools/repo_gates/tool_home_gate.py`)로 강제
- 앱 전체 구조: [APP_STRUCTURE.md](APP_STRUCTURE.md)
- 최상위 평면 금지: G15 게이트 `tools/repo_gates/flat_root_gate.py` — 규칙 `configs/flat_root_gate.json`, 기준선 `configs/flat_root_baseline.json`(줄이기만). pre-commit `--staged`, CI `--check-all`
- 폴더 승인(G16): `tools/repo_gates/folder_gate.py` — 코드(.py·.ts·.tsx·.js)가 든 모든 폴더는 `configs/folder_registry.json` 에 승인돼 있어야 한다(하위 폴더도 각각). 새 폴더는 작업 창 → 지휘창 '새 폴더 요청'(경로·목적·왜 기존 폴더로 안 되는지) → 대표님 승인 → 목록 추가 → PR 라벨 `folder-approved`(지휘창만 붙임). pre-commit `--staged`, CI `--check-all` + `--check-approval`(목록 추가 시 라벨 확인). 삭제는 승인 불필요.
- 번들 경로 일관성(G17): `tools/repo_gates/bundle_path_gate.py` — 폴더를 옮기면 파이썬 밖의 참조(PyInstaller spec 진입 파일·우리 모듈 hiddenimports·datas, `admin-web/electron/package.json` extraResources, `lib/*.js` 의 `process.resourcesPath` 경로, `desktop-release.yml` 경로)도 함께 고친다. pre-commit `--staged`(관련 파일 staged 시만), CI `--check-all`.

## T4 진행 기록 (local_agent 3벌 → 1벌, 설계 `_coordination/T4_DESIGN.md`)
- C1·C2: 경로 고정·잠금 경쟁 수정(W2).
- C3: 서버·PC 공유 계약 4개를 `ai_orchestrator/contracts/` 로 — `user_present_ws_contract`·`action_risk_policy`·`local_task_protocol`·`local_agent_actions`(참조 직접 교체, shim 없음).
- C4~C8: 서버 쪽 에이전트 허브를 `ai_orchestrator/agent_hub/` 로 — 루트(models·redaction·audit_builders·error_mapping·response_builders·user_present_*·action_*·business_*), `policy/`(risk·status·cleanup·audit_event·file_upload_policy·user_approval_gate), `registry/`(facade + leaf 8 + diagnostics 2), `router/`(root + 11), `actions/`(핸들러 7).
- C9: PC 런타임 57개를 `local_agent/runtime/` 으로. C10: 네이버 워크플로 5개를 `scripts/naver/{blog,cafe}/` 로.
- C11: `scripts/local_agent/` 해체 — 컨트롤러 3개는 `local_agent/`, 점검·스모크는 `scripts/ops/`, 정부24·민원24·웹메일·CLI 라우터는 `scripts/sites/`, g2b E2E 는 `scripts/g2b/`, CDP 크롬 기동은 `scripts/browser/cdp/`.
- C12: 사이트 믹스인 15개는 도구 집(`scripts/naver/{blog,cafe,mail}/`), CDP 엔진과 JS 는 `scripts/browser/agent/`(+`_js/`).
- C13: `ai_orchestrator/local_agent/`·`scripts/local_agent/` 폴더 소멸, 폴더 승인 목록과 G11 예외(`local_agent/`·`ai_orchestrator/local_agent/`·`scripts/local_agent/`)에서 제거. `ai_orchestrator/` 최상위 `local_agent_*` 평면 33 → 0.
