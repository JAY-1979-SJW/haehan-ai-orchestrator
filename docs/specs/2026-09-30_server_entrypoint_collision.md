# `ai_orchestrator/server.py` ↔ `ai_orchestrator/server/` 이름 충돌 정리 — 기준서

- 날짜: 2026-09-30 / 상태: **v2 적용(별칭 제거)** — v1(lazy 별칭 유지)은 CI 순환 검사에서 실패해 폐기 / 브랜치: `refactor/server-entrypoint-collision`
- 근거: STRUCT-01(같은 부모에 `x.py` 와 `x/` 공존 금지) 도입 전 기존 충돌 6건 중 1건. 사례 원장 CASE-16.

## 1. 문제
- 파이썬은 `server.py` 와 `server/` 가 함께 있으면 **패키지가 이긴다** → `server.py` 는 `import` 로 절대 못 불러온다.
- 그래서 `server/__init__.py` 가 `spec_from_file_location("ai_orchestrator._server_module", …)` 로 **파일을 직접 실행**하는 우회 로더를 쓴다.
  - 이 모듈은 `sys.modules` 에 등록되지 않아 도구·디버거·`reload` 가 다루기 어렵고, 로그 이름이 `ai_orchestrator._server_module` 로 찍힌다.
  - `-m ai_orchestrator.server` 로 실행 불가(현재 참조 0건이라 영향 없음).

## 2. 변경 (제안)
| 항목 | 내용 |
|---|---|
| `git mv ai_orchestrator/server.py ai_orchestrator/asgi.py` | 내용 변경 0줄. 이력 보존 |
| `ai_orchestrator/server/__init__.py` | 우회 로더 제거. `__getattr__("app")` 이 `from ai_orchestrator.asgi import app` 를 **처음 요청받을 때** 실행(순환 import 방지 목적의 lazy 유지) |
| 진입점 표기 | `ai_orchestrator.server:app` **그대로 동작**(참조 유지) → uvicorn 10개 파일·`from … import app` 25개 파일 수정 불필요 |
| 후속(이 작업에서 같이) | `configs/module_registry.json` 의 파일 경로 → `registry_sync.py --fix`; 문서의 `server.py` 경로 언급 6곳 갱신 |
- 레이어/의존성 방향, API 응답 key, DB, 산식, 보안 정책: **변경 없음**. 신규 파일 위치: `asgi.py` 는 기존과 같은 디렉터리(서버 진입점, L8).

## 3. 드라이런 결과 (git worktree 에서 실제 이름 변경 후 측정, 저장소 미변경)
| 측정 | 변경 전 | 변경 후 |
|---|---|---|
| 라우트 수 / 목록 | 295 | 295, **목록 완전 동일** |
| 미들웨어 | CORS, BrowserGate | 동일 |
| lifespan | `merged_lifespan` | 동일 |
| `app` 두 번 import | 같은 객체 | 같은 객체 |
| `reload` 후 | 새 객체 아님 | 동일 |
| 관련 테스트 10개 파일 | 29 실패 / 87 통과 / 13 skip | **29 / 87 / 13, 실패 목록 동일** |
- 주의 1: worktree 에는 `.env`(추적 안 됨)가 없어 처음엔 401 로 4건 더 실패 → `.env` 복사 후 동일. 코드 차이 아님.
- 주의 2: 기존 29 실패는 **이번 변경과 무관한 기존 부채** — `test_fetch_web_page` 10, `test_approval_read_api` 14, 기타 5. 별도 이슈로 다룬다.
- 확인 못 한 것: 실제 서버 기동(uvicorn)·Electron 경유 기동. 변경 후 실기동 `/health` 200 확인을 실행 단계에 포함한다.

## 4. 부작용
- 로그 로거 이름 `ai_orchestrator._server_module` → `ai_orchestrator.asgi` (과거 로그는 그대로, 필터가 이름에 걸려 있는지 실행 단계에서 grep 확인).
- 기록·문서 속 `server.py` 서술은 과거 시점 기록(worklog 등)은 손대지 않는다.

## 5. 실행 순서(승인 후)
1. `git mv` + `__init__.py` 교체 → 2. `registry_sync.py --fix` → 3. 문서 경로 갱신
4. 게이트: `codebase_layer_audit.py`, `test_codebase_layer_audit.py`, `quality_gate.py --staged --enforce --allow-existing-code-change`
5. 위 10개 테스트 재실행(29/87/13 유지) + 서버 실기동 `/health` 200 → 6. 커밋·PR (병합은 사용자)

