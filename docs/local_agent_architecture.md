# 로컬 에이전트 아키텍처 (Local Agent — Stage 1)

적용 범위: Windows PC 에서 실행되는 사용자 설치형 에이전트와
서버 오케스트레이터 (`ai_orchestrator`) 간 연결 구조.

> `capture_screenshot` 액션의 운영 정책(승인 흐름, 금지 기능, 민감정보
> 미노출, 게이트 테스트, 금지 문자열 재스캔)은 별도 문서
> [로컬 에이전트 화면 캡처 운영 정책](./local_agent_capture_policy.md)
> 에서 관리한다. 본 아키텍처 문서는 구조 설명, 정책 문서는 운영 경계다.

> **본 문서는 1단계 설계서다.** 실제 WebSocket 양방향 푸시·실행 채널은
> 2단계에서 도입한다. 1단계는 사용자가 직접 시작·종료 가능한 로컬 프로세스를
> 전제로, 서버 측 작업 큐와 폴링/WS 게이트웨이만 정의한다.

---

## 1. 역할 정의

### 서버 오케스트레이터 (ai_orchestrator)

- 로컬 에이전트 등록 / 조회 / 작업 큐 관리
- 작업별 risk_level 분류 → 자동 실행 vs 승인 대기 결정
- 텔레그램 승인 게이트와 동일 메커니즘 재사용 (`approval.py`)
- 모든 등록·작업 요청을 감사 로그에 기록 (토큰 원문 제외)
- 로컬 에이전트의 호스트/PC 환경에는 절대 접근하지 않는다
  (서버는 큐만 노출, 실행은 에이전트 측에서 능동적으로 가져간다)

### Windows 로컬 에이전트 (local_agent/)

- 사용자가 자신의 PC 에 명시적으로 **설치·시작**한 프로세스
- 시작 시 서버에 register → `agent_id` + `device_token` 발급 받음
- 큐에 등록된 작업을 가져와 실행 (read-only / 안전 작업만)
- 실행 결과를 서버에 보고
- 사용자가 종료 (Ctrl+C / 트레이) 하면 즉시 멈춘다
- 백그라운드 자동 실행·자동 시작·은폐 실행 모두 금지

> **무단 원격제어 금지**: 사용자가 직접 설치·실행한 PC 외에는 어떤 PC 도
> 연결될 수 없다. 서버는 에이전트가 먼저 register 하지 않으면 통신 자체가
> 불가능하다.

---

## 2. 연결 구조 (WebSocket — 단계별)

```
[Windows PC]                       [Server Orchestrator]
┌─────────────────┐                ┌──────────────────────┐
│ local_agent     │                │ /api/v1/local-agents │
│  ├─ agent.py    │ register ───▶ │  POST /register      │
│  ├─ ws_client   │ ─────────────▶│  GET  /              │
│  ├─ actions     │ poll/execute  │  POST /{id}/tasks    │
│  └─ audit       │ ◀──────────── │  GET  /{id}/tasks/.. │
└─────────────────┘   결과 보고    └──────────────────────┘
                                           │
                                           ▼
                                  ┌──────────────────────┐
                                  │ approval.py          │
                                  │ (텔레그램 승인 게이트) │
                                  └──────────────────────┘
```

### 1단계 (현재)
- **HTTP 폴링** + 작업 큐 (인메모리 + JSONL append-log)
- 에이전트는 `GET /api/v1/local-agents/{agent_id}/tasks/{task_id}` 로 자기에게
  할당된 작업 상태를 조회한다 (실행 자체는 단일 프로세스 데모 단계)
- WebSocket 인터페이스는 `core/agent_runtime/connection/websocket_client.py` 에 스텁만 존재

### 2단계 (예정)
- 에이전트 ↔ 서버 영구 WebSocket 연결 (`/ws/local-agent/{agent_id}`)
- 서버 → 에이전트 작업 푸시
- 에이전트 → 서버 진행 상태/하트비트 푸시

> 1단계에서는 WebSocket 핸드셰이크만 정의하고 **실제 push 는 활성화하지 않는다**.
> 사용자가 명시적으로 활성화하기 전까지는 폴링으로만 동작한다.

