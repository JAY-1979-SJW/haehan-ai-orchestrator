# 완성도 개선 2차분 기준서·드라이런 (2026-09-26, 코드 미수정)

근거: docs/maturity-assessment.md, docs/specs/2026-09-26_maturity_fix_batch1.md. 읽기 전용 조사(하위 에이전트 4 병렬 + 직접 확인), 코드·git 변경 없음. **EUM 관련은 보류로 제외.** 운영서버 접속·배포 없음(로컬 코드·git 이력만).
줄번호 일부는 grep 기준이며 구현 시 재확인. 사용자 승인 후 별도 지시로 구현.

## 요약

| # | 건 | 결론 | 작업량 | 보안 보고 |
|---|---|---|---|---|
| 1 | 배포 안전망(#4, #6) | 서버측 게이트를 `server_deploy.py` 에 + 로컬 pre-push 보조. deploy_trigger_daemon 은 삭제됐지만 라우터·systemd 유닛이 아직 의존 → 문서만 고치면 불충분, **복원 권고** | M (문서만 S) | – |
| 2 | user_auth 감사·테스트 | 신규 L7 `auth_audit` 모듈 + 라우터 호출 1줄씩 + 테스트 | S~M | **있음 4건** |
| 3 | 무테스트 상위 3개 스모크 | 인스타 DM / 인스타 릴스 발행 / 하나팩스, 외부호출 0 | M(DM M, 나머지 S) | – |
| 4 | gonobi·지원사업 레이더 | 로깅·에러 최소 보강. **gonobi 는 DB 0바이트·수집 미사용 → 폐기 판단이 먼저** | S | – |
| 5 | 라우트 스냅샷 개선 | 정확 개수 → 하한+필수 라우트 단언, **같은 결함 테스트가 5파일 더 있음(36개 실패)** | S~M | – |

---
## 1. 배포 안전망 (결함 #4, #6)

**현재 동작**
- tools/server_deploy.py (99줄, `main()` :84): `--approved` 필수(없으면 2) → `_guard_server_only`(:27-31, docker 없으면 exit 3 = **로컬 실행 불가**) → `_git_sync`(:39-56: fetch, 뒤처진 커밋 수, `merge --ff-only`, 분기 시 exit 4, 0 커밋이면 배포 생략) → `_compose_rebuild`(:59) → `_reload_nginx`(:69, best-effort). **테스트·게이트 단계 없음.**
- deploy_trigger_daemon.py: 커밋 b4ad2f70(2026-06-02 "fix(zombie)")에서 삭제. 복원 `git show b4ad2f70^:scripts/ops/deploy_trigger_daemon.py`(8401 포트 HTTP, HMAC 검증 POST `/trigger`, server_deploy.py 호출). 아직 살아 있는 참조: CLAUDE.md:63, AGENTS.md:48, docs/deploy_troubleshooting.md:23, docs/architecture/DEPLOY_PIPELINE_REPAIR.md:17·61, PROD_DEPLOY_PLAN.md:26·75, docs/inventory.md:53·74, **scripts/ops/ai-orchestrator-deploy-trigger.service:10(ExecStart 가 삭제된 파일 — 설치 시 Restart=always 로 크래시 루프)**, **ai_orchestrator/routers/deploy_router.py:37-40 이 `host.docker.internal:<port>/trigger` 로 POST(502/503 처리 :78,:80) — 호스트에 데몬이 있다고 가정**.

**변경안**
1. 신규 `scripts/ops/deploy_gate.py`(docker 호출 금지 — no_local_docker_cli 게이트): ① import 스모크 `python -c "import ai_orchestrator.server"` ② 라우트 수 하한 검사(기준값 파일 신규 `configs/deploy_gate_baseline.json`, 감소 시 실패 — 현재 288 기준값은 파일이 없어 신규 생성) ③ 핵심 테스트 소수(`tests/test_codebase_layer_audit.py` 등 60초 예산, **서버에 pytest 설치 여부 미확인**) ④ 실패 시 종료코드 5 + 상태 JSON.
2. `server_deploy.py`: merge 전 이전 HEAD 기록 → `_git_sync` 후 게이트 호출 → 실패 시 **기록한 HEAD 로 복귀(working tree reset --hard 금지, 기록-복귀 방식)** 후 docker 단계 전에 `sys.exit(5)`. configs/quality_gate.json 예외 허용은 server_deploy.py 1개에만 적용됨 — gate 는 docker 를 부르지 않으므로 무관.
3. 로컬 보조: `.githooks/pre-push`(현재 `ai_code_review_gate.py` 만)에 import 스모크 추가. 단 push 는 우회 가능하므로 **강제 게이트는 서버측**.
4. 데몬: **복원 권고** — deploy_router·systemd 유닛이 이미 의존하고, 삭제 전 정상 동작하던 코드라 diff 가 작다(죽은 참조 `deploy_api_with_runtime_gates` 제거만). 대안: 유닛 삭제+문서 수정(라우터도 정리 필요).
5. 문서: defect_index #4·#6 정정, 위 참조 줄 갱신.

**예상 diff**: deploy_gate.py 신규 ~80줄, server_deploy.py +~25줄, 데몬 복원 1파일(git show), 문서 ~6곳, tests/test_deploy_gate.py 신규.
**영향 테스트**: `tests-for server_deploy.py` = 0건 → 신규 테스트 필요(게이트 함수 단위, docker·git 은 monkeypatch). 라우트 영향 없음.
**위험**: 서버 환경 차이로 정상 배포가 막힘(pytest 부재·시간 초과) / 데몬 복원은 서버에서 실제로 돌고 있는지 확인이 필요(서버 접속 금지라 사용자 확인) / 라우트 하한 기준값 갱신 절차.
**작업량**: M (문서만이면 S). **병렬 겹침**: server_deploy.py, CLAUDE.md·AGENTS.md(미커밋 편집 있음), docs/defect_index.json, docs/inventory.md, .githooks/pre-push, deploy_router.py(변경 시).

---
## 2. user_auth 감사 로그·테스트

**현재 동작**
- ai_orchestrator/connectors/user_auth_router.py (L8, prefix /users): :144 POST /signup, :157 POST /login(성공/401/403 대기), :172 GET /me, :177 PUT /me/password(204), :187 GET /pending(admin), :196 POST /{user_id}/approve(admin). **role 변경·로그아웃·토큰 갱신·비밀번호 재설정 엔드포인트 없음**(JWT 무상태, 만료 30일). routers/auth_router.py:23 GET /auth/me 만.
- 서비스층 없음: 라우터가 ai_orchestrator/persistence/user_db.py 를 직접 호출(create_user:67, approve_user:99, authenticate_user:122, is_pending_login:131, update_password:145). 관리자 게이트 gates/auth.py `require_role`. **로깅·감사 grep 0건.**
- 재사용 후보: scripts/op_log.py `log_op`:185(scripts 계층 → ai_orchestrator 에서 import 하면 역방향 우려, allowed_deps 확인), scripts/critical_logger.py, ai_orchestrator/audit_evidence/(내용 미확인 — 구현 시 인증 이벤트 적합성 먼저 확인).

**변경안**
- 신규 L7 모듈 `ai_orchestrator/persistence/auth_audit.py`(또는 audit_evidence 어댑터): `record_auth_event(event, actor_id, outcome, ...)`. 기록 실패는 try/except 로 격리해 **로그인 흐름을 깨지 않음**.
- 라우터의 login(성공·401·403 대기)·signup 성공·비밀번호 변경 성공/실패·approve 성공/404 에 각 1줄. `_admin` 변수(`_`)를 `admin` 으로 바꿔 actor 접근.
- 마스킹: 비밀번호·토큰·JWT 미기록, 이메일은 `a***@domain` 또는 sha256 앞 12자, user_id 만 원문.
- 테스트 `tests/test_user_auth_audit.py` 신규(TestClient + 임시 DB 경로 monkeypatch, **AUTH_ENABLED=True 로 설정 — false 면 get_jwt_user 가 owner 반환**): 로그인 성공/실패 기록, 승인 대기 403 기록, 일반 사용자의 approve 403, approve 시 감사 기록, 마스킹 검증. 기존 auth 테스트가 없어 fixture 재사용 불가.
**영향 테스트**: `tests-for` 미실행(구현 시 확인). **라우트 영향 없음**(경로·응답 키 불변, 내부 호출만 추가). **위험**: 감사 실패가 인증을 깨지 않게 격리, 저장소 계층 신규 파일의 registry 등록. **작업량 S~M**. **병렬 겹침**: user_auth_router.py, module_registry(신규 파일 등록).

**보안 보고 대상(수정안만, 이번 배치 구현 범위 아님 — 사용자 결정)**
1. user_auth_router.py:157-169 **로그인 시도 횟수 제한·잠금 없음**(무차별 대입 가능) — IP+이메일 기준 실패 카운트/지연.
2. config.py:89 JWT_SECRET 미설정 시 프로세스마다 랜덤 생성 — 재시작 시 토큰 전부 무효, 다중 워커 시 불일치. 운영 env 설정 강제 또는 미설정 경고.
3. 토큰 만료 30일(JWT_EXPIRE_DAYS)+폐기 수단 없음, **비밀번호 변경 후에도 기존 토큰 유효**.
4. :162 이후 비밀번호 일치 시 "승인 대기"를 노출 — 계정 존재·비번 정답을 확인할 수 있는 오라클.

---
## 3. 테스트 0 기능군 상위 3개 스모크

**선정(영향도 = 실운영·돈·신뢰)**: ① 인스타 댓글→DM(고객 대상 자동 DM, 계정 정지 위험) ② 인스타 릴스/캐러셀 발행(공개 게시, 되돌리기 어려움) ③ 하나팩스 대량발송(건당 과금·외부 수신자). 제외: 스마트스토어 문의(CDP 의존이라 스모크 곤란), 네이버 검색(읽기 전용), 그룹상품(미구현), YouTube standalone(로컬 도구). user_auth·gonobi·레이더는 2·4 번에서 다룸.

| 테스트 파일 | 진입점(파일:줄) | 케이스(외부 호출 0) | 작업량 |
|---|---|---|---|
| tests/test_instagram_dm_contract.py | ai_orchestrator/connectors/instagram_dm_router.py webhook_verify:71, webhook_receive:83, POST /rules/simulate:331, rules CRUD :282-317, health:376 | rule_engine 키워드 매칭/비매칭 reason · 템플릿 치환 · /rules/simulate 응답 키(matched, reason, matched_rule, matched_keyword, preview_dm), 계정 없음 404 · webhook_verify 토큰 불일치 403 계열 · 자동화 off 시 미매칭. fixture: tests/test_kakao_webhooks.py(웹훅 TestClient·env monkeypatch) | M |
| tests/test_instagram_api_publish_smoke.py | scripts/instagram/api_publish.py publish_reel:104(confirmed=False 기본), create_reel_container:65, wait_ready:83, publish:97, _post:49/_get:58/_creds:40 | import 스모크 · confirmed=False 거부/미리보기(외부 호출 0) · confirmed=True + `_post/_get/wait_ready` monkeypatch 로 컨테이너→publish 순서·파라미터 · 토큰 없음 실패 경로 · wait_ready 에러 상태 예외 | S |
| tests/test_hanafax_bulk_send_smoke.py | scripts/hanafax/bulk_send.py send_bulk_batch:68, load_batch:47, save_result:57, _get_creds:38; router.py run_hanafax:25 | import 스모크(부작용 없음) · load_batch 샘플 JSON(tmp_path) · save_result 라운드트립 · _get_creds env 없음 실패 · run_hanafax help/알 수 없는 task. **send_bulk_batch 실호출 금지(비용)** | S |
- 신규 파일 3개 → `registry_sync --fix`(골격 게이트), 라우트·기존 코드 영향 없음. 위험: 실호출 방지(`_post/_get/requests/CDP` 반드시 monkeypatch). 이미 커밋된 `tests/test_hanafax_bulk_send_paths.py`(HAEHAN_G2B_FAX_DIR)와 파일명 구분.
- 병렬 겹침: 서로 다른 신규 파일이라 충돌 없음. registry_sync 는 마지막에 직렬 1회.
- 미확인: rule_engine/db 정확한 시그니처, hanafax 로그인 방식(구현 시 확인).

---
## 4. gonobi(7점)·지원사업 레이더(10점) 최소 보강

**gonobi** — ai_orchestrator/connectors/gonobi_router.py(130줄): `POST /scrape`:30 백그라운드 `_run`→`runner.run_scrape`, `/scrape/status`, `/posts`, `/posts/{log_no}`, `/stats`, `POST /classify`. except 5건(bare/pass 아님, 전부 `except Exception`): :58 수집 실패를 `logger.error`+`_scrape_state["current"]="오류…"`로만 기록(`errors` 미갱신, `running=False`, traceback·이력 없음), :86,:103,:116,:129 **로그 없이 `HTTPException(500, str(e))`**(예외 문자열이 클라이언트에 노출·서버 로그 없음), :68 `add_done_callback(lambda t: t.exception())` 은 조회만 하고 로그 없음. `_scrape_state` 는 메모리 전역(재시작 시 소멸).
- **사실: data/gonobi.db 0바이트(수정 2026-08-16), 코드는 2026-06-23 이후 변경 없음, 메모리에 활용 기록 없음 → 수집은 사실상 미사용.**
- 보강안: :86,:103,:116,:129 → `logger.exception("gonobi <op> 실패")`+`detail="internal_error"`; :58 → `logger.exception`, `errors+=1`, `log_op("gonobi.scrape", ok=False, message=type(e).__name__)`, 성공 시 `log_op(ok=True, metadata={total,new,errors})`.

**지원사업 레이더** — ai_orchestrator/connectors/grant_radar_router.py(243줄) except 8 + scripts/grant_radar 9 = 17건(전부 `except Exception`). 위험도 순: 라우터 :56,:65 설정/목록 로드 실패 시 `{}`/`[]` 를 로그 없이 반환(정상 빈 결과로 오인) · scripts/scan.py:122 print 후 `[]` 반환(포털 하나 실패가 "0건 성공"으로 보임) · form_fill.py:99 요청 JSON 파싱 실패를 `{}` 로 삼킴 · report.py:39 설정 실패 시 기본값 조용히 반환. 이미 `logger.error`+`ok:False` 인 곳(라우터 :77,:114,:154,:224)은 `logger.exception` 으로. :177,:241 감사로그 실패 warning 무시는 허용. 산출물 scan_latest.json/report_latest.* 는 덮어쓰기라 이력 없음, **2026-06-08 이후 갱신 없음**.
- 보강안: 위 지점에 `logger.warning(..., exc_info=True)`, scan.py:122 는 오류 표시를 `errors` 에 합산, `log_op("grant_radar.scan", ...)`(재사용: scripts/op_log.py `log_op`:185, data/logs/ops.log). 선택: `scan_YYYYMMDD.json` 날짜별 사본(46KB 수준).
- 최소 테스트: tests/test_gonobi_router_contract.py(`/stats` 에서 `open_db` 예외 → 500·detail 에 원문 없음·caplog 기록 / `/scrape` 에서 `run_scrape` 예외 → status current 오류·running False), tests/test_grant_radar_router_contract.py(외부 실행 실패 → `ok:False, reason:exec_error` / 설정 로드 예외 → caplog warning·반환 `{}`).
- **라우트 영향 없음**(경로 불변). 응답 key 는 gonobi 500 detail 문자열만 변경 — 프론트가 detail 을 화면에 노출하는지 확인. **위험 낮음. 작업량 S**(6파일 수정+테스트 2).
- **병렬 겹침**: gonobi_router.py, grant_radar_router.py, scripts/grant_radar/{scan,report,form_fill}.py 는 다른 건과 겹치지 않음(현재 미커밋 변경 목록에도 없음).
- **판단 제안**: gonobi 는 보강보다 **폐기/보존 결정이 먼저**(DB 0바이트).

---
## 5. 라우트 스냅샷 테스트 개선

**현재**: 2026-05-18 시점 정확 개수 단언(`== 63`, POST `== 27`)이 여러 테스트에 흩어져 있음. 배치 1 의 2d 에서 deployment 테스트 1개만 현행값(284/122)으로 갱신했으나, 같은 결함이 남아 있음.
- 실측(stage/mat-tests): tests/test_app_approval_gate_readonly_polish_20260518.py:116,124, test_app_logs_audit_readonly_view_20260518.py:261,268, test_app_task_detail_readonly_polish_20260518.py:218, test_app_test_baseline_current_contract_sync_20260518.py:187 및 동 파일 `test_runtime_endpoint_count_is_63`·`http_count_is_62`·`cycle_test_count_63`, tests/test_backend_domain_core_models_20260516.py:845 — **이 5개 파일을 돌리면 36개 실패**(정확 개수 + 페이지 경로 `(legacy)` 이동 + `_src()` 가 빈 문자열을 돌려 UI 단언 다수 실패 등 복합 원인).
- verify_change 는 이미 "서버 라우트 수" 를 커밋 전후 비교(tools/verify_change.py:208, :383-391, `--expect-routes`)하므로 **정확 개수 스냅샷 테스트는 중복이자 취약**.

**변경안**
1. 공용 헬퍼 `tests/_route_helpers.py`(신규): `collect_routes()`, `assert_routes_present(paths)`, `assert_route_floor(n)`.
2. 각 테스트의 `== N` 을 (a) 필수 라우트(`/api/v1/auth/me`, `/api/v1/sites/catalog`, `/api/v1/ops/audit-events` 등 해당 기능이 실제로 의존하는 경로) 존재 단언 + (b) 하한(`>= 250`) 단언으로 교체. 정확 개수는 verify_change 가 담당.
3. 5파일의 페이지 경로 `(legacy)` 이동은 2d 와 동일하게 정정, `_src()` 가 빈 문자열이면 명시적으로 fail 하는 fixture 로 교체(빈 문자열로 통과/실패가 가려지지 않게).
4. 원인이 복합이라 파일별로 실패 원인 재진단 후 커밋(파일당 1커밋 권장, 또는 라우트 단언만 1커밋 + 경로 정정 1커밋).
**영향 테스트**: 위 6개 파일(수정 대상). 라우트 영향 없음(테스트만). **위험**: 필수 라우트 목록을 잘못 잡으면 검증이 약해짐 → 각 테스트가 보호하던 기능 경로로 한정. **작업량 S~M**(파일 6개). **병렬 겹침**: 이미 커밋된 stage/mat-tests 2d 와 같은 파일(test_app_deployment_readonly_polish_20260518.py)이 포함되므로 병합 후 진행.

---
## 브랜치 분할안 (병렬 가능 묶음)

| 브랜치 | 내용 | 겹침 |
|---|---|---|
| stage/mat2-deploy | 1 배포 게이트+데몬 복원+문서 | server_deploy.py, CLAUDE.md·AGENTS.md, defect_index.json, .githooks/pre-push (다른 브랜치와 겹치지 않음, 단 메인 미커밋 CLAUDE.md 편집 주의) |
| stage/mat2-userauth | 2 auth_audit+테스트 | user_auth_router.py, persistence 신규 |
| stage/mat2-smoke | 3 스모크 테스트 3개 | 신규 테스트 파일만 |
| stage/mat2-lowscore | 4 gonobi·레이더 보강 | gonobi_router.py, grant_radar_router.py, scripts/grant_radar |
| stage/mat2-routetests | 5 라우트 스냅샷 개선 | stage/mat-tests 병합 후 |
- 공통: 신규 파일이 있는 브랜치는 `registry_sync --fix`(module_registry.json 충돌 가능) → **병합 순서를 직렬로 하고 병합 때마다 registry_sync 재실행**. verify_change·병합은 메인 직렬.
- 권장 진행 순서: mat2-routetests(병합 후 즉시, 게이트 신뢰 회복) → mat2-deploy → mat2-userauth → mat2-smoke → mat2-lowscore.

## 결정이 필요한 항목 (추천안 포함)

- D1 deploy_trigger_daemon: **복원(추천)** vs 문서·유닛 삭제. 운영서버에서 데몬이 실제로 도는지 사용자 확인 필요(이 창은 서버 접속 금지).
- D2 배포 게이트 위치: **서버측 강제 + 로컬 pre-push 보조(추천)**. 서버에 pytest 설치 여부 확인. 라우트 하한 기준값 파일 신규 생성 승인.
- D3 user_auth 감사 저장소: **신규 L7 auth_audit(추천)** vs audit_evidence 재사용(내용 확인 후) vs op_log(역방향 위험).
- D4 보안 보고 4건(로그인 시도 제한, JWT_SECRET, 토큰 폐기, 대기 상태 오라클)을 이번 배치에 포함할지 — **추천: 감사 기록만 이번에, 시도 제한·JWT_SECRET 은 보안 2단계로**.
- D5 스모크 상위 3개 선정 승인(DM·릴스·하나팩스). 스마트스토어 문의는 CDP 의존이라 제외(동의?).
- D6 gonobi: **폐기/보존 먼저 결정(추천)**. 보존이면 최소 보강만, 폐기면 코드·라우터 제거는 별도 기준서.
- D7 라우트 스냅샷: 필수 라우트 목록 확정 방식(각 테스트가 의존하는 경로를 구현 시 자동 도출 후 사용자 확인) 및 하한값(추천 250).
- D8 성숙도 평가 문서의 과대 수치(local_agent 삼킴 143/117)를 배치 1 기준서 결론대로 정정할지.
