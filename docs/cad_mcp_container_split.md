# CAD MCP 컨테이너 분리

## 왜 분리했는가

기존 `Dockerfile.backend`는 `app/`(REST API)와 `mcp_server/`(MCP 서버) 소스를 하나의 이미지에 묶어 빌드했다.
그러나 MCP 서버 프로세스는 실제로 기동되지 않았고, `mcp` 라이브러리 자체도 backend 이미지에 누락된 상태였다.

이번 단계의 목적은 컨테이너 책임을 명확히 분리하는 것이다.

- **cad-domain 스택** = 도메인 처리 (REST API / Celery worker / Redis)
- **cad-mcp** = MCP tool interface adapter 전용

## 컨테이너 책임

| 컨테이너 | 역할 | 이미지 |
|---------|------|--------|
| `cad-backend` | CAD 물량산출 REST API (FastAPI) | `Dockerfile.backend` |
| `cad-worker` | Celery 백그라운드 작업 | `Dockerfile.backend` |
| `cad-redis` | Redis 브로커/결과 저장소 | `redis:7-alpine` |
| `cad-frontend` | React 정적 파일 서빙 (nginx) | `Dockerfile.frontend` |
| `cad-mcp` | MCP SSE 서버 (tool schema/protocol adapter) | `Dockerfile.mcp` ← 신규 |

## 네트워크 구조

```
[외부 클라이언트]
    │
    ▼ (HTTPS)
[nginx / app_web 네트워크]
    │
    ▼
[orchestrator:8400]  ← auth / approval / audit 게이트
    │
    ├─▶ /api/v1/cad/* proxy ──▶ [cad-backend:8000]   (cad-quantity_default 내부)
    │
    └─▶ (향후) /api/v1/mcp/* proxy ──▶ [cad-mcp:8001] (cad-quantity_default 내부)

[cad-mcp:8001]  ← SSE transport, expose only
    │  read 전용 직통 (GET)
    ▼
[cad-backend:8000]   (내부 DNS: http://cad-backend:8000)
    │
    ▼
[cad-redis:6379] + [cad_storage volume]

cad-mcp write 경로:
    [cad-mcp:8001]
        │  write → orchestrator 경유 (직통 불가)
        ▼
    [orchestrator:8400] /api/v1/cad/* ← 2차 auth/approval/audit 게이트
        │
        ▼
    [cad-backend:8000]
```

## 진입점 및 실행 모드

- **진입 파일**: `mcp_server/server.py`
- **실행 커맨드**: `python3 mcp_server/server.py`
- **컨테이너 모드**: SSE transport (`MCP_TRANSPORT=sse`)
- **내부 포트**: 8001 (expose only — host 바인딩 없음)
- **로컬 Claude Desktop 모드**: `MCP_TRANSPORT=stdio` (기본값, 변경 없음)

---

## MCP Read vs Write 정책

> MCP 는 편의 인터페이스일 뿐 권한 우회 계층이 아니다.
> write 는 항상 orchestrator 승인 체계를 통과해야 한다.

### 도구 분류표 (42개 CAD API 액션)