---

## 3. 작업 큐 구조

### TaskQueueEntry

```
LocalAgentTask
├── task_id          : "lat-<uuid12>"
├── agent_id         : 대상 에이전트
├── action           : ping / system_info / open_url / capture_screenshot ...
├── params           : 작업 인자 (민감값 저장 금지)
├── risk_level       : low / medium / high
├── status           : queued / running / waiting_approval
│                      / completed / failed / rejected
├── requested_by     : 요청자 actor (Basic auth 사용자명)
├── created_at       : ISO8601
├── updated_at       : ISO8601
├── token_id         : (high risk 일 때만) 승인 토큰 ID
└── result_summary   : 안전 요약 텍스트 (민감 원문 금지)
```

### 상태 전이

```
queued ──▶ running ──▶ completed / failed
   │
   └─ (high risk) ──▶ waiting_approval ──┬── 승인 ──▶ running
                                        └── 거절/만료 ──▶ rejected
```

| 상태 | 의미 |
|------|------|
| `queued` | 작업이 큐에 등록됨 (low/medium 자동 진행, high 는 승인 대기로 즉시 전이) |
| `running` | 에이전트가 실행 중 (1단계는 동기 즉시 완료) |
| `waiting_approval` | high risk → 텔레그램 승인 대기 |
| `completed` | 정상 완료 |
| `failed` | 실행 실패 (에이전트 측 error_code) |
| `rejected` | 승인 거절 또는 토큰 만료 |

---

## 4. 승인 게이트 연결

high risk 작업은 기존 `approval.issue_token_for_dev_reg()` 와 동일한 토큰 발행
경로를 재사용한다. dev-reg 와 동일 구조를 사용해 텔레그램 [승인]/[거절] 흐름을
한 곳에서 관리한다.

```
POST /api/v1/local-agents/{agent_id}/tasks
        │ risk_level=high
        ▼
  issue_token_for_dev_reg(task_id, requested_by, risk_level)
        │
        ▼
  status: waiting_approval  + token_id 저장
        │
   (텔레그램 승인 — 1단계는 발송 자체는 생략, 승인 토큰만 발행)
        │
   ┌────┴────┐
승인│         │거절
   ▼         ▼
 running    rejected
```

> 1단계에서는 텔레그램 메시지 실제 발송은 dev-reg 와 같은 코드 경로로
> 추후 통합한다. 본 단계는 **승인 토큰 발행 + 상태 분기**까지만 구현.

---

## 5. 권한 모델

### 서버 측 RBAC

| 엔드포인트 | 허용 역할 |
|------------|-----------|
| `POST /api/v1/local-agents/register` | admin / owner |
| `GET  /api/v1/local-agents` | admin / owner / viewer |
| `POST /api/v1/local-agents/{agent_id}/tasks` | admin / owner |
| `GET  /api/v1/local-agents/{agent_id}/tasks/{task_id}` | admin / owner / viewer |

### 에이전트 인증

- register 시 서버가 발급: `agent_id` (UUID) + `device_token` (URL-safe 32B)
- 이후 모든 에이전트 → 서버 호출은 `device_token` 헤더 필요 (2단계)
- `device_token` 원문은 **응답에 1회만** 노출, 서버는 SHA-256 해시만 저장
- 토큰 원문은 감사 로그에 절대 기록 금지

### 작업 risk 매핑

| action | risk_level | 자동 실행 | 비고 |
|--------|------------|-----------|------|
| `ping` | low | ✓ | 헬스체크 |
| `system_info` | low | ✓ | OS/host 정보 (개인정보 제외) |
| `list_allowed_apps` | low | ✓ | 허용 앱 목록 |
| `open_url` | low | ✓ | http(s) URL 만 허용 |
| `capture_screenshot` | medium | ✓ | 본인 화면 (1단계는 즉시 실행) |
| `list_files_readonly` | medium | ✓ | 사전 화이트리스트 디렉터리만 |
| `delete_file` | — | **거절** | 1단계 불가 (action 자체 미등록) |
| `upload_file` | — | **거절** | 1단계 불가 |
| `modify_file` | — | **거절** | 1단계 불가 |
| `execute_shell` | — | **거절** | unrestricted shell 영구 금지 |

