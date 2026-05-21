# CAD Agent ↔ Desktop Hub ↔ CAD Bridge 연동 설계서 (v1)

- **작업명:** `CAD-AGENT-DESKTOP-INTEGRATION-SPEC-01`
- **작성일:** 2026-05-21
- **대상 repo:** `haehan-ai-orchestrator` (본 문서) + `14. CAD 산출 프로그램_WORK` (참조)
- **선행 commit (haehan):**
  - `9a59746` `feat(cad-agent): add CAD control command contract`
  - `b4b2535` `feat(desktop): add CAD bridge subprocess lifecycle`
  - `0a94224` `feat(desktop): add CAD bridge registry/status route`
  - `babcf9f` `feat(desktop): add CAD bridge proxy with allow-list + mutating block`
- **선행 commit (CAD repo):**
  - `a64a52c` `test(cad): add local_bridge e2e smoke + contract + audit`
- **상태:** **설계서 단독** — 코드 변경 0건 (이 문서 1건만 커밋).

---

## 1. 목적

AI 에이전트(`local_agent/`)가 CAD AutoCAD를 직접 조작하는 것을 방지하면서도, **건축탭 9 카드 / 도서 인벤토리 / 일람표 검출 / 공사 순서 계획**과 같은 candidate-payload 형태의 산출 결과를 안전하게 받아올 수 있도록, 데스크탑 허브(`desktop.local_server`)가 두 계층 사이의 단일 통로 역할을 하도록 통합 구조를 정착한다.

설계 원칙:

1. **AI agent → CAD bridge 직접 호출 0건.** 반드시 desktop hub 경유.
2. **AutoCAD COM 자동 실행 0건.** 모든 mutating 동작은 사용자 승인 게이트.
3. **payload contract 만 허용.** 카드/도면 인벤토리/일람표/공사 순서 응답은 contract 명령으로 정의되고, CAD 도면이나 DXF 원본은 절대 변경하지 않는다.
4. **단일 source-of-truth.** Allow-list / risk 분류는 `local_agent/cad/command_contract.py` 하나만.
5. **다층 방어.** 정책 위반은 임의로 1줄만 통과하지 않도록 contract → desktop proxy → CAD bridge 세 곳에서 같은 게이트가 동작.
6. **CAD repo 무수정 원칙.** desktop hub / agent 측에서만 통합 구조를 만든다.

---

## 2. 시스템 아키텍처

```
┌────────────────────────────────────────────────────────────────────┐
│ AI Agent (local_agent/)                                            │
│   - openai_chat_client / ai_chat_adapter                           │
│   - command_contract  ← schema/registry/validator (commit 9a59746) │
│   - command_audit     ← redact + record dataclass                  │
│   - command_approval  ← in-memory PoC, hash-only, one-time use     │
│                                                                     │
│   책임:                                                              │
│   1) chat / prompt → tool_id + args 후보 추출                       │
│   2) CadCommandValidator.propose() → CadAgentCommand                │
│   3) READ_ONLY / CANDIDATE_PAYLOAD: validator 통과 즉시 executor    │
│   4) MUTATING_*: approval store 에 등록, 사용자 승인 대기            │
│                                                                     │
│   금지:                                                              │
│   - autoExecute=True                                                │
│   - local_bridge / app.backend / mcp_server 직접 import             │
│   - AutoCAD COM 호출                                                 │
│   - raw token / api key / raw_text 저장                              │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ (executor 트랙에서 wiring 예정)
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ Desktop Hub (desktop/, port 8765, host 127.0.0.1)                  │
│                                                                     │
│  cad_bridge_registry  ← config / status check (commit 0a94224)      │
│  cad_bridge_runner    ← subprocess lifecycle (commit b4b2535)       │
│  cad_bridge_proxy     ← allow-list + mutating block (babcf9f)       │
│                                                                     │
│  라우트:                                                              │
│    GET  /cad/bridge/status        — registry + runner snapshot     │
│    POST /cad/bridge/start         — subprocess start               │
│    POST /cad/bridge/stop          — subprocess stop                │
│    POST /cad/bridge/restart       — subprocess restart             │
│    GET  /cad/bridge/proxy/{path}  — read-only allow-list passthrough│
│    POST /cad/bridge/proxy/{path}  — candidate payload passthrough  │
│                                                                     │
│  단일 책임: registry/lifecycle/proxy 의 3 모듈 분리. local_server   │
│  는 라우트만 연결.                                                   │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ httpx.AsyncClient, timeout 5s
                               │ forwardable headers: Content-Type, Accept
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│ CAD Local Bridge (14. CAD 산출 프로그램_WORK/local_bridge/)          │
│ uvicorn local_bridge.server:app --host 127.0.0.1 --port 8766         │
│                                                                     │
│  /acad/inventory/analyze-drawing-inventory                          │
│  /acad/schedule-tables/detect                                       │
│  /acad/construction-sequence/plan                                   │
│  /acad/arch-quantity-tab/build-cards                                │
│  /acad/health, /acad/openapi.json (read-only introspection)         │
│                                                                     │
│  + 360 그 외 endpoint (현재 proxy allow-list 외 — 직접 호출 차단)    │
│  + AutoCAD COM read/write (별 트랙 — 본 통합에서 자동 실행 0건)      │
└────────────────────────────────────────────────────────────────────┘
```

