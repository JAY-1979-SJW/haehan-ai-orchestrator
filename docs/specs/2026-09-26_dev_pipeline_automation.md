# 개발 파이프라인 자동화 — 기준서 + 드라이런 (2026-09-26)

> 상태: **기준서·드라이런만 작성. 코드·설정 미수정, 커밋 없음.** 사용자 승인 후 단계별(P1→P4) 착수.
> 범위: "사람이 손으로 지시·승인·조율하는 개발 흐름"을 Anthropic 공식 Claude Code 기능 + 기존 저장소 자산으로 자동화.
> 원칙: 공식 문서에 있는 기능만 사용(각 기능 옆에 문서 URL). LLM이 할 필요 없는 일(락·게이트·병합·체크리스트 대조)은 **결정론적 Python**으로 한다.

---

## 0. 요약

| 항목 | 결론 |
|---|---|
| 흐름 | 과제 카드(JSON 1개) → spec-writer → 드라이런 → **사람 승인 1회(카드 해시 단위)** → worktree 자동 생성 → implementer → 빠른 게이트 → code-reviewer(분리 컨텍스트) → verify(전역 락, 직렬) → merge_stage(ff-only) → 결과 카드 갱신 → 체크리스트 대조 리포트 |
| 오케스트레이터 | **메인 세션 + 스킬 `/stage-run` + Agent 도구(서브에이전트)** 를 기본으로, 상태기계·락·git 조작은 `scripts/ops/pipeline_runner.py`(LLM 호출 없음)가 전담. headless `claude -p` 는 P4 선택 사항 |
| 오늘 오류 7건 | 모두 코드/훅/권한 규칙으로 차단(§8 드라이런 표). 문서 규칙에만 의존하는 항목 0 |
| 즉시 효과 큰 것 | **P1: 전역 락 + map.json 신선도 강제** (코드 2~3개 파일, 에이전트 정의 불필요) |
| 사람 개입 지점 | 카드 승인 1회, 보안·비가역(push·운영 배포·데이터 삭제·유료 외부 AI API), 권한 설정 변경 |
| 핵심 발견 | 프로젝트 `.claude/settings.json` 의 `defaultMode: "bypassPermissions"` 는 **공식 문서상 프로젝트 설정에서 효력이 없다** → 세션은 Manual/auto 로 시작하고, 그래서 worktree 삭제·프로세스 종료가 auto 분류기에 막혔다(§6.1) |
| 근본 문제(§13) | ① 로컬 Python 3.14 ↔ 운영 3.11 검증 0 ② CLAUDE.md 703줄(공식 권장 200줄 미만의 3.5배, 47%가 사이트 운영자료) + **API 키 원문 포함** ③ 상시 실패 277건 기준선이 정본 없이 흩어짐 ④ "금지/STOP" 규칙 다수가 문서에만 존재 ⑤ 사람 작성 지시문·kitchen-sink WIP. 로드맵은 §11 에 통합 |

---

## 1. 요구사항 (오늘 실제 발생한 수동 오류)

| # | 오류 | 근본 원인 | 필요한 강제 수단 |
|---|---|---|---|
| R1 | `verify_change` 2회 동시 실행 → 로그 오염 (첫 실행을 죽은 줄 오판) | 동시 실행 금지가 문서에만 있음. 실행 중 여부를 알 방법 없음 | 코드 레벨 전역 락 + PID 생존 확인 + 재실행 시 "실행 중, 로그는 여기" 안내 + 훅 이중 차단 |
| R2 | 피어 Claude 창에 보낸 지시가 "사용자 확인 없이 설정 변경 불가"로 거부 | **문서화된 정상 동작**: 다른 세션 메시지는 동의가 아니며 설정 변경 불가 | 피어 세션을 지휘 수단으로 쓰지 않음 → 서브에이전트/러너로 대체 |
| R3 | 지시문에서 CLAUDE.md 코딩 컨벤션·명령어 누락 | 사람이 매번 손으로 작성, 대조 수단 없음 | 카드 스키마에 표준 요구사항 자동 주입 + 체크리스트 대조기 |
| R4 | 오래된 `data/code_map/map.json` 으로 측정 → 위반 34 vs 43 불일치 | `layer_count.py`·`query.py` 가 map 을 재생성/검증 없이 읽음 | 지문(커밋+작업트리) 스탬프 + 불일치 시 자동 재빌드 또는 거부 |
| R5 | 단계마다 긴 지시문 수작업(브랜치·worktree·게이트·금지사항 반복) | 템플릿 부재 | 카드 → `agent_brief.py` 로 브리프 자동 생성 |
| R6 | 권한 분류기가 worktree 삭제·프로세스 종료를 막아 흐름 정지 | bypass 설정이 무효 + 좁은 allow 규칙 없음 | 러너 1개 명령만 좁게 allow, 러너가 자기 소유 자원만 삭제/종료 |
| R7 | 병합은 verify PASS 후 `merge_stage.py`(ff-only), 직렬 | 순서가 사람 기억에 의존 | 상태기계가 순서 강제, merge 락 |

---

## 2. 공식 문서 근거 (설계에 쓰는 기능만)

| 기능 | 설계 내 용도 | 문서 |
|---|---|---|
| 서브에이전트 `.claude/agents/*.md` frontmatter: `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills`, `hooks`, `isolation`, `effort`, `omitClaudeMd` | spec-writer / implementer / code-reviewer 정의 | https://code.claude.com/docs/en/sub-agents |
| 서브에이전트 frontmatter `hooks` — "그 서브에이전트가 도는 동안만 실행, `Stop`은 `SubagentStop`으로 변환" | implementer 전용 PreToolUse(worktree 밖 편집 차단) | https://code.claude.com/docs/en/hooks |
| 서브에이전트가 서브에이전트를 생성(기본 3단계 깊이) | 스킬(fork) 안에서 implementer 호출 가능 | https://code.claude.com/docs/en/sub-agents |
| `isolation: worktree` (기본 브랜치 `worktree-<name>`, `.claude/worktrees/` 아래, 기본 base=기본 브랜치) | **채택 안 함**(§5.4 사유) | https://code.claude.com/docs/en/worktrees |
| 스킬 `SKILL.md`: `disable-model-invocation: true`, `allowed-tools`(해당 턴만), `arguments`/`$0`, `` !`command` `` 동적 주입, `context: fork` + `agent` | `/stage-run <card>` , `/card-new` | https://code.claude.com/docs/en/skills |
| 훅 `PreToolUse` JSON `permissionDecision: allow/deny/ask`, exit 2 차단, `if` 필드(권한 규칙 문법) | verify 중복 실행 차단, 승인 파일 위조 차단 | https://code.claude.com/docs/en/hooks |
| 훅 `UserPromptSubmit` — "사용자가 프롬프트를 제출할 때" 발화 | 사람 승인 문구(`승인 <card>`)를 결정론적으로 기록 | https://code.claude.com/docs/en/hooks |
| 훅 `SubagentStop`(차단 불가, `last_assistant_message` 입력) | 에이전트 결과를 카드에 자동 기록 | https://code.claude.com/docs/en/hooks |
| "CLAUDE.md 지시는 권고, 훅은 결정론적" / 검증 가능한 체크 제공 / 분리 컨텍스트 적대적 리뷰 | 설계 원칙 | https://code.claude.com/docs/en/best-practices |
| 권한 규칙: deny→ask→allow 순서, `Bash(cmd *)` 접두 와일드카드, 복합명령은 하위명령 각각 매칭, `PowerShell(...)` 동일 문법 | 러너 전용 allow, 파괴 명령 deny | https://code.claude.com/docs/en/permissions |
| 프로젝트 `.claude/settings.json` 의 `defaultMode` `auto`/`bypassPermissions` 는 효력 없음 | R6 원인 진단 | https://code.claude.com/docs/en/permission-modes |
| auto 모드: 좁은 Bash/PowerShell allow 규칙은 분류기 전에 해석, `Bash(*)`·와일드카드 인터프리터는 정지 / `autoMode` 는 프로젝트 설정에서 읽지 않음(사용자·managed·`--settings`만) / 3회 연속·20회 누적 차단 시 fallback | R6 해결 설계 | https://code.claude.com/docs/en/auto-mode-config , https://code.claude.com/docs/en/permission-modes |
| 교차 세션 메시지: "동의로 간주 안 됨", "설정 변경 불가", 받는 세션 권한 프롬프트 그대로, bypass 세션은 기본 hold | R2 원인·대안 | https://code.claude.com/docs/en/cross-session-messaging |
| headless `claude -p`, `--output-format json`(`result`,`session_id`,`total_cost_usd`), `--json-schema`→`structured_output`, `--allowedTools`, `--permission-mode dontAsk/acceptEdits/auto`, `--permission-prompts none`, `--agents`, `--settings`, `--bare`(API 키 필요·구독 로그인 미사용), 종료코드 0/비0, SIGTERM→143 | P4 선택안 | https://code.claude.com/docs/en/headless |
| `--max-turns`, `--max-budget-usd`(print 전용), `--no-session-persistence`, `--agent`, `--name`, `--append-system-prompt-file` | P4 선택안 상한 | https://code.claude.com/docs/en/cli-reference |
| Agent SDK: 서드파티는 claude.ai 로그인/사용량을 제품에 쓰지 말고 API 키 사용 | 비용·정책 판단 | https://code.claude.com/docs/en/agent-sdk/overview |
| `-p` 실행의 worktree 는 자동 정리 안 됨, 잠긴 worktree 는 `git worktree unlock` 후 remove | 러너 정리 로직 | https://code.claude.com/docs/en/worktrees |

