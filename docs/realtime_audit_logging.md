# 실시간 감사 및 로그 운영 기준

**작성일**: 2026-05-13  
**목적**: 사이트 자동화 작업의 시작/완료/실패를 실시간으로 추적하고, 작업별 JSON 실행 로그와 공통 감사 로그를 연결한다.

---

## 1. 로그 파일

| 파일 | 용도 |
|------|------|
| `data/logs/realtime_audit.jsonl` | 구조화 감사 이벤트. 자동 분석/필터링용 |
| `data/logs/realtime_audit.log` | 사람이 tail로 보는 한 줄 요약 로그 |
| `data/logs/app.log` | 일반 디버그 로그 |
| `data/logs/critical.log` | 중요작업 감사 로그 |
| `data/eum_runs/<workflow>/*.json` | EUM workflow별 실행 상세 기록 |

---

## 2. 기록 방식

공통 기록 API:

```python
from scripts.common.realtime_audit import emit_event

emit_event(
    "EUM_WORK_STARTED",
    site="eum",
    workflow="device_history",
    status="running",
    risk="read",
    message="EUM workflow started",
    metadata={"args": ["DEVICE-001"]},
)
```

민감키는 저장 전에 마스킹한다.

- `token`
- `password`
- `secret`
- `cookie`
- `session`
- `authorization`
- `api_key`

---

## 3. 실시간 감시 명령

최근 감사 이벤트:

```bash
python scripts/common/realtime_audit.py recent --limit 30
python scripts/common/realtime_audit.py recent --site eum
```

JSONL 실시간 감시:

```bash
python scripts/common/realtime_audit.py tail
```

사람이 읽는 텍스트 로그 감시:

```bash
python scripts/common/realtime_audit.py tail --text
python tools/runtime/watch_log.py
```

특정 파일 감시:

```bash
python tools/runtime/watch_log.py data/logs/app.log
python tools/runtime/watch_log.py data/logs/critical.log
```

---

## 4. EUM 자동 연결

`scripts/eum/run_log.py`는 `work_run()` 컨텍스트를 통해 다음 이벤트를 자동 기록한다.

| 이벤트 | 시점 |
|--------|------|
| `EUM_WORK_STARTED` | workflow 실행 시작 |
| `EUM_WORK_COMPLETED` | workflow 정상 종료 |
| `EUM_WORK_FAILED` | 예외 발생 |

연결된 명령 예:

```bash
python scripts/entry/cdp_cli.py eum work history DEVICE-001
python scripts/entry/cdp_cli.py eum work registration P-001 D-001 Seoul --prepare
```

---

## 5. 다른 사이트 적용 기준

새 사이트는 각 workflow 실행 컨텍스트에서 다음 이벤트를 최소 기록한다.

```text
<SITE>_WORK_STARTED
<SITE>_WORK_COMPLETED
<SITE>_WORK_FAILED
```

권장 metadata:

| 필드 | 설명 |
|------|------|
| `code` | 사이트 내부 페이지/업무 코드 |
| `command` | 사용자 실행 명령 |
| `args` | 민감값 제거 또는 마스킹된 인자 |
| `artifact_path` | 상세 실행 JSON 경로 |
| `error_type` | 실패 시 예외 타입 |
| `error` | 실패 시 짧은 오류 메시지 |

상태 변경 작업은 실시간 감사 이벤트만으로 승인된 것으로 간주하지 않는다. 최종 제출은 반드시 별도의 승인 게이트를 통과해야 한다.

---

## 6. 초기 품질 게이트

저장소 변경 품질은 `tools/quality/quality_gate.py`가 검사한다.

검사 항목:

- 기존 active code 수정 여부 차단
- 코드 변경 시 테스트 또는 설계문서 동반 여부 확인
- DB/schema 관련 변경 시 문서와 테스트 동반 여부 확인
- destructive SQL 키워드 감지
- 배포 관련 변경 시 성공한 dry-run 증적 필수
- 검사 결과를 `QUALITY_GATE_CHECK` 감사 이벤트로 기록

실행:

```bash
python tools/quality/quality_gate.py
python tools/quality/quality_gate.py --staged --enforce
```

로컬 pre-commit 훅 설치:

```bash
python tools/quality/install_quality_gate.py
```

훅은 staged 변경만 검사하므로 기존 작업트리의 미정리 파일 때문에 커밋 전 검사가 불필요하게 깨지지 않는다.

---

## 로그인 실시간 탐지 및 세션 저장

운영 기준:

- 모든 로그인은 감지 즉시 저장한다.
- 저장 대상은 쿠키와 localStorage/sessionStorage 기반 세션이며, 비밀번호/OTP/인증서/토큰 평문은 저장하지 않는다.
- 세션 파일은 `scripts/auth/auth_session.py`의 암호화 저장 경로를 사용한다.
- 감지 결과는 `scripts/browser/cdp/cdp_db.py`의 `sessions.session_file`에도 연결한다.
- `LOGIN_SESSION_SAVED` 감사 이벤트를 남긴다.

실시간 감시 명령:

```powershell
python scripts\entry\cdp_cli.py login-watch
```

지정 시간만 실행:

```powershell
python scripts\entry\cdp_cli.py login-watch 1 300
```

등록된 사이트는 사이트 키로 저장하고, 등록되지 않은 사이트는 현재 URL host를 site key로 저장한다.

배포 관련 변경 전 dry-run 기록:

```bash
python tools/deploy/deploy_dry_run.py -- <dry-run command>
```

예:

```bash
python tools/deploy/deploy_dry_run.py -- python -m pytest tests/test_quality_gate.py -q
```

`docker/`, `Dockerfile`, `docker-compose.yml`, `ai_orchestrator.connectors.instagram/`, `ai_orchestrator.browser_tool.worker/`, `services/`, GitHub Actions workflow 변경은 성공한 dry-run 증적 없이는 게이트가 실패한다.
## App Realtime Check

Updated: 2026-05-13

Use `tools/runtime/app_realtime_check.py` for live app-level monitoring. It is
read-only and records one `APP_REALTIME_CHECK` event per cycle.

Checks:

- API health: `http://127.0.0.1:8400/api/v1/health`
- CDP browser health and tab count: `http://127.0.0.1:9222/json/*`
- Realtime audit log freshness
- Latest pre-change dry-run status
- Worktree index freshness

Run once:

```powershell
python scripts\ops\app_realtime_check.py
```

Run continuously:

```powershell
python scripts\ops\app_realtime_check.py --max-runs 0 --interval-seconds 30 --quiet
```

Artifacts:

- `data/logs/app_realtime_check_latest.json`
- `data/logs/app_realtime_check.jsonl`
- `data/logs/app_realtime_check.pid`