포트 분리:
- `8765` = desktop hub (haehan-ai-orchestrator)
- `8766` = CAD local_bridge (CAD repo). registry default + proxy upstream 고정
- `8001` = **금지 포트** (FORBIDDEN_CAD_BRIDGE_PORTS)

---

## 3. 명령 흐름 — 6 단계 시퀀스

### 3.1 READ_ONLY / CANDIDATE_PAYLOAD (승인 불필요)

```
User chat → AI agent → tool_id 추출
  ↓
CadCommandValidator.propose(tool_id, args, auto_execute=False)
  ↓ requiresApproval=False / status=VALIDATED
CadAgentCommand (dataclass, autoExecute=@property=False)
  ↓ (executor 트랙에서 wiring — 본 통합 설계 후속)
desktop hub : POST /cad/bridge/proxy/<endpointPath>
  ↓ allow-list 검증 (POST_ALLOW + GET_ALLOW + 17 mutating keyword)
  ↓ Header strip: Host/Authorization/Cookie/X-*  →  Content-Type/Accept 만 forward
  ↓ httpx.AsyncClient → http://127.0.0.1:8766/<path>
CAD local_bridge service (예: build_arch_quantity_tab_cards)
  ↓ payload 변환 (autoExecute=False 정책, decisionPayload persistDecision=False)
응답 (cards / inventory / schedule candidates / plan)
  ↓ desktop proxy: status / content-type 그대로, marker 주입 0
AI agent : audit record (redact_args + summarize_result) + response 사용자 노출
```

### 3.2 MUTATING_DXF / MUTATING_AUTOCAD_COM (승인 필수)

```
User chat → AI agent → tool_id 추출
  ↓
CadCommandValidator.propose(tool_id, args, auto_execute=False)
  ↓ requiresApproval=True / status=APPROVAL_REQUIRED
CadCommandApprovalStore.create_approval(command_id, tool_id)
  → (approval_id, raw_token) caller 에게 1회만 반환
  → store: tokenHash 만 보존, status=PENDING, expiresAt=15분
  ↓
사용자 승인 UI (desktop GUI 또는 별 채널)
  ↓ admin/operator 검토 + approve(approval_id)
store: status=APPROVED, approvedAt=now
  ↓
AI agent: verify(approval_id, raw_token) → True
  ↓ executor 호출 직전 store.consume(approval_id, raw_token) → True
  ↓ status=USED (one-time, 재사용 거부)
desktop hub : POST /cad/bridge/proxy/<mutating_endpoint>
  ↓ ⚠ 현재 proxy 는 MUTATING 17 키워드 차단 → 403
  ↓ (이 흐름이 완성되려면 별도 "MUTATING route" 가 approval token 검증
    함께 처리하는 후속 트랙 필요)
```

