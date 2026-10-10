# 2026-09-28 세션 인수인계 — STD 정리 + install-readiness 점검

**목표**: 이 앱은 AI 에이전트로 개발됐고, **타인 PC에 설치해서 쓸 수 있는 수준으로 품질을 올리는 것**이 최종 목표다. 오늘은 그 준비 작업으로 코드 표준(STD-02/04) 정리와 "설치하면 바로 깨지는" 종류의 문제(치명 등급)를 우선 처리했다.

## 오늘 완료한 것 (커밋 순서대로, 전부 push 완료)

### 1. STD-04 (예외 처리) — 완전 완료
- BLE001(blind-except) 2,140건 → 0건. 10개 병렬 서브에이전트(worktree 격리) + 수동 검토 27개 파일.
- S110/SIM105/E722 잔여 229건 → 0건. 5개 병렬 서브에이전트.
- **실제 보안 버그 1건 수정**: `ai_orchestrator/services/execution_policy_service.py` — 정책 모듈 로드 실패 시 fail-open이던 것 5개 메서드를 fail-closed로.
- `configs/ruff.toml`에 `BLE` 카테고리 정식 채택(앞으로도 계속 강제됨).

### 2. STD-02 (pathlib 전환) — PTH 부분 완료
- os.path.* → pathlib.Path 736건(226개 파일) → PTH 관련 실질 잔여 7건(전부 보안 경계 로직이라 의도적으로 os.path 유지, 사유 주석 있음).
- 10개 병렬 서브에이전트, 매 파일 `code_map/query.py tests-for` + 실제 pytest 실행으로 검증(회귀 0건, git stash 베이스라인 대조로 확인).
- **주의**: `configs/ruff.toml`엔 아직 `PTH` 카테고리가 select에 없음 — 그래서 PTH용 noqa 주석은 커밋 훅이 "미사용"으로 자동 제거한다(RUF100). 이후 이 파일들을 다시 건드리면 noqa 없이 평문 설명 주석만 있는 상태를 그대로 존중할 것.
- **미완료**: ABS-PATH-LITERAL(하드코딩 절대경로 문자열) 172건은 이번 범위 밖으로 남겨둠 — 대부분 테스트 픽스처(가짜 보안 테스트 입력값)로 보이나 전수 확인은 안 함.

### 3. 실제 버그 발견·수정 (STD 작업 중 우연히 발견, 총 5건)
| 파일 | 문제 | 커밋 |
|---|---|---|
| `ai_orchestrator/services/execution_policy_service.py` | fail-open 정책 판정 5개 메서드 | (STD-04 배치 중) |
| `ai_orchestrator/persistence/registration_code_store.py` | DB 쓰기 실패를 조용히 삼켜 1회용 등록코드 재사용 가능 | `a910ba57` |
| `scripts/google/common/live_inputs_fill.py` | `Path` import 누락으로 무조건 NameError (5월부터 존재) | `9d20cac9` |
| `.githooks/pre-commit.orig` 등 3개 훅 | worktree에서 커밋 시 메인 체크아웃을 조용히 훼손 | `19e6035b` |
| `.githooks/commit-msg` | 자기 `print()`가 cp949에서 죽어 대량삭제 차단 자체가 안 됨 | `c6d0be71` |

### 4. install-readiness (오늘 세션의 진짜 목적)
- **requirements.txt 보정**: `beautifulsoup4`, `python-docx`, `matplotlib`, `mcp` 4개 실제 누락 의존성 추가(`bd34c28e`). PyPI 실재 확인함.
  - ERR-01(설치 시 ModuleNotFoundError) 원래 521건 → 지금 30건 → 이 4개 빼면 나머지는 각 standalone 앱(`apps/*-standalone`) 자체 requirements.txt에 이미 있거나(PyQt6/yt_dlp/faster_whisper), try/except로 이미 안전 폴백돼 있거나(plyer/win10toast/winotify/winrt/konlpy/sklearn), 개발자가 수동 실행하는 영상제작 도구(edge_tts/manim, `scripts/video/`, `manim_diagram_scene.py`)라 무관함을 개별 확인 완료.
