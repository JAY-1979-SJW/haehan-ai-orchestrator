# 작업 기록 저장소(Work Record Store, WRS) — 기준서

- 날짜: 2026-10-05 / 상태: **기준서 초안(코드 미착수) — 드라이런 포함, 사용자 승인 대기** / 브랜치: `stage/spec-work-records`
- 기존 구현 확인: 완료(읽기 전용 inventory 3종 — 서버 persistence 스토어, `data/` 파일 저장소, 훅·메모리·조회 API). 통합 job/run/artifact 저장소는 **없음**으로 확인. `capability_check`·코드 실행은 하지 않았다(문서 작업).
- 요청 원문: "작업한 것을 저장하는 저장소 및 기록을 저장하고, 재호출해서 다시 사용이 되게 해야 하니 클로드 웹도 작업 기록을 저장하고 호출하듯이 동일하게 해줘."
- 원칙: 새 저장 방식을 발명하지 않는다. 기존 SQLite 스토어 패턴을 재사용하고, 기존 스토어는 **참조(링크)** 한다. 이번에는 문서만 — 코드·스키마·설정 변경 없음.

## 1. 목적과 범위

사이트 탐색 결과(지도), 업무 정의(task spec), 실행 이력, 결과, 사용자 결정, 승인, 오류, 산출물 파일을 **작업(job) → 단계(step) → 산출물(artifact)** 로 저장하고, 검색·재호출·재실행(같은 입력/수정해서)·이어서 하기(resume)·복제가 되게 한다. 신규 사이트 탐색·지도·업무개발(6a 담당 `new_site_onboarding`, `site_task_map` 계열)의 기반 저장소다.

### 1-1. Claude 웹 기능 대응표

| Claude 웹 기능 | 이 저장소의 대응 | 현재 상태/빈틈 |
|---|---|---|
| 대화/프로젝트 목록 + 제목 | job 목록 + `title` | 작업 단위 제목 필드 없음. 6곳 분산(inv_B §6) |
| 타임라인(대화 흐름) | `wrs_events` append-only | agent_dispatch.subtasks, gongmu.events 등 부분 선례뿐 |
| 검색(제목·내용) | 제목·태그·상태·사이트·기간 필터 + 요약 필드 검색 | 기존은 limit 만, 기간/전문검색 없음(inv_A §5-4) |
| 이어가기(대화 계속) | resume: 마지막 완료 step 이후부터 새 run | `sites/job_state` 가 유일한 pause/resume 선례(JSONL, 메모리) |
| 다시 생성/편집 후 재전송 | 재실행(`rerun_of`): 같은 입력 / 수정 입력 | 재실행 링크·parent 구조 없음 |
| 대화 분기 | 복제(`forked_from`) | 없음 |
| 즐겨찾기/태그/보관 | `starred`, `tags`, `archived` | 없음 |
| 첨부 파일 | artifact(경로+sha256+크기) | gongmu.task_docs 만 선례, 범용 없음 |
| 내보내기/삭제 | export(JSON 번들), 보존·삭제 | retention 없음, 삭제 API 없음 |

핵심 차이: Claude 웹은 읽기만 하지만 이 저장소의 재호출은 **외부 사이트에 영향**을 줄 수 있다. 그래서 재실행·resume 은 승인 게이트를 우회하지 않는다(§6-3).

## 2. 현황 (기존 구현 inventory)

레이어는 `configs/module_registry.json` 기준(inv_A). 위치 `s/` = `ai_orchestrator/storage/`.

