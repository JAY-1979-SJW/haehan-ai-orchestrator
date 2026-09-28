#!/usr/bin/env python
# module_category: audit
# primary_trade: common
"""커밋 전 체크리스트 훅 설치기 — 저장소별 활성 훅 디렉터리에 래퍼 pre-commit 설치.

기준서: docs/specs/2026-09-13_커밋전_체크리스트_전저장소_훅강제_spec.md
- 기존 pre-commit 은 내용 그대로 pre-commit.orig 로 보존, 래퍼가 체크리스트 후 호출.
- 검사기·설치기 사본을 저장소 .githooks/ 에 두어(추적) 다른 PC 에서 재설치 가능.
- 재실행 안전(이미 래퍼면 사본만 갱신).
사용: python install_commit_checklist.py [--dry-run] <repo> [<repo> ...]
"""

from __future__ import annotations

import argparse
import contextlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path

MARKER = "# commit-checklist-wrapper v1"
HERE = Path(__file__).resolve().parent

WRAPPER = f"""#!/bin/sh
{MARKER}
# 커밋 전 체크리스트(공통) → 통과 시 기존 훅(pre-commit.orig) 실행. 설치기: .githooks/install_commit_checklist.py
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
TOP="$(git rev-parse --show-toplevel)"
CHK="$TOP/.githooks/commit_checklist.py"
[ -f "$CHK" ] || CHK="$TOP/scripts/ops/commit_checklist/commit_checklist.py"
# 워크트리·다른 브랜치엔 사본이 없을 수 있어 설치 시점 원본 절대경로로 대체(없는 브랜치 커밋 전면차단 방지)
[ -f "$CHK" ] || CHK="__CANON__"
# PATH 순서가 꼬여 bare python/python3 가 엉뚱한(패키지 없는) 인터프리터로 잡히거나
# python3 가 Windows Store 실행 별칭 스텁으로 연결되는 PC가 있어(2026-09-28 실측),
# py 런처로 버전을 명시할 수 있으면 그걸 우선한다.
if command -v py >/dev/null 2>&1 && py -3.14 -c "pass" >/dev/null 2>&1; then
  PY_BIN=py
  PY_VER=-3.14
else
  PY_BIN=python
  command -v python >/dev/null 2>&1 || PY_BIN=py
  PY_VER=
fi
if [ -f "$CHK" ]; then
  "$PY_BIN" $PY_VER "$CHK" || exit 1
else
  echo "[커밋 전 체크리스트] 검사기 없음: $CHK — 커밋 차단(설치 확인)"; exit 1
fi
if [ -f "$HOOK_DIR/pre-commit.orig" ]; then
  "$PY_BIN" $PY_VER "$HOOK_DIR/pre-commit.orig" "$@"
  exit $?
fi
exit 0
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def active_hooks_dir(repo: Path) -> Path:
    hp = git(repo, "config", "core.hooksPath")
    if not hp:
        return Path(git(repo, "rev-parse", "--absolute-git-dir")) / "hooks"
    p = Path(hp)
    return p if p.is_absolute() else repo / p


def install(repo: Path, dry: bool) -> dict:
    repo = repo.resolve()
    if not git(repo, "rev-parse", "--show-toplevel"):
        return {"repo": str(repo), "error": "git 저장소 아님"}
    hooks = active_hooks_dir(repo)
    pre = hooks / "pre-commit"
    orig = hooks / "pre-commit.orig"
    already = pre.exists() and MARKER in pre.read_text(encoding="utf-8", errors="replace")
    plan = {
        "repo": str(repo),
        "hooks_dir": str(hooks),
        "existing_hook": pre.exists() and not already,
        "already_wrapped": already,
        "copy_to": str(repo / ".githooks"),
    }
    if dry:
        return plan
    hooks.mkdir(parents=True, exist_ok=True)
    gh = repo / ".githooks"
    gh.mkdir(exist_ok=True)
    for name in ("commit_checklist.py", "install_commit_checklist.py"):
        if (HERE / name).resolve() != (gh / name).resolve():
            shutil.copy2(HERE / name, gh / name)
    if not already:
        if pre.exists():
            if orig.exists():
                raise RuntimeError(f"{orig} 이미 존재 — 수동 확인 필요")
            pre.rename(orig)
        canon = (gh / "commit_checklist.py").resolve().as_posix()
        pre.write_text(WRAPPER.replace("__CANON__", canon), encoding="utf-8", newline="\n")
    for f in (pre, orig):
        if f.exists():
            f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    plan["installed"] = True
    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("repos", nargs="+")
    a = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    rc = 0
    for r in a.repos:
        try:
            print(install(Path(r), a.dry_run))
        except Exception as e:  # noqa: BLE001 - 여러 저장소를 순회 설치하는 CLI — 한 저장소 설치 실패 시에도 나머지 저장소를 계속 처리하기 위해 의도적으로 폭넓게 예외를 잡음(코드 내 기존 주석과 동일 취지), 오류는 print로 보고되고 종료코드 1로 반영됨
            # 여러 저장소를 순회 설치하는 CLI: 한 저장소가 어떤 이유로든(git 오류·권한·I/O 등)
            # 실패해도 나머지 저장소는 계속 처리해야 한다 — 의도적으로 폭넓게 잡는다.
            print({"repo": r, "error": str(e)})
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
