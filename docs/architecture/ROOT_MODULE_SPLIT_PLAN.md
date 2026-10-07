# 루트 모듈 기능별 분리 기준서 (초안 · 승인 대기)

작성: 2026-10-07 · 대상: 저장소 루트의 `.py` 36개 · 상태: **드라이런 완료, 실행 전 승인 필요**

## 1. 왜
루트에 1단계 골격 시절 모듈 36개가 평평하게 놓여 있다. 운영 진입점은 `ai_orchestrator.asgi:app`(Dockerfile)이고
루트 모듈은 레거시 v1 앱(`app.py`, `start_admin.bat`)과 그 부속이다. 기능 경계가 보이지 않아 신규 기능이 또 루트에 쌓인다.

## 2. 분리안 (기능별 패키지)
> **확정(2026-10-07):** 이름 충돌(`apps/*/core`, 범용명 tasks·inbox) 방지를 위해 전부 상위 패키지 **`orchestrator_v1/`** 아래에 둔다.
> 예: `orchestrator_v1/core/logger.py`. 루트 shim은 `sys.modules` 별칭 방식(동일 모듈 객체 → mock.patch·전역상태 안전).

| 새 패키지 | 이동 대상 | 비고 |
|---|---|---|
| `core/` | logger, logging_utils, audit_logger, security_utils, models | 참조 많음(logger 20, audit_logger 17, security_utils 16, models 19) |
| `tasks/` | task_store, tasks_router, candidate_store, candidate_to_task, executor, whitelist_executor, approval_manager, policy_engine, risk_assessor | 승인·실행 흐름 |
| `inbox/` | inbox_store, inbox_router, email_classifier, email_task_store, email_task_approval, email_task_executor, message_classifier, hiworks_mail_reader, kakaowork_reader, notice_router | 메일·메신저 수신 |
| `monitoring/` | monitor, dashboard, log_analyzer, telegram_notifier | dashboard 41, monitor 25 참조 |
| `webhooks/` | webhooks_router | 단일 파일 |
| `scripts/verify/` | verify_agent_ws_auth, verify_live_agent_smoke, verify_live_browser_readonly_dispatch, verify_live_task_dispatch, verify_local_runtime_dry_run | 참조 거의 없음 |
| **루트 유지** | `app.py`, `conftest.py` | app.py 참조 58(테스트 34) — 진입점·pytest 호환 |

기존 하위 구조(`ai_orchestrator/` 589, `scripts/` 1043, `admin-web/`, `local_agent/`)는 **이번에 건드리지 않는다**
(이미 기능별 분리됨).

## 3. 안전장치
1. **호환 shim**: 이동한 모듈마다 루트에 `from <새경로> import *` 한 줄짜리 shim을 남긴다 → 기존 import·`python -m`·bat 전부 무변경으로 동작. 참조가 0이 된 것부터 shim 제거.
2. **새 브랜치 + 별도 worktree**에서만 작업. master·기존 worktree 41개는 건드리지 않는다.
3. 단계별(core → tasks → inbox → monitoring → verify) 커밋, 단계마다 `pytest` + 품질 게이트(`audit_kit_gate.py --staged`) 통과 확인. 실패 시 해당 단계만 되돌림.
4. `git mv`로 이동해 히스토리 보존. Dockerfile(`COPY . .`)은 영향 없음.

## 4. 위험
- 진행 중 브랜치/worktree 41개가 같은 파일을 수정하면 병합 충돌 → 이동 직후 shim이 있어도 파일 경로 충돌은 발생.
  → 진행 중 PR을 먼저 정리(머지)한 뒤 실행 권장.
- 문자열 참조(`"module.path"` 형태 patch 대상, 설정 JSON)는 grep 실측으로 놓칠 수 있음 → pytest 전체로 확인.

## 5. 드라이런 결과
- 이동 대상 36개 중 참조 0~3개: 22개(대부분 verify_*·reader·router 류) — 저위험
- 참조 10개 이상: app, dashboard, monitor, logger, models, audit_logger, executor, security_utils, approval_manager — shim 필수
- 루트 간 상호 참조가 있어(logger 13, audit_logger 9) **core를 먼저** 이동해야 함