| 이름·파일 | 저장 내용 | 키/스키마 | 위치·백엔드 | 보존 | 검색 | 재호출 | 민감 위험 | 레이어 | 중복·빈틈 |
|---|---|---|---|---|---|---|---|---|---|
| agent_dispatch_store | 작업 분배안+하위작업 | dispatches/subtasks, user_version=1 | `s/agent_dispatch.db` SQLite | 삭제 API 없음 | limit≤100, 인덱스 없음 | `/ai-agent/dispatch` admin/owner | prompt/result_text 평문 | L7 | job/step 에 가장 근접하나 parent·산출물·tenant 없음 |
| scheduled_job_store | 예약작업 jobs+runs | user_version=2, idx_runs_job | `s/scheduled_jobs.db` | runs 정리 없음 | list_runs | `/scheduled-jobs` | params 에 수신자·본문 평문 | L7 | 승인 포함 회차 전이 있음, 산출물·parent 없음 |
| site_task_map_store | 호스트별 업무 지도 | `data/site_task_map/<host>.json` 원자 교체 | 파일 | 이력 없음(덮어쓰기) | 지도 내 lookup | `/site-map/*` admin/owner | 구조만(URL 쿼리 확인 필요) | L7 | 버전 이력·실행 이력 없음 |
| site_registry_store | 등록 사이트 | `data/site_registry/sites.json` | 파일 | deregistered 표시 | load_all | `/site-registry` | 구조만 | L7 | 프로세스 내 락만 |
| site_task_map_request_store | 탐색 요청(승인 카드) | uuid 파일 | `data/site_task_map_requests/` | 없음 | glob+정렬 | `/site-map/explore/requests` | start_url 쿼리 가능 | L7 | 페이징 없음 |
| approval_record_store (browser_tool) | 브라우저 승인 이벤트 | `workflow_run_id`,`tenant_id`,`site_id` 보유 | `<LOG_DIR>/approval_records.jsonl` | 없음 | 전체 로드 후 메모리 필터 | `/browser-approvals/*` | URL 리다크션+sha256(`:247-297`) | L7 | 승인 3종 중 하나, 키 정합 기준 |
| dev_reg_approval (gates) | 개발자등록 승인 | task_id, token_hash | `dev_reg_approvals.jsonl` | 없음 | history limit/offset | `/dev-reg/approvals/*` | screenshot_path 해시 없음 | L2 | 승인 개념 중복 |
| approval_tokens.jsonl (gates/approval) | 승인 토큰 | 구조 확인 필요 | `approval_tokens.jsonl` | 없음 | 확인 필요 | 확인 필요 | 확인 필요 | L2 | 승인 3종 중복 |
| audit_logger | 전체 감사 이벤트 | task_id 하나 | `audit_logs.jsonl` | 순환 없음 | 전체 read_text 후 tail | `GET /logs`(JWT만) | target/note 자유 텍스트 | L12 | 역할 제한 없음 |
| auth_audit | 인증 이벤트 | 이메일 마스킹 | `auth_audit.jsonl` | 없음 | 읽기 함수 없음 | 없음 | 낮음 | L2/L7 불일치 | 읽기 경로 부재 |
| dev_reg_audit_log | 감사 실행 요약 | 13필드 화이트리스트 | `data/dev_reg_audit_runs.jsonl` | 없음 | load_recent_runs | CLI | 안전 | L7 | 화이트리스트 선례 |
| gongmu_store | 공무 업무판 | tasks/task_docs(경로+sha256)/events, v2 | `s/gongmu.db` | 삭제 API 없음 | idx | `/gongmu/*` | 원본 미저장 | L7 | 산출물·events 선례 |
| naver_mail_draft / fax / mail_bulk | 초안·승인서·발송이력 | events, document_hash | `s/*.db` | draft TTL 만 | list | 각 라우터(미조사) | 전체 주소·본문 DB 저장 | L7 | 승인불변·dedupe 선례 |
| sites/job_state | 자동화 job pause/resume | RUNNING→PAUSED_FOR_REAUTH→RESUMABLE→DONE | `site_jobs.jsonl` | 없음 | 메모리 | 내부 | 쿠키/OTP 금지 규약 | L1 | resume 선례 |
| ai_work_records | 레인별 작업 기록 | 22개 키(approval_status, steps, decisions, resume_next_step, task_id 등) | `data/runtime/ai_work_records/<lane>/` latest.json + history.jsonl | history 무한 append | 파일 읽기 | `ai_work_session.py resume-check` | secret_values_output=false, safe_text | 스크립트 | 레인 1개(google)만 실사용. 기본 history 경로 불일치 |
| data/sitemap (구 계통) | 호스트·시각별 탐색 JSON | auto/crawl/snapshot 3형식 | `data/sitemap/*.json` | 누적, 삭제 없음 | 파일명 glob(sitemap_gate) | `task_mapper.import_auto_sitemap` | 낮음~중 | 스크립트 | 로컬 폴더 부재, 신 계통과 이중 |
| data/audit | 브라우저·승인 감사 | L1/L2/L3 일·월 분할 | `data/audit/` | 분할만 | check_audit.py | 스크립트 | 중(마스킹 의존) | L4 | 공통 task_id 없음 |
| data/ops/worklog.jsonl | 커밋 로그 | ts,kind,path / hash,subject | 파일 | 인계 시 정리 | tail | `session_handoff.py` | 낮음 | 스크립트 | 작업 단위 아님 |
| W1~W7 창고 폴더 | approvals/drafts/evidence/artifacts 등 | `shared_warehouse_model.md` | `data/<창고>/` | 없음 | 없음 | 없음 | - | 문서 | 쓰는 코드 없음, 자리만 존재 |
| docs/defect_index.json, 메모리, BOARD.md | 결함/인계/상태 | 사람 편집 JSON·md | 저장소/저장소 밖 | 수동 | 없음 | 사람이 읽음 | 낮음 | L12 | 기계 조회 불가(WRS 비대상, 링크만) |

### 2-1. 쿠키 백업 파일 사실(내용 미열람)