**현재 상태:** MUTATING 경로의 desktop proxy 통과 자체가 봉인되어 있다. AI agent 가 MUTATING 명령을 만들 수는 있으나(`CadAgentCommand` 생성 + approval 토큰 발급), **실제 실행은 본 설계 v1 범위 밖**이며 후속 `CAD-AGENT-MUTATING-EXECUTOR-GATE-01` 트랙에서 별도로 다룬다.

---

## 4. Risk Level 매트릭스

| Risk | 등록 endpoint | 승인 필요 | 자동 실행 | desktop proxy 통과 | 본 v1 사용 |
|---|---|---|---|---|---|
| `READ_ONLY` | 9 (tool_catalog 의 layer/block/text/entity/geometry/dimension/drawing.search 등) | × | × (autoExecute=False) | GET allow (단, READ_ONLY 의 endpointPath 는 현재 None — executor 트랙에서 endpointPath 매핑 보완) | 진단/조회 |
| `CANDIDATE_PAYLOAD` | 4 (arch_quantity_tab.build_cards / drawing_inventory.analyze / schedule_tables.detect / construction_sequence.plan) | × | × | POST allow | 9 카드 / 인벤토리 / 일람표 / 공사 순서 |
| `MUTATING_DXF` | 0 (enum 만 정의) | ✓ | × | **차단** (mutating keyword + path allow-list 외) | 사용 안 함 (v1) |
| `MUTATING_AUTOCAD_COM` | 0 (enum 만 정의) | ✓ | × | **차단** | 사용 안 함 (v1) |

`autoExecute`는 `CadAgentCommand.autoExecute` `@property` 가 무조건 `False` 를 반환한다. 외부에서 dataclass field 처럼 set 불가 (CadAutoExecuteForbidden 예외).

---

## 5. 안전 게이트 — 다층 방어

같은 정책이 세 곳에서 독립적으로 동작한다.

### 5.1 AI agent 측 (`local_agent/cad/`)

1. `CadCommandValidator.propose(auto_execute=True)` → `CadAutoExecuteForbidden` 예외
2. unknown tool_id → `CadToolNotRegistered`
3. `args` 가 Mapping 아니면 `TypeError`
4. MUTATING_* risk → 자동으로 `requiresApproval=True / status=APPROVAL_REQUIRED`
5. `redact_args`: 18 secret 키 패턴 (api_key, password, token, bearer, authorization, private_key, client_secret, refresh_token, access_token, session_id, cookie, ...) + `raw_text` 키 강제 `[REDACTED]`
6. approval token 원문 저장 0건 — SHA256 hash 만
7. one-time use — `consume` 후 USED 전이, 재사용 거부
8. `DuplicateApprovalError` — silent overwrite 방지
9. 만료 15분 + `is_expired()` 검증
10. dataclass `frozen=True` — 상태 임의 변경 불가

### 5.2 Desktop hub proxy 측 (`desktop/cad_bridge_proxy.py`)

11. method allow-list: GET / POST 만
12. path allow-list: READ_ONLY GET 2 + CANDIDATE_PAYLOAD POST 4 (registry 동기화)
13. 17 mutating keyword 차단 (`execute / apply / mutate / write / save / delete / remove / update / approve / reject / command/run / command/execute / cad-control/execute / commit / drop / create-job / run-job / perform`)
14. path normalization: traversal `..` / absolute URL `://` / `//` prefix 거부
15. header strip: Host / Authorization / Cookie / X-* 모두 제거. Content-Type / Accept 만 forward
16. upstream URL: 항상 `http://127.0.0.1:8766/...` (registry 기본값 고정)
17. timeout: 5.0s (`DEFAULT_PROXY_TIMEOUT_SECONDS`)
18. response passthrough: status code / content / content-type 그대로. `_source` / `_generatedBy` / `fallback` marker 주입 0건
19. command_contract.DEFAULT_REGISTRY 의 CANDIDATE_PAYLOAD endpointPath ⊆ proxy POST_ALLOW 정합 검증 (테스트 강제)

### 5.3 CAD bridge 측 (`14. CAD 산출 프로그램_WORK/local_bridge/`)