- **고아 코드 삭제 2건**: `scripts/content_rag/`(numpy+sentence_transformers 쓰지만 아무도 안 부름), `scripts/ops/shared/excel_utils.py`의 `open_excel()`(안 쓰임, `excel_session()`이 안전한 대안으로 이미 존재).
- **ERR-03(subprocess shell=True) 4건 정리**: `os.startfile()`로 교체 2건, list 인자 방식으로 교체 1건(dead code라 실위험은 낮았음), 1건은 로컬 CLI 도구라 위험 없음 확인 후 주석만 추가.
- **EFF-06(Excel COM 정리 누락)**: 위 고아 함수 삭제로 자동 해결.

### 5. STD-01 (인코딩 누락, PLW1514) — 완료
- 33건(12개 파일) 전부 `encoding="utf-8"` 명시. 이 프로젝트 자체 ruff.toml은 preview 모드가 아니라서 평소엔 이 규칙 자체가 안 걸린다(`--preview` 플래그로만 검사 가능) — 조용히 쌓여있던 클래스의 문제.

### 6. DOC-02 (외부 도구 문서 미등록) — 완료 + 정식 승격
- 12개 도구(keyring, cryptography, PyJWT, Starlette, Flask, google-auth-oauthlib, google-api-python-client, websocket-client, psutil, pyperclip, win32clipboard, openai) 전부 공식 문서 WebFetch로 확인.
- `32. Claude 개발표준\standard\docs_registry.toml`에 정식 등록(커밋 `19a1db8`) → `audit-kit`에 `sync_standard.py`로 재동기화(커밋 `70c20e1`) → 3개 저장소 전부 push 완료.

### 7. audit-kit 자체 개선 (다른 프로젝트에도 재사용됨)
- `audit-kit fix report`가 "기준선에도 있고 지금도 실패 중인 테스트"를 대상 프로젝트의 `docs/known_preexisting_issues.json`(+`.md`)에 **영구 자동 기록**하도록 추가(`fixflow.py`, 커밋 `7504989` in audit-kit repo).
- 목적: 오늘처럼 여러 서브에이전트가 같은 기존 실패의 원인을 매번 재조사하는 낭비를 막기 위함. `fix start`는 이미 문서화된 원인이 몇 건인지 알려준다.
- `haehan-ai-orchestrator/docs/known_preexisting_issues.md`에 오늘 발견한 기존 결함들(fastapi/httpx 버전 불일치, 존재하지 않는 속성 참조 등)을 수기로 먼저 정리해뒀음 — 다음에 이 파일들 건드릴 일 있으면 먼저 참고.

## ⚠️ 중요 — audit-kit "치명" 숫자를 곧이곧대로 믿지 말 것

이번 세션에서 **3번** 확인한 패턴: audit-kit std가 번들로 들고 있는 기준서(`rules.toml`+`ruff.toml`)가 이 프로젝트 자체 `configs/ruff.toml`의 **정당한 커스터마이징을 모르고** 재검사해서 대량의 가짜 "치명" 항목을 만들어낸다.

| 사례 | audit-kit 번들 기준 | 이 프로젝트 실제 |
|---|---|---|
| STD-02 (PTH) | 882건(worktree 오염 포함 시) | 7건 |
| STD-04 (S110 등) | 263건 | 0건(`scripts/**`는 S/B 카테고리 완화돼 있음) |
| STD-05 (B006/B008/RUF012) | 494건 | **0건** — `configs/ruff.toml`이 이미 `B008`/`RUF012`를 "FastAPI 패턴"이라고 명시하며 ignore 처리해둠 |