- `data/_cdp_cookies_backup.json`(34,876B, 2026-06-04), `data/_cdp_cookies_preserve.json`(76,147B, 2026-06-05) 존재 (inv_B §3).
- gitignore: `.gitignore:215` `data/**/*.json` 포괄 규칙으로만 무시, git 추적 없음. 파일명 전용 규칙 없음.
- 생성·읽기 코드: 저장소 전체 grep 에서 파일명 문자열 없음 → 생성/읽기 코드 부재(고아 파일 추정).
- 평문 여부는 의도적으로 열지 않아 **확인 필요**. 규칙 충돌 가능성: `CLAUDE.md` 보안 금지선 "쿠키/session 추출 금지", `shared_warehouse_model.md`("session/cookie/token/password 저장 금지"). → 처리는 열린 질문 Q7.

### 2-2. 주요 빈틈

1. 통합 job/run/artifact 저장소 없음 — SQLite 4~7개 + JSONL 6개 + JSON 3종에 분산.
2. 승인 저장소 3종 중복(approval_tokens / approval_records / dev_reg_approvals).
3. 지도 구(`data/sitemap`) · 신(`data/site_task_map`) 두 계통, 둘 다 로컬 부재.
4. retention·백업 없음(history 무한 증가, 삭제 API 없음).
5. parent/재실행 링크·버전 이력 없음(지도는 덮어쓰기).
6. 작업 기록 6곳 분산, 공통 task_id 없음.
7. prompt/params 평문 저장(마스킹 없음), `GET /logs` 역할 제한 없음.

## 3. 데이터 모델

원칙: **메타데이터는 SQLite, 산출물은 파일(경로+sha256)**. 값(결과 데이터·폼 값)은 기본 저장하지 않는다 — M5 runner 의 "구조만 저장" 원칙과 일치(§3-6).

### 3-1. job (`wrs_jobs`, 가변: 상태·태그·즐겨찾기만)

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| job_id | TEXT PK | O | uuid4 hex32 |
| kind | TEXT | O | `site_map_explore` / `task_run` / `dev_task` / `ops_check` / `manual`. 허용목록 |
| title | TEXT | O | 사람이 읽는 제목(검색 대상) |
| status | TEXT | O | §3-2 |
| site_id / host | TEXT | - | 도메인(`site_registry` 의 host 와 동일 표기) |
| input_params_json | TEXT | O | 허용 필드 화이트리스트+마스킹 후 값. 비밀 제외 |
| input_hash | TEXT | O | 정규화 입력 sha256(동일 입력 재실행 판정) |
| tags_json | TEXT | - | 문자열 배열 |
| starred / archived | INTEGER | O | 0/1 |
| rerun_of / forked_from / resumed_from | TEXT | - | 다른 job_id(자기 참조 FK). 한 job 에 하나만 |
| version | INTEGER | O | 같은 `input_hash` 계보 내 순번 |
| tenant_id | TEXT | O | 기본 `default`(Q3) |
| created_by / updated_by | TEXT | O | actor 문자열(기존 관례) |
| retention_class | TEXT | O | `standard`/`short`/`keep`(Q2) |
| workflow_run_id / task_id | TEXT | - | 기존 승인·감사 키와 연결 |
| created_at / updated_at | TEXT | O | ISO8601 UTC |

### 3-2. 상태와 허용 전이 (원자적 `UPDATE ... WHERE status IN (...)` rowcount==1 판정 — `agent_dispatch_store.py:143-152`)

| 상태 | 의미 | 다음 허용 |
|---|---|---|
| draft | 입력 작성 중 | pending_approval, cancelled |
| pending_approval | 승인 대기 | running, cancelled, expired |
| running | 실행 중 | succeeded, failed, paused, cancelled |
| paused | 재인증/사용자 결정 대기 | resumable, cancelled |
| resumable | 이어서 하기 가능 | running(새 승인 후), cancelled |
| succeeded / failed / cancelled / expired | 종료 | (전이 없음; 재실행은 새 job) |

기동 시 `running` 이 남아 있으면 `interrupted` 로 보이게 하는 기존 관례(`site_task_map_explore_service.py`)를 따라 뷰에서만 파생 표시(추정, 구현 시 확인).

### 3-3. step (`wrs_steps`, 상태만 가변)

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| job_id, seq | PK(복합) | O | 순번 |
| kind | TEXT | O | explore/classify/navigate/read/fill/submit/verify/approve 등 |
| status | TEXT | O | pending/running/succeeded/failed/skipped |
| risk | TEXT | O | read/write/submit (지도 task 의 risk 와 동일 값) |
| started_at / finished_at | TEXT | - | |
| input_summary / output_summary | TEXT | - | 마스킹·길이 제한 요약만 |
| error | TEXT | - | 500자 제한, 마스킹 |
| approval_ref | TEXT | - | 기존 승인 저장소 ID 참조(§3-5) |
| attempt | INTEGER | O | 재시도 횟수 |
| irreversible | INTEGER | O | 1이면 resume 자동 재개 금지 |

