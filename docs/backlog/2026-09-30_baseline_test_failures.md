# 기존 테스트 실패 백로그 (2026-09-30 기준선)

- 측정: 커밋 `4bc8e2b4`(브랜치 `feat/login-state-by-element`), Python 3.14.7, `pytest --timeout=60`, 실행 시간 약 11분(스냅샷) + 4.6분(실제 트리 재확인)
- **전체 목록:** [`2026-09-30_baseline_test_failures.tsv`](2026-09-30_baseline_test_failures.tsv) — 350건(실패 349 + 오류 5~6 중 G6 인코딩 4건 해소 후), 75개 파일. **2026-10-07 갱신(W4): 확인·정리된 248줄 삭제 → 102건, 14개 파일 → 통합 브랜치에서 t2·t3 병합 후 g2b 6·user_field_test 12줄 삭제 → 84건, 12개 파일** (65개 파일 재측정 시 실패는 g2b 6·user_field_test 12·blueprint 2·contract_sync 1뿐이었고 앞의 3묶음 중 blueprint·contract_sync 는 이 브랜치에서 수정, g2b·user_field_test 는 `stage/testfix-t2-fixtures`·`stage/testfix-t3-user-field-test` 에서 처리돼 통합 브랜치에 병합됨(해당 줄 삭제 완료). 남은 줄: CDP 실브라우저 미실행 2파일 + 보류 10파일). 컬럼 `status / test_id / message`
- 목적: 게이트가 "이번 편집이 만든 실패"만 막도록 기준선이 생겼으므로(`post_edit_fast_gate.py`, 2026-09-30), 이 목록은 **나중에 묶음 단위로 정리할 작업 목록**이다. 이 문서 작성 시 코드는 한 줄도 고치지 않았다.

## 1. 측정 방법과 한계 (숫자를 읽기 전에)
| 단계 | 방법 | 결과 |
|---|---|---|
| 1 | HEAD 를 임시 폴더에 풀어(`git archive`) 전체 `tests`+`ai_orchestrator/tests` 실행(멈춤 결함 파일 `test_local_agent_installer_package.py` 제외) | 실패 1,128 + 오류 526 = **1,654건** (통과 9,789) |
| 2 | 1의 실패가 있던 127개 파일만 **실제 작업 트리**에서 재실행 | 실패 349 + 오류 5~6 = **354건** ← 이 문서의 기준선 |
- 스냅샷에는 `docs/`, `data/`, `admin-web/`이 없어서 "문서 없음"(105), "설계서 없음"(45), `FileNotFoundError` 등 **1,304건이 스냅샷의 산물**로 판명돼 제외했다.
- **전체 실행에서만 나온 517건**(`ImportError: module tools.gates.auth/approval not in sys.modules`)은 파일 단위 재실행에서는 사라졌다 → 테스트 간 순서 의존 오염으로 추정(§3 P3-1). 원인은 아직 확인하지 않았다.
- 실제 트리 재실행에는 이번 세션의 미커밋 변경이 포함돼 있다. 로그인 판정·게이트 관련 새 테스트 46개는 모두 통과했고, 스냅샷과 실제 트리의 차이 7건은 아래로 설명된다: 스냅샷에 `admin-web`이 없어 `HomePage` 검사 2건이 안 보였음, `STORAGE_BOUNDARY` 4건은 스냅샷에서 다른 이유로 먼저 실패했음, 시크릿 스캔 1건은 **이 세션이 만든 스냅샷 캐시가 원인**이었고 캐시를 저장소 밖으로 옮겨 해소함.
- 한계: 실행 시각 하나의 측정이다. 시간·네트워크·CDP 상태에 따라 달라지는 테스트(`cdp_playwright_smoke` 등)가 섞여 있을 수 있다.

## 2. 원인 묶음 (건수는 tsv 의 파일명·메시지로 센 근사치)
증거가 코드·메시지로 확인된 것은 "확인", 메시지 패턴에서 추정한 것은 "추정"으로 표시했다.