**교훈**: 이 프로젝트에서 audit-kit std 결과를 볼 때는, 큰 숫자가 나오면 먼저 `py -3.14 -m ruff check --config configs/ruff.toml --select <규칙ID>`로 **이 프로젝트 자체 설정 기준** 실제 건수를 대조하고 나서 작업 여부를 판단할 것. (근본 해결책은 audit-kit이 프로젝트 자체 ruff.toml의 ignore를 병합해서 검사하도록 고치는 것인데, 이번엔 손대지 않았다 — 다음 세션 후보 작업.)

## 최종 상태 (2026-09-28 세션 종료 시점)

```
audit-kit std --path "C:\Users\skyjw\claude-dev-handoff\01. haehan-ai-orchestrator" --no-mypy --fail-on never
→ 치명 787 / 개선 2672 / 참고 60 / 무시 9703
```
치명 787건 중 실질적으로 남은 건 거의 없음(STD-04/05 조합만 750+건이고 전부 설정 불일치 노이즈로 확인됨).

## 다음 세션 후보 작업 (우선순위 순, 미정)

1. ~~**ABS-PATH-LITERAL 172건 재검토**~~ — **완료(2026-09-28 2차 세션)**. 173건 실측 결과:
   - 테스트 파일 104건 = 전부 가짜 픽스처(`C:\path\file.exe` 류) 확인, 문제 없음.
   - 비-테스트 69건 중 **실제 버그 1건 발견·수정**: `tools/gates/risk_classifier.py:7`
     민감 경로 목록에 `"C:/Users/skyjw/.ssh/"`가 사용자명 하드코딩돼 있어, 다른 계정/PC에서 실행하면
     SSH 디렉터리 보안 감지가 조용히 무력화되던 문제. `Path.home()` 기반 동적 계산으로 수정,
     `test_risk_classifier.py` 5개 통과·ruff·layer audit 확인. (미커밋 — 다음 세션에서 커밋 필요)
   - 나머지 68건은 설계 의도로 판정하고 미수정: Chrome/Edge 실행파일 후보 경로·`malgun.ttf`·시스템
     폴더 차단목록(OS 표준 위치, 계정 무관), `scripts/ops/*`의 `/home/ubuntu/...`(원격 배포 서버
     고정 경로, 정책과 일치), `scripts/video`·`instagram`·`hanafax`·`mk_catalog`·`yt_upload`·
     `naver/blog/accounts.py`·`eum/shared/layout_schema.py`(본인 전용 수동 도구, install 대상 아님).
   - **audit-kit 개선 후보(미수정)**: `ABS_PATH_RE`가 파일 경로가 아닌 **웹 URL 경로**까지 오탐.
     `scripts/common/auth_window_gate.py:255`(`"/home/about"`), `scripts/grant_radar/scan.py:38`
     (`"/home/2-2/"`) 둘 다 `/home/`으로 시작하는 URL 문자열인데 파일 경로로 오판됨.
   - **부수 발견(미수정, 저우선순위)**: `gen_remaining_posts.py`·`e2e_deep_scan.py`×2·
     `e2e_full_report.py`가 9/27 이전 프로젝트 위치(`C:\work\01. haehan-ai-orchestrator\...`)를
     참조 — 이미 죽은 경로지만 전부 개발자 수동 도구라 후순위.