### 3-4. artifact (`wrs_artifacts`, 불변 — 삭제는 보존 정책에 의해서만)

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| artifact_id | TEXT PK | O | |
| job_id / step_seq | TEXT / INT | O / - | 소속 |
| kind | TEXT | O | site_map_snapshot / task_spec / run_result_meta / screenshot / report / export |
| path | TEXT | O | 저장소 상대 경로 (`data/work_records/artifacts/...`, 제안) |
| sha256 / size_bytes | TEXT / INT | O | 읽을 때 해시 검증 |
| media_type | TEXT | O | |
| sensitivity | TEXT | O | `public`/`internal`/`restricted` (§6) |
| retention_class | TEXT | O | |
| created_at | TEXT | O | |

### 3-5. event·결정 링크·연결 키

- `wrs_events`(append-only): `event_id AI, job_id, step_seq?, at, actor, event, detail(마스킹 요약)`. 수정·삭제 불가(gongmu_store.events 패턴).
- `wrs_links`: `job_id, link_type(approval/audit/dispatch/scheduled_run/gongmu_task), ref_store, ref_id`. 승인·결정은 **원본을 복제하지 않고 ID 만 참조**한다.
- 연결 키: `task_id`(audit_logger), `workflow_run_id`·`tenant_id`·`site_id`(approval_record 의 필드명과 동일) — 정합 유지.
- 인덱스(제안): (status, updated_at), (host, updated_at), (kind, created_at), (rerun_of), (input_hash), 태그는 별도 `wrs_job_tags(job_id, tag)` 로 정규화해 태그 검색 인덱스.

### 3-6. 값 저장 규칙

기본은 **구조·해시·개수만** 저장하고 결과 값(표 내용 등)은 응답으로만 돌려준다(M5 runner §4와 동일). 값 보존이 필요한 업무는 job 단위 명시 옵션(`store_result=true`)과 sensitivity 등급 지정이 있어야 하며 기본값은 false(Q8).

## 4. 6a 인터페이스

6a(`feat/gongmu-g2`)의 문서: 선행(master) `new_site_onboarding`·`site_task_map`·`m5_runner`·`m6_business_sites`·`m7_onboarding_auto_prepare`, 6a 신규 M8(링크 이동형 읽기)·M9(정밀 탐색: `data_sources`, `declared_tools`). 이 절은 제목·절·저장 방식만 읽어 맞춘 접점이며 6a 문서 본문과 어긋나면 6a 문서가 우선이다(확인 필요).

| 6a 산출 | WRS 에서의 저장 | 방식 |
|---|---|---|
| 호스트별 지도 JSON(`data/site_task_map/<host>.json`) | artifact(`site_map_snapshot`)로 **버전 스냅샷** 보관. job(`site_map_explore`)은 artifact 를 참조 | 지도 저장 시점마다 사본 1개+해시. 현행 덮어쓰기 스토어는 변경하지 않음 |
| task spec(steps/risk/state, M9 data_sources·declared_tools) | 지도 안의 task 를 `task_key` 로 식별해 `kind=task_spec` artifact 로 스냅샷(검증상태 observed/verified/stale 포함). 별도 엔티티 테이블은 두지 않음 | 지도 스냅샷의 부분 참조(`task_key`+지도 해시) |
| 실행 결과(`POST /site-map/{host}/run`, MCP `sitemap.run`) | job(`task_run`)의 한 run. step 은 Recorder 단계 단위, 결과는 **열 이름·행 수·해시** 메타만(artifact `run_result_meta`) | 기본 값 미저장 |
| 지도 변경 이력(`outcome` 기록으로 verified/stale 전이) | `wrs_events` 에 `map_outcome` 이벤트 + 새 스냅샷 | `/{host}/outcome` 호출 지점에서 기록 |
| 탐색 요청 카드(`site_task_map_request_store`) | `wrs_links(link_type=explore_request)` 로 참조 | 파일은 그대로 |

6a 호출 시그니처 초안(스케치, 구현 아님; 위치는 서비스 계층 L6):

```python
record_job_start(kind, title, host, params, *, actor, tenant_id=None, rerun_of=None) -> job_id
record_step(job_id, seq, kind, risk, *, status, input_summary=None, output_summary=None,
            error=None, approval_ref=None, irreversible=False) -> None
attach_artifact(job_id, kind, src_path, *, step_seq=None, sensitivity="internal") -> artifact_id
finish_job(job_id, status, *, error=None) -> None      # 허용 전이 위반 시 예외
```

