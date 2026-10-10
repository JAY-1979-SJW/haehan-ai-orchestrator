# 인수인계 — AI 에이전트 작업 분배(멀티 실행) 2026-10-02

기준서(설계): `docs/specs/2026-10-02_app_agent_dispatch.md` (다른 세션이 P0 "CDP 칸 분리" 절을 추가함 — 건드리지 말 것)
이 문서 = **작업기록 + 남은 일을 창(세션) 단위로 쪼갠 것**. 새 창은 이 문서의 해당 "창" 절만 읽고 시작하면 된다.

---

## 1. 지금까지 한 일 (작업기록)

사용자 요청: "AI 에이전트 작업 시 멀티창으로 작업 분배 — 앱이 되게 분배해". 계획 P1~P5 중 **P1·P2·P3 완료**, P4·P5 미착수.

| 단계 | 커밋 | 내용 |
|---|---|---|
| P1 동시 실행 | `5d28ff45` | 로컬 에이전트가 `LOCAL_AGENT_MAX_PARALLEL`(기본 1, 최대 3)만큼 동시 처리. 서버는 auth 때 받은 `max_parallel` 만큼 push. 기본값 1 = 기존과 동일 |
| P2 충돌 정책 | `b784ae29` | `gates/agent_dispatch_policy.py`(L2, 순수): 전역 직렬 자원·배타 자원·모호하면 직렬(fail-closed)·계획 검증·`next_step` |
| P3 분배 | `4d268141` `4030eddd` | 저장소(sqlite)·서비스(L6)·러너·API 5개(`/ai-agent/dispatch*`, 관리자 전용·AI 호출 불가). 역할 4종(조사·검토·종합·구현). 계획자→사람 승인→병렬 실행 |
| 종단 시험 중 결함 | `d4e2a4b3` | 서버 결과 필터가 문자열을 500자로 잘라 계획 JSON 파싱 실패 → `run_claude_agent` 선택 파라미터 `result_max_chars` + 결과 키 `result_full`(최대 20000). 기존 `result` 불변 |
| 채팅 수정 | `7b404bc5` | 채팅 `/ai-agent/run` 이 `result_max_chars=20000` 요청, 화면은 `result_full` 우선, 대화기록 상한 8000→20000 |
| 적대적 검증 A | `498e78fc` | **`--allowedTools` 는 도구를 제한하지 않는다**(실측: Read/Grep/Glob 만 허용해도 Bash 실행됨, 프로젝트 설정 `bypassPermissions`). → `run_claude_agent` 에 `restricted=True`(`--restricted --strict-mcp-config --tools`). 분배의 모든 호출에 적용. 앞선 결과는 "신뢰할 수 없는 데이터"로 구분 |
| 적대적 검증 B | `e1b8b2cb` | 취소↔tick 락, 조건부 갱신, 시작 선점(`starting`)으로 이중 큐잉 방지, 서버 시작 시 러너 재개, 러너 DB 오류 내성, 분배 전체 시간 초과(2시간) |
| 적대적 검증 C | `4661d514` | 전역 직렬 작업은 읽기 전용 작업과도 동시에 안 돎, 경로 정규화(표기 우회 차단·판정 불가는 전역 직렬) |
| 종단 시험 하니스 | (이 커밋) | `tools/smoke/agent_dispatch_e2e.py` — 실제 Claude Code 로 계획→병렬 조사→종합 실행(비용 약 $0.15) |

**푸시 완료**: `feat/login-state-by-element` (`1b6291be..4661d514` 및 이후 이 문서 커밋). **master 병합·운영 배포는 안 됨**(아래 창 A).
**서버(8401)는 옛 코드 실행 중** — P1·P3·채팅 수정은 재시작 전까지 이 PC 앱에 반영 안 됨.

### 검증 상태
- 분배 관련 시험 132개 통과(`tests/test_agent_{parallel_p1,dispatch_policy,dispatch_paths,dispatch_service,dispatch_router,dispatch_races}.py` 등). 영향 시험 1,689개 중 실패 113개는 **기존 실패**(기준 커밋과 동일, 새 실패 0).
- 실제 Claude Code 종단 시험 통과(동시 2개, 46초, 약 $0.12). 제한 모드에서 Bash·MCP·Write 차단 / Read 정상을 실제로 확인.
- 독립 리뷰어 3명 적대적 검증 → 치명 1·높음 2 수정 완료. **미수정 잔여는 아래 창 D·E.**
- 라우트 수 기준값 `EXPECTED_RUNTIME_ROUTES = 380`(`tools/audits/backend/audit_backend_runtime_contract.py`). 이전 369 는 HEAD 실측 375 보다 6개 뒤처져 있었음.