| # | 묶음 | 건수 | 대표 파일 | 증거 | 권장 조치 |
|---|---|---|---|---|---|
| **G1** | **앱 UI 문구·구조 고정 테스트가 개편된 화면과 어긋남** | ~170 | `test_app_*_readonly_polish_20260518`(logs_audit·deployment·storage·external_sites·task_queue·task_detail·nav_active·approval_gate), `test_app_ui_shell_*`, `test_app_ui_readonly_*`, `test_app_standard_ui_dashboard`, `test_admin_web_ops_dashboard_boundary` | 실패 메시지에 현재 화면 소스(`HomePage — 단일 AI 작업 콘솔`)가 찍힘 / 옛 화면 파일을 못 찾는 `FileNotFoundError` — **확인**(화면이 단일 콘솔로 바뀜) | 옛 화면을 기대하는 테스트는 삭제 또는 현재 구조로 갱신. 한 파일씩이 아니라 `..._20260518` 계열을 한 번에 결정 |
| **G2** | **핫픽스로 제거된 라우트·별칭을 기대하는 테스트** | ~60 | `test_approval_read_api`(17, 404), `test_kakao_webhooks`(17), `test_backend_direct_dict_boundary_lock`(7), `test_backend_legacy_router_direct_dict_audit`(7), `test_backend_domain_core_models`(1), `test_ops_router_read_only` | 04-24 핫픽스 `3c155f55` 가 라우터를 되돌리며 승인 조회·텔레그램 별칭을 제거 — **확인**(승인·텔레그램). 카카오·라우트 수 고정은 **추정** | 복구할 기능인지 먼저 결정(공개 엔드포인트 추가는 별도 승인). 복구 안 하면 테스트를 현재 라우트 기준으로 갱신 |
| **G3** | **브라우저 제출 정책·엔진 라우팅 API 변경** | ~35 | `test_browser_submit_*`(6+4+4+1), `test_browser_site_compliance_policy`(3, Gmail 정책이 `CDP_READ_ONLY` 로 바뀜 — 테스트는 `OAUTH_API_ONLY` 기대), `test_browser_engine_routing_*`(2), `test_browser_sandbox_gate`, `test_dry_run_manual_local_agent_browser_smoke` | `AttributeError: '…' object has no attribute` 다수 — 모듈 API가 바뀐 뒤 테스트 미갱신 **추정** | 해당 모듈 현재 API 확인 후 테스트 갱신 또는 폐기 |
| **G4** | **로컬 에이전트 계열** | ~30 | `test_local_agent_user_field_test`(12), `test_tenant_runtime_hooks`(9, MagicMock), `test_local_agent_ws`, `test_local_agent_gui_ux_design_spec`, `test_local_agent_ip_allowlist_policy`, `test_authed_local_agent_dispatch_dry_run` | `FileNotFoundError`(설계서·픽스처 경로), 목 객체 어긋남 — **추정** | 파일 경로가 옮겨진 것부터 확인(이동 후 테스트 미갱신 가능성) |
| **G5** | **구조·품질 게이트 테스트(코드 자체의 위반)** | ~25 | `STORAGE_BOUNDARY`(`test_app_foundation_p1_gates`·`domain_room_allocation`·`shared_warehouse_policy`, 4건), `test_root_legacy_scripts_audit`, `test_module_separation_gate`, `test_live_inputs_split`, `test_required_quality_gate`, `test_app_scope_web_desktop_boundary`, `test_ai_agent_*_baseline`, `test_mcp_gateway_baseline` | `sqlite3` 직접 import 14곳(`instagram_dm_db.py`, `persistence/user_db.py`, `apps/ig-comment-dm-bot/core/processed_store.py`, `scripts/naver/automation/scheduler.py` 외) — **확인**. 나머지 게이트는 위반 목록이 메시지에 있음 | **테스트가 아니라 코드 쪽 부채.** 저장 계층으로 옮기거나 허용 목록에 근거와 함께 등록 |
| **G6** | **환경·인코딩 의존** | ~5 (인코딩 4건은 **2026-09-30 해소**) | ~~`test_browser_site_compliance_policy`(4, `UnicodeDecodeError: cp949`)~~ → `FIXTURE_PATH.open(encoding="utf-8")` 로 해결, `test_cdp_playwright_smoke`(2, CDP 연결), `test_capture_screenshot_dry_run`(3, WebSocketDisconnect) | 인코딩 4건은 확인·해소. 나머지는 브라우저·웹소켓 상태 의존 **추정** | CDP 계열은 CDP 있을 때만 돌도록 마커. (당초 G6 를 ~12 로 잡았으나 인코딩은 4건뿐이었음 — 정정) |
| **G7** | **개별 원인 (묶이지 않음)** | ~20 | `test_naver_cafe_list_collector`(7), `test_fetch_web_page`(10), `test_naver_service_router`(4, KeyError), `test_message_classifier`(4), `test_user_present_runtime_integration`(3, asyncio 타입 오류), `test_dashboard_routes`(6, `dashboard.html` 없음), `test_post_tasks_medium_isolation_smoke`(6, APIRouter 중복 포함), `test_auth_me`, `test_registration_codes` 외 | 개별 확인 필요 | 묶음 정리 후 남는 것을 하나씩 |