2. ~~**DUP-02(중복 코드) 정확한 측정**~~ — **완료(2026-09-28 2차 세션)**. audit-kit
   `check_func_body_dup`을 직접 호출해 110개 그룹(관여 함수 264개, 이전 보고 건수와 일치)을
   전수 파일별로 뽑았다(원본 스크립트: 이 세션 스크래치패드, 재실행하려면
   `audit_kit.std.checks.check_func_body_dup` + `MIN_DUP_STATEMENTS=5` 기준으로 프로젝트
   전체를 AST 파싱하면 재현됨). 4개 군으로 분류, **파일 수정은 하지 않음**(측정 범위):
   - **① `apps/marketing-standalone/` ↔ `scripts/naver`·`scripts/instagram` 원본 병렬 구현
     (최대 군, 약 71개 함수/16개+ 그룹)**: `naver_writer.py`(16개, `scripts/naver/blog/core/writer.py`
     와), `instagram_graph_api.py`(6개), `content_rules.py`(4개), `cdp_helper.py`(3개),
     `blog_images.py`(2개), `blog_router.py`(2개), `naver_login_check.py`·`ai_responder.py`(각 1개)
     — 함수 본문이 사실상 동일. **의도된 설계일 가능성이 높음**: `apps/marketing-standalone`은
     L10(로컬 PC 앱, `module-separability` 스킬 대상)이라 `ai_orchestrator`/`scripts`에 의존하지
     않고 독립 배포되도록 일부러 복사했을 수 있다 — 확정하려면 사용자 확인 필요(다음 세션 후보).
     만약 의도된 게 아니라면 DUP-04(프로젝트 간 복사 금지) 정식 위반이라 공용 모듈 분리 대상.
   - **② `scripts/eum/registration.py` ↔ `deregistration.py`**(6개 그룹, 12개 함수):
     `_analysis_entries`·`_selector_from_field`·`_selector_from_button`·`_analyzed_field_selectors`·
     `_analyzed_submit_selectors`·`_denial_reason`. 이미 `scripts/eum/shared/`가 있는데 이 헬퍼들만
     못 옮겨간 것으로 보임 — 프로젝트 내부 리팩터링 후보(낮은 리스크, 다음 세션에 시도 가능).
   - **③ `scripts/video/ig_dm_bot_ep01*.py` ↔ `kakao_skill_bot_ep01*.py`**(8개 그룹, 16개 함수)
     + `ai_g2b_youtube_ep01_real.py` ↔ `ep02.py`(3개 그룹): 에피소드별 영상 제작 스크립트 복붙 —
     전부 본인 전용 수동 도구라 후순위.
   - **④ 나머지 (~4개 함수)**: 테스트 픽스처 보일러플레이트(`_make_test_client`·`_isolated_storage`
     등, pytest 관례상 흔함·낮은 우선순위), `scripts/ops/audit_backend_premium_*.py` 8개 파일의
     `main()` 함수(CLI 진입점 보일러플레이트, 통상 무해), `gabia`/`google`/`hiworks`/`youtube`의
     `validate_*_action_plan`(4-way, 벤더별 검증기라 구조가 비슷한 건 자연스러움) 등 소규모 산발.
   - **다음 세션 판단 필요**: ①이 의도된 설계인지 사용자에게 확인 — 아니라면 이 프로젝트에서
     가장 큰 DUP-04 부채.

