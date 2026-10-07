#!/usr/bin/env bash
# CI 수동 실행(workflow_dispatch)의 base 입력(짧은 해시·긴 해시·브랜치 이름)을 커밋 해시 한 줄로 바꾼다.
# 입력은 환경변수 DISPATCH_BASE 로만 받는다(워크플로 스크립트에 직접 끼워 넣지 않아 주입을 막는다).
# 성공: 표준출력에 40자 해시 한 줄. 실패(빈 값·해석 불가): 표준오류에 이유를 쓰고 종료코드 1.
#
# `git rev-parse <없는 ref>` 는 실패하면서도 인자 문자열을 표준출력에 찍으므로, 반드시 --verify --quiet 를 쓴다.
set -u
base_in="${DISPATCH_BASE:-}"
if [ -z "$base_in" ]; then
  echo "resolve_ci_base: DISPATCH_BASE 가 비어 있습니다" >&2
  exit 1
fi
sha=$(git rev-parse --verify --quiet "origin/${base_in}^{commit}" || git rev-parse --verify --quiet "${base_in}^{commit}" || true)
if [ -z "$sha" ] || [ "$(printf '%s\n' "$sha" | wc -l)" -ne 1 ]; then
  echo "resolve_ci_base: base '${base_in}' 를 커밋으로 해석하지 못했습니다(origin 에 있는 브랜치 이름 또는 가져온 커밋 해시를 쓰세요)" >&2
  exit 1
fi
printf '%s\n' "$sha"