## 3. 우선순위
| 순위 | 항목 | 이유 |
|---|---|---|
| **P1** | G5 (STORAGE_BOUNDARY 14곳 등) | 테스트가 아니라 **실제 코드가 규칙을 어김**. 다른 묶음은 낡은 테스트일 수 있지만 이건 그렇지 않다 |
| **P1** | G2 중 승인 조회·웹훅 | 04-24 핫픽스 이후 **비활성으로 남은 기능**일 수 있다 — 복구 여부는 사용자 결정 |
| **P2** | G6 인코딩 | 한 줄씩 고치면 되고 효과가 확실. 고객 PC 설치형이므로 cp949 환경 실패는 실제 사고로 이어질 수 있다 |
| **P2** | G1 앱 UI 고정 테스트 | 건수가 가장 많지만 대부분 "낡은 테스트 삭제·갱신" 한 번의 결정으로 묶임 |
| **P3** | G3, G4, G7 | 모듈별 API 확인이 필요해 손이 많이 감 |
| **P3-1** | 전체 실행 시 517건 순서 의존 오염 | 원인 미확인. 전체 pytest 를 다시 쓰려면 반드시 필요한 조사(지금은 전체 실행을 금지해 둔 상태) |

## 4. 다음 단계 제안 (이 문서는 계획일 뿐 승인된 작업이 아님)
1. ~~G6(인코딩)~~ — 인코딩 4건 해소(2026-09-30). 남은 G6 는 CDP·웹소켓 상태 의존.
2. G1 은 테스트 삭제·갱신 방침을 정한 뒤 `..._20260518` 계열을 한 브랜치로.
3. G2 는 복구할 기능과 폐기할 기능을 표로 나눠 승인 요청.
4. G5 는 기준서 작성 후 진행(코드 이동이라 영향이 큼).
5. 정리한 묶음은 tsv 에서 줄을 지우고, 이 문서의 건수를 갱신한다. **정리가 끝난 테스트가 다시 깨지면 게이트가 새 실패로 막는다.**

## 5. 이 기준선을 쓰는 방법
- 게이트(`post_edit_fast_gate.py`)는 기준선을 **실행 시점의 HEAD 에서 직접 측정**한다(이 tsv 를 읽지 않는다). 그래서 이 파일이 낡아도 게이트 동작에는 영향이 없다.
- 이 tsv 는 사람이 정리 진행 상황을 볼 때만 쓴다. 갱신하려면 위 §1 의 2단계를 다시 돌린다.