6a 가 지킬 규칙: (1) 기록 실패가 업무 실행을 막지 않도록 호출은 best-effort 이되 **실패를 조용히 삼키지 않고** 로그에 남긴다(`defect_index` 의 조용한 실패 금지 관례). (2) 비밀·쿠키·폼 값·OTP 를 `params`/`summary` 에 넣지 않는다(화이트리스트 거부). (3) 지도 직접 경로 변경 금지 — 스토어(L7) 경유. (4) WRS 호출 때문에 CDP·브라우저를 새로 열지 않는다. (5) 다른 업무 도메인 간 직접 import 금지 규칙 유지 — WRS 는 공통 하위 서비스로만 import 된다.

## 5. 저장소 선택·레이어

### 5-1. 재사용할 기존 패턴

| 패턴 | 근거 |
|---|---|
| 마이그레이션 | `persistence/sqlite_schema.py:60-91` `apply_schema`(user_version 순차, BEGIN IMMEDIATE, SchemaTooNewError), `:51` `add_column_if_missing`, `:20` `set_busy_timeout` |
| 연결 | `agent_dispatch_store.py:87-97` `_conn()`(timeout=30, isolation_level=None, row_factory, apply_schema) |
| 원자적 상태전이 | `agent_dispatch_store.py:143-152`, `scheduled_job_store.py:250-266` |
| 선점 BEGIN IMMEDIATE | `scheduled_job_store.py:182-214` |
| 컬럼 허용목록 UPDATE | `agent_dispatch_store.py:202-226` |
| 산출물 경로+sha256, append-only events | `gongmu_store`(task_docs, events) |
| JSON 원자 교체 | `site_task_map_store.py:45-57` |
| 안전 필드 화이트리스트 / URL 리다크션+해시 | `dev_reg_audit_log.py:34-70` / `approval_record_store.py:247-297` |

### 5-2. 대안 비교

| 안 | 장점 | 단점 | 판정 |
|---|---|---|---|
| A. 메타 SQLite + 산출물 파일(경로+해시) | 기존 패턴 그대로, 의존성 추가 없음, 인덱스·원자 전이·페이징 가능, 되돌리기 쉬움(DB 파일 삭제) | 다중 서버 동시 쓰기 한계, 운영 볼륨 영속 확인 필요 | **권장** |
| B. JSONL/JSON 만 | 단순, 사람 읽기 쉬움 | 전체 로드·검색 약함, 전이 원자성 없음(현 빈틈의 반복) | 비권장 |
| C. Postgres | 다중 접속·전문검색 강함 | 운영 의존성 증가, 현재 유일 선례도 기본은 메모리(`registration_code_store`), 로컬 개발 부담 | 옵션(Q1) |

### 5-3. 레이어와 신규 모듈 후보 (제안만, 파일은 만들지 않음)

| 층 | 후보 파일 | 역할 |
|---|---|---|
| L1 | `ai_orchestrator/domain/work_record.py` | 상태 전이표·허용 kind·화이트리스트 필드 정의(순수) |
| L7 | `ai_orchestrator/persistence/work_record_store.py` | SQLite 스키마·CRUD·상태 원자 전이, DB `storage/work_records.db`, 산출물 루트 `data/work_records/`(제안, gitignore 필요 확인) |
| L6 | `ai_orchestrator/services/work_record_service.py` | 마스킹·검증·재실행/resume 규칙·승인 확인·해시 검증 |
| L8 | `ai_orchestrator/routers/work_record_router.py` | HTTP 만. **SQL 금지** |
| L9 | `admin-web/src/app/work-records/` | 목록·상세·타임라인 화면 |

정본은 `configs/module_registry.json` — 신규 파일은 registry 등록 후 `registry_sync.py --fix`. 의존 방향: router → service → store → domain. store 는 service·router 를 import 하지 않는다. 6a 사이트 모듈은 service 만 호출(역방향 금지)하고 WRS 는 사이트 모듈(`site_task_map_*`)을 import 하지 않는다 — 접점은 6a 쪽이 서비스 함수를 호출하는 한 방향이라 순환이 생기지 않는다.

### 5-4. 기존 스토어와의 관계

**참조(링크)가 기본, 통합은 하지 않는다.** agent_dispatch·scheduled_job·approval_record·dev_reg_approval·gongmu 는 그대로 두고 `wrs_links` 로 ID 만 연결한다. 통합 후보(승인 3종, 지도 구/신, `ai_work_records`)는 열린 질문(Q4~Q6).

## 6. API / CLI / UI

### 6-1. 엔드포인트 (제안; 접두사는 확인 필요, 인증은 `require_role` 기존 방식)