### 반드시 기억할 교훈
1. `--allowedTools` ≠ 제한. 읽기 전용 보장은 `restricted=True`. 프로젝트 설정이 `bypassPermissions` 라서 허용 목록 밖 도구도 실행된다.
2. 서버 `_strip_result_data` 가 문자열 값을 500자로 자른다 → 긴 결과는 `result_full` 키로만 통과(20000).
3. 가짜 큐 시험으로는 위 두 가지를 못 잡았다 → 새 단계는 반드시 `tools/smoke/agent_dispatch_e2e.py` 로 실제 호출 확인.
4. 이 PC 는 메모리 사용률 90%+(여유 1~1.5GB). 분배는 여유 1500MB 미만이면 시작 보류(`AGENT_DISPATCH_MIN_FREE_MB` 로 조정). `verify_change`(145커밋)는 메모리 부족으로 중단됨.
5. 에이전트/서버/keyring 은 공유 자원 — 격리 인스턴스로 에이전트를 새로 등록하면 기존 자격증명을 덮어쓸 위험. 시험은 스레드 큐 대역(하니스)으로.

---

## 2. 창(세션) 분리 계획

### 공통 규칙 (모든 창)
- **창마다 자기 worktree + 브랜치**에서 작업한다(같은 폴더 동시 편집 금지 — 2026-09-27 커밋 뒤섞임 사고):
  `git worktree add C:\hhwt-<창이름> -b stage/<창이름> feat/login-state-by-element` (경로는 짧게).
- **git·DB·배포·서버 재시작은 직렬**: 창 A 만 master/배포/서버 재시작을 한다. 나머지 창은 자기 브랜치에 커밋·푸시까지만.
- 코드 전 기준서(해당 절 갱신) → 드라이런 → 승인 → 구현. 전체 pytest 금지(영향 시험만), ruff 는 내 파일만 `--fix`.
- 신규 파일은 `registry_sync.py --fix` 로 정본 등록, 이름 때문에 L4 로 오분류되면 `module_registry.json` 에 L6 확정(예: `agent_dispatch_service.py` 선례).
- 외부 유료 AI API(OpenAI 등) 금지. `claude -p`(사용자 Claude Code)는 소액 시험 가능.
- 보고는 한국어. 완료 보고 전에 시험·게이트 실행 증거 확인.

### 파일 담당 영역 (충돌 방지)
| 창 | 만지는 파일 | 만지지 않는 파일 |
|---|---|---|
| A 배포 | 코드 없음(git·PR·서버 운영) | 전부 |
| B P4 쓰기 격리 | `local_agent/actions.py`(cwd 파라미터), `services/agent_dispatch_service.py`, 신규 `workflows/agent_dispatch_worktree.py`, `gates/agent_dispatch_policy.py` | `local_agent/websocket_client.py`, `admin-web/` |
| C P5 화면 | `admin-web/src/**`(신규 컴포넌트 위주) | 백엔드 전부 |
| D 병렬 보강 | `local_agent/websocket_client.py`, `local_agent/config.py`, `ai_orchestrator/agent_hub/router/ws.py`, `local_agent_registry_agent.py` | 분배 서비스·화면 |
| E 결과 필터 보강 | `ai_orchestrator/agent_hub/redaction.py`, `admin-web/.../UniversalChat.tsx`(한 줄), 상수 통합 | 분배 서비스 로직 |

권장 진행 순서: **A(승인 필요, 먼저)** → B·C·D·E 는 서로 독립이라 동시 진행 가능. B 는 C 의 "구현 역할" 화면 문구와 `WRITE_ISOLATION_READY` 값만 맞추면 된다.

---