| # | 도구 이름 | HTTP Method | 상류 호출 대상 | 승인 필요 |
|---|-----------|------------|----------------|-----------|
| 1 | `cad_list_projects` | GET | cad-backend 직통 | 불필요 |
| 2 | `cad_get_project` | GET | cad-backend 직통 | 불필요 |
| 3 | `cad_list_drawings` | GET | cad-backend 직통 | 불필요 |
| 4 | `cad_get_drawing` | GET | cad-backend 직통 | 불필요 |
| 5 | `cad_list_drawing_parse_jobs` | GET | cad-backend 직통 | 불필요 |
| 6 | `cad_get_drawing_parse_status` | GET | cad-backend 직통 | 불필요 |
| 7 | `cad_get_parse_job` | GET | cad-backend 직통 | 불필요 |
| 8 | `cad_get_parse_logs` | GET | cad-backend 직통 | 불필요 |
| 9 | `cad_get_project_parse_status` | GET | cad-backend 직통 | 불필요 |
| 10 | `cad_list_parsed_entities` | GET | cad-backend 직통 | 불필요 |
| 11 | `cad_list_mappings` | GET | cad-backend 직통 | 불필요 |
| 12 | `cad_list_quantity_rows` | GET | cad-backend 직통 | 불필요 |
| 13 | `cad_get_quantity_summary` | GET | cad-backend 직통 | 불필요 |
| 14 | `cad_list_exports` | GET | cad-backend 직통 | 불필요 |
| 15 | `cad_get_export` | GET | cad-backend 직통 | 불필요 |
| 16 | `cad_get_download_export_url` | GET | cad-backend 직통 | 불필요 |
| 17 | `cad_list_issues` | GET | cad-backend 직통 | 불필요 |
| 18 | `cad_get_issues_summary` | GET | cad-backend 직통 | 불필요 |
| 19 | `cad_list_bridge_sessions` | GET | cad-backend 직통 | 불필요 |
| 20 | `cad_get_bridge_session` | GET | cad-backend 직통 | 불필요 |
| 21 | `cad_get_bridge_batch` | GET | cad-backend 직통 | 불필요 |
| 22 | `cad_get_bridge_batch_logs` | GET | cad-backend 직통 | 불필요 |
| 23 | `cad_create_project` | POST | **orchestrator 경유** | **필수** |
| 24 | `cad_update_project` | PATCH | **orchestrator 경유** | **필수** |
| 25 | `cad_delete_project` | DELETE | **orchestrator 경유** | **필수** |
| 26 | `cad_upload_drawing` | POST(multipart) | **orchestrator 경유** | **필수** |
| 27 | `cad_update_drawing` | PATCH | **orchestrator 경유** | **필수** |
| 28 | `cad_delete_drawing` | DELETE | **orchestrator 경유** | **필수** |
| 29 | `cad_parse_drawing` | POST | **orchestrator 경유** | **필수** |
| 30 | `cad_start_parse_bulk` | POST | **orchestrator 경유** | **필수** |
| 31 | `cad_create_mapping` | POST | **orchestrator 경유** | **필수** |
| 32 | `cad_auto_generate_mappings` | POST | **orchestrator 경유** | **필수** |
| 33 | `cad_update_mapping` | PATCH | **orchestrator 경유** | **필수** |
| 34 | `cad_calculate_quantity` | POST | **orchestrator 경유** | **필수** |
| 35 | `cad_confirm_quantity_row` | PATCH | **orchestrator 경유** | **필수** |
| 36 | `cad_create_export` | POST | **orchestrator 경유** | **필수** |
| 37 | `cad_update_issue` | PATCH | **orchestrator 경유** | **필수** |
| 38 | `cad_start_bridge_session` | POST | **orchestrator 경유** | **필수** |
| 39 | `cad_upload_bridge_batch` | POST | **orchestrator 경유** | **필수** |
| 40 | `cad_close_bridge_session` | PATCH | **orchestrator 경유** | **필수** |
| 41 | `cad_bridge_heartbeat` | PATCH | **orchestrator 경유** | **필수** |
| 42 | `cad_trigger_bridge_batch_quantity` | POST | **orchestrator 경유** | **필수** |

### Direct Read 허용 범위

- **허용 조건**: `MCP_ALLOW_DIRECT_READ=true` (기본값) + HTTP method = `GET`
- **허용 대상**: cad-backend 내부 DNS (`http://cad-backend:8000`)
- **비허용**: `MCP_ALLOW_DIRECT_READ=false` 시 RuntimeError 발생 후 즉시 거부
- **이유**: 내부 네트워크 내 조회는 auth overhead 없이 허용 (cad-backend 는 외부 비노출)

### Direct Write 금지 방식

```python
# config.py — 코드 레벨 하드락
MCP_ALLOW_DIRECT_WRITE: bool = False  # HARD-LOCKED — DO NOT CHANGE WITHOUT REVIEW
```

- `MCP_ALLOW_DIRECT_WRITE` 는 코드에 `False` 로 **하드코딩** — env 로 `true` 설정해도 **무효**
- `write_guard.check_write_prerequisites()` 가 `allow_direct_write=True` 감지 시 즉시 `McpWriteError(mcp_write_direct_forbidden)` 발생
- write 헬퍼 함수(`call_cad_write_via_orchestrator`) 내부에 `CAD_BACKEND_URL` 참조 없음 (소스코드 검사 테스트 포함)

### Orchestrator 경유 방식