| 메서드 | 경로 | role | 응답 |
|---|---|---|---|
| GET | `/work-records/jobs` | admin/owner | 목록. 필터: q(제목·태그·요약), status, kind, host, tag, starred, from/to, cursor/limit(≤100) |
| GET | `/work-records/jobs/{id}` | admin/owner | job+steps+artifact 메타+links |
| GET | `/work-records/jobs/{id}/timeline` | admin/owner | events 시간순 |
| GET | `/work-records/jobs/{id}/artifacts/{aid}` | admin/owner (restricted 는 owner) | 해시 검증 후 파일 |
| POST | `/work-records/jobs/{id}/rerun` | admin/owner | body: `mode=same|edited`, `params`. **새 job(draft→pending_approval)** 생성, 즉시 실행 아님 |
| POST | `/work-records/jobs/{id}/resume` | admin/owner | `resumable` job 에서 새 승인 요청 생성 |
| POST | `/work-records/jobs/{id}/fork` | admin/owner | 복제(draft) |
| PATCH | `/work-records/jobs/{id}` | admin/owner | title/tags/starred/archived 만 |
| GET | `/work-records/jobs/{id}/export` | owner | JSON 번들(비밀 제외) |
| DELETE | `/work-records/jobs/{id}` | owner | 소프트 삭제+감사 기록. 보존 정책 우선 |

쓰기(기록 생성)는 HTTP 가 아니라 서비스 함수(§4) — 외부에서 임의 기록 주입 불가.

### 6-2. CLI (제안, `scripts/ops/work_record_cli.py`)

| 명령 | 동작 |
|---|---|
| `list [--q --status --host --since]` | 목록 |
| `show <job_id> [--timeline]` | 상세 |
| `rerun <job_id> [--edit k=v]` | 새 draft 생성(승인 대기까지만) |
| `resume <job_id>` | 승인 요청 생성까지만 |
| `tag/star <job_id>` | 가변 필드 |
| `export <job_id>` / `verify <job_id>` | 번들 / 산출물 해시 검증 |

### 6-3. 재실행·resume 안전 규칙 (명시)

1. 재실행은 항상 **새 job** 이며 `risk>=write` step 이 하나라도 있으면 **새 승인** 필요. 이전 승인 재사용 금지(승인은 job 단위로 만료).
2. resume 은 마지막 `succeeded` step 의 다음부터 새 run 으로 시작하되 `irreversible=1` step(제출·송금·전자서명·삭제)은 **자동 재개 금지** — 사용자가 해당 step 만 다시 승인.
3. 로그인 재인증이 필요하면(`paused`) OTP·캡차는 사용자가 한다. WRS 는 세션을 저장·복원하지 않는다.
4. 투찰/전자서명/송금/결제 자동 실행 금지 규칙은 그대로 적용.

### 6-4. admin-web·MCP

| 접점 | 관계 |
|---|---|
| 기존 `/ops`(ApprovalQueue, AuditEventTable)·`/tasks`·`/site-map`·`/gongmu` | 유지. 각 화면의 상세에서 `wrs_links` 로 해당 job 으로 이동하는 링크만 후보 |
| 신규 화면 후보 | `/work-records`(목록+필터+검색), 상세(타임라인·산출물·재실행/이어서 하기/복제 버튼) — 범위는 Q9 |
| MCP | `sitemap.lookup/list/explore` 는 지도 조회·탐색용으로 유지. 후보 `workrecord.list/show` (읽기 전용만, 재실행은 MCP 에 노출하지 않음 — 승인 UI 경유) |

## 7. 보안

| 항목 | 규칙 |
|---|---|
| 저장 금지 | 비밀값·쿠키·세션·토큰·OTP·비밀번호·결제정보·민감 폼 값. 마스킹/해시/참조 ID 만 |
| 필드 방식 | **허용 필드 화이트리스트**(`dev_reg_audit_log.py:34-70` 방식). 화이트리스트 밖 키는 거부, 키 이름에 password/token/secret/cookie/otp 포함 시 값 제거 |
| URL | `approval_record_store.py:247-297` 의 리다크션+sha256 재사용(중복 구현 금지, import 또는 공통 헬퍼로 승격은 구현 시 판단) |
| 산출물 등급 | public(지도 구조) / internal(실행 메타) / restricted(스크린샷·개인정보 가능). restricted 는 owner 만, 목록 응답에 경로 비노출 |
| 인증·권한 | JWT + `require_role("admin","owner")`(기존 site-map 라우터와 동일). 소유자 필터: owner 는 전체, admin 은 tenant 내 전체(Q3) |
| 기존 접점 지적 | `GET /logs` 는 `get_jwt_user` 만 요구, 역할 제한 없음(inv_A §6) — WRS 는 이 방식을 따르지 않는다. `/logs` 개선은 별건(열린 질문 Q12) |
| 개인정보 | 수신자·메일 본문·연락처는 job 에 저장하지 않고 건수·해시·참조 ID 만(scheduled_job params, naver_mail_draft 는 원본 스토어에 두고 링크) |
| 삭제·보존 | 소프트 삭제, 삭제 이벤트는 `wrs_events` 에 남김. 기본 보존 기간은 Q2 |
| 쿠키 백업 2개 | WRS 는 읽지도 가져오지도 않는다. 처리는 Q7 |
| CDP | 저장소 기능은 CDP/9222/사용자 Chrome 을 호출하지 않는다(순수 DB·파일). 시험도 접촉 없음 |
| 감사 | 기록 조회·재실행·삭제·내보내기는 기존 `audit_logger` 이벤트로도 남김 |