### 창 A — 배포 마무리 (master 병합 → 운영 서버 → 로컬 서버)
**목표**: 지금까지의 작업을 master 로 병합하고 운영·로컬에 반영.
**현재 상태 (2026-10-02 저녁)**
- **초안 PR #57**(`feat/login-state-by-element` → master) 생성됨. GitHub 서버에서 필수 검사가 자동 실행됨: `frontend` **통과**, `secrets` **통과**(PR 기준), `verify` **진행 중이었음**(확인 필요: `gh pr checks 57`). 앞서 `secrets` 가 실패하던 것은 수동 실행(`workflow_dispatch`) 기준 — PR 기준으로는 통과했으니 최종 결과를 다시 확인할 것.
- master 는 **보호 브랜치**: 필수 검사 `verify`, `frontend`, `secrets`, 병합은 Pull Request. **보호 규칙 우회 금지.**
- 이 브랜치는 master 보다 145+커밋 앞서고 **다른 세션 작업(CDP 칸 분리, 스마트스토어 조사, 하이웍스 문서, 건설업 공무 문서 등)이 섞여 있다.** PR 은 그것까지 포함 — 병합 범위를 사용자가 정해야 한다(필요하면 이 작업만 따로 추려 새 브랜치로 PR).
- `merge_stage.py` 는 master 체크아웃이 필요 → 공유 폴더에서 브랜치 전환 금지. PR 병합이 정식 경로.
- 로컬 `verify_change.py --base origin/master --head <sha>` 는 145커밋 규모에서 **메모리 부족으로 중단**됨 → GitHub `verify` 결과로 대체.
- 운영 배포: 서버는 `origin/master` 만 pull(`tools/server_deploy.py`). webhook 자동배포는 끊긴 것으로 추정(`defect_index #6`) → 운영 서버에서 직접 실행해야 하며 **서버 접근 방법·별도 승인 필요**.
**할 일(승인 후)**: ① PR #57 확인(초안 해제 여부 포함) → ② GitHub 검사 3개 결과 확인 → ③ 병합 범위 결정(다른 세션 작업 포함 여부) → ④ 병합 → ⑤ 운영 서버 `server_deploy.py` → ⑥ 로컬 서버(8401) 재시작(앱 안 쓸 때) + 실제 채팅 긴 답변·`/ai-agent/dispatch` 확인 → ⑦ 임시 worktree·`verify_base_*` 정리(사용자 확인 후).
**시작 문구**: "docs/specs/HANDOFF_2026-10-02_agent-dispatch.md 의 창 A 를 이어서 해줘. 승인 없이 master 병합·서버 재시작·운영 배포는 하지 마."

### 창 B — P4 쓰기 작업 격리(worktree) + 병합 승인
**목표**: `implement` 역할 승인 허용. 쓰기 하위 작업을 git worktree 에서 실행, 결과는 브랜치로 남기고 **병합은 사람이 하나씩 승인**.
**현재 상태**: `WRITE_ISOLATION_READY = False`(`services/agent_dispatch_service.py`) → implement 가 든 분배안은 승인 거부. 정책의 `path:` 정규화·전역 직렬 규칙은 P4 선행 조건으로 이미 완료.
**할 일**
1. `run_claude_agent` 에 작업 폴더 지정 파라미터(cwd) 추가 — 기본은 저장소 루트(불변). 제한 모드와 함께 쓰면 `--restricted` 가 파일 도구를 작업 폴더로 가둔다.
2. `workflows/agent_dispatch_worktree.py`: 짧은 경로 `C:\hhwt-<id>`, 임시 브랜치 생성·정리, 충돌 시험(임시 저장소로, 실제 프로젝트 브랜치 미접촉). git 은 서버 PC 로컬만.
3. implement 도구 집합: `Read,Grep,Glob,Edit,Write` + 제한 모드(셸·MCP 없음). 병합 승인 API/상태(`merge_pending`) 추가, 병합은 직렬·사람 승인.
4. 심볼릭 링크/정션은 이름으로 판별 불가 → worktree 격리로 보완(기준서 §4 명시됨).
5. 시험 + `tools/smoke/agent_dispatch_e2e.py` 로 실제 호출 확인(쓰기 목표는 임시 저장소에서만).
**시작 문구**: "docs/specs/HANDOFF_2026-10-02_agent-dispatch.md 의 창 B(P4) 를 해줘. 기준서 갱신→드라이런→승인 순서로."

### 창 C — P5 화면(AI 콘솔 "작업 분배" 패널)
**목표**: 목표 입력 → 분배안 카드(하위 작업·역할·병렬/직렬 표시·비용 상한) → [승인하고 시작] → 진행 보드(대기/시작 중/실행/완료/실패/건너뜀) → 결과·종합 카드.
**API(완료)**: `POST /api/v1/ai-agent/dispatch {goal, max_parallel}` · `GET …/dispatch` · `GET …/dispatch/{id}`(`status`, `subtasks[]`, `waves`, `blocked_reason`, `waiting_reason`, `final_result`, `note`) · `POST …/{id}/approve` · `POST …/{id}/cancel`. 모두 관리자 전용, 프록시 경로 `/api/proxy/api/v1/ai-agent/dispatch*`.
**주의**: 하위 작업 상태에 `starting` 이 있음. `blocked_reason` 이 있으면 승인 버튼 비활성+사유 표시(implement 는 P4 전). `waiting_reason`(메모리 부족 대기)을 진행 보드에 표시. 폴링 주기 3~5초, `result_text` 는 최대 20000자라 접기/펼치기. 기존 `UniversalChat` 카드 방식 재사용.
**검증**: `cd admin-web && npm run typecheck`. 서버 재시작 전에는 실데이터 확인 불가(창 A).
**시작 문구**: "HANDOFF_2026-10-02_agent-dispatch.md 의 창 C(P5 화면) 를 해줘. 백엔드는 건드리지 마."

