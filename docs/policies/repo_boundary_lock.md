# Repo Boundary Lock Policy v1.0

## 목적

haehan-ai-orchestrator 작업 중 다른 앱/다른 repo를 탐색·수정·커밋하지 못하도록
작업 범위를 명시적으로 잠금한다.

## 적용 대상

haehan-ai-orchestrator repo 내 모든 작업 (Claude Code 지시 포함)

## Target Repo 확인 기준

작업 시작 시 반드시 아래를 확인한다.

```
pwd
git rev-parse --show-toplevel
git remote -v
git branch --show-current
git status --short
```

- git root가 `haehan-ai-orchestrator`가 아니면 즉시 STOP
- remote가 `https://github.com/JAY-1979-SJW/haehan-ai-orchestrator.git`이 아니면 즉시 STOP

## Allowed Root

```
C:/Users/skyjw/OneDrive/03. PYTHON/35. haehan-ai-orchestrator
```

이 경로 밖은 접근 금지다.

## 금지 행위

- 다른 앱 폴더 `cd` 금지
- 다른 앱 파일 `read` 금지
- 다른 앱 `grep` / `find` 금지
- 다른 앱 `git status` / `git log` 금지
- 다른 앱 수정 / 삭제 / rename / commit / push 금지
- `OneDrive/03. PYTHON` 상위 폴더 전체 `find` / `grep` 금지

접근 금지 앱 예시:

- `15. 위험성평가표 자동생성기` / `risk-assessment-generator`
- `construction-attendance`
- `office-analysis-engine`
- `g2b`
- `attendance`
- haehan-ai-orchestrator 밖의 모든 repo/app

## Repo Root 불일치 시 처리

1. 즉시 STOP 보고
2. 다른 앱/상위 폴더 탐색하지 않음
3. 사용자에게 작업 위치 확인 요청
4. 사용자의 명시 승인 없이 repo 전환 금지

## 필요한 파일이 현재 Repo에 없을 때

1. 다른 앱에서 찾지 않는다.
2. "현재 repo에 없음"으로 STOP 보고한다.
3. 사용자의 명시 승인을 받은 후에만 다음 단계를 진행한다.

## 다른 앱 이름이 로그/보고서/지시문에 등장했을 때

- 해당 앱 경로를 자동으로 탐색하지 않는다.
- 단순 참조 정보로만 취급한다.
- 접근이 필요하면 사용자에게 명시 승인을 요청한다.

## 예외 조건

사용자가 아래처럼 명시적으로 지시한 경우에만 허용한다.

> "위험성평가표 앱으로 전환해"
> "다른 앱 위치를 찾아라"

예외 허용 시에도:
- read-only 탐색만 가능
- 수정 / 삭제 / rename / commit / push 금지
- 전환 후에도 새 작업의 target repo를 다시 명시적으로 고정해야 함

## 작업 지시문 표준 블록

모든 Claude Code 작업 지시문에 아래 블록을 포함한다.

```
[작업 범위 잠금]
- target repo: haehan-ai-orchestrator
- expected remote: https://github.com/JAY-1979-SJW/haehan-ai-orchestrator.git
- allowed root: current git root only
- repo root 불일치 시 STOP
- 다른 앱/다른 프로젝트 폴더 탐색 금지
- 상위 폴더 전체 find/grep 금지
- 필요한 파일이 현재 repo에 없으면 다른 앱에서 찾지 말고 STOP
```

## 점검 스크립트

`scripts/check_repo_boundary.sh` 참조.

작업 시작 전 또는 CI 단계에서 실행하여 repo 위치를 자동 검증한다.