20. payload-only response — 카드 / 인벤토리 / 일람표 / 계획 응답에 CONFIRMED/FINAL/APPROVED 표시 0건 (정책 audit 다수 강제)
21. actionButton `autoExecute=false` (frontend hardening 트랙에서 정착)
22. unclassified_finish_review `persistDecision=false` (decision 자동 저장 0)
23. AutoCAD COM 자동 실행 0건 (별도 confirm_write 게이트)

---

## 6. 모듈 책임 분리

| 모듈 | repo | 책임 | 의존 |
|---|---|---|---|
| `local_agent/cad/command_contract.py` | haehan | schema + registry + validator | `tool_catalog`(자체 패키지) — CAD repo import 0 |
| `local_agent/cad/command_audit.py` | haehan | redaction + audit record dataclass | command_contract |
| `local_agent/cad/command_approval.py` | haehan | in-memory approval, hash-only | (없음) |
| `desktop/cad_bridge_registry.py` | haehan | config + 외부 status probe (HTTP) | (없음) |
| `desktop/cad_bridge_runner.py` | haehan | subprocess 관리 | cad_bridge_registry |
| `desktop/cad_bridge_proxy.py` | haehan | allow-list + passthrough | cad_bridge_registry, command_contract |
| `desktop/local_server.py` | haehan | FastAPI route 등록만 | 위 3 모듈 |
| `local_bridge/...` | CAD repo | 실 CAD/AutoCAD API | (haehan import 0) |

**책임 boundary 규칙:**
- desktop hub 가 CAD route 를 직접 import 하지 않음
- local_agent 가 desktop hub route 를 직접 import 하지 않음 (모든 hub 호출은 HTTP)
- CAD repo 가 haehan 을 모름

---

## 7. 운영 시퀀스

### 7.1 첫 기동 (콜드 스타트)

```bash
# 1) CAD repo 에 환경변수 알리기 (사용자/운영 자동화)
$env:CAD_REPO_PATH = "C:\Users\skyjw\OneDrive\03. PYTHON\14. CAD 산출 프로그램_WORK"

# 2) Desktop hub 기동
python -m uvicorn desktop.local_server:app --port 8765 --host 127.0.0.1

# 3) Desktop hub UI 또는 HTTP 호출로 CAD bridge 기동
curl -X POST http://127.0.0.1:8765/cad/bridge/start
  → runner.start() — Popen(["python", "-m", "uvicorn",
      "local_bridge.server:app", "--host", "127.0.0.1",
      "--port", "8766", "--log-level", "info"], cwd=CAD_REPO_PATH)
  → start_verify_delay=1.0s → state=RUNNING

# 4) 상태 확인
curl http://127.0.0.1:8765/cad/bridge/status
  → { status: RUNNING, signaturePathsPresent: 2,
      runnerState: { state: running, pid: ..., port: 8766 } }

# 5) AI agent 가 카드 빌드 요청 (executor 트랙 wiring 후)
curl -X POST http://127.0.0.1:8765/cad/bridge/proxy/acad/arch-quantity-tab/build-cards \
     -H "Content-Type: application/json" -d "{}"
  → proxy allow-list 통과 → upstream 8766 → 9 카드 payload 반환
```

### 7.2 정상 종료

```bash
curl -X POST http://127.0.0.1:8765/cad/bridge/stop
  → runner.stop(): terminate → wait(5s) → fallback kill → wait(2s)
  → state=STOPPED
```

### 7.3 충돌 시나리오

- **포트 8766 다른 프로세스 점유:**
  - registry.check_status → UNREACHABLE (sig path 부재)
  - runner.start → Popen 성공해도 listen 실패 → start_verify 통과 후 일정 시간 뒤 발견
  - 임의 kill 0건 — 사용자가 외부 프로세스 정리
- **CAD repo path 미설정:**
  - runner._validate_before_start → "cad_repo_path required"
  - state=ERROR / last_error 기록 → desktop 서버 본체는 200 유지
- **proxy upstream 미응답:**
  - 504 (timeout) 또는 502 (unreachable) 반환 — desktop 서버 안정성 유지