## 6. 되돌리기
커밋 1개 revert 로 원복(파일 이동 + `__init__.py` 뿐).

## 7. 환경 메모
- 이 PC `py -3.14` 의 FastAPI 가 0.136.3 이라 `requirements.txt`(`>=0.137.0`) 미충족 → `iter_route_contexts` ImportError. 0.142.2 로 올려 해결(환경 조치, 저장소 변경 없음). `~udit-kit` 깨진 설치 흔적 경고도 있음.

---
## v2 — 별칭 제거 (2026-09-30, CI verify 가 잡은 결함에 대한 근본 수정)

### 왜 v1 을 버렸나
v1 은 `server/__init__.py` 의 lazy `__getattr__` 로 `ai_orchestrator.server:app` 표기를 유지했다. 그러나 CI `verify` 의
**모듈 순환 검사가 80 → 81** 로 늘었다: `ai_orchestrator ↔ ai_orchestrator/server` (server → asgi 연결선이 정적으로 드러남).
옛 우회 로더(`spec_from_file_location`)는 이 연결선을 검사기에서 숨기고 있었을 뿐이다. 로컬 `codebase_layer_audit` 는 0 이라고
했지만 CI 가 쓰는 측정(`verify_change` 의 `modules.py`)과 다른 도구였다 → **로컬 통과를 CI 통과로 보고하지 말 것.**
`importlib.import_module("리터럴")` 로 바꿔도 검사기가 문자열 리터럴 import 까지 읽어 소용없었고, 상수로 가려서 통과시키는 방법은
검사기를 속이는 것이라 채택하지 않았다.

### 변경
- `ai_orchestrator/server/__init__.py`: `app` 별칭 제거. 이 패키지는 asgi 를 참조하지 않는다(방향은 asgi → router → server.* 하나).
- 진입점 표기 전부 `ai_orchestrator.asgi:app` 로: `docker-compose.yml`, `start_server.bat`, `scripts/ops/dev_launch.ps1`, `AGENTS.md`, `CLAUDE.md`,
  `docs/deploy-api-container.md`, `ai_orchestrator/app.py`(주석), `reach.py`(주석), `configs/verify_change.json`(route_check).
- `from ai_orchestrator.server import app` → `from ai_orchestrator.asgi import app` (24개 파일), 테스트의 `server` 모듈 reload/import 5곳 → `asgi`.
- 감사 스크립트의 서버 계층 이름: `codebase_layer_audit.py`(OPENAPI_APP_MODULES 교체, 금지 import 쌍 추가), `audit_backend_premium_domain_core.py`,
  `module_quality_gate_modules.py`(py_compile 대상 경로), `local_agent/config.py`(주석).
- 잠금 테스트: `tests/test_backend_router_server_cycle_break_20260516.py` 에 "server/__init__.py 가 asgi 를 (문자열 포함) 참조하지 않음" 추가.
- 손대지 않음: 과거 기록(`docs/worklog.md`, `docs/defect_index.json`, 2026-09-26 기준서).

### 검증 (기준 = origin/master 를 별도 worktree 로 같은 조건 실행)
| 항목 | 기준 | 변경 후 |
|---|---|---|
| 모듈 순환(CI 와 같은 측정 함수) | 80 | **80, 새로 생긴 것 없음** |
| 라우트 목록 | 296 | 296, **완전 동일** |
| 영향 테스트 28개 파일 | 91 실패 / 543 통과 | 91 실패 / 544 통과 (**새 실패 0**, 통과 +1 = 새 잠금 테스트) |
| 실기동 `uvicorn ai_orchestrator.asgi:app` | — | `/api/v1/health` 200, 로거 이름 `ai_orchestrator.asgi` |
- 기준의 91 실패는 이번 변경과 무관한 기존 부채(`test_fetch_web_page`, `test_approval_read_api` 등).

### 남는 위험
- **배포 표기가 바뀐다**: 운영 서버가 이 커밋을 pull 하면 `docker-compose.yml` 의 명령이 `ai_orchestrator.asgi:app` 이 된다(코드와 같은 커밋이라 함께 바뀜).
  저장소 밖(예: 서버에 따로 둔 systemd/스크립트, 패키징된 설치본)에 `ai_orchestrator.server:app` 이 남아 있으면 `app` 속성 없음(AttributeError)으로 즉시 실패한다 — 병합 전에 확인 필요.