> `delete_file` / `upload_file` / `modify_file` / `execute_shell` 등 미등록
> 액션은 `400 UNKNOWN_ACTION` 으로 즉시 거절되며 큐에 진입하지 못한다.

---

## 6. 감사 로그

서버 측 `audit_logger.py` 에 다음 이벤트를 추가한다.

| 이벤트 | 발생 시점 |
|--------|-----------|
| `LOCAL_AGENT_REGISTERED` | register 성공 |
| `LOCAL_AGENT_TASK_QUEUED` | task 큐 등록 (low/medium → 자동 실행 흐름) |
| `LOCAL_AGENT_TASK_WAITING_APPROVAL` | high risk → 승인 대기 진입 |
| `LOCAL_AGENT_TASK_COMPLETED` | 작업 정상 완료 |
| `LOCAL_AGENT_TASK_FAILED` | 작업 실패 |
| `LOCAL_AGENT_TASK_REJECTED` | 미등록 액션 / 승인 거절 / 만료 |

> 기록 금지: `device_token`, `token_id` 원문 (해시·alias 만), params 원문
> (안전 키만), 파일 내용, 스크린샷 바이너리.

---

## 7. 보안 원칙

| 원칙 | 적용 방법 |
|------|-----------|
| 사용자 설치 기반 | local_agent 는 사용자가 직접 실행, 서비스/자동 시작 금지 |
| 무단 원격제어 금지 | 서버는 register 한 agent_id 외 일체 통신 불가 |
| 위험 작업 승인 게이트 | risk_level=high → `issue_token_for_dev_reg` 재사용 |
| 파일 수정/삭제 금지 | 액션 자체가 미등록 (`UNKNOWN_ACTION`) |
| read-only 우선 | 1단계 모든 자동 실행 액션은 부수 효과 없는 작업만 |
| 토큰 보호 | device_token 은 SHA-256 해시 저장, 원문 1회 노출 |
| URL 화이트리스트 | open_url 은 `http://`/`https://` 만 허용, file:// / javascript: / data: 금지 |
| 디렉터리 화이트리스트 | list_files_readonly 는 사전 정의 디렉터리만 (`config.py` 의 `READ_ONLY_DIRS`) |
| 민감정보 마스킹 | params / result 에서 password/token/cookie/secret 키 제거 후 로그 |
| 로컬 PC 종료 | 사용자가 Ctrl+C 로 즉시 종료 가능, 서버에는 무영향 |

---

## 8. 1단계 범위 / 비범위

### 포함
- 로컬 에이전트 디렉터리 골격 (`local_agent/`)
- 서버 측 등록·조회·큐 API 4종
- 액션 6종 (read-only 안전 작업)
- 감사 로그 6종
- 텔레그램 승인 게이트 토큰 발행 (high risk)
- 단위 테스트 (필수 8종)

### 미포함 (2단계 이후)
- 실제 WebSocket 양방향 푸시
- 텔레그램 메시지 발송 통합 (dev-reg 와 동일 경로 통합)
- 멀티 에이전트 동시 작업 분배
- 파일 업/다운로드 (별도 보안 검토 후)
- 사용자 GUI 트레이 / 자동 업데이트

---

## 9. 디렉터리 구조

```
local_agent/                        # Windows PC 측 (사용자 설치)
├── agent.py                        # 메인 엔트리
├── config.py                       # 서버 URL / 토큰 / 화이트리스트
├── actions.py                      # ping / system_info / open_url 등 구현
├── websocket_client.py             # WS 스텁 (2단계 용)
├── audit.py                        # 로컬 감사 로그
└── README.md                       # 설치/실행 가이드

ai_orchestrator/                    # 서버 측
├── local_agent_registry.py         # 에이전트 + 작업 큐 (인메모리 + JSONL)
├── local_agent_router.py           # FastAPI 라우터
└── tests/test_local_agent_*.py     # 회귀 테스트
```