- **mutating keyword 포함 path 요청:**
  - 403 + `reason="mutating_keyword_blocked:<kw>"`

---

## 8. 검증 매트릭스

| 검증 항목 | audit / test | 통과 기준 |
|---|---|---|
| AI agent CAD 직접 호출 0 | `audit_cad_agent_command_contract.py` | subprocess/urlopen/httpx import 0 |
| autoExecute=False 강제 | `test_cad_agent_command_contract::test_command_auto_execute_always_false` | property=False, set 불가 |
| Approval one-time use | `test_cad_agent_command_contract::test_approve_then_verify_then_consume_once` | 두 번째 consume → False |
| token 원문 저장 0 | `audit_cad_agent_command_contract` `token_hash_only_ok` | dataclass field 에 raw token 0 |
| desktop hub CAD module import 0 | `audit_desktop_cad_bridge_*` ast 검증 | `local_bridge.*` import 0 |
| proxy allow-list 강제 | `test_cad_bridge_proxy::test_get_non_allowlisted_acad_path_403` 등 | 403 |
| mutating keyword 차단 | `test_cad_bridge_proxy::test_mutating_keyword_blocked` (12 케이스) | 403 + upstream 호출 0 |
| host/auth header strip | `test_only_content_type_and_accept_forwarded` | forward 헤더에 Host/Auth/Cookie 0 |
| upstream marker 미주입 | `test_upstream_response_body_no_source_marker_injected` | response body 에 `_source` 0 |
| runner 외부 PID kill 0 | `audit_desktop_cad_bridge_lifecycle` + `test_runner_does_not_call_os_kill_or_taskkill` | 정적 + 동적 0 |
| CAD repo 무수정 | git status (CAD repo) | HEAD `a64a52c`, status 76, staged 0 변동 0 |

**현재 PASS audits (haehan):**
- `PASS_DESKTOP_CAD_BRIDGE_REGISTRY_STATUS`
- `PASS_DESKTOP_CAD_BRIDGE_LIFECYCLE`
- `PASS_DESKTOP_CAD_BRIDGE_PROXY`
- `PASS_CAD_AGENT_COMMAND_CONTRACT`

**테스트:** 합산 210/210 PASS (proxy 51 + command contract 50 + lifecycle 29 + registry/status 29 + desktop_local_runner / status_provider / tray_app 52).

---

## 9. 본 v1 범위에서 명시적으로 제외한 것

다음 항목은 본 통합 설계에서 정의만 하고 **구현은 별 트랙으로 분리**한다. 본 설계 안에서 임의로 활성화 금지.

| 후속 트랙 | 책임 | 범위 |
|---|---|---|
| `CAD-AGENT-CAD-COMMAND-EXECUTOR-WIRING-01` | local_agent | `executor.py` 에서 desktop hub `/cad/bridge/proxy/...` 호출 wiring. READ_ONLY + CANDIDATE_PAYLOAD 만. MUTATING_* 차단 유지 |
| `CAD-AGENT-CAD-COMMAND-AUDIT-PERSISTENCE-01` | local_agent | `CadCommandAuditRecord` 를 파일/DB 에 기록. redaction 정책 유지 |
| `CAD-AGENT-MUTATING-EXECUTOR-GATE-01` | local_agent + desktop hub | MUTATING_DXF / MUTATING_AUTOCAD_COM 명령의 approval token 검증 + 별도 proxy 게이트 (mutating route, 본 proxy 와 분리) |
| `CAD-LOCAL-BRIDGE-HOST-HARDEN-LOOPBACK-01` | CAD repo | `local_bridge.server` 의 `host=0.0.0.0` → `127.0.0.1` 변경 |
| `CAD-BACKEND-LOCAL-CAD-BRIDGE-URL-HUB-MIGRATION-01` | CAD repo (backend) | backend `LOCAL_CAD_BRIDGE_URL` 을 desktop hub 경유로 변경 (선택) |
| `CAD-DESKTOP-HUB-CAD-BRIDGE-WS-ACTION-01` | desktop hub | WS dispatcher 에 `cad_bridge_start / stop / restart / status` action 통합 (HTTP route 외 부가) |
| `CAD-AGENT-USER-APPROVAL-UI-01` | desktop hub UI | approval token PENDING → APPROVED 전환의 사용자 UI 흐름 |

