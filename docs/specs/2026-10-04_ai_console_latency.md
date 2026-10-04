# AI 창 응답 속도 개선 기준서 (2026-10-04 개정 2, 승인 대기)

개정 2: 공식 문서(code.claude.com/docs: headless, cli-reference, prompt-caching, agent-sdk)와 이 PC 의 `claude --help`(v2.1.286)로 전제를 검증하고 옵션별로 실측해 변경안을 고쳤다.

## 1. 현상
AI 창(UniversalChat)에 질문하면 답이 오기까지 오래 걸린다.

## 2. 현재 구조와 실측 (사이트 지도 조회 질문, UI 와 같은 프롬프트)
```
UniversalChat ─POST /ai-agent/run→ 서버 큐(queued)
   └─ [A] 에이전트가 집어가기까지 대기              실측 8.3초 (0~10초)
로컬 에이전트(WebSocket) ─→ `claude -p` 새 프로세스
   └─ [B] Claude 실행: 시작 약 3.5초 + 3턴            약 13초, $0.18
UniversalChat ─GET 2초 간격 폴링→ 완료 감지
   └─ [C] 폴링 지연                                 0~2초 (평균 1초)
```
합계 ≈ 8 + 13 + 1 = 약 22초. [A]·[C] 는 AI 가 일하지 않는 순수 대기다.

### 원인
- [A] `local_agent_router_ws.py`: 서버가 새 queued 작업을 푸시하는 시점이 에이전트 heartbeat 수신 때뿐이다. heartbeat 주기는 `local_agent/config.py` `POLL_INTERVAL_SEC=10`. 큐에 넣는 쪽(`ai_agent_router.run_agent`)은 에이전트를 깨우지 않는다.
- [B] `_build_claude_command` 가 질문마다 새 프로세스를 띄우고 저장소 루트에서 CLAUDE.md(약 3.3만 토큰)·프로젝트 훅·모든 내장 도구가 열린 채 실행한다. 직원 지침이 없는 질문이면 앱 도구 대신 파일을 뒤져 21턴 64초까지 늘어졌다(지침이 있으면 3턴).
- [C] `UniversalChat.tsx` `POLL_INTERVAL_MS = 2000` 고정.

## 3. 공식 문서·실측으로 확인한 사실 (전제 교정)
| 항목 | 확인 결과 | 근거 |
|---|---|---|
| `--bare` | CLAUDE.md·훅·MCP 자동탐색을 건너뛰지만 **OAuth·키체인을 읽지 않고 `ANTHROPIC_API_KEY`/apiKeyHelper 만 인증**으로 쓴다. 이 앱은 구독 로그인이라 **사용 불가**(유료 API 키 사용은 프로젝트 승인 규칙 대상) | headless.md, `claude --help` |
| `--restricted` | 코드 실행 도구(Bash 등)·WebFetch 제거, 사용자/프로젝트/로컬 설정(훅 포함) 무시, 파일 도구를 작업 폴더로 제한, bypassPermissions 거부. 앱이 이미 읽기 전용 역할에서 쓰는 공식 옵션 | `claude --help` |
| `--strict-mcp-config` | **인자 없는 플래그**. `--mcp-config` 의 서버만 쓰고 사용자 PC 의 다른 MCP(failed 2개 포함)를 무시 | `claude --help` |
| `--tools ""` | 내장 도구 전부 비활성의 공식 문법. MCP 도구는 영향 없이 남는다(실측으로도 확인) | cli-reference.md |
| `--exclude-dynamic-system-prompt-sections` | 공식 존재. 프롬프트 캐시 재사용 개선용이나 실측 효과 없음(아래) | cli-reference.md |
| `--no-session-persistence` | 공식 존재. 단 `--resume` 불가 → **대화 이어가기를 쓰는 UniversalChat 에는 부적합** | `claude --help` |
| 영속 프로세스 | `--input-format stream-json`(한 프로세스에 여러 메시지) 또는 Agent SDK `ClaudeSDKClient` 가 공식 경로 | headless.md, agent-sdk |
| 진행 스트리밍 | `--output-format stream-json --verbose --include-partial-messages` | headless.md |

### 옵션별 실측 (같은 질문, UI 프롬프트, 3턴 경로)
| 변형 | Claude 실행 | 비용 | 캐시 생성 토큰 |
|---|---|---|---|
| 현재(저장소 루트, 설정 전부 로드) | 13.4초 | $0.18 | 약 33,000 |
| `--restricted --strict-mcp-config --tools ""` (루트 그대로) | 11.7초 | $0.058 | 약 11,600 |
| 저장소 밖 cwd + strict + tools "" + exclude-dynamic + no-persistence | 11.9초 | $0.057 | 약 11,300 |
| 루트 + strict + tools "" + `--setting-sources ""` + exclude-dynamic | 13.5초 | $0.061 | 약 11,800 |
| **영속 프로세스**(restricted+strict+tools "", 같은 프로세스에 3회 질문) | **8.4초 → 4.1초 → 3.7초** | $0.055 → 0.064 → 0.076 | 10,674 → 508 → 1,490 |

해석:
- 저장소 밖 cwd·`--setting-sources`·`exclude-dynamic` 은 `--restricted` 위에 얹어도 추가 이득이 없다 → **채택하지 않는다**(변경 최소화).
- 지연을 실제로 줄이는 건 **영속 프로세스**(시작 3.5초 제거 + 캐시 유지). 비용 절감은 `--restricted` 가 낸다.
- 영속 프로세스의 후속 질문이 도구를 다시 부르지 않고 앞 답을 재사용하는 경우가 있어(3번째 질문) **최신성 위험**이 있다 → 직원 지침에 "수치·상태는 매번 앱 기능으로 다시 조회" 문장 필요.