## 8. 마이그레이션

| 기존 | 관계 | 방식 |
|---|---|---|
| `data/runtime/ai_work_records`(22개 키) | 읽기 어댑터 | 변경 없음. `task_id`·`steps`·`decisions`·`resume_next_step` 를 job/step 으로 읽어 매핑(키 대응은 구현 단계에서 확정) |
| `data/sitemap` 구 계통 | 읽기 어댑터(선택) | 기존 `task_mapper.import_auto_sitemap` 경로 유지, 로컬 부재라 우선순위 낮음(Q5) |
| `data/site_task_map`·`site_registry`·`requests` | 참조(스냅샷 신규 생성부터) | 기존 스토어 무변경 |
| `data/ops/worklog.jsonl`, `data/audit` | 링크만(job 의 커밋·감사 참조) | 복제 금지 |
| `data/approvals` 등 W1~W7 빈 창고 | 사용 안 함 | `shared_warehouse_model.md` 와의 정합은 Q10 |
| approval 3종 | 참조 | 통합 여부 Q4 |

이행 단계: (1) 신규 기록부터 쓴다 → (2) 읽기 어댑터로 기존 기록을 목록에 노출 → (3) 과거 백필 여부는 Q6. 되돌리기: 신규 DB·산출물 폴더 삭제만으로 원복, **기존 파일은 한 줄도 수정하지 않는다**.

## 9. 검증 계획

- 모든 시험은 합성 데이터·tmp DB(`tmp_path`)·가짜 산출물 파일. **실사이트·CDP·사용자 Chrome 접촉 없음**, 서버 기동 없음, 외부 호출 없음.
- 시험 목록: 상태 전이(허용/거부 전이표 전수), 재실행 링크(`rerun_of` 체인·자기참조 거부), resume(마지막 완료 step 계산, irreversible 자동재개 거부), 마스킹/화이트리스트(금지 키·URL 쿼리·이메일), 해시 검증(변조 시 실패), 권한(role·tenant·restricted), 페이징/검색(커서·필터 조합), 스키마 마이그레이션(`SchemaTooNewError`), 읽기 어댑터(`ai_work_records` 샘플 합성), 동시 전이(선점 경합 2건), 내보내기에 비밀 없음.
- 게이트 계획: `codebase_layer_audit.py`·`tests/test_codebase_layer_audit.py`, `registry_sync.py --fix`(신규 파일 등록), ruff(`configs/ruff.toml`, 변경 파일만), 영향 테스트만(`code_map/query.py tests-for`, 전체 pytest 금지), `quality_gate.py --staged --enforce --allow-existing-code-change`, 필요 시 `verify_change.py`. 측정 도구는 quick_measure 를 사용할 수 있는지 구현 시 확인.

## 10. 단계(M번호)·위험·영향 파일

| 단계 | 산출물 | 영향 파일(층) | 위험 | 롤백 | 승인 필요 |
|---|---|---|---|---|---|
| M1 | 스키마·스토어·도메인 | `domain/work_record.py`(L1), `persistence/work_record_store.py`(L7), registry | 스키마 확정 후 변경 비용 | 신규 파일 삭제, DB 삭제 | 스키마 변경 승인, Q1·Q3 |
| M2 | 서비스·마스킹·화이트리스트 | `services/work_record_service.py`(L6) | 마스킹 누락=민감정보 저장 | 신규 파일 삭제 | Q8 |
| M3 | 읽기 API | `routers/work_record_router.py`(L8), `router.py` include 1줄(기존 파일 수정) | 라우트 노출·권한 | include 줄 제거 | 신규 라우트 승인 |
| M4 | CLI·재실행/resume | `scripts/ops/work_record_cli.py`, 서비스 | 승인 우회 위험 | 신규 파일 삭제 | 승인 게이트 설계 검토 |
| M5 | admin-web 화면 | `admin-web/src/app/work-records/`(L9) | 화면 범위 확장 | 폴더 삭제 | Q9, typecheck |
| M6 | 마이그레이션 읽기 어댑터 | 서비스 내 어댑터 | 기존 파일 형식 가정 오류 | 어댑터 제거 | Q5·Q6 |
| M7 | 6a 연동 | 6a 쪽 호출 지점(`site_task_map_*` 서비스, L6) | 6a 와 호출 규약 불일치, 도메인 간 import | 호출 줄 제거 | Q11, 6a 담당과 합의 |