각 후속 트랙은 본 설계의 boundary 와 audit 를 깨지 않는 조건에서만 진입한다.

---

## 10. 정책 단일 source-of-truth

- **Allow-list / risk 분류:** `local_agent/cad/command_contract.py:DEFAULT_REGISTRY` (READ_ONLY 9 + CANDIDATE_PAYLOAD 4)
- **포트:** `desktop/cad_bridge_registry.py:DEFAULT_CAD_BRIDGE_PORT = 8766`, `DEFAULT_CAD_BRIDGE_HOST = "127.0.0.1"`, `FORBIDDEN_CAD_BRIDGE_PORTS = (8001,)`, `DESKTOP_HUB_PORT = 8765`
- **mutating keyword:** `desktop/cad_bridge_proxy.py:MUTATING_KEYWORDS` (17)
- **redaction 키 패턴:** `local_agent/cad/command_audit.py:_REDACT_KEY_SUBSTRINGS` (18)
- **token 알고리즘:** `local_agent/cad/command_approval.py` — SHA256 hex 64, `secrets.token_urlsafe(32)` 256-bit
- **start verify delay:** `desktop/cad_bridge_runner.py:_DEFAULT_START_VERIFY_DELAY = 1.0`
- **proxy timeout:** `desktop/cad_bridge_proxy.py:DEFAULT_PROXY_TIMEOUT_SECONDS = 5.0`

이 값들을 변경할 때는 본 설계서를 함께 갱신하고, 해당 audit + test 가 함께 통과하는지 확인한다.

---

## 11. 위험 / 한계

1. **AI agent → executor wiring 미존재.** 현재는 `CadAgentCommand` 가 만들어져도 자동으로 `/cad/bridge/proxy/...` 가 호출되지는 않는다. executor 트랙에서 wiring.
2. **Approval store 가 in-memory only.** desktop hub 재기동 시 PENDING approval 소실. persistence 트랙에서 보완.
3. **proxy 가 backend `/api/v1/` 경유와 분리.** CAD frontend 의 기존 hardening 트랙은 frontend → backend `/api/v1/cad/arch-quantity-tab/build-cards` → CAD bridge 8765 (env 기본값). 본 hub proxy 와 같은 endpoint 를 두 경로로 호출 가능 — 충돌 없음 (둘 다 read-only/candidate). 다만 운영상 단일 경로 선호 시 `CAD-BACKEND-LOCAL-CAD-BRIDGE-URL-HUB-MIGRATION-01` 진행.
4. **CAD repo `host=0.0.0.0`.** local_bridge 가 LAN 노출 가능. 본 통합으로 desktop hub 가 127.0.0.1 만 사용하면 외부 노출이 줄지만 CAD repo 자체 host 변경은 별 트랙 필요.
5. **MUTATING 명령의 desktop proxy 경유 통과는 봉인.** v1 에서 의도적으로 차단. v2 mutating gate 트랙에서 token 검증 + 별 라우트 + 추가 audit 가 함께 들어가야 함.

---

## 12. 완료 판정

`PASS_CAD_AGENT_DESKTOP_INTEGRATION_SPEC_01_READY`

본 설계서는 **현재 시점까지 구현된 4 commit (registry/lifecycle/proxy + command contract)** 가 어떻게 합쳐져서 AI 에이전트가 안전하게 CAD candidate payload 까지 도달하는지를 단일 문서로 잠근다. 본 설계서 자체는 코드 변경 0건 — 별도 commit 으로 보존한다.

다음 진입 후보:
1. **`CAD-AGENT-CAD-COMMAND-EXECUTOR-WIRING-01`** — 본 설계의 §3.1 흐름 wiring
2. **`CAD-AGENT-CAD-COMMAND-AUDIT-PERSISTENCE-01`** — §11 risk 2 보완

— end of spec v1
