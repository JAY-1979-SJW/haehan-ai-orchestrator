# AI 코드 품질 게이트 — 기준서 + 드라이런 (2026-09-26)

> 이 문서만 신규 작성됨. 실제 `.claude/settings.json` / `.claude/agents/*` / `CLAUDE.md` 는
> **아직 수정하지 않았다** — 사용자 승인 후 별도 커밋에서 반영.

## 0. 요약

| 항목 | 결론 |
|---|---|
| 신규 코드 | 거의 없음 — 기존 `duplicate_code_check.py`, `code_map/query.py`, `verify_change.py`, `.githooks/pre-commit.orig`(ruff), `configs/ruff.toml`, `admin-web` tsc를 훅에서 재호출만 |
| 신규 파일 | `.claude/hooks/pre_edit_dup_check.py`, `.claude/hooks/post_edit_fast_gate.py`, `.claude/agents/code-reviewer.md`, CLAUDE.md 문단 추가 |
| 사용자 요구와 다른 점 | 3곳 — 아래 §5 "차이점" 참조. 근거: 실측 시간·기존 결함(#30 레거시 lint 오류)·Stop 훅 한계 |
| 실측 | ruff 1파일 0.55s / query.py tests-for 0.37s / admin-web tsc --noEmit 13.4s |
| 결정 필요 | 4건 — §7 |

---

## 1. 목적/범위

Claude가 신규 함수를 짤 때 (a) 이미 있는 유사 기능을 다시 짜는 것, (b) 검증 없이 "완료"라고
보고하는 것, 이 두 가지 사고를 **커밋 전에** 기계적으로 잡는다. 대상 레이어: L2(정책/훅) — 실행
코드가 아니라 Claude Code 하네스 설정과 가벼운 python 스크립트다. 업무 도메인 코드는 건드리지
않는다.

## 2. 영향 파일

| 경로 | 신규/수정 | 이유 |
|---|---|---|
| `.claude/settings.json` | 수정 | hooks 배열에 항목 추가 (기존 훅 순서·동작 보존, 병합만) |
| `.claude/hooks/pre_edit_dup_check.py` | 신규 | PreToolUse(Edit\|Write) 전용 — 기존 `prewrite_capability_check.py`는 Write 매처 1개뿐이고 "자동화/사이트" 키워드 기반 조회이지, Edit 대상이 아니고 함수/클래스명 매칭도 아님. 별개 스크립트가 필요 |
| `.claude/hooks/post_edit_fast_gate.py` | 신규 | ruff(변경분만, 기준선 대비 diff) + `code_map/query.py tests-for` 선별 실행 + (TS 변경 시) admin-web tsc를 얇게 오케스트레이션. 새 판정 로직은 없음 — 기존 3개 도구 호출만 |
| `.claude/agents/code-reviewer.md` | 신규 | 별도 컨텍스트 서브에이전트 정의 (Claude Code 표준 agent 파일 형식) |
| `CLAUDE.md` | 수정 | 기존 "작업 원칙" 절 아래 문단 추가(신규 섹션 만들지 않음 — 기존 "기준서→드라이런→승인", "게이트 실행 의무"와 중복 방지) |

기존 파일은 **수정하지 않는다**: `tools/hooks/duplicate_code_check.py`,
`tools/code_map/query.py`, `tools/verify_change.py`, `.githooks/pre-commit.orig`,
`configs/ruff.toml` — 그대로 재사용.

왜 `.claude/hooks/`인가 (기존 관례와 차이): 현재 저장소의 모든 훅 스크립트는 `scripts/ops/`에
있고 `settings.json`에서 절대경로로 참조한다(예: `guard_openai_call.py`). 이 관례를 따르는 것이
더 일관적이므로, 신규 파일도 **`scripts/ops/`에 둔다** (`.claude/hooks/`가 아님 — 위 표는 최초
초안이었고 조사 중 기존 관례를 재확인해 정정함). 최종 경로:

- `tools/hooks/pre_edit_dup_check.py`
- `tools/hooks/post_edit_fast_gate.py`

## 3. 각 훅 설계

### 3.1 PreToolUse(Edit|Write) — `pre_edit_dup_check.py`

입력: stdin JSON (`tool_input.file_path`, `tool_input.new_string`/`content`).
동작:
1. `new_string`(Edit) 또는 `content`(Write)에서 `def `/`class ` 신규 정의명을 정규식으로 추출.
2. 각 이름을 대상 파일과 같은 최상위 디렉터리(예: `ai_orchestrator/`, `scripts/naver/`)에서
   `Grep`과 동등한 파이썬 `re`로 검색 — **기존 `duplicate_code_check.py`의 본문 해시 비교는
   여기서 그대로 못 쓴다**(그건 사후 전체 스캔용, 여기는 편집 "전" 이름 매칭이라 다른 신호).
   `duplicate_code_check.py`는 이 훅과 별개로 세션 종료 시 1회 참고 실행만 유지.
3. 동일 이름이 대상 파일 외 2곳 이상에서 발견되면 `hookSpecificOutput.additionalContext`에
   경고 텍스트를 실어 반환(차단은 하지 않음 — 오탐이 잦은 신호라 Claude가 판단하도록 정보만 제공).
   Claude Code 훅 규약상 PreToolUse는 `permissionDecision: "ask"`로 차단도 가능하지만, 여기서는
   **차단하지 않고 컨텍스트만 주입**한다(과도한 차단은 흔한 이름(`main`, `run`, `handler`)에서
   작업을 막아버림).
- 타임아웃: 3초 (grep 범위가 좁아 실측 여유 충분 — §6).

### 3.2 PostToolUse(Edit|Write) — `post_edit_fast_gate.py`

입력: stdin JSON (`tool_input.file_path`).
동작 (파일 확장자별 분기):
- `.py`: `ruff check --config configs/ruff.toml <file>` 실행. **기준선 대비만 차단** — 결함 #30
  (레거시 lint 오류 다수)이 있으므로, `git show HEAD:<file>`을 임시로 ruff에 돌려 커밋 시점
  오류 집합을 구하고, 이번 편집 후 오류 집합과 **차집합(신규 오류)**만 실패로 취급. 이렇게 안
  하면 기존 오류가 있는 파일을 열기만 해도 무한 수정 루프에 빠진다(사용자 원 요구는 "lint 전체
  통과"였으나 결함 #30 때문에 기준선 방식으로 조정 — §5).
  - 신규 오류가 있으면 stderr에 오류 내용 출력 후 `exit 2` → Claude Code가 이 stderr를 컨텍스트로
    받아 스스로 고친다(공식 규약).
- `.py` 추가: `python -m tools.code_map.query tests-for <file>`로 매핑되는 테스트만 선별,
  최대 3개까지 `pytest -x -q <selected>` 실행(전체 스위트 21분+·행 걸림 결함을 피함). 매핑 테스트가
  0개면 스킵(전체 실행 강제하지 않음 — 전체는 커밋 훅/verify_change 담당).
- `.ts`/`.tsx`: admin-web 내부 파일이면 `npm run typecheck`(=`tsc --noEmit -p tsconfig.app.json`)
  1회 실행. 실측 13.4초 — 파일마다 매번 돌리면 누적 비용이 크므로 **직전 실행 후 5분 이내면
  스킵**(캐시 플래그 파일 `data/.post_edit_gate_tsc_cache`에 타임스탬프 기록).
- 타임아웃: 전체 20초 상한(ruff 1초 + pytest 선별 최대 3건 + tsc 조건부). 20초 초과 시 강제
  종료하고 "시간 초과 — 수동 확인 필요"만 경고(차단 아님) — Stop 훅에서 최종 확인하므로 여기는
  빠른 피드백이 목적.

### 3.3 Stop — 기존 `behavior_gate.py` 뒤에 체이닝

방법: 새 훅 항목을 추가하지 않고 `behavior_gate.py` 자체를 수정하는 대신(파일 보존 원칙),
Stop 배열에 **새 항목을 하나 더 추가**한다(`hooks` 배열은 여러 개 등록 가능, 기존 동작 안 건드림):
- `tools/hooks/stop_fast_verify.py` (신규, 위치는 `scripts/ops/` 관례 유지):
  1. `git status --porcelain`으로 이번 세션에서 바뀐 파일 목록만 추출.
  2. `.py` 있으면 ruff(기준선 diff) + 매핑 테스트(§3.2와 동일 로직, 중복 호출 시 결과 캐시 재사용).
  3. `.ts`/`.tsx` 있으면 tsc 1회(있으면 캐시 재사용).
  4. 상한 30초. 초과/실패 시 `decision: "block"` + `reason`에 실패 내용 — Claude가 계속 진행.
  5. **무한 루프 방지**: 입력 JSON의 `stop_hook_active`가 true면 무조건 통과(재차단 금지) —
     공식 규약 그대로 준수.
- **사용자 원 요구(Stop=전체 테스트/빌드 최종 확인)와의 차이**: 전체 pytest는 21분+이고
  `tests/test_local_agent_installer_package.py`에서 멈추는 결함이 있어 Stop 훅(매 응답 종료마다
  실행)에 넣으면 세션이 사실상 못 끝난다. 그래서 "세션에서 바뀐 파일 기준 빠른 게이트"로 축소.
  **전체 검증은 커밋 시점의 `verify_change.py`(이미 존재, 결함 목차 9항목)가 담당** — 이 둘의
  역할 분담을 CLAUDE.md 문단에 명시한다.

## 4. `.claude/agents/code-reviewer.md` 초안 전문

```markdown
---
name: code-reviewer
description: diff만 보고 중복 구현·테스트 존재/동작검증·과도한 추상화·보안/성능을 점검하는 독립 리뷰어. 작성 과정을 모르는 상태에서 결과물만 평가한다. 코드 변경 후 커밋 전에 사용.
tools: Read, Grep, Glob, Bash
model: sonnet
---

너는 이 변경을 작성하지 않았다. `git diff`(또는 전달된 diff)만 보고 아래를 판정한다.

## 점검 항목
1. **중복 구현** — 이 변경이 추가한 함수/클래스가 저장소 다른 곳에 이미 있는 기능을
   다시 짠 것인가. `tools/hooks/capability_check.py`, `tools/hooks/duplicate_code_check.py`
   결과를 참고해 확인한다.
2. **테스트 존재/동작 검증** — 이 변경에 대응하는 테스트가 있는가. 없다면 "테스트 없음"으로
   명시한다. 있다면 실제로 실행해 통과하는지 확인한다(주장만 보지 않는다).
3. **과도한 추상화** — 지금 요구사항 대비 불필요한 레이어/인터페이스/설정 옵션을 추가했는가.
4. **보안/성능** — secret 로깅, SQL 인젝션 가능성, N+1, 불필요한 전체 스캔/루프 등.

## 보고 등급
각 발견 항목에 다음 등급 중 하나를 붙인다:
- **CONFIRMED** — 실행/읽기로 직접 확인함(파일 경로·줄 번호 제시)
- **PLAUSIBLE** — 코드만 보고 판단, 실행 확인 못함(왜 확인 못했는지 명시)
- **NEEDS_INFO** — 판단에 필요한 정보 부족(무엇이 필요한지 명시)

## 금지
- diff에 없는 배경(왜 이렇게 짰는지)을 추측해서 정당화하지 않는다.
- 작성자 의도를 안다고 가정하지 않는다 — 결과물만 본다.
- 사소한 스타일(포맷)은 ruff/lint가 이미 잡으므로 언급하지 않는다.

## 출력 형식
```
## 중복 구현: [CONFIRMED|PLAUSIBLE|없음]
## 테스트: [CONFIRMED 통과|CONFIRMED 실패|테스트 없음]
## 과도한 추상화: [...]
## 보안/성능: [...]
## 종합 판정: PASS | WARN | FAIL
```
```

## 5. CLAUDE.md 추가 문단 초안 (기존 "작업 원칙" 절 하위, 신규 섹션 아님)

```markdown
## 코딩 컨벤션 및 완료 보고 기준 (2026-09-26 추가)

### 재사용 우선
새 함수/유틸을 만들기 전 `tools/hooks/capability_check.py`, `tools/hooks/duplicate_code_check.py`,
Grep으로 유사 기능이 있는지 먼저 확인한다. 있으면 재사용/import, 없을 때만 신규 작성.
검증 안 된 추측성 코드 금지 — 불확실하면 Grep/Read로 실제 시그니처·동작을 확인한 뒤 작성한다.

### 완료 보고 기준
**작업이 끝났다고 보고하기 전에 반드시 테스트를 실행하거나 빌드/타입체크를 통과시켜 증거를
확인할 것. 실행해보지 않은 코드를 '완료'로 보고하지 말 것.**

### 워크플로
복잡하거나 여러 파일에 걸친 작업은 Explore → Plan(Plan Mode) → Implement → Verify → Commit
순서로 진행한다. Verify 단계는 `tools/verify_change.py`(전체) 또는 세션 빠른 게이트
(ruff+영향 테스트, 바뀐 파일 기준)로 한다 — 전체 pytest는 21분+ 걸리고 멈추는 결함이 있어
매번 돌리지 않는다.

### 반복 실수(gotcha)
- 전체 `pytest` 실행 금지 — `tests/test_local_agent_installer_package.py`에서 멈춤. 영향 테스트만.
- ruff는 레거시 오류가 많은 파일이 다수 존재 — 새 훅은 "이번 편집으로 새로 생긴 오류"만 차단.
- Windows에서 훅은 셸 스크립트가 아니라 python 스크립트로 작성(기존 관례, PowerShell/cmd 차이 회피).
```

## 6. `.claude/settings.json` 예상 diff (요약, 실제 반영 안 함)

```diff
   "PreToolUse": [
     { "matcher": "Write", "hooks": [ ...기존... ] },
+    { "matcher": "Edit|Write",
+      "hooks": [ { "type": "command",
+        "command": "python \"...\\tools\hooks\pre_edit_dup_check.py\"",
+        "statusMessage": "중복 구현 가능성 검사 중..." } ] },
     { "matcher": "Bash|PowerShell", "hooks": [ ...기존 4개 그대로... ] },
     ...
   ],
   "PostToolUse": [
     { "matcher": "Write|Edit|NotebookEdit", "hooks": [ ...기존 log_code_change 그대로... ] },
+    { "matcher": "Edit|Write",
+      "hooks": [ { "type": "command",
+        "command": "python \"...\\tools\hooks\post_edit_fast_gate.py\"",
+        "statusMessage": "빠른 게이트(ruff+영향테스트) 실행 중..." } ] },
     { "matcher": "Write", "hooks": [ ...기존 hook_check_a4 그대로... ] }
   ],
   "Stop": [
     { "hooks": [ ...기존 behavior_gate 그대로... ] },
+    { "hooks": [ { "type": "command",
+        "command": "python \"...\\tools\hooks\stop_fast_verify.py\"",
+        "statusMessage": "세션 변경분 최종 게이트 확인 중..." } ] }
   ]
```
기존 PreToolUse `Write` 단독 매처(`prewrite_capability_check.py`)는 그대로 두고, 새 `Edit|Write`
매처를 별도 배열 항목으로 추가 — 같은 이벤트에 여러 matcher가 매치되면 Claude Code는 매치되는
모든 항목을 실행하므로 기존 동작과 충돌 없음.

## 7. 드라이런 (시뮬레이션, 파일 미수정)

시나리오: `ai_orchestrator/telegram_notifier.py`에 `def send_alert(...)` 함수를 새로 추가하는
Edit을 가정.

1. PreToolUse(Edit) → `pre_edit_dup_check.py`: `new_string`에서 `send_alert` 추출 →
   `ai_orchestrator/` 디렉터리 grep → 동일 이름 없음 → additionalContext 없이 통과. (예상 0.2초)
2. Edit 적용.
3. PostToolUse(Edit) → 기존 `log_code_change.py` 실행(변경 없음) → 신규
   `post_edit_fast_gate.py`:
   - ruff on `telegram_notifier.py`: 실측 0.547초, "All checks passed" (기존 오류 없음 확인됨).
   - `query.py tests-for telegram_notifier.py`: 실측 0.368초, 매핑 테스트 다수 검색됨(위 실행에서
     `test_backend_router_server_cycle_break_20260516.py` 등 확인). 상위 3개만 pytest -x -q 실행
     — 예상 5~15초(파일당 상이, 미실측이나 개별 테스트 파일이라 pytest 전체 21분과 무관).
   - `.ts` 아니므로 tsc 스킵.
   - 합계 예상 ~6~16초 — 20초 상한 내.
4. Stop → 기존 `behavior_gate.py` 통과(변경 없음) → `stop_fast_verify.py`: 세션 변경 파일 1개
   재확인(캐시로 ruff/테스트 재실행 스킵 가능) → PASS.

TS 시나리오(admin-web 파일 변경 가정): tsc --noEmit 실측 13.4초 — PostToolUse 20초 상한에
근접하므로, **5분 캐시**로 같은 세션 연속 편집 시 재실행 방지. 첫 편집만 13.4초 소요, 이후는
0초.

예상 게이트 통과: 신규 스크립트 자체는 기존 도구 재호출뿐이라 로직 결함 리스크는 낮음.
`FORBIDDEN_IMPORT`/`SECURITY_PATTERN`/`CIRCULAR_IMPORT` 해당 없음(신규 모듈이 상위 레이어
python 스크립트만 import).

사이드이펙트/위험:
- ruff `--fix` 없이 `check`만 실행(자동 수정 안 함) — Edit 직후 파일을 훅이 또 고치면 Claude의
  Edit 결과와 충돌 가능성 있어 자동 수정은 배제. 필요 시 Claude가 stderr 보고 직접 고침.
- pytest 선별 실행이 부작용 있는 테스트(외부 API 호출 등)를 우연히 포함하면 예상 밖 호출 위험
  → `tests-for`가 반환하는 목록에 `test_*live*`, `test_*e2e*` 같은 이름이 있으면 실제 실행에서
  **제외**하는 안전장치를 `post_edit_fast_gate.py`에 넣어야 함(구현 시 반영, 이 문서에 명시).
- tsc 캐시 파일(`data/.post_edit_gate_tsc_cache`)이 git에 커밋되지 않도록 `.gitignore` 확인 필요
  (기존 `data/`가 이미 대부분 gitignore 대상인지 구현 시 확인).

## 8. 동작 증명 테스트 계획 (사용자 승인 후 실행)

1. 실제 파일 1개(예: 로그/주석만 바뀌는 안전한 파일)에 Edit 수행 → PreToolUse 경고 유무 확인,
   PostToolUse 출력에 ruff/테스트 결과 포함 확인, 소요시간 로그.
2. 의도적으로 미사용 변수(ruff 신규 오류)를 넣은 Edit → PostToolUse가 `exit 2` + stderr로
   오류 내용 반환하는지 확인 → Claude가 스스로 고치는지 관찰.
3. `code-reviewer` 에이전트를 그 diff에 대해 1회 호출 → CONFIRMED/PLAUSIBLE 등급이 실제로
   나오는지, "테스트 없음"을 정직하게 보고하는지 확인.
4. Stop 훅이 세션 종료 시 위 변경분에 대해 재확인하고, `stop_hook_active=true` 재진입 시
   무한루프 없이 통과하는지 확인.

## 9. 사용자 결정 필요 항목

1. **pytest 선별 실행 범위** — `tests-for` 결과 상위 몇 개까지 자동 실행할지(현재 안: 3개).
   너무 적으면 놓치고, 많으면 PostToolUse가 느려짐.
2. **PreToolUse 중복 경고를 차단(ask)으로 할지 정보 제공(context)으로 할지** — 현재 안은
   차단 안 함(오탐 방지). 더 엄격히 하려면 특정 디렉터리(예: `scripts/naver/`)에서만 차단.
3. **tsc 캐시 유효시간(5분)** — 짧으면 매번 13초 대기, 길면 변경분 반영 안 된 상태로 통과 가능.
4. **code-reviewer 자동 트리거 여부** — 매 커밋 전 자동 실행(PreToolUse에 걸기)할지, 아니면
   사용자가 필요할 때 수동 호출(`Agent` 도구로)만 할지. 자동화하면 커밋마다 지연 발생.

---

## 부록: 조사 근거 (재사용 확인)

- `.claude/settings.json` 현재 hooks: `guard_openai_call.py`, `guard_cdp_new_tab.py`,
  `guard_instagram_publish.py`, `guard_youtube_upload.py`, `guard_force_cdp.py`(PreToolUse),
  `prewrite_capability_check.py`(PreToolUse Write), `log_code_change.py`, `hook_check_a4.py`
  (PostToolUse), `behavior_gate.py`(Stop), `install_git_hooks.py`(SessionStart).
- `.claude/agents/` 디렉터리 없음 (신규 생성 필요, 삭제/충돌 없음).
- `tools/hooks/duplicate_code_check.py` — 본문 해시 기반 사후 전체 스캔, PreToolUse 실시간
  이름 매칭과 목적이 달라 별도 스크립트 필요하나 세션 종료 시 참고용으로 그대로 재사용 가능.
- `tools/verify_change.py` — 9개 판정 항목 이미 구현(기준 커밋과 비교, 영향 테스트 포함).
  전체 검증은 이것을 그대로 쓰고 신규 로직 불필요.
- `tools/code_map/query.py tests-for` — 실측 0.368초, 파일→영향 테스트 매핑 이미 존재.
- `.githooks/pre-commit.orig` — ruff check --fix + format을 `configs/ruff.toml`로 이미 실행 중
  (커밋 시점). 훅은 세션 중 더 빠른 피드백을 주는 보완재.
- `admin-web/package.json` — `npm run lint`(next lint), `npm run typecheck`(tsc --noEmit -p
  tsconfig.app.json) 이미 존재. 실측 13.4초.
- 전체 pytest 21분+·멈춤 결함은 지시사항에 명시된 대로 실행하지 않음(재확인 없이 신뢰).
