# 상시 작업기록 + 새 세션 강제 (2026-09-24)

```yaml
spec:
  id: session-handoff-guard
  status: planned
  files:
    add:
      - tools/hooks/session_guard.py
      - tools/hooks/session_handoff.py
      - configs/session_guard.json
```

## 결정 (사용자 지시)
"상시 작업기록을 저장하고, 사용자에게 새로운 세션을 강제하자." — 토큰 효율 구조(docs/specs/2026-09-24_token_efficient_architecture.md §8 단계=세션 경계)의 강제 장치.

## 실측
이 세션 기록 14.7MB(중간 압축 1회 후), 과거 세션 최대 132MB. 긴 세션은 매 응답마다 누적 맥락을 다시 읽어 비용이 커지고, 압축 요약으로 세부가 흐려진다.

## 1. 상시 작업기록 (사람·AI 기억에 의존하지 않음)
| 언제 | 무엇 | 어디 |
|---|---|---|
| 모든 커밋(git post-commit 훅) | 커밋 해시·제목·바뀐 파일 수·브랜치·시각 1줄 | `data/ops/worklog.jsonl` |
| 병합·검증(merge_stage/verify_change) | 판정 표 요약 1줄 | 같은 파일 |
| 세션 종료 직전(Stop 훅)·압축 직전(PreCompact 훅) | `session_handoff.py` 가 인계 파일 갱신 | `data/impact/HANDOFF.md` |
인계 파일 내용(자동 생성, AI 작성 아님): 이번 세션 커밋 목록 · 열린 작업 브랜치/worktree · 상태 building/planned 기준서 · 마지막 검증 결과 · 미커밋 변경 목록 · "다음 할 일"(기준서·메모리의 대기 항목에서 추출).

## 2. 새 세션 강제 (UserPromptSubmit 훅 `session_guard.py`)
| 조건 | 동작 |
|---|---|
| 세션 기록 ≥ 경고선(기본 8MB) | 입력은 통과, AI 에게 "[세션 경고] ... 진행 중 서브에이전트를 마무리(새 투입 금지)하고 작업기록 저장 후 사용자에게 /clear 안내." 주입 |
| 세션 기록 ≥ 차단선(기본 12MB) **또는** 단계 완료 표시(`data/impact/PHASE_DONE`) | **입력 차단** + 사용자에게 안내: "세션 한도 도달 — 작업기록 저장 완료: data/impact/HANDOFF.md. 진행 중인 서브에이전트가 없으면 이 창에서 /clear 입력 후 '인계 이어서'라고 입력하세요." 차단 직전 인계 파일 자동 갱신 |
| 비상 우회 | 입력 맨 앞 `!계속` — 1회 통과, 우회 기록 남김 |
임계값은 `configs/session_guard.json`(경고·차단 MB, 우회 문구). 메인 저장소 기준으로 기록.

새 세션을 여는 대신 같은 창에서 `/clear` 를 쓰는 이유: 새 창을 열면 그 창의 대화 맥락이 끊겨 사용자가 다시 설명해야 하지만, `/clear` 는 같은 세션 안에서 대화 기록만 비우고 `SessionStart`(source=`clear`) 훅이 곧바로 `HANDOFF.md` 요약을 재주입한다. **`/clear` 는 사용자가 직접 입력해야 한다** — AI 가 대신 트리거할 수 없다. 또한 **진행 중인 서브에이전트가 있으면 /clear 하지 않는다**(서브에이전트 결과가 메인 세션에 돌아올 곳이 없어져 유실됨) — 먼저 서브에이전트를 마무리하거나 핸드백을 받은 뒤에 안내한다.

### 차단 순서 (사용자 지시: "새 세션을 하라고 지시하기 전에 작업기록을 저장")
1. `session_handoff.py` 실행 → HANDOFF.md·worklog.jsonl 저장
2. **저장 확인**(파일 존재·갱신 시각·필수 절 존재) — 실패하면 차단하지 않고 "저장 실패" 경고만(기록 없이 세션을 끊지 않는다)
3. 확인 통과 후에만 입력 차단 + `/clear` 안내(인계 파일 경로 포함)

## 3. 새 세션 자동 시작 (SessionStart 훅)
`SessionStart` 는 `source` 값이 `startup`(새 창) · `resume`(`--resume`) · `clear`(`/clear` 직후) 셋 다 대상 — `HANDOFF.md` 가 최근 것이면 요약을 AI 맥락에 자동 주입 → 사용자가 설명하지 않아도 이어서 시작. 이어간 뒤 `PHASE_DONE` 해제. (`compact` 등 다른 source 는 대상 아님 — no-op.)

## 4. 새 작업 시작 시 불필요 문서 정리 (사용자 지시)
새 세션이 인계 파일로 시작되면 `session_handoff.py --start` 가 이전 세션의 **쓸모없어진 산출물**을 정리한다. 기준은 규칙(설정 파일)으로, 판단이 필요한 것은 목록만 보고.
| 대상 | 규칙 | 처리 |
|---|---|---|
| 이전 인계 파일 | 이어받은 뒤 | 요점 1단락을 worklog.jsonl 에 남기고 삭제(최신 1개만 유지) |
| 이전 세션 임시 폴더(scratchpad: 시제품·분석 산출물) | 결과가 기준서·메모리·커밋에 반영된 것 | 삭제. 반영 안 된 것은 목록 보고 후 사용자 확인 |
| 병합 끝난 작업 브랜치의 worktree·로컬 브랜치 | verified/* 태그가 있는 것 | 삭제(태그로 복원 가능) |
| 검증 임시 폴더(verify_base_*) | 남아 있으면 | 삭제 |
| 기준서(docs/specs) | status superseded(대체됨) | 삭제(git 이력·대체 기준서로 추적). done/building/planned 는 3자 대조에 필요하므로 유지 |
| 메모리 작업기록 | 같은 주제의 오래된 작업기록 | 최신 기록에 요점 병합 후 삭제, MEMORY.md 목록 정리 |
| 미사용 문서(코드맵 DOC 중 어디서도 참조·언급 없음) | 판단 필요 | 목록만 보고 → 사용자 확인 후 삭제 |
- 삭제는 git 추적 파일이면 커밋(`[allow-delete]` + 복원 명령을 docs/deleted_code_index.md 에), 미추적이면 삭제 목록을 worklog.jsonl 에 기록.
- 로그인 세션·크롬 프로필·.env·data 의 업무 데이터는 정리 대상에서 **항상 제외**.

## 설정 위치
훅은 `.claude/settings.local.json`(이 PC 전용, 미추적) 에 등록 — `.claude/settings.json` 은 다른 작업분이 미커밋 상태라 건드리지 않는다. 공용 스킬(판매 키트)에는 설치 스크립트가 settings 에 등록하는 방식으로 포함.

## 깨뜨리기
기록 크기 임계값을 작게 낮춘 설정으로: 경고 주입 확인 → 차단·안내·인계 파일 생성 확인 → `!계속` 1회 통과·기록 확인 → 새 세션 SessionStart 주입 확인 → 원복.

## 영향
훅 3개 추가(PC 설정), 스크립트 2 + 설정 1. 앱 동작 영향 없음. 차단은 사용자 입력을 막는 강한 동작이라 우회 문구를 반드시 둔다.

## 롤백
settings.local.json 에서 훅 항목 제거.