문서에서 확인하지 못해 **설계에 쓰지 않는 것**: 피어 세션에 권한을 원격 부여하는 방법(문서상 불가), 서브에이전트 종료를 차단하는 훅(SubagentStop 은 차단 불가), `isolation: worktree` 의 브랜치명 지정(문서상 `worktree-<name>` 고정·`baseRef` 는 `fresh`/`head` 만).

---

## 3. 기존 자산 (재사용, 신규 중복 금지)

| 자산 | 현재 동작(실측) | 이 설계에서의 역할 |
|---|---|---|
| `tools/verify_change.py` (439줄) | `--base/--head/--json`, 기준·대상 트리를 임시 `git worktree`(`verify_base_*`)로 꺼내 병렬 측정, 잔여 프로세스 정리(`kill_leftovers`). **락 없음** | 락 획득 1곳만 추가(§5.2). 나머지 그대로 |
| `tools/merge_stage.py` (286줄) | 내부에서 verify_change 실행 → PASS 시 `merge --ff-only` + 태그 `verified/<name>`, base 체크아웃 확인·태그 중복·겹침 검사 | 그대로 사용. merge 락 + 자식 verify 에 토큰 전달만 추가 |
| `tools/code_map/build.py` | `meta = {generated_at, commit(short HEAD), scan_root, digest}` — **작업트리 변경 반영 여부 없음** | 지문 필드 추가 |
| `tools/code_map/layer_count.py` | map.json 을 **검증 없이** 읽음(R4 원인) | 신선도 확인 호출 1줄 |
| `tools/code_map/query.py` | map.json 로드, 없으면 에러 | 신선도 확인 |
| `tools/code_map/agent_brief.py` | `configs/agent_roles.json` 역할표로 브리프 생성(대상·영향 테스트·WIP 금지 파일·검증 명령) | 카드 → 브리프 변환의 본체 |
| `configs/agent_roles.json` | implement/review=sonnet, compare=haiku, design=main, 도구호출 상한, handoff 경로 | 서브에이전트 `model`·`maxTurns` 의 정본 |
| `tools/hooks/agent_usage.py` | 역할별 토큰·도구호출 jsonl 기록/집계 | SubagentStop 훅에서 자동 기록 |
| `tools/code_map/registry_sync.py`, `skeleton_gate.py` | 정본 동기화 / pre-commit 대조 게이트 | 게이트 단계에서 호출 |
| `.claude/agents/code-reviewer.md` | tools Read/Grep/Glob/Bash, sonnet, 등급·출력 형식 고정 | 그대로 리뷰 단계에 사용 |
| `.claude/settings.json` hooks | guard_openai_call·guard_cdp_new_tab·guard_instagram·guard_youtube(PreToolUse Bash/PS), pre_edit_dup_check / post_edit_fast_gate / stop_fast_verify(품질게이트 3종), behavior_gate | 유지. 신규 훅 2개 추가만 |
| `.claude/settings.local.json` hooks | session_guard(UserPromptSubmit/SessionStart/Stop/PreCompact) | 유지 |
| CLAUDE.md | 기준서→드라이런→승인, 게이트 의무, 병렬 금지, 유료 외부 AI API 승인제, 코딩 컨벤션·명령어(291~352행) | 카드 표준 요구사항의 출처 |

실측 부수 발견: `git worktree list` 에 `.../CreatorTemp/verify_base_x196rucj/{base,head}` 가 **남아 있음** — 오늘 중복/중단된 verify 가 정리 못 한 흔적. P1 락의 stale 복구가 이것도 정리해야 한다.

---

## 4. 전체 흐름

```
[사람] 카드 초안 요청 (/card-new "<목표>")
   │
   ▼
① card     data/pipeline/cards/<id>.json  ← 표준 요구사항(CLAUDE.md 유래) 자동 주입
② spec     spec-writer 서브에이전트 → docs/specs/<date>_<id>.md (기준서)
③ dryrun   pipeline_runner.py dryrun <id>  (예상 영향 파일·레이어·게이트 예측, 파일 미수정)
④ APPROVE  ★사람 1회★  "승인 <id>" 입력 → UserPromptSubmit 훅이 카드 해시와 함께 기록
─────────────── 이하 사람 개입 없음(보안·비가역 예외 제외) ───────────────
⑤ prepare  runner: git worktree add C:/work/wt-<id> -b stage/<id> <base>
⑥ implement implementer 서브에이전트 (브리프 1개만 읽고 시작, worktree 밖 편집 훅 차단)
⑦ gate     runner: ruff(바뀐 파일)·영향 테스트·codebase_layer_audit·quality_gate·skeleton_gate
           FAIL → implementer 재호출(새 에이전트 + 실패 요약, 최대 2회) → 그래도 FAIL 이면 STOP·보고
⑧ review   code-reviewer 서브에이전트 (diff 만, 분리 컨텍스트) → FAIL 이면 ⑥로 1회
⑨ verify   runner: 전역 verify 락 획득 → map 재빌드 → verify_change --head stage/<id>
⑩ merge    runner: merge 락 → merge_stage.py stage/<id> (내부 verify 는 토큰으로 락 재진입)
⑪ report   runner: 카드 results 갱신 + 체크리스트 대조 리포트(PASS/WARN/FAIL) + worktree 정리
```

사람 개입 지점(그 외 전부 자동):
- ④ 카드 승인(카드 내용이 바뀌면 해시 불일치 → 재승인).
- 카드의 `human_checkpoints` 에 적힌 비가역 작업: `git push`, 운영 배포, 데이터 삭제, 유료 외부 AI API, 외부 발행. → `permissions.ask` 규칙 + 기존 guard 훅이 강제.
- 권한 설정 변경(§6) — 최초 1회.

병합(⑩)의 사용자 승인: 현 `merge_stage.py` docstring 은 "AI 가 사용자 승인 없이 실행하지 않는다". 본 설계는 **④의 카드 승인에 "PASS 시 master 병합"을 포함**시키는 것을 추천하되, 사용자 결정 항목 D3 으로 둔다(로컬 master 만 변경, push 는 별도 ask).

---

## 5. 구성요소 설계

### 5.1 과제 카드 스키마 (`data/pipeline/cards/<id>.json`, git 미추적 — `data/` 관례)

