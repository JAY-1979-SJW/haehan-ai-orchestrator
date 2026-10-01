# 사용자 예약 작업 — 기준서 v1

- 날짜: 2026-10-01 / 사용자 요청: "사용자가 예약 작업을 할 수 있는 기능을 개설해줘" · 계획 승인: 2026-10-01(플랜 모드)
- 결정: 작업 범위 = 발행·전송 포함(승인 필요, 2단계) / 반복 = 한 번·매일·매주·N분마다 / 예약 실행 시 CDP 자동 기동
- 관련: `docs/specs/2026-10-01_scheduler_cdp_ensure.md`(커뮤니티 스케줄러 CDP 보장)

## 1. 현황
앱에는 예약 기능이 없다. 서버에는 고정 주기 루프 3개(커뮤니티·gonobi·네이버 검색)만 있다. 일반화된 스케줄러(`scripts/naver/automation/platform/scheduler.py`)는 저장된 문자열을 `importlib` 로 실행하고 승인·위험 검사가 없어 쓰지 않는다.

## 2. 원칙
1. **임의 실행 금지** — 닫힌 허용 목록(`ACTIONS`)의 작업만 이름으로 실행한다. 파라미터는 작업별 검증을 통과해야 한다.
2. **위험 등급** — `local_agent/action_risk_policy.classify_action()` 을 예약 생성 시와 실행 시 두 번 적용한다.
   - `AUTO_ALLOWED`: 예약만 하면 무인 실행(1단계).
   - `USER_DELEGATED`(발행·전송): 회차마다 앱에서 승인해야 실행(2단계). 승인 전에는 실행하지 않는다. 1단계에서는 생성 자체를 거부한다.
   - `USER_DIRECT`·`BLOCKED`: 생성 거부.
3. **놓친 실행** — 예정 시각보다 10분 넘게 늦으면 실행하지 않고 "놓침"으로 기록하고 다음 회차를 계산한다(서버 중단 후 한꺼번에 실행되는 것 방지).
4. **직렬 실행** — 작업은 단일 락으로 한 번에 하나씩(브라우저 공유). 중복 실행은 SQLite `BEGIN IMMEDIATE` 선점으로 막는다.

## 3. 구성 (레이어)
| 레이어 | 파일 | 역할 |
|---|---|---|
| L7 | `ai_orchestrator/persistence/scheduled_job_store.py` | SQLite `storage/scheduled_jobs.db` — `jobs`·`runs`, 원자적 선점 `claim_due` |
| L6 | `ai_orchestrator/services/scheduled_job_service.py` | 반복 계산(once/daily/weekly/interval), 생성·수정·검증, `tick()`, 실행·기록 |
| L6 | `ai_orchestrator/workflows/scheduled_job_actions.py` | 허용 목록, 브라우저 작업 전 CDP 보장 |
| L8 | `ai_orchestrator/routers/scheduled_job_loop.py` | 서버 lifespan 루프(30초 틱). `connectors/` 가 아니라 `routers/` 에 둔 이유: 지도에서 `ai_orchestrator.*` 절대 import 는 루트 패키지 연결로 잡혀, 루트(`server.py`)가 가져오는 새 폴더가 모듈 순환을 만든다. `routers/` 는 이미 루트와 상호 import 관계라 새 순환이 없다 |
| L8 | `ai_orchestrator/routers/scheduled_job_router.py` | `/scheduled-jobs` (admin·owner). PATCH 는 CORS 에서 허용 안 돼 POST 사용 |
| L9 | `admin-web/src/app/scheduled/page.tsx`, `src/lib/nav.ts` | "예약 작업" 화면·메뉴 |

## 4. 데이터
- `jobs(id, name, action, params, recurrence, status[active|paused|done], next_run_at, last_run_at, last_status, last_message, created_by, created_at)`
- `runs(id, job_id, scheduled_for, started_at, finished_at, status[running|ok|failed|missed|skipped], message)`
- 시각은 UTC ISO(`+00:00`)로 저장해 문자열 비교가 가능하다. 매일·매주 시각(HH:MM)은 PC 로컬 시간대로 해석한다.
- 반복: `once{at}` / `daily{time}` / `weekly{days[0=월..6=일],time}` / `interval{minutes>=5}`. cron 은 지원하지 않는다.

## 5. 1단계 작업(무인)
| 키 | 실행 | 브라우저 | 위험 판정 |
|---|---|---|---|
| `community_analysis` | `scripts.community.scheduler.run_all_sites("scheduled")` | 사용 | `extract_text` |
| `naver_login_check` | `naver_session_guard.ensure_login(target)` | 사용 | `detect_login_status` |
| `gonobi_collect` | `scripts.naver.blog.gonobi.runner.run_scrape` | 안 씀 | `extract_text` |
- 네이버 검색 수집(`run_scheduled_collection`)은 `NAVER_SEARCH_SCHEDULE_ENABLED` 가 꺼져 있으면 아무것도 안 하고 성공처럼 보이므로 이번에는 넣지 않는다.

## 6. 2단계(별도 커밋)
회차 승인 흐름(승인 대기→승인/거부, 30분 안 승인 없으면 건너뜀)과 발행·전송 작업 등록. 기존 실행 함수의 시그니처를 확인한 뒤에만 등록한다.

## 7. 검증
단위 테스트(반복 계산·원자 선점·놓침·허용 목록·위험 등급 거부·CDP 호출 조건·라우터 권한), 게이트 3종, `npm run typecheck`·`lint`. 서버 재시작(승인 필요) 후 Electron 화면에서 실제 회차 확인.

## 8. 한계
서버가 꺼져 있으면 예약은 실행되지 않는다. 승인 알림은 앱 화면뿐이다(2단계). 사용자의 수동 브라우저 작업과 CDP 를 함께 쓴다.