## 4. 변경안 (수정)
| # | 변경 | 위치(레이어) | 기대 효과 | 위험 |
|---|---|---|---|---|
| P1 | 큐에 넣는 즉시 연결된 에이전트의 WS 루프를 깨워 푸시(에이전트별 wake 이벤트, 기존 heartbeat 푸시는 폴백으로 유지) | `local_agent_router_ws.py` (L8), `ai_agent_router.py` 는 호출만 | [A] 8초 → 0.3초 미만 | 낮음. 전달 대상·용량·승인 규칙 불변 |
| P2 | 폴링 간격 2000ms → 700ms(오래 걸리면 2000ms 로 완화) | `UniversalChat.tsx` (L9) | [C] 평균 1초 → 0.35초 | 매우 낮음 |
| P3 | UniversalChat 기본 호출에 `lean` 옵션: `--restricted --strict-mcp-config --mcp-config .mcp.json --tools ""` 만 추가. cwd 이동·bare 없음. 기본값은 현재 동작 유지 | `local_agent/actions.py`, `ai_agent_router.py` | 비용 68% 절감($0.18→0.058), 파일 뒤지기 경로 차단, 첫 질문 약 1.5초 단축 | 중간. lean 에서는 CLAUDE.md 훅(세션 보호 등)·내장 도구가 없고 서버 게이트(허용 API 집합·sitemap.run 조회 제한·승인 카드)가 유일한 강제선. 공무·메일·팩스·블로그 창이 내장 도구를 쓰는지 창별 확인 후 적용 |
| P4(별도 기준서) | **영속 프로세스 풀**: 채팅(chat_id)별 `claude -p --input-format stream-json` 1개 유지, 유휴 시 종료, 동시성·메모리 상한, 채팅 간 컨텍스트 분리 | `local_agent/` 신규 모듈(L10) + 에이전트 액션 | 후속 질문 약 12초 → 약 4초 | 높음. 프로세스 수명·누수·승인 대기 상호작용·컨텍스트 오염. 설계·시험 후 승인 |
| P5(보류) | 진행 상황 스트리밍("도구 호출 중…") | 대공사 | 체감 속도 | 별도 기준서 |

기대: P1+P2+P3 → 약 22초가 약 11초(첫 질문), P4 까지 → 후속 질문 약 5초.

## 5. 범위·불변
- API 응답 key, DB, 정책, 승인 흐름 변경 없음. 신규 엔드포인트 없음 → 라우트 수 기준선(416) 불변. P1~P3 은 새 .py 없음.
- 유료 외부 AI API(OpenAI·Anthropic API 키) 사용 없음 — 구독 로그인 CLI 유지(`--bare` 배제 사유).

## 6. 검증 계획
1. 드라이 런: 변경 diff 와 영향 테스트 목록(`tests-for`) 보고 — 파일 수정 없이.
2. 승인 후 구현 → 영향 테스트(`test_local_agent_ws*.py`, `test_ai_agent*`, `test_employee_protocol.py`) + ruff(바뀐 파일만) + `verify_change`.
3. 앱 실측 재시험: 같은 질문으로 [A]/[B]/[C] 재측정, 전후 표 보고. P3 는 lean 적용 창별로 조회·승인 카드 동작 확인.

## 7. 구현 결과 (2026-10-04, P1·P2 + 추가 발견 P0 적용, 미커밋)
적용: P1(큐 등록 즉시 푸시), P2(폴링 0.7초→2초), **P0(신규 발견)** `action_run_claude_agent` 의 `subprocess.run` 에 `stdin=subprocess.DEVNULL`.

### P0 — stdin 3초 대기 (실측으로 발견)
에이전트는 Electron(Node spawn)이 stdin 을 **열린 빈 파이프**로 넘겨 띄운다. `claude -p` 는 stdin 이 TTY 가 아니면 입력을 3초 기다린 뒤 시작한다. 같은 함수를 stdin 조건만 바꿔 두 번씩 재현: 열린 PIPE 18.6초·18.6초, DEVNULL 15.1초·15.1초. (단독 `claude -p` 반복은 네트워크 변동에 묻혀 구분되지 않았으므로, 위 함수 단위 재현이 근거다.)

### 전후 비교 (사이트 지도 조회 질문, UI 와 같은 프롬프트, API 기준)
| 단계 | 변경 전 | 변경 후 |
|---|---|---|
| [A] 큐 대기 | 8.3초 | 0.04초 |
| [B] Claude 실행(에이전트 경유) | 약 20초(stdin 3초 포함) | 약 13~17초 |
| 합계 | 약 28초 | 12.9 / 15.4 / 17.4초 (평균 15.2) |
UI(Electron) 실측: 첫 질문 17.1초, 이어지는 질문(--resume) 10.2초.

### 남은 과제
- P3(`--restricted` lean): 비용 $0.18→$0.058, 지연 단축은 1~2초에 그침 — 다른 AI 창 확인 후 별도 승인.
- P4(영속 프로세스): 후속 질문 약 4초 기대. 별도 기준서.
- 이어지는 질문에서 AI 가 앞 답을 재사용하고 새로 조회하지 않는 경우를 확인함("이번에는 새로 조회하지 않았습니다" 라고 정직하게 밝힘) — 직원 지침에 "수치·상태는 매번 앱 기능으로 다시 조회" 문장 추가 검토.
- 시험 결함(기존): `ai_orchestrator/tests/test_local_agent_ws.py`·`test_approval_public_id.py` 는 시험마다 `auth` 를 reload 하지만 하위 라우터는 reload 되지 않아 파일 전체 실행 시 두 번째 시험부터 `KeyError: 'agent_id'`. 원본 HEAD 에서도 동일(격리 실행하면 전부 통과).