```json
{
  "schema": "pipeline-card/1",
  "id": "2026-09-26-lock-p1",
  "title": "verify 전역 락",
  "goal": "verify_change 동시 실행을 코드로 차단",
  "base": "master",
  "branch": "stage/lock-p1",
  "worktree": "C:/work/wt-lock-p1",
  "layer": "L2",
  "files_allowed": ["scripts/ops/pipeline_lock.py", "tools/verify_change.py", "tests/test_pipeline_lock.py"],
  "files_forbidden": ["configs/module_registry.json"],
  "spec_path": "docs/specs/2026-09-26_lock_p1.md",
  "expect_routes": null,
  "requirements": [
    {"id": "U1", "text": "동시 실행 시 두 번째는 exit 4", "source": "user", "check": {"type": "command", "cmd": "python -m pytest tests/test_pipeline_lock.py -q", "expect_exit": 0}},
    {"id": "C-RUFF", "text": "바뀐 py 파일 ruff 신규 오류 0", "source": "CLAUDE.md#테스트·빌드·린트 명령", "check": {"type": "evidence", "key": "gate.ruff_new_errors", "expect": 0}},
    {"id": "C-AFFECTED", "text": "영향 테스트만 실행, 전체 pytest 금지", "source": "CLAUDE.md#반복 실수", "check": {"type": "evidence", "key": "gate.affected_tests_pass", "expect": true}},
    {"id": "C-GATES", "text": "게이트 3종 PASS", "source": "CLAUDE.md#게이트 실행 의무", "check": {"type": "evidence", "key": "gate.triple_pass", "expect": true}},
    {"id": "C-SCOPE", "text": "files_allowed 밖 변경 0", "source": "card", "check": {"type": "diff_scope"}},
    {"id": "C-REUSE", "text": "중복 구현 없음", "source": "CLAUDE.md#재사용 우선", "check": {"type": "evidence", "key": "review.duplicate", "expect": "없음"}},
    {"id": "C-VERIFY", "text": "verify_change PASS", "source": "CLAUDE.md#게이트 실행 의무", "check": {"type": "evidence", "key": "verify.ok", "expect": true}}
  ],
  "human_checkpoints": ["git push", "운영 배포", "유료 외부 AI API"],
  "budget": {"implement_max_tool_calls": 40, "review_max_tool_calls": 25, "retries": 2},
  "approval": null,
  "state": "draft",
  "history": [],
  "results": {}
}
```

- `C-*` 요구사항은 **`configs/pipeline_standard_requirements.json`**(신규, CLAUDE.md 해당 절을 가리키는 정본)에서 `/card-new` 가 자동 주입 → R3·R5 해결. CLAUDE.md 가 바뀌면 이 파일 한 곳만 갱신.
- `approval` = `{"by":"user-prompt","at":"…","card_sha256":"…"}` — 승인 이후 `goal/files_allowed/requirements/human_checkpoints` 가 바뀌면 해시 불일치로 러너가 ⑤ 이후 진행 거부.
- `state` 전이는 러너만 수행: `draft→spec_ready→dryrun_ready→approved→prepared→implemented→gated→reviewed→verified→merged→reported` (+`failed`, `stopped`).

### 5.2 전역 락 (`scripts/ops/pipeline_lock.py`, 신규 L2 — 정책/게이트)

- 락 파일: 메인 저장소 공통 위치 `data/ops/locks/{verify,merge}.lock` (worktree 에서 실행돼도 `git rev-parse --git-common-dir` 로 메인 루트를 찾는다 — `skeleton_gate.py` 와 같은 방식 재사용).
- 획득: `os.open(O_CREAT|O_EXCL)` 원자 생성. 내용 `{pid, proc_create_time, started_at, cmd, head, log_path, tmp_dir, token}`.
- 이미 존재 시:
  1. PID 생존 + **프로세스 생성시각 일치**(PID 재사용 오판 방지) → **exit 4** + 안내: `이미 실행 중 (pid, 시작 N분 전). 로그: <log_path>. 재실행 금지 — 로그 tail 로 진행 확인`. (R1의 "죽은 줄 오판" 차단: 로그 경로를 주므로 확인 수단이 생김.)
  2. 죽음 → stale 복구: 기록된 `tmp_dir` 의 `verify_base_*` worktree 를 `git worktree remove --force` + `git worktree prune`, 락 삭제 후 재획득, 경고 출력.
- 재진입: `merge_stage.py` 가 merge 락을 잡고 자식 verify 에 `PIPELINE_LOCK_TOKEN` 환경변수 전달 → verify 는 verify 락을 **토큰 일치 시에만** 공유.
- 해제: `atexit` + `finally`. SIGTERM 류로 죽어도 다음 실행의 stale 복구가 처리.
- 생존 확인 구현: Windows 는 `ctypes` `OpenProcess`+`GetProcessTimes` (외부 의존 없음), POSIX 는 `os.kill(pid,0)`. psutil 미의존.
- 로그: verify 출력 사본을 `data/ops/logs/verify_<ts>.log` 에 tee — 두 번째 실행자에게 알려줄 경로.
- **이중 차단 훅**(문서: PreToolUse `permissionDecision: deny` + `permissionDecisionReason`): `scripts/ops/guard_single_verify.py` — Bash/PowerShell 명령에 `verify_change.py` 또는 `merge_stage.py` 가 있고 해당 락이 살아 있으면 deny, 사유에 로그 경로. 에이전트는 재실행 대신 로그를 읽게 된다.

### 5.3 map.json 신선도 강제 (`scripts/ops/code_map/freshness.py`, 신규 L2)

- `build.py` meta 에 `head_full`(40자) + `worktree_fingerprint` 추가: `sha256(git rev-parse HEAD + git status --porcelain=v1 -z + git diff HEAD 의 *.py 내용 해시)`.
- `ensure_fresh(root, mode="rebuild"|"refuse")`: 현재 지문 ≠ meta 지문이면 `rebuild`(기본) 또는 exit 5.
- 호출처 추가(각 1~2줄): `layer_count.py`, `query.py`, `agent_brief.py`. `verify_change.py` 는 이미 매 측정마다 `build.py` 를 돌리므로 변경 불필요(실측 311·196행).
- `layer_count.py` 출력(`layer_baseline.json`)에 `meta.worktree_fingerprint` 기록 → 두 수치를 비교할 때 지문이 다르면 "다른 트리 측정값"으로 표시(R4의 34 vs 43 재발 시 원인 즉시 식별).
- worktree 별 map: 각 트리의 `data/code_map/map.json` 은 그 트리 기준. 카드 results 에는 **측정 트리 경로 + 지문**을 같이 기록.

### 5.4 서브에이전트 정의 (`.claude/agents/`)

| 파일 | tools | model / maxTurns | 핵심 제약 |
|---|---|---|---|
| `spec-writer.md` (신규) | Read, Grep, Glob, Bash, Write | `inherit`(agent_roles `design=main`) | 쓰기는 `docs/specs/*` 만 — frontmatter `hooks.PreToolUse`(Write\|Edit) 로 경로 밖 deny. `capability_check.py` 선행 의무를 본문에 |
| `implementer.md` (신규) | Read, Grep, Glob, Edit, Write, Bash, PowerShell | `sonnet` / `maxTurns` = agent_roles `implement.max_tool_calls`(40) | frontmatter `hooks.PreToolUse`: 카드의 worktree 밖 Edit/Write deny, `files_allowed` 밖 경고. `git commit` 은 worktree 안에서만, `git push`/merge 금지(`disallowedTools` 불가 → 러너가 담당, ask 규칙) |
| `code-reviewer.md` (기존) | Read, Grep, Glob, Bash | `sonnet` | 그대로. 입력은 러너가 만든 `git diff <base>...stage/<id>` 파일 경로 |
| `verifier.md` | — | — | **만들지 않음 추천**: verify 는 결정론적 스크립트라 LLM 이 판단할 것이 없음. LLM 에 맡기면 R1(재실행 오판)이 다시 생김. 결과 요약은 러너가 JSON→표로 출력 |

