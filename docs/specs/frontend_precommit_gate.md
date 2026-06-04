# 기준서 — pre-commit 프론트(.ts/.tsx) 게이트 추가

작성일: 2026-06-05 / 사용자 승인: (A)

## 1. 문제

- `.githooks/pre-commit` 은 staged **`.py` 만** ruff/quality_gate 로 검사.
- `.ts/.tsx`(프론트)는 어떤 git 훅도 검사하지 않음 → `CafeClient.tsx` 대량 변경/삭제가
  게이트 없이 커밋됨(수동 `npm run build` 에만 의존).
- pre-push AI 검수는 .tsx diff 도 보지만 **push 시에만** 실행.

## 2. 변경 (단일 파일)

`.githooks/pre-commit` 에 **프론트 검사 블록 추가**(기존 .py ruff·quality_gate 로직 보존, 추가만):

1. **타입체크(차단)**: staged 파일에 `admin-web/**.ts(x)` 있으면
   `node node_modules/typescript/bin/tsc --noEmit -p tsconfig.app.json` 실행(cwd=admin-web).
   - npm/.cmd 셸 의존을 피하려 node 로 tsc 직접 호출.
   - 타입 오류 → `sys.exit(1)` 로 커밋 차단.
   - 측정: app 한정 ~10초.
2. **대량 삭제 경고(비차단)**: `git diff --cached --numstat --diff-filter=M` 에서
   `.py/.ts/.tsx` 의 **순삭제(deleted-added) ≥ 60줄** 파일을 경고 출력.
   - 코드 보존 원칙 환기용. 차단하지 않음(정상 리팩터링 방해 금지).

## 3. 실행 순서 (pre-commit 내)

```
.py staged → ruff check --fix + format + re-stage (기존)
프론트 staged(.ts/.tsx) → tsc --noEmit (신규, 차단)
대량 삭제 경고 (신규, 비차단)
quality_gate --staged --enforce (기존, 마지막 exit)
```

## 4. 영향/리스크

- node·tsc(admin-web/node_modules) 필요 — 이미 존재. 없으면 스킵(안전 폴백).
- 프론트 미변경 커밋엔 영향 없음(.ts/.tsx staged 없을 때 스킵).
- 커밋 시간 +~10초(프론트 변경 시에만).
- 보안/DB/외부 영향 없음.
