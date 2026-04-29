#!/usr/bin/env bash
set -euo pipefail

EXPECTED_REPO="haehan-ai-orchestrator"
EXPECTED_REPO_SLUG="JAY-1979-SJW/haehan-ai-orchestrator"

RESULT="PASS"
WARNINGS=()

# Normalize remote URL to owner/repo slug format
# Supports: https, git@, ssh:// with various hosts (github.com, github-orchestrator, etc.)
normalize_remote_to_slug() {
  local url="$1"

  # Remove trailing .git
  url="${url%.git}"

  # Extract owner/repo from various URL formats
  # Pattern: look for owner/repo at the end of the URL
  if [[ "$url" =~ ([a-zA-Z0-9._-]+)/([a-zA-Z0-9._-]+)$ ]]; then
    echo "${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    return 0
  fi

  # Fallback: return original (shouldn't reach here for valid git URLs)
  echo "$url"
  return 0
}

# 1. git repo 확인
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "FAIL: not a git repository"
  exit 1
fi

GIT_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$GIT_ROOT")
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")

echo "=== Repo Boundary Check ==="
echo "git root   : $GIT_ROOT"
echo "repo name  : $REPO_NAME"
echo "remote     : $REMOTE_URL"
echo "branch     : $CURRENT_BRANCH"
echo ""

# 2. repo 이름 확인 (폴더명 prefix 무시, remote URL로 판정)
if [[ "$REPO_NAME" != *"$EXPECTED_REPO"* ]]; then
  echo "FAIL: repo name mismatch (expected to contain: $EXPECTED_REPO, got: $REPO_NAME)"
  exit 1
fi

# 3. remote URL 확인 (slug 기반)
if [[ -z "$REMOTE_URL" ]]; then
  WARNINGS+=("WARN: no remote 'origin' configured")
  RESULT="WARN"
else
  NORMALIZED_SLUG=$(normalize_remote_to_slug "$REMOTE_URL")
  if [[ "$NORMALIZED_SLUG" != "$EXPECTED_REPO_SLUG" ]]; then
    echo "FAIL: remote slug mismatch"
    echo "  expected slug : $EXPECTED_REPO_SLUG"
    echo "  normalized    : $NORMALIZED_SLUG"
    echo "  raw remote    : $REMOTE_URL"
    exit 1
  fi
fi

# 4. 현재 경로가 git root 내부인지 확인
PWD_ABS=$(pwd -P 2>/dev/null || pwd)
GIT_ROOT_ABS=$(cd "$GIT_ROOT" && pwd -P 2>/dev/null || echo "$GIT_ROOT")
if [[ "$PWD_ABS" != "$GIT_ROOT_ABS"* ]]; then
  WARNINGS+=("WARN: current path may be outside git root")
  RESULT="WARN"
fi

# 5. 결과 출력
for w in "${WARNINGS[@]}"; do
  echo "$w"
done

echo ""
echo "=== Result: $RESULT ==="

if [[ "$RESULT" == "FAIL" ]]; then
  exit 1
fi
exit 0