`isolation: worktree` 를 쓰지 않는 이유(https://code.claude.com/docs/en/worktrees): 생성 위치 `.claude/worktrees/<name>`, 브랜치 `worktree-<name>`, base 는 `fresh`(원격 기본 브랜치) 또는 `head` 만 — 이 저장소의 `stage/*` 브랜치·`C:/work/wt-*` 위치·`merge_stage.py` 규약과 맞지 않는다. 러너가 `git worktree add` 로 직접 만들고, implementer 에게는 절대경로 + 경로 제한 훅으로 격리를 준다.

에이전트 결과 기록: 프로젝트 `SubagentStop` 훅(`matcher: "implementer|code-reviewer|spec-writer"`) → `pipeline_runner.py record-agent` 가 `last_assistant_message` 를 카드 history 에 저장 + `agent_usage.py record` 호출. (SubagentStop 은 차단 불가이므로 기록 전용.)

### 5.5 스킬

`.claude/skills/stage-run/SKILL.md` (신규)
```yaml
---
name: stage-run
description: 승인된 과제 카드를 prepare→implement→gate→review→verify→merge→report 까지 진행
disable-model-invocation: true      # 병합 부작용 → 사람이 /stage-run 으로만 시작
arguments: [card]
allowed-tools: Bash(python scripts/ops/pipeline_runner.py *) PowerShell(python scripts/ops/pipeline_runner.py *)
---
현재 상태:
!`python scripts/ops/pipeline_runner.py status $card`

규칙: 상태 전이는 pipeline_runner.py 만 한다. 다음 LLM 단계가 필요하면 지정된 서브에이전트만 호출.
... (단계별 지시: next 명령 출력이 "AGENT implementer <brief-path>" 이면 Agent 도구로 implementer 호출 등)
```
- `allowed-tools` 는 **호출 턴 동안만** 유효(문서) — 장기 권한은 §6 의 allow 규칙이 담당.
- `/card-new` 스킬: 목표 문장 → 카드 초안 + 표준 요구사항 주입 + spec-writer 호출 → 드라이런 출력 → "승인 <id>" 입력 대기.

### 5.6 러너 (`scripts/ops/pipeline_runner.py`, 신규 L6 업무흐름 — LLM 호출 없음)

| 서브커맨드 | 동작 | 재사용 |
|---|---|---|
| `new/status <id>` | 카드 생성/조회 | — |
| `dryrun <id>` | 예상 영향: `query.py tests-for`, 레이어, files_allowed 존재, 예상 게이트 | query.py |
| `approve-record <id>` | (UserPromptSubmit 훅 전용) 승인 기록 | — |
| `prepare <id>` | 해시 확인 → `git worktree add <wt> -b stage/<id> <base>` → `agent_brief.py` 로 브리프 생성 → `AGENT implementer <brief>` 출력 | agent_brief.py |
| `gate <id>` | 바뀐 파일 ruff, 영향 테스트, 게이트 3종, skeleton_gate → evidence 기록 | 기존 게이트 스크립트 |
| `review-input <id>` | diff 파일 생성 → `AGENT code-reviewer <diff>` | code-reviewer.md |
| `verify <id>` | verify 락 → `verify_change.py --base <b> --head stage/<id> --json` | verify_change.py |
| `merge <id>` | merge 락 → `merge_stage.py stage/<id>` | merge_stage.py |
| `report <id>` | 체크리스트 대조(§5.7) → 카드 results, `worktree remove`(자기 카드 worktree 만, 병합 완료 확인 후) | — |
| `next <id>` | 현재 state 로 다음 할 일 1줄 출력(스킬이 읽음) | — |

러너 자체의 안전장치: worktree 삭제는 **카드에 기록된 `C:/work/wt-<id>` 이고 브랜치가 base 에 병합된 경우만**, 프로세스 종료는 **락 파일에 기록된 PID + 생성시각 일치 시만**. 임의 경로·PID 인자는 받지 않는다 → 좁은 allow 규칙(§6)을 줄 근거.

### 5.7 체크리스트 대조기 (`scripts/ops/pipeline/checklist.py`, 신규 L2 판정)

- 입력: 카드 `requirements` + `results.evidence`(gate/review/verify JSON).
- `check.type`: `command`(실행·exit 비교), `evidence`(키 조회·기대값), `diff_scope`(`git diff --name-only base...branch` ⊆ files_allowed), `grep`(패턴 존재/부재), `manual`(WARN 로만 표시).
- 출력: 요구사항별 PASS/WARN/FAIL 표(markdown) + 카드 저장. FAIL 1건 이상이면 `merge` 단계 진입 거부(verify 전에 판정 가능한 항목은 verify 전에 1차 대조).

### 5.8 사람 승인 기록 (UserPromptSubmit 훅)

- `scripts/ops/pipeline_approve_hook.py`: 프롬프트가 `^승인 (\S+)$` 이면 카드 해시를 `data/pipeline/approvals/<id>.json` 에 기록. UserPromptSubmit 은 사람이 제출한 프롬프트에서만 발화(문서) → 에이전트·피어가 승인을 만들 수 없다.
- 위조 방지: `permissions.deny` 에 `Edit(data/pipeline/approvals/**)`, `Write(data/pipeline/approvals/**)`. Bash 리다이렉트 우회는 문서상 규칙이 "보안 경계가 아님"(permissions 문서 Bash rule limits) → 러너가 승인 파일의 기록 주체 필드 + 훅이 남긴 별도 감사 로그(`data/ops/approvals.jsonl`)를 교차 확인. 잔여 위험은 §9.

---

## 6. 권한 설계

### 6.1 원인 진단 (R6)

- 현 `.claude/settings.json`: `"permissions": {"defaultMode": "bypassPermissions"}`.
- 문서(https://code.claude.com/docs/en/permission-modes): *"If you set `"bypassPermissions"` in those two files [.claude/settings.json, .claude/settings.local.json], it doesn't take effect either, and the session starts in Manual mode."* 또한 v2.1.283+ 는 대화형 기본이 auto.
- 즉 CLAUDE.md 가 전제한 "bypass 자동 실행"은 실제로 동작하지 않고, auto 분류기가 `git worktree remove`·`Stop-Process` 를 파괴적 행동으로 막은 것. (guard_openai_call 훅의 ask 강제는 모드와 무관하게 여전히 유효.)

### 6.2 추천 규칙 (프로젝트 `.claude/settings.json`, 사용자 승인 후 반영)

```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/ops/pipeline_runner.py *)",
      "PowerShell(python scripts/ops/pipeline_runner.py *)",
      "Bash(git worktree list)",
      "Bash(git worktree prune)"
    ],
    "ask": [
      "Bash(git push *)",
      "PowerShell(git push *)"
    ],
    "deny": [
      "Edit(data/pipeline/approvals/**)",
      "Write(data/pipeline/approvals/**)",
      "Bash(git push --force *)",
      "Bash(git merge *)",
      "PowerShell(git merge *)"
    ]
  }
}
```
- 근거: 좁은 allow 는 auto 모드에서도 분류기 전에 해석(auto-mode-config), 복합 명령은 하위명령 각각 매칭이라 `runner && rm -rf …` 는 통과 못 함(permissions). deny→ask→allow 순서.
- `git merge` deny 는 **Claude 의 직접 병합**만 막는다. `merge_stage.py` 내부 subprocess 의 git 은 권한 규칙 대상이 아님(권한은 Claude 의 도구 호출에 적용) → 병합 경로가 러너/merge_stage 하나로 강제됨(R7).
- `git worktree remove C:/work/wt-*` 를 직접 allow 하지 않는 이유: 경로 와일드카드가 `wt-*` 뒤 임의 인자(`--force` 등)를 허용. 러너 경유로 "병합 완료 + 카드 소유" 조건을 코드로 검사하는 편이 안전.
- **불확실(도입 시 실측 필요)**: 문서는 "wildcarded interpreters" 규칙이 auto 모드에서 정지된다고만 하고, `python <특정스크립트> *` 형태가 이에 해당하는지 명시하지 않는다. P1 도입 직후 auto 세션에서 러너 호출이 프롬프트 없이 통과하는지 확인하고, 막히면 D2-b(사용자 `autoMode.allow`)로 보완.

### 6.3 대안 (사용자 결정 D2)

| 안 | 내용 | 장단점 |
|---|---|---|
| a (추천) | §6.2 좁은 allow + 러너 경유 | 프로젝트 파일로 버전관리, 범위 최소. 위 불확실성 1건 |
| b | `~/.claude/settings.json` 의 `autoMode.allow` 에 산문 규칙 추가: "Removing git worktrees under C:/work/wt-* whose stage/* branch is already merged into master is allowed", "Stopping a process whose PID is recorded in this repo's data/ops/locks/*.lock is allowed" (`"$defaults"` 포함) | 프로젝트 설정의 autoMode 는 무시되므로 **사용자 설정에만** 가능(문서). 분류기 판단이라 결정론적이지 않음 |
| c | `--permission-mode bypassPermissions` 로 기동 | 문서: "Isolated containers and VMs only". 비추천 |

`defaultMode: "bypassPermissions"` 줄은 효력이 없으니 오해 방지를 위해 제거하거나 주석성 문서로 대체할지 D2-d 로 확인.

---

## 7. 오케스트레이션 방식 비교 (메인+Agent 도구 vs headless `claude -p`)

| 기준 | A. 메인 세션 + `/stage-run` + Agent 도구 (추천) | B. `pipeline_runner.py` 가 `claude -p` 서브프로세스 호출 |
|---|---|---|
| 사람 승인 | 같은 세션에서 "승인 <id>" → 훅 기록, 자연스러움 | 러너는 카드 승인 파일만 확인, 이후 무인 |
| 격리 | 서브에이전트 컨텍스트 분리 + 경로 훅. 프로세스·cwd 는 메인과 공유 | 프로세스·cwd(=worktree) 완전 분리, `--allowedTools`·`--permission-mode dontAsk`·`--permission-prompts none` 으로 권한 봉인 |
| 상한 | 서브에이전트 `maxTurns` | `--max-turns`, `--max-budget-usd`(print 전용) |
| 결과 수신 | 에이전트 최종 메시지 + SubagentStop 훅 | `--output-format json` 의 `result`/`structured_output`(`--json-schema`), 종료코드 |
| 피어 문제(R2) | 해당 없음(같은 세션 권한) | 해당 없음(러너가 `--settings` 로 권한 지정) |
| 비용 | 사용자 Claude Code 사용량(구독) | 동일(비 `--bare`). `--bare` 는 `ANTHROPIC_API_KEY` 필요 = 유료 API 과금 |
| 위험 | 메인 컨텍스트에 결과 요약만 쌓임(메모리 규칙 "메인은 지휘만"과 일치) | 무인 실행 중 분류기 fallback 시 "행동은 안 하고 계속 진행"(문서) → 결과 검증 필수. 프로젝트 hooks 가 `-p` 에서도 실행됨(비 bare) |
| 구현량 | 에이전트 md 2개 + 스킬 1개 | 러너에 프로세스 관리·타임아웃·SIGTERM(143) 처리 추가 |

**추천: A 를 기본(P2~P3), B 는 P4 선택.** 이유: (1) 사람 승인 1회를 같은 세션에서 결정론적으로 받기 쉬움, (2) 기존 메모리 원칙 "메인은 지휘만, 작업은 새 서브에이전트"와 동일, (3) 무인 `-p` 는 분류기 fallback 이 조용히 행동을 건너뛰므로 게이트가 완전히 갖춰진 뒤에 도입하는 게 안전. B 도입 시에도 LLM 단계만 `claude -p` 로 바꾸고 락·게이트·병합은 러너 그대로.

B 호출 형태(참고, P4):
```
claude -p "@<brief-path> 를 읽고 구현" --agent implementer --permission-mode dontAsk \
  --allowedTools "Read,Grep,Glob,Edit,Write,Bash(python -m ruff *),Bash(python -m pytest *)" \
  --max-turns 40 --output-format json --json-schema <schema> --name card-<id>
```
(cwd = `C:/work/wt-<id>`. `--settings` 로 `crossSessionInbound: "refuse"` 지정해 피어 메시지 차단 — cross-session-messaging 문서.)

### 7.1 피어 창 문제(R2) 대안

- 문서상 피어 메시지는 **동의·설정 변경 권한이 없다**(https://code.claude.com/docs/en/cross-session-messaging). 우회 시도 금지.
- 대체: 피어 창에 맡기던 작업은 (1) 메인 세션의 서브에이전트, 또는 (2) 러너가 띄우는 headless 프로세스로 옮긴다 — 둘 다 권한이 **사전에 파일(settings/allowedTools)로 정의**되므로 대화 중 승인이 필요 없다.
- 피어 세션을 계속 쓰려면: 필요한 권한을 사용자가 **사전에** 프로젝트/사용자 설정에 넣어두고, 피어에는 정보 전달("stage/x 병합됨, rebase 하라")만 보낸다. 참고: bypass 계열 세션은 기본적으로 피어 메시지를 hold(승인 대화상자) 한다.

---

## 8. 드라이런 — 오늘 흐름을 새 설계로 재생

| 오늘 사건 | 새 설계에서 발생 지점 | 차단/해결 방식 | 결과 |
|---|---|---|---|
| R1 verify 2회 동시 실행 | ⑨ 에이전트가 2번째 `verify_change.py` 실행 시도 | ① PreToolUse `guard_single_verify.py` 가 deny + "로그: data/ops/logs/verify_…log" ② 훅 우회(변수 등)해도 `pipeline_lock` 이 exit 4 | 2번째 실행 0회. 로그 오염 없음. 잔여 `verify_base_*` worktree 는 다음 실행 stale 복구가 정리 |
| R2 피어 창 거부 | 해당 단계 없음 | 피어 대신 서브에이전트(권한 사전 정의) | 발생 불가 |
| R3 컨벤션·명령 누락 | ① 카드 생성 | 표준 요구사항 C-RUFF/C-AFFECTED/C-GATES/C-VERIFY/C-REUSE 자동 주입 → ⑪ 대조기가 증거로 판정 | 누락 시 FAIL 로 표시, merge 진입 거부 |
| R4 map 34 vs 43 | ③ dryrun, ⑦ gate 의 layer_count | `ensure_fresh` 가 지문 불일치 감지 → 재빌드. 결과에 지문 기록 | 동일 트리 측정만 비교됨. 다른 트리면 표에 명시 |
| R5 긴 지시문 수작업 | ⑤ prepare | 카드 → `agent_brief.py` 브리프 자동 생성(브랜치·worktree·금지파일·게이트 명령 포함) | 사람 작성 0 |
| R6 worktree 삭제·프로세스 종료 차단 | ⑪ report 의 정리, ① 락 stale 복구 | 러너 1개 명령만 좁게 allow, 러너가 소유·병합 조건 검사 후 수행 | 분류기 대상 아님(§6.2 불확실성 1건 실측 필요) |
| R7 병합 순서 | ⑩ | state 가 `verified` + 체크리스트 FAIL 0 일 때만 `merge` 허용, merge 락 직렬, Claude 직접 `git merge` deny | 순서 위반 불가 |

예상 흐름 시간(참고): 사람 개입은 ④ 1회 + (push 시) ask 1회. 오늘처럼 단계마다 지시문 작성·재확인하던 왕복이 제거된다.

게이트 통과 예측(P1 기준): 신규 파일은 L2(`scripts/ops/`) 로 기존 게이트 스크립트와 같은 층, 역방향 import 없음(표준 라이브러리 + `ctypes` 만). `configs/module_registry.json` 에 신규 파일 등록 필요 → `registry_sync.py --fix` 로 정본 반영(skeleton_gate 요구).

---

## 9. 위험

| 위험 | 영향 | 완화 |
|---|---|---|
| 락 파일이 남아 파이프라인 정지 | 모든 verify 거부 | PID+생성시각 확인 후 자동 stale 복구, `pipeline_runner.py unlock --stale` |
| PID 재사용으로 살아있다고 오판 | 불필요한 대기 | 생성시각 비교 |
| 훅은 문자열 매칭이라 우회 가능(CLAUDE.md 가 guard_openai_call 에 대해 이미 인정) | 중복 실행 | 락이 코드 레벨 최종 방어선 |
| 승인 파일을 Bash 로 위조 | 무승인 진행 | deny 규칙 + 훅 감사 로그 교차확인. 완전 차단은 불가(문서: Bash 규칙은 보안 경계가 아님) → D4 |
| 무인 `-p`(P4) 에서 분류기 fallback 이 행동을 건너뛰고 계속 | "완료"로 오보 | 러너가 게이트·체크리스트로 결과를 재검증, 에이전트 자기보고 불신 |
| `python … *` allow 규칙이 auto 에서 정지될 가능성 | R6 미해결 | P1 직후 실측, 안되면 D2-b |
| implementer 가 메인 저장소를 편집 | WIP 오염 | 서브에이전트 frontmatter PreToolUse 경로 제한 + merge_stage 의 겹침 검사(기존) |
| 병합 자동화로 master 가 사람 확인 없이 변경 | 되돌리기 비용 | D3: 카드 승인에 병합 포함 여부 사용자 결정. push 는 항상 ask |
| 비용 | 사용량 증가 | agent_usage 기록 + 카드 budget, P4 에서는 `--max-budget-usd` |

---

## 10. 비용·정책

- 메인 세션·서브에이전트·비 bare `claude -p` 는 모두 **사용자의 Claude Code 사용량(구독 한도)** 을 소비한다. `--output-format json` 의 `total_cost_usd` 는 클라이언트 추정치(headless 문서).
- `--bare` 는 구독 로그인을 쓰지 않고 `ANTHROPIC_API_KEY` 를 요구(headless 문서) → **종량 유료 API 과금**. Agent SDK 도 문서상 API 키 인증 권장.
- CLAUDE.md "외부 유료 AI API 호출 승인제"의 대상은 앱 런타임의 OpenAI 등 **외부 유료 API 호출**이다. 개발 도구로서의 Claude Code 사용은 현재 이 규칙 대상이 아닌 것으로 해석하되(지금도 서브에이전트를 사용 중), **무인 `claude -p` 반복 실행과 `--bare`/SDK(API 키) 사용은 과금 구조가 달라지므로 사용자 결정 D1 로 둔다.**
- `guard_openai_call.py` 훅은 `-p` 세션에서도 프로젝트 hooks 로 실행된다(비 bare) — 러너가 띄운 에이전트도 같은 차단을 받는다.

---

## 11. 단계별 도입 계획 (§13 근본 문제 해결책 통합본)

| 단계 | 내용 | 영향 파일 (레이어) | 예상 diff | 효과 |
|---|---|---|---|---|
| **P0 보안 즉시** (승인 즉시, 코드 변경 최소) | CLAUDE.md 의 YouTube API 키 원문 제거 → `.env` 참조로 대체, GCP 에서 키 재발급(히스토리에 남음), `commit_checklist.py` 에 Google API 키 패턴 추가 | `CLAUDE.md` 1줄, `.githooks/commit_checklist.py` +1줄 | 2줄 | 비밀 노출 중단(G2) |
| **P1 락·신선도·Python 3.11 게이트** (즉시, 추천 1순위) | `pipeline_lock.py` 신규, verify_change/merge_stage 에 락 획득·토큰 재진입, `guard_single_verify.py` 훅, `freshness.py` 신규 + build/layer_count/query/agent_brief 호출. **+ 3.11 인터프리터 import 스모크·핵심 테스트 게이트**(G1) | 신규 `scripts/ops/pipeline_lock.py`(L2, ~120줄), `scripts/ops/guard_single_verify.py`(L2, ~50줄), `scripts/ops/code_map/freshness.py`(L2, ~60줄), `scripts/ops/py311_gate.py`(L2, ~80줄), 테스트 3개(L11, ~160줄). 수정: `verify_change.py` +8줄(+3.11 항목 1개), `merge_stage.py` +10줄, `build.py` +6줄, `layer_count.py`/`query.py`/`agent_brief.py` 각 +2줄, `.claude/settings.json` PreToolUse 1항목, `configs/verify_change.json` 에 `py311` 경로, `configs/module_registry.json` 등록 | 약 +500줄 / 기존 로직 변경 없음 | R1·R4·G1 해결 |
| **P2 카드·러너·권한·기준선** | 카드 스키마, 표준 요구사항 정본, `pipeline_runner.py`, `checklist.py`, 승인 훅, 권한 규칙. **+ 테스트 실패 기준선 정본**(G3) **+ 문서 전용 규칙 강제화 1차**(G4: 병렬 금지·git merge·메일/발행 guard) | 신규 `scripts/ops/pipeline_runner.py`(L6, ~300줄), `scripts/ops/pipeline/checklist.py`(L2, ~150줄), `scripts/ops/pipeline_approve_hook.py`(L2, ~50줄), `configs/pipeline_standard_requirements.json`(L1), `configs/test_baseline.json`(L1), 테스트 3개. 수정: `.claude/settings.json` permissions + UserPromptSubmit 1항목, `post_edit_fast_gate.py` 기준선 참조 +10줄 | 약 +800줄 | R3·R5·R6·R7·G3·G4 해결 |
| **P3 에이전트·스킬·CLAUDE.md 분할** | `spec-writer.md`, `implementer.md`(`maxTurns` 실제 설정), `/stage-run`, `/card-new`, SubagentStop 기록 훅. **+ CLAUDE.md 분할**(G2, 사용자 승인 대상) **+ 로깅 표준화**(G6) **+ 의존성 잠금**(G7) | `.claude/agents/` 2개, `.claude/skills/` 2개+사이트 스킬 3~4개(EUM·네이버·유튜브·Electron), `.claude/rules/` 신규, `CLAUDE.md` 703→~180줄, 로깅 10개 파일, `requirements.lock`(또는 `pylock.toml`) | 문서 이동 위주 | 흐름 전체 자동, 규칙 준수율 상승 |
| **P4 (선택) headless** | 러너에 `run-agent --headless` 추가(`claude -p`), 무인 배치 | `pipeline_runner.py` +~120줄 | — | 무인 실행. D1 결정 후 |

각 단계는 본 문서 규약대로 별도 카드·기준서·드라이런·승인을 거친다(P1 은 P2 러너 없이 기존 방식으로 진행). 단계 후 게이트: `codebase_layer_audit.py`, `test_codebase_layer_audit.py`, `quality_gate.py --staged --enforce --allow-existing-code-change`, `verify_change.py`.

보안/DB/API 영향: 없음(운영 DB·API 응답 key·스키마 변경 없음, secret 미취급). 권한 설정 변경은 있음 → D2.

---

## 12. 사용자 결정 항목과 추천

| # | 결정 | 선택지 | 추천 |
|---|---|---|---|
| D1 | 무인 headless(`claude -p`) 도입과 과금 | (a) 도입 안 함 (b) 구독 사용량으로 `-p` 도입(비 bare) (c) API 키(`--bare`/SDK) | **(a) 로 시작, P3 안정화 후 (b) 검토.** (c) 는 유료 API → 승인제 적용 |
| D2 | 권한 | (a) 좁은 allow(§6.2) (b) 사용자 `autoMode.allow` 추가 (c) bypass 기동 (d) 무효인 `defaultMode: bypassPermissions` 줄 정리 여부 | **(a) + 실측 후 필요 시 (b). (c) 비추천. (d) 는 오해 방지를 위해 정리 추천** |
| D3 | 카드 승인에 "verify PASS 시 로컬 master 병합" 포함 | (a) 포함 (b) 병합 전 별도 확인 | **(a)** — push 는 항상 ask 로 별도 |
| D4 | 승인 위조 잔여 위험 수용 | (a) deny 규칙+감사 로그로 수용 (b) 승인을 git 서명 태그 등으로 강화 | **(a)** (1인 개발 환경, 에이전트가 의도적으로 위조할 동기 없음) |
| D5 | 피어 창 사용 | (a) 지휘 용도 중단, 정보 전달만 (b) 계속 사용 + 권한 사전 설정 | **(a)** |
| D6 | `verifier` 에이전트 | (a) 만들지 않음(러너가 결정론적으로 수행) (b) haiku 요약 에이전트 | **(a)** |
| D7 | 착수 범위 | P1 만 / P1~P2 / P1~P3 | **P0·P1 즉시 착수**(비밀 노출 중단 + 오늘 오류 2건 + 3.11 검증 공백), P2·P3 는 각 기준서 승인 후 |
| D8 | Python 버전 정합(G1) | (a) 로컬에 3.11 설치 + 3.11 게이트 (b) 서버 이미지를 3.12 로 올림(로컬 3.12 이미 설치됨) (c) 서버를 3.14 로 올림 | **(a) 먼저**(운영 무변경, 검증 공백만 제거). 3.11 설치 방법(python.org 설치본 vs `py` 런처 관리) 결정 필요. (b)/(c) 는 별도 배포 카드 |
| D9 | CLAUDE.md 분할·이동(G2) | (a) 사이트 운영자료 → 스킬·`.claude/rules/`(경로 한정) 이동, 본문 ~180줄 (b) `@import` 로만 분리 (c) 유지 | **(a)**. (b) 는 문서상 import 도 시작 시 전부 로드되어 분량 문제 해결 안 됨. **사용자 승인 대상** |
| D10 | YouTube API 키(G2) | (a) CLAUDE.md 에서 제거 + GCP 키 재발급 (b) 제거만 | **(a)** — git 히스토리(커밋 5977212e 이후)에 남아 있으므로 제거만으로는 불충분 |
| D11 | 상시 실패 277건(G3) | (a) 기준선 정본화 + 매주 N건 소각 카드 (b) 일괄 격리(skip) | **(a)**. 일괄 skip 은 결함을 숨김 |
| D12 | 의존성 잠금 방식(G7) | (a) `pip freeze` 기반 `requirements.lock`(==, 선택적으로 `--hash`) (b) `pylock.toml`(PEP 751) | **(a)** — pip 문서에 있는 방식. pylock.toml 은 규격만 확정, pip 지원 여부는 확인한 문서에 없음 |

---

## 13. 근본 문제 진단 (공식 best-practices 대조)

> 근거 문서: Anthropic — https://code.claude.com/docs/en/best-practices , https://code.claude.com/docs/en/memory , https://code.claude.com/docs/en/hooks ; Python — https://docs.python.org/3/whatsnew/3.14.html , https://docs.python.org/3/howto/logging.html , https://docs.python.org/3/howto/logging-cookbook.html , https://packaging.python.org/en/latest/specifications/pylock-toml/ , https://pip.pypa.io/en/stable/topics/repeatable-installs/ .
> 실측은 2026-09-26 이 저장소(HEAD `bce62baa`) 기준. 문서에 없는 주장은 넣지 않았다.

### 13.1 문제별 대조표

| # | 공식 권장 (URL · 요지) | 우리 현황 (실측) | 영향 | 해결책 (파일·장치) | 작업량 | 우선 |
|---|---|---|---|---|---|---|
| **G1 로컬↔운영 Python 불일치** | whatsnew/3.14: 주석 지연 평가(PEP 649/749 — 정의 시점 `NameError` 가 안 남), `except A, B:` 괄호 없는 문법(PEP 758), t-string(PEP 750), `finally` 안 제어흐름 SyntaxWarning(PEP 765) 등 **3.14 에서만 통과하는 코드가 생길 수 있는 변경** 포함 | 로컬 `python --version` = **3.14.3**, `py -0p` 에 3.14·3.12 만 있고 **3.11 없음**. 운영 `Dockerfile:1` = `FROM python:3.11-slim`. `configs/ruff.toml:5` `target-version = "py311"`. 테스트·verify 는 전부 3.14 에서만 실행 → **3.11 실행 검증 0**. 3.12+ 전용 API 사용 0건(메인 grep 실측; 본 작성 중 `itertools.batched`·`typing.override`·`type X =`·제네릭 클래스 문법 재확인 0건) | 3.14 에서만 되는 코드(특히 주석 전방참조)가 운영 배포 후에야 터짐. ruff py311 은 문법 일부만 잡고 런타임 차이는 못 잡음 | `scripts/ops/py311_gate.py`(신규 L2): 3.11 인터프리터로 ① 바뀐 파일 `py_compile` ② LIVE 모듈 import 스모크(verify_change 의 LIVE import 목록 재사용) ③ 핵심 테스트 소수(`configs/verify_change.json` 의 `py311_tests`). verify_change 항목 10 "3.11 import 스모크"로 편입 → merge_stage 가 자동 강제. 3.11 인터프리터가 없으면 조용히 통과하지 않고 **"미검증" 표시 + 카드 체크리스트 FAIL** | 소(~80줄+설정) + 3.11 설치 | **P1 최상** |
| **G2 CLAUDE.md 비대화 + 비밀 원문** | memory: *"target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence"*, 경로 한정 `.claude/rules/` 권장, **`@import` 한 파일도 시작 시 로드되어 컨텍스트에 들어감**. best-practices: *"Bloated CLAUDE.md files cause Claude to ignore your actual instructions!"*, 가끔만 필요한 도메인 지식은 스킬로, 제외 목록에 "Information that changes frequently" | `CLAUDE.md` **703줄 / 36,856바이트**(권장의 3.5배). 사이트별 운영자료 **376~703행 = 328줄(47%)**: EUM 현장표·추출법 376~510(135줄), 네이버 OpenAPI 511~602(92줄), YouTube OAuth 603~663(61줄), 포트·Electron asar 664~703(40줄). **617행에 YouTube Data API 키 원문**(값 미인용 — 보안 보고 대상). 현 `.githooks/commit_checklist.py` 비밀 패턴은 Anthropic·OpenAI·AWS·GitHub·개인키만, **Google API 키 패턴 없음** → 커밋 `5977212e` 로 통과해 히스토리에 남음 | 규칙 준수율 저하(오늘 R3 와 같은 계열), 매 세션 토큰 낭비, **비밀 노출(작업트리·히스토리)** | P0: 617행 값 제거 → "`.env` 의 `YOUTUBE_DATA_API_KEY` 참조", GCP 키 재발급, commit_checklist 에 Google 키 패턴. P3: EUM/네이버/유튜브/Electron 절 → 각 스킬(`.claude/skills/<domain>-ops/SKILL.md`), 경로 한정 가능한 코드 규칙 → `.claude/rules/*.md`(`paths:`), 본문 ~180줄 목표. `@import` 분리는 분량 해결책이 아님(문서) | P0 소 / P3 중 | **P0 최상** / P3 |
| **G3 검증은 있으나 기준선이 흐림** | best-practices: *"Give Claude a check it can run"*, 성공 주장 대신 증거, *"If you can't verify it, don't ship it"* | `data/impact/HANDOFF.md:59~62` 최근 verified 4건 모두 **영향 테스트 실패 277(263~265파일) / LIVE import 실패 12 / 수집 오류 1 / 모듈 순환 75** 가 기준=변경 후. verify_change 는 실패 테스트 id **집합 차이**(`verify_change.py:255, 394~396`)로 새 실패를 가려내므로 병합 판정은 가능하나, 빠른 게이트·에이전트·사람은 277건 속 새 실패를 구분 못 함. "약 96% 통과" 인식과 대조할 **정본 수치 파일 없음** | "원래 실패" 속에 새 실패가 묻힘, 완료 보고 증거력 약화 | `configs/test_baseline.json`(신규 L1): 실패 테스트 id·사유·등록일. 병합 PASS 시 러너가 갱신(감소만 허용, 증가는 FAIL). `post_edit_fast_gate.py`·`stop_fast_verify.py` 출력을 "기존 실패 N / **새 실패 M** / 통과율 x%"로. 소각 카드 주 N건 | 중 | P2 |
| **G4 문서에만 있는 규칙** | best-practices: *"Unlike CLAUDE.md instructions which are advisory, hooks are deterministic and guarantee the action happens"*, 잘 지켜지는 규칙은 지우거나 *"convert it to a hook"*. memory: CLAUDE.md 는 *"context, not enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook"* | §13.2: 완전 강제 10 · 부분 7 · **문서 전용 8** | 오늘 R1·R7 같은 위반 반복 | §13.2 "강제 장치" 열 — P0(비밀), P1(verify 동시실행·map 신선도), P2(절차·병렬·직접 merge·전체 pytest·메일/발행·운영 DB), P3(나머지) | 중 | P0~P3 |
| **G5 kitchen-sink 세션·WIP 혼재** | best-practices: 무관한 작업 사이 `/clear`, *"After two failed corrections, /clear and write a better initial prompt"*, 세션을 작업흐름별로 이름 붙여 분리, 조사는 서브에이전트로 | 기존: `tools/hooks/session_guard.py`(기록 **크기** 기반 새 세션 강제·HANDOFF 주입, 설계 `2026-09-24_session_handoff_guard.md`) — 주제 혼재·반복 수정은 못 봄. `HANDOFF.md:66` "미커밋 변경 총 739개", 현 `git status` 77항목(추적 변경 17: marketing-standalone·youtube-analyzer·naver·smartstore 테스트 등 서로 다른 작업)이 메인 작업트리에 혼재. 같은 수정 반복 횟수 카운터 없음 | 컨텍스트 오염, WIP 가 작업트리 모드 verify·merge_stage 겹침검사를 흐림 | 카드 1 = worktree 1 = 에이전트 1(§4). SessionStart 주입을 "활성 카드 요약"으로 한정. 카드 history 로 **같은 게이트 FAIL 2회 → 러너가 새 implementer(새 컨텍스트)로 교체**(문서의 "2회 실패 후 /clear"를 코드로). 메인 WIP 는 카드로 흡수 또는 정리 목록화 | 중 | P2~P3 |
| **G6 계획 없는 구현 / 과도한 탐색** | best-practices: *"Explore first, then plan, then code"*, 단 *"If you could describe the diff in one sentence, skip the plan"*, 무한 탐색은 범위 축소 또는 서브에이전트 | CLAUDE.md 는 1줄 수정 외 모든 변경에 기준서·드라이런 요구(소규모엔 과잉)인데 강제 장치는 없음. `configs/agent_roles.json` 의 `max_tool_calls`(implement 40, review 25)는 **`.claude/agents/code-reviewer.md` 에 `maxTurns` 로 반영되지 않음** → 상한이 문서값 | 계획 없는 구현, 또는 탐색으로 컨텍스트 소진 | "diff 한 문장" 카드는 spec 생략 경로(러너 `--quick`, 체크리스트 동일 적용). 모든 에이전트 frontmatter 에 `maxTurns` 를 agent_roles 값으로 실제 설정(sub-agents 문서 필드) | 소 | P3 |
| **G7 사람이 손으로 쓰는 지시문** | best-practices: 자기완결 스펙(파일·인터페이스·범위 밖·종단 검증), 반복 워크플로는 스킬 | §1 R3·R5 | 누락·오타 | §5.1 카드 + 표준 요구사항 정본 + `agent_brief.py` 자동 브리프 + `/card-new` | (§11) | P2 |
| **G8 기준선 신선도** | best-practices: 검증은 Claude 가 읽을 수 있는 pass/fail 신호여야 함 | `build.py:151~158` meta 에 짧은 커밋만(작업트리 반영 없음), `layer_count.py:54` 무검증 로드 → R4(34 vs 43). 테스트 기준선 파일 없음(G3) | 틀린 수치로 판단 | §5.3 지문 + `ensure_fresh`, G3 기준선 | (§11) | P1 |
| **G9 로깅 비표준** | logging HOWTO: 모듈마다 `logging.getLogger(__name__)`, `basicConfig()` 는 로깅 호출 **전에** 앱 시작 시, 라이브러리는 `NullHandler` 외 핸들러·루트 로거 사용 금지, 신규 앱은 `dictConfig()` 권장. Cookbook: 다중 모듈 로깅 패턴 | `logging.basicConfig` **10개 파일**(예 `core/agent_runtime/agent.py:339`, `scripts/cdp_daemon.py:53`, `scripts/eum_send_mail_batch.py:116`, `scripts/hanafax/bulk_send.py:24`, `tools/hooks/hook_check_a4.py:19`; 메인 보고 9곳과 1곳 차이 — 본 작성 시 재실측), `getLogger(__name__)` 121개 파일, 문자열 이름 로거 13개 파일. 서버는 이미 `ai_orchestrator/logging_setup.py` 의 `setup_logging()` 진입점 사용(`server.py:10,41`). `ai_orchestrator/` 내 `print(` 343건. 성숙도 로깅 점수 2.0(메인 제공) | 형식·레벨·출력처 제각각 → 장애 추적 곤란 | 설정 진입점 1곳: 기존 `logging_setup.py` 재사용(신규 중복 금지), CLI 스크립트는 `main()` 에서 1회 호출, 모듈은 `getLogger(__name__)` 만. quality_gate 에 **신규** `basicConfig` 추가 차단 규칙(기존 10곳은 소각 목록) | 중 | P3 |
| **G10 의존성 비고정** | pip "Repeatable installs": `==` 고정, `pip freeze` 로 전이 의존성 포함 고정, `--hash` 해시 검증. packaging: `pylock.toml`(PEP 751, 2025-04 승인)은 재현 설치용 잠금 규격 | `requirements.txt` 32줄 중 `>=` 28 / `==` 4, 잠금 파일 없음. `Dockerfile` 은 `pip install -r requirements.txt` → **빌드마다 버전이 달라질 수 있음**, 로컬(3.14)·서버(3.11) 설치 결과도 다를 수 있음 | 로컬 통과·운영 실패, 재빌드 시 예고 없는 업그레이드 | `requirements.txt`(범위, 사람이 편집) + **`requirements.lock`**(3.11 환경에서 `pip freeze`, `==`, 선택적 `--hash`) 이원화, Dockerfile 은 lock 설치. 생성은 G1 의 3.11 환경에서. 갱신은 카드로만 | 소~중 | P3 |

### 13.2 문서 전용 규칙 목록 (CLAUDE.md "금지/STOP/필수" 대조)

| 규칙 (CLAUDE.md) | 강제 여부 (실측) | 강제 장치 제안 | 단계 |
|---|---|---|---|
| 유료 외부 AI API 사전 승인 | 강제: PreToolUse `guard_openai_call.py`(ask). 문자열 매칭 한계는 CLAUDE.md 가 자인 | 유지 | — |
| 수동 실행 요청 표현 금지 | 강제: Stop `behavior_gate.py` 정규식 | 유지 | — |
| claude-in-chrome 금지 | 강제: `guard_force_cdp.py` | 유지 | — |
| 인스타·유튜브 발행/업로드 재확인 | 강제: `guard_instagram_publish.py`, `guard_youtube_upload.py` | 유지 | — |
| 로컬 Docker CLI 금지 | 강제(커밋): quality_gate `NO_LOCAL_DOCKER_CLI` | 유지 | — |
| 보안 패턴·FORBIDDEN_IMPORT·순환 | 강제(커밋): quality_gate / pre-commit | 유지 | — |
| 지도↔골격 대조 | 강제(커밋): `skeleton_gate.py` | 유지 | — |
| vision_extract.py 차단 | 강제: 코드 `RuntimeError` | 유지 | — |
| 병합 전 verify PASS | 강제(merge_stage 경유 시) | 아래 직접 merge 항목 참조 | — |
| 신규 파일 정본 등록 | 강제(커밋): skeleton_gate | 유지 + 카드 `layer` 필드 | — |
| 세션 파기 코드 금지 | 부분: pre-commit 이 staged `.py` 추가 줄만 검사(`install_git_hooks.py:55~75`). **실행 시점 명령은 미검사** | PreToolUse(Bash\|PowerShell) 에 같은 패턴 | P2 |
| Claude 의 직접 `git merge` | 부분: 무방비(merge_stage 우회 가능) | `permissions.deny` `Bash(git merge *)`(§6.2) | P2 |
| secret 원문 금지 | 부분: 코드 패턴만, **CLAUDE.md 자체가 뚫림**(G2) | commit_checklist Google 키 패턴 | **P0** |
| 작업 후 게이트 3종 | 부분: 커밋 훅이 quality_gate·skeleton 실행, `codebase_layer_audit.py`·그 테스트 단독 실행은 문서 | 러너 gate 단계(§5.6) | P2 |
| capability_check 선행 | 부분: `prewrite_capability_check.py`(Write 시) | 카드 spec 체크리스트 | P2 |
| 전체 pytest 금지 | 부분: 빠른 게이트는 영향 테스트만, Claude 의 직접 `pytest` 는 무방비 | PreToolUse: 대상 없는 `pytest` deny + `query.py tests-for` 안내 | P2 |
| 외부 발행 재확인(인스타·유튜브 외) | 부분: 블로그·카페 guard 없음 | `guard_publish_send.py`(기존 guard 패턴 복제) | P2 |
| **verify 동시 실행 금지** | 문서 전용 | 락 + 훅(§5.2) | **P1** |
| **map.json 최신 기준 측정** | 문서 전용(규칙 자체도 없음) | `ensure_fresh`(§5.3) | **P1** |
| **3.11 운영 환경 검증** | 문서 전용(규칙 자체도 없음) | `py311_gate.py`(G1) | **P1** |
| 기준서 → 드라이런 → 승인 | 문서 전용 | 카드 state + UserPromptSubmit 승인 기록(§5.8) | P2 |
| 병렬 금지(git·DB·배포·같은 파일) | 문서 전용 | 러너 락 확장 + implementer 경로 훅 | P2 |
| 메일·메시지 전송 재확인 | 문서 전용 | `guard_publish_send.py` 에 메일·팩스 발송 스크립트 포함 | P2 |
| 운영 DB write·schema 변경 승인 | 문서 전용(커밋 시 코드 패턴 일부) | PreToolUse: 운영 DB 접속·마이그레이션 명령 ask | P2 |
| 삭제된 스크립트 복구 금지 | 문서 전용 | quality_gate 금지 경로 목록 | P3 |

집계: 완전 강제 10 · 부분 7 · 문서 전용 8.

### 13.3 근본 문제 상위 5 (우선순위순)

1. **G1 Python 3.14↔3.11** — 운영 인터프리터 검증 0 → P1 `py311_gate.py` 를 verify_change 항목으로 편입(3.11 설치 D8).
2. **G2 CLAUDE.md 703줄 + API 키 원문** — 준수율 저하·비밀 노출 → P0 키 제거·재발급·패턴 추가, P3 사이트 자료를 스킬/rules 로 이동(D9 사용자 승인).
3. **G4 문서 전용 규칙 8건(+부분 7건)** — 오늘 R1·R7 의 원인 → P1 락·신선도·3.11, P2 훅·deny 규칙 전환.
4. **G3 상시 실패 277건의 기준선 부재** — 새 실패가 묻힘 → P2 `configs/test_baseline.json` + 게이트 출력 "새 실패 M".
5. **G5/G7 kitchen-sink WIP + 수작업 지시문** — 컨텍스트 오염·누락 → P2~P3 카드=worktree=에이전트 1:1, 같은 FAIL 2회 시 새 컨텍스트 교체.

(G9 로깅·G10 의존성 잠금은 P3. G10 은 G1 의 3.11 환경이 선행 조건.)