M1~M2 는 DB·서비스만이라 외부 영향이 없다. 각 단계는 별도 브랜치·별도 승인(기준서→드라이런→승인→코드).

## 11. 드라이런 결과

- 이 기준서 작성 시점의 **예상 diff**: 신규 `docs/specs/2026-10-05_work_record_store.md` 1개. 수정 파일 0개, 코드·스키마·설정·`CLAUDE.md`·`.claude/**` 변경 없음. 커밋 직전 `git diff --stat origin/master` 로 1개만임을 확인한다(결과는 최종 보고).
- 게이트 통과 예상: 문서 1개 커밋이라 layer audit·quality_gate·registry 대상 변화 없음(코드 파일 미포함). 지도↔골격 대조 게이트도 영향 없을 것으로 추정(실행 안 함).
- 구현 단계 예상 신규 파일(M1~M4 기준): 위 §5-3 후보 5개 + 테스트 `tests/test_work_record_*.py` 수 개 + CLI 1개. 수정 파일: `ai_orchestrator/router.py` include 1줄, `configs/module_registry.json` 등록.
- 예상 사이드 이펙트: 없음(문서). 구현 후에는 디스크 증가(산출물), `.gitignore` 에 `data/work_records/` 확인 필요(`data/**/*.json` 포괄 규칙은 `.db`·png 미포함이라 추가 규칙이 필요할 수 있음 — 확인 필요).

## 12. 열린 질문 (사용자 결정 필요 — 추측 금지)

| # | 질문 | 권장안(참고) |
|---|---|---|
| Q1 | 백엔드: SQLite 단독 vs Postgres 옵션 | SQLite 단독으로 시작, 스토어 인터페이스는 교체 가능하게 |
| Q2 | retention 기본값(job·artifact·events 별 기간, restricted 산출물 단기) | 미정 — 사용자 결정 |
| Q3 | 테넌트 모델: 현재 `tenant_id` 는 approval_record 만 보유. 필수화할지, `default` 고정할지 | 컬럼은 두되 `default` |
| Q4 | 승인 저장소 3종(approval_tokens / approval_records / dev_reg_approvals) 통합 여부 | 이번 범위 밖, 링크만 |
| Q5 | 지도 구(`data/sitemap`)·신(`data/site_task_map`) 계통 통합 여부 | 신 계통만 스냅샷 |
| Q6 | 과거 기록(`ai_work_records` history 88줄 등) 백필 여부 | 읽기 어댑터만, 백필 보류 |
| Q7 | 쿠키 백업 2개 처리: 삭제 / 안전 보관 / 암호화(`auth_session` Fernet 선례). 내용은 미열람이며 열람·이동은 사용자 지시 후에만 | 삭제 또는 암호화 중 사용자 결정 |
| Q8 | 평문 prompt/params 마스킹 정책, 결과 값 저장 옵션(`store_result`)의 허용 범위 | 기본 미저장, 화이트리스트 |
| Q9 | admin-web 화면 범위(목록만 vs 재실행 버튼까지) | 읽기 목록·상세 먼저 |
| Q10 | W1~W7 창고 폴더(`shared_warehouse_model.md`)와 `data/work_records/` 관계(재사용 vs 별도) | 문서 정합 후 결정 |
| Q11 | 6a 호출 규약(함수 시그니처·실패 시 동작·기록 시점) 확정 | §4 초안으로 6a 와 협의 |
| Q12 | 전문 검색 범위(제목·태그·요약만 vs 오류 메시지·event detail 포함) 및 `GET /logs` 역할 제한 개선을 별건으로 할지 | 제목·태그·요약, `/logs` 별건 |
| Q13 | 강제 추적된 `naver_mail_inbox_dump/parsed.json` 처리 | WRS 범위 밖, 별건 보고 |

### 확인 필요 (inventory 미확인 항목)

- `server.py` 라우터 마운트 접두사, `require_role` 구현 세부, `/ops/approvals/gc` 인증, approval_record_router 접두사·인증.
- 운영 서버 `storage/`·`data/` 의 Docker 볼륨 영속 여부와 용량(SQLite 선택의 전제).
- `approval_tokens.jsonl`(gates/approval) 구조, `audit_records`/`execution_history`/`inbox` 쓰기 코드.
- site_task_map task 상세 필드의 URL 쿼리 마스킹, approval_record 의 tenant 필터 사용 여부.
- `ai_work_record.py` 기본 history 경로와 레인 경로 불일치의 의도, `data/realtime_log.jsonl` 작성 주체.
- 6a 문서 본문 세부(여기서는 제목·절·저장 방식만 확인), 실행 결과 저장 위치(M5 문서는 값 미저장으로 기술).
- 쿠키 백업 2개의 평문 여부(의도적 미열람).