### 창 D — 병렬 켜기 전 보강 (P1 하드닝)
**목표**: `LOCAL_AGENT_MAX_PARALLEL>1` 을 안전하게 켤 수 있게. (기본값 1 이라 지금은 무영향)
**할 일(적대적 검증에서 확인된 항목)**
1. 병렬은 `run_claude_agent` 등 허용 목록 액션만 — `cdp.run`·`browser.execute_*`·`cad.execute` 는 병렬 금지(전역 직렬 락). [높음]
2. ack 타임아웃 시 서버는 running 인데 클라이언트는 포기 → 용량 슬롯 영구 점유. 서버 만료(`expire_stale_tasks`) 보장 또는 클라이언트 취소 통지. [높음]
3. 연결 끊김 시 스레드가 안 멈춤 → 재접속 후 실제 동시 실행이 상한 초과. 끝난 스레드 결과는 유실. [중간]
4. 용량이 agent_id 키라 재접속·다중 연결에서 초기화. 연결 단위 관리. [중간]
5. `running_ack.status` 를 클라이언트가 안 봄(이미 failed 인 작업 실행). [중간]
6. `set_agent_capacity` 에 `Infinity` → `OverflowError` 미처리, `LOCAL_AGENT_MAX_PARALLEL=abc` → import 시 예외. [낮음]
7. 시험 보강: ack 타임아웃·재접속 용량·select_agent·동일 task_id.
**실제 에이전트로 병렬 확인은 공유 에이전트/서버를 건드림 → 창 A 와 조율, 사용자 승인.**
**시작 문구**: "HANDOFF_2026-10-02_agent-dispatch.md 의 창 D 를 해줘. 실제 에이전트·서버는 건드리지 말고 시험은 가짜 ws 로."

### 창 E — 결과 필터·채팅 보강
**할 일**
1. `result_full` 값 수준 비밀 마스킹(`sk-`, `AIza`, `Bearer`, `KEY=` 등) — 노출 가능 분량이 500→20000자로 늘었음(재현됨, 기존 `result` 도 값 검사 없음). [중간]
2. 프런트 `UniversalChat.tsx` 218줄: `??` 가 빈 문자열을 폴백하지 않아 빈 `result_full` 이면 빈 말풍선 → `||`/빈값 검사. [낮음]
3. 20000 상수가 6곳에 하드코딩(`actions.py`, `local_agent_redaction.py`, `ai_agent_router.py`, `agent_dispatch_service.py`, `chat_sessions.py`, 저장소) → 한 곳으로. [낮음]
4. 대문자 키 `RESULT_FULL` 도 20000자 예외를 받음 — 의도 확인. `result_max_chars` 음수는 조용히 0. 환경변수 `AGENT_DISPATCH_MIN_FREE_MB` 가 import 시점 고정(런타임 반영 안 됨).
5. `chat_sessions.json` 이 `indent=2` 로 매 메시지마다 전체 재작성 — 메시지 상한 상향으로 쓰기 증폭(개인 1명이라 낮음).
**시작 문구**: "HANDOFF_2026-10-02_agent-dispatch.md 의 창 E 를 해줘."

---

## 3. 정리 대기 (사용자 확인 후)
- 리뷰어가 남긴 임시 worktree: `.claude/worktrees/agent-a92f0525dafbf56c7`, `agent-ad3bbef508026f4bb` (+ 이전 세션 것 다수)
- `C:\Users\Public\Documents\ESTsoft\CreatorTemp\verify_base_*` 3개(일부는 git worktree 로도 등록됨)
- 로컬 브랜치 `backup/pre-scrub-20261002` — 민감 값 포함 원본 이력, **절대 푸시 금지**

## 4. 미커밋·타 세션 상태 (이 세션이 건드리지 않음)
- 작업 폴더의 `ai_orchestrator/connectors/community_router.py` 미커밋 변경, `data/content_rag/`, `data/hanafax_test/`, `admin-web/electron/.htmlvalidate.json` 미추적 — 다른 세션 작업.
- 같은 브랜치에 다른 세션이 커밋을 계속 올리는 중(CDP 칸 분리 P0, 건설업 공무 문서 등). 푸시 전 항상 겹치는 파일 확인.