3. ~~**32번 도구(전체 ruff 규칙) 재검토**~~ — **완료(2026-09-28 3차 세션), 판정: 셋 다 지금은 도입 안 함**.
   `32. Claude 개발표준\project\ruff.toml`(전체 규칙, preview) 로 이 프로젝트를 직접 재검사해
   3개 후보를 실측했다. B008 은 이전 세션 판정(452건 전부 FastAPI Depends 패턴 오탐, 실제 0건)
   그대로 재확인됨.
   - **PLC0415(함수 안 import, 1503건) — 도입 안 함**: 표본 확인 결과 거의 다 의도된 지연 import
     (순환 참조 회피용 `# lazy import` 명시 주석 포함, stdlib 지연 로딩 등). `standard/rules.toml`
     에도 없는 규칙이라 원래 STD 대상이 아님 — 추가 안 함.
   - **ERA001(죽은 주석 코드, 92건) — 도입 보류, 원인 규명**: 20개+ 표본을 직접 대조했는데
     **실제 죽은 코드 0건, 전부 오탐**이었다. 오탐 원인 2가지: ① 이 프로젝트 자체 파일 헤더
     관례(`# module_category: ...` / `# primary_trade: ...`, 14개 파일 × 2줄 = 28건) ②
     콜론으로 구분된 한글/영문 설명 주석("키: 설명" 형태 — 예: `# 기본값: memory (안전)`,
     `# (pattern, tag, is_blocker)`, dataclass 필드 그룹 헤더 `# Required: Schema & IDs` 등)이
     코드처럼 보여 오판됨. `rules.toml` STD-10 에 이미 이름만 올라 있으나(severity=improve),
     이 프로젝트에 켜려면 두 패턴을 전부 예외처리해야 해서 실익이 거의 없다 — 지금은 미도입.
   - **C901(복잡도, 348건) — 일부만 후속 후보로 채택, 전체 도입은 보류**: `rules.toml` STD-08 에
     이미 있고(severity=improve, 차단 아님) 분포를 보면 158건(45%)이 임계값(10) 바로 위(11~13)라
     당장 규칙화하면 노이즈가 큼. 다만 **복잡도 30 이상 극단값 14개**는 실제 리팩터링 후보로
     가치 있어 보여 따로 남긴다:
     `scripts/cdp_client.py:main`(**134**, 압도적 1위) · `tools/code_map/fullmap.py:extend`(44) ·
     `scripts/naver/blog/community/blog_explorer.py:main`(39) ·
     `scripts/naver/cafe/collection/cafe_explorer.py:main`(38) ·
     `tools/code_map/modules.py:main`(38) · `tools/repo_gates/codebase_layer_audit.py:classify_path`(35) ·
     `local_agent_redaction.py:_strip_result_data`(32) ·
     `tools/audits/google/audit_google_automation_baseline_contract.py:audit`(32) ·
     `tools/audits/backend/audit_post_tasks_medium_approve_gate_preflight.py:run_audit`(32) ·
     `tools/audits/app/audit_site_sso_subdomain_runtime_baseline.py:audit`(33) ·
     `scripts/naver/mail/collection/inbox_collector.py:collect_inbox`(34) ·
     `browser/agent.py:_cli`(30) · `scripts/explorer/site_crawler.py:crawl_site`(31) ·
     `tools/audits/backend/audit_backend_operation_final_closeout.py:run_audit`(30).
     대부분 CLI `main()`의 긴 if/elif 분기라 구조적으로는 이해되지만, `cdp_client.py`(134)와
     `fullmap.py:extend`(44)는 CLI 분기가 아니라 실질적 복잡도라 우선순위가 높아 보임(미확인 —
     실제 리팩터링은 하지 않음, 다음 세션 후보).
   - **코드 변경 없음** — 이번 항목은 순수 검토/판정. `configs/ruff.toml`·`rules.toml` 둘 다 그대로.
   - **추가 발견·삭제(2026-09-28, 4차 세션)**: ERA001 92건을 전수(92개 전부) 소스라인까지
     직접 대조하다가 `tests/test_browser_admin_approval_contract.py`의 `TestStatusVocabulary`
     클래스(테스트 7개)가 **실제 assert문이 하나도 없는 스텁**임을 발견 — `status = "received"
     # noqa: F841` 처럼 변수만 대입하고, "can_approve = true, can_reject = true" 같은 의도를
     주석으로만 남겨둔 채 실제 검증 코드가 없어 항상 무조건 통과하던 가짜 테스트였다(사용자
     지시 "기능적으로 구현이 안되는 코드는 모두 삭제해"로 삭제 확정). 삭제 후 확인:
     - 같은 의도(상태값 검증)를 실제로 assert 하는 진짜 테스트가 다른 파일에 이미 존재함
       (`tests/test_browser_websocket_payload_schema.py::TestStatusVocabulary`, 스키마 대상
       실제 검증) — 커버리지 공백 없음.
     - 모듈 docstring의 "5. Status vocabulary consistency" 항목 삭제 + 왜 지웠는지 사유 주석 추가.
     - `pytest tests/test_browser_admin_approval_contract.py` 44→37개로 통과(제거한 7개 제외 전부
       그대로 통과), ruff 통과, layer audit FORBIDDEN/SECURITY/CIRCULAR 0건 확인.
     - **범위 한정**: 이번엔 이 파일 1건만 처리. "기능 미구현 코드 전수 삭제"를 코드베이스
       전체로 확대하려면(assert 없는 테스트, `pass`만 있는 스텁 함수 등) 별도의 전수 스캔이
       필요 — 이번 세션 범위 밖, 다음 세션 후보로 남김. — audit-kit std 결과(110건)는 신뢰할 만해 보이지만(worktree 오염 전후 동일), 실제 파일별 breakdown은 아직 안 봤음.