```
write tool 호출
    │
    ▼ [1차 MCP 게이트: write_guard.check_write_prerequisites()]
    │  ├─ allow_direct_write == False 확인
    │  ├─ ORCHESTRATOR_URL 존재 확인
    │  ├─ actor 존재 확인
    │  ├─ task_id 존재 확인
    │  └─ approval_token 존재 확인
    ▼
    [upstream.call_cad_write_via_orchestrator()]
    │  URL: {ORCHESTRATOR_URL}/api/v1/cad/{path}
    │  Headers: X-Task-Id, X-Approval-Token-Id, X-MCP-Actor
    │  Auth: MCP_ORCHESTRATOR_USER:PASS (Basic)
    ▼
    [2차 orchestrator 게이트: ai_orchestrator/cad/router.py]
    │  ├─ HTTP Basic Auth 검증
    │  ├─ role 확인 (operator 이상)
    │  ├─ approval.validate_token() 재검증
    │  └─ audit log: CAD_PROXY_CALL / CAD_PROXY_DENIED
    ▼
    [cad-backend:8000]
```

### Approval 토큰 요구사항

write 도구 호출 시 필수 파라미터:

| 파라미터 | 획득 방법 | 설명 |
|---------|----------|------|
| `task_id` | `POST /api/v1/tasks` 응답 | 사전 작업 제출 |
| `approval_token` | `POST /api/v1/tasks/{id}/approve` 응답 | admin/owner 승인 후 획득 |
| `actor` | 호출자 직접 제공 | audit trail 용 사용자 식별자 |

### 이중 게이트 구조

| 게이트 | 위치 | 담당 |
|--------|------|------|
| 1차 | `mcp_server/write_guard.py` | actor/task_id/approval_token/orchestrator_url 전치 검사 |
| 2차 | `ai_orchestrator/cad/router.py` | HTTP Basic Auth + approval 재검증 + audit log |

"나중에 orchestrator 가 검사하겠지"가 아닌 **MCP 레벨 선차단 + orchestrator 레벨 재차단** 이중 구조.

### 향후 Claude Desktop 연결 시 주의사항

- Claude Desktop 이 `cad-mcp` 에 stdio/SSE 로 직접 연결되더라도 write 도구는 동일하게 `approval_token` + `task_id` + `actor` 를 요구한다
- Claude Desktop 은 orchestrator 의 `/api/v1/tasks` → `/api/v1/tasks/{id}/approve` 흐름을 사용자에게 안내해야 한다
- Claude Desktop 환경에서 `ORCHESTRATOR_URL` 이 외부 공개 주소인 경우 TLS + Basic Auth 설정 필수
- MCP 프로토콜 자체는 권한 없음 — 모든 권한 검사는 orchestrator 계층에서 수행

---

## 환경변수 목록

### cad-mcp 전용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MCP_TRANSPORT` | `stdio` | `sse` 또는 `streamable-http` 지정 시 HTTP 모드 |
| `FASTMCP_HOST` | `127.0.0.1` | MCP 서버 바인딩 호스트 (컨테이너: `0.0.0.0`) |
| `FASTMCP_PORT` | `8000` | MCP 서버 바인딩 포트 (컨테이너: `8001`) |
| `FASTMCP_LOG_LEVEL` | `INFO` | 로그 레벨 |
| `DISCIPLINE` | `all` | MCP 도구 그룹 모드 (`all`/`lazy`/`legacy`) |
| `CAD_BACKEND_URL` | `http://cad-backend:8000` | cad-backend 내부 주소 (read 전용) |
| `ORCHESTRATOR_URL` | `http://haehan-ai-orchestrator-api:8400` | write 경유 주소 (필수) |
| `MCP_ALLOW_DIRECT_READ` | `true` | read 도구의 cad-backend 직통 허용 여부 |
| `MCP_ORCHESTRATOR_USER` | (없음) | orchestrator Basic Auth 서비스 계정 ID |
| `MCP_ORCHESTRATOR_PASS` | (없음) | orchestrator Basic Auth 서비스 계정 PW |
| `MCP_READ_TIMEOUT_SEC` | `30` | read 타임아웃(초) |
| `MCP_WRITE_TIMEOUT_SEC` | `60` | write 타임아웃(초) |
| `STORAGE_ROOT` | `/storage` | DXF/DWG 파일 공유 스토리지 |

