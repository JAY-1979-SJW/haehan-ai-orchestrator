# 상시 작업기록 + 새 세션 강제 (2026-09-24)

```yaml
spec:
  id: session-handoff-guard
  status: planned
  files:
    add:
      - scripts/ops/session_guard.py
      - scripts/ops/session_handoff.py
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
| 세션 기록 ≥ 경고선(기본 8MB) | 입력은 통과, AI 에게 "인계 준비" 안내 주입 → AI 가 기록 저장·마무리 보고 |
| 세션 기록 ≥ 차단선(기본 12MB) **또는** 단계 완료 표시(`data/impact/PHASE_DONE`) | **입력 차단** + 사용자에게 안내: "세션 한도 — 인계 파일 저장됨(data/impact/HANDOFF.md). 새 세션을 열고 '인계 이어서'라고 입력하세요." 차단 직전 인계 파일 자동 갱신 |
| 비상 우회 | 입력 맨 앞 `!계속` — 1회 통과, 우회 기록 남김 |
임계값은 `configs/session_guard.json`(경고·차단 MB, 우회 문구). 메인 저장소 기준으로 기록.

## 3. 새 세션 자동 시작 (SessionStart 훅)
새 세션이 열리면 `HANDOFF.md` 가 최근 것이면 요약을 AI 맥락에 자동 주입 → 사용자가 설명하지 않아도 이어서 시작. 이어간 뒤 `PHASE_DONE` 해제.

## 설정 위치
훅은 `.claude/settings.local.json`(이 PC 전용, 미추적) 에 등록 — `.claude/settings.json` 은 다른 작업분이 미커밋 상태라 건드리지 않는다. 공용 스킬(판매 키트)에는 설치 스크립트가 settings 에 등록하는 방식으로 포함.

## 깨뜨리기
기록 크기 임계값을 작게 낮춘 설정으로: 경고 주입 확인 → 차단·안내·인계 파일 생성 확인 → `!계속` 1회 통과·기록 확인 → 새 세션 SessionStart 주입 확인 → 원복.

## 영향
훅 3개 추가(PC 설정), 스크립트 2 + 설정 1. 앱 동작 영향 없음. 차단은 사용자 입력을 막는 강한 동작이라 우회 문구를 반드시 둔다.

## 롤백
settings.local.json 에서 훅 항목 제거.
