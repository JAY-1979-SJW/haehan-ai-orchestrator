# 기준서 — 게이트/훅 보강 (대량삭제 차단 + frozen-safe 검사)

작성일: 2026-06-05 / 사용자 승인: (대량 삭제 차단 + frozen-safe 패턴 검사)

## 1. 배경 (이번 세션 교훈)

- **코드 보존 위반**: 프론트 대량 삭제가 게이트 없이 커밋됨 → 경고만으론 부족, 차단 필요.
- **frozen-exe 버그**: `subprocess.run([sys.executable, SCRIPT, "--once"])` 가 frozen exe에서
  `sys.executable`=`haehan-server.exe`(파이썬 아님)라 동작 안 함(session 모니터 미실행).

## 2. 보강 항목

### ① 대량 삭제 차단 — commit-msg 훅 (신규)

`.githooks/commit-msg` (git hooksPath=.githooks 라 자동 적용):

- staged 변경(`git diff --cached --numstat --diff-filter=MD`)에서 `.py/.ts/.tsx` 의
  **순삭제(deleted-added) ≥ 60줄** 파일이 있으면:
  - 커밋 메시지($1)에 `[allow-delete]` 있으면 통과.
  - 없으면 파일 목록 출력 + `exit 1` 차단.
- 이유: 코드 보존 원칙(기존 코드 무단 삭제 금지) 강제. 의도된 삭제는 명시적 표식으로 허용.
- pre-commit 의 기존 "대량 삭제 경고"(비차단)는 **조기 안내용으로 유지**.

### ② frozen-safe 패턴 검사 — pre-commit 보강

- 대상: staged `ai_orchestrator/**.py` (frozen 서버에서 실제 구동되는 코드).
- `git diff --cached -U0` 의 **추가된(+) 줄**에서 다음 패턴 검출 시 차단:
  - `sys.executable` 이 스크립트 실행에 쓰임(같은 줄에 `.py` / `SCRIPT` / `script` 동반).
- 허용: 해당 줄에 `# frozen-ok` 주석이 있으면 통과(정당한 예외).
- 이유: frozen exe 에서 `sys.executable` 로 .py 실행은 깨짐 → in-process 호출로 유도.
- 범위를 `ai_orchestrator/**` 로 한정해 dev 전용 스크립트(scripts/**) 오탐 방지.

## 3. 적용 위치

| 파일 | 변경 |
|------|------|
| `.githooks/commit-msg` (신규) | 대량 삭제 차단([allow-delete] 예외) |
| `.githooks/pre-commit` | frozen-safe 검사 블록 추가(기존 로직 보존) |

## 4. 영향/리스크

- 정상 리팩터링(대량 삭제 의도)은 `[allow-delete]` 로, 정당한 sys.executable 은 `# frozen-ok` 로 통과.
- frozen-safe 검사는 추가 줄만 보므로 기존 코드엔 영향 없음.
- 보안/DB/외부 영향 없음. 커밋 시간 영향 미미.

## 5. 드라이런

- 대량 삭제 차단: 60줄+ 삭제 stage → 차단 / `[allow-delete]` 메시지 → 통과 확인.
- frozen-safe: `[sys.executable, SCRIPT, ...]` 추가 줄 stage → 차단 / `# frozen-ok` → 통과 확인.