> **주의**: `MCP_ALLOW_DIRECT_WRITE` 환경변수는 의도적으로 존재하지 않는다.
> write 허용 여부는 코드 레벨에서 `False` 로 하드락되어 있으며 env 로 변경 불가.

### cad-backend / cad-worker (기존 유지)

기존 `.env` 그대로 사용. MCP 관련 변수 오염 없음.

---

## 배포 방법

```bash
# cad-quantity 프로젝트 디렉터리에서
cd /home/ubuntu/apps/cad-quantity

# 1. MCP 이미지 빌드
docker compose build cad-mcp

# 2. cad-mcp만 기동 (기존 서비스 재시작 없음)
docker compose up -d cad-mcp

# 3. 상태 확인
docker compose ps cad-mcp
docker compose logs cad-mcp --tail=30
```

## 검증 방법

```bash
# 1. 컨테이너 기동 확인
docker compose ps cad-mcp

# 2. 내부 포트 리스닝 확인
docker exec cad-mcp python3 -c \
  "import socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', 8001)); print('OK')"

# 3. cad-backend health 확인 (기존 기능 회귀 없음)
curl -s http://127.0.0.1:8092/health | python3 -m json.tool

# 4. orchestrator → cad proxy 동작 확인 (기존 42 action 경로 무결)
curl -s -u admin:PASSWORD http://127.0.0.1:8400/api/v1/cad/projects

# 5. 외부 포트 미노출 확인
ss -tlnp | grep 8001   # 아무 결과 없어야 함

# 6. nginx에 cad-mcp 직접 노출 없음 확인
grep -r 'cad-mcp\|8001' /etc/nginx/sites-enabled/ 2>/dev/null   # 결과 없어야 함

# 7. write guard 동작 확인 (approval 없이 거부)
docker exec cad-mcp python3 -c "
from mcp_server.write_guard import check_write_prerequisites, McpWriteError
try:
    check_write_prerequisites(orchestrator_url='http://orch:8400',
        actor='', task_id='', approval_token='', allow_direct_write=False)
    print('FAIL: should have raised')
except McpWriteError as e:
    print(f'PASS: {e.error_code}')
"

# 8. MCP_ALLOW_DIRECT_WRITE 하드락 확인
docker exec cad-mcp python3 -c "
from mcp_server.config import MCP_ALLOW_DIRECT_WRITE
assert MCP_ALLOW_DIRECT_WRITE is False, 'FAIL'
print('PASS: MCP_ALLOW_DIRECT_WRITE is hard-locked False')
"
```

## 금지 사항

- `cad-mcp` host port 직접 바인딩 (`ports: - "8001:8001"` 형태) 금지
- nginx에 `cad-mcp:8001` 직접 upstream/server block 추가 금지
- orchestrator auth/approval/audit를 우회하는 cad-mcp 직접 외부 공개 금지
- 한 컨테이너에서 `cad-backend` + `cad-mcp` 동시 프로세스 실행 금지
- `call_cad_write_via_orchestrator()` 내부에서 `CAD_BACKEND_URL` 참조 금지
- tool 함수 내에서 직접 `httpx`/`requests` 호출 금지 (반드시 upstream 헬퍼 경유)
- write tool 에 `approval_token` 없이 cad-backend 접근 허용 금지

## 변경 파일 목록

| 파일 | 상태 | 내용 |
|------|------|------|
| `mcp_server/__init__.py` | 신규 | 패키지 초기화 |
| `mcp_server/config.py` | 신규 | read/write 정책 env 설정 (MCP_ALLOW_DIRECT_WRITE 하드락) |
| `mcp_server/write_guard.py` | 신규 | MCP 레벨 1차 write 게이트 |
| `mcp_server/upstream.py` | 신규 | read/write 상류 호출 헬퍼 분리 |
| `mcp_server/server.py` | 신규 | FastMCP 서버 (22 read + 20 write 도구) |
| `mcp_server/tests/test_write_guard.py` | 신규 | write 게이트 + 보안 불변 테스트 |
| `mcp_server/requirements.txt` | 신규 | cad-mcp 전용 의존성 |
| `ai_orchestrator/audit_logger.py` | 수정 | MCP_WRITE_DENIED 이벤트 타입 추가 |
| `docs/cad_mcp_container_split.md` | 수정 | read/write 정책 섹션 추가 (이 문서) |