3. **32번 도구(전체 ruff 규칙) 재검토** — 노이즈(RUF105 2,939건, preview 모드 noqa 문법 차이)를 뺀 진짜 후보: `PLC0415`(함수 안 import, 1507건), `C901`(복잡도, 354건), `B008`(사실 FastAPI라 0건으로 판명), `ERA001`(죽은 주석 코드, 92건) 등. 사용자가 "나중에 따로 다루자"고 미뤄둔 상태.
4. **STD-06~10 등 나머지 STD 카테고리** — 이번 세션에서 아예 안 봄(STD-03=print문, STD-06~10 등). audit-kit 번들 기준 카운트가 크지만(수백 건씩), 위 "설정 불일치" 함정이 있으니 프로젝트 자체 config로 먼저 재확인할 것.
5. **`.claude/settings.json`/`settings.local.json`의 `C:\work\...` 하드코딩 경로** — 이전 세션에서 발견됐으나 이번 세션 범위 밖. install-readiness와 직결(다른 PC/경로에서 hook 전체가 무동작).
6. **로컬 Docker 미설치 전제 재확인** — CLAUDE.md에 "로컬 Docker CLI 없음" 명시돼 있음, 타인 PC엔 Docker가 있을 수도 없을 수도 있어 설치 문서에 명확히 남길 것.

## 재현/검증에 쓴 핵심 명령어

```bash
# 이 프로젝트 자체 기준 특정 규칙 재검사(audit-kit 번들 대신)
py -3.14 -m ruff check --config configs/ruff.toml --select <RULE_ID> --statistics .

# 영향 테스트 찾기 + 실행 (전체 pytest 금지, 21분+ 걸리고 멈추는 결함 있음)
HAEHAN_NO_BROWSER_LAUNCH=1 py -3.14 tools/code_map/query.py tests-for <파일>
py -3.14 -m pytest <나온 테스트 파일들> -q

# 게이트 3종 (커밋 전 필수)
py -3.14 tools/repo_gates/codebase_layer_audit.py
py -3.14 -m pytest tests/test_codebase_layer_audit.py -q
py -3.14 tools/quality/quality_gate.py --staged --enforce --allow-existing-code-change

# audit-kit 공식 재검사 (worktree 없는 깨끗한 상태에서만 신뢰할 것)
audit-kit std --path "C:\Users\skyjw\claude-dev-handoff\01. haehan-ai-orchestrator" --no-mypy --fail-on never
```

## 병렬 서브에이전트 작업 시 체크리스트 (오늘 정립됨)
- `isolation: "worktree"` 필수(PreToolUse 가드가 강제함).
- 건수 기준 균등 분배 스크립트: `C:\Users\skyjw\AppData\Local\Temp\claude\C--Users-skyjw\ef243338-b841-4d44-884b-0885d5c3373f\scratchpad\balanced_split.py` (세션 스크래치패드라 다음 세션엔 없을 수 있음 — 필요하면 이 문서의 로직 참고해 재작성).
- 매 파일 실제 pytest 실행 + 가능하면 git stash로 수정 전/후 대조까지 요구할 것(이번 세션에서 가장 신뢰도 높았던 검증 방식).
- 완료 후 `docs/known_preexisting_issues.md`를 먼저 참고/갱신하도록 지시문에 명시할 것(아직 습관화 안 됨, 이번엔 사후에 만들어서 이번 배치엔 적용 못 함).
- 작업 끝나면 병합 전 worktree 프로세스 정리 확인(Chrome/cdp_daemon.py 등 좀비 프로세스가 worktree 폴더 삭제를 막을 수 있음 — `Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like "*<agent-id>*"}`로 확인 후 종료).
