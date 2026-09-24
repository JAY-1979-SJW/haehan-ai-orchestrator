# module_category: gate
# primary_trade: common
"""지도↔골격 대조 의무화 — ③ 병합 게이트 (결함 #34 후속).

docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md 참조.
stage/* 브랜치를 master 로 합치기 전에 scripts/ops/verify_change.py(9항목: 지도↔골격 대조 포함)를
강제로 돌려 PASS 일 때만 `git merge --ff-only` 하고, 검증표를 메시지로 담은 태그
`verified/<branch-이름(stage/ 접두 제거)>` 를 남긴다. PASS 기록 없이는 master 로 못 들어간다.

사용:
    python scripts/ops/merge_stage.py stage/skeleton-gate [--base master] [--dry-run]

주의: 이 스크립트는 실제 병합을 수행할 수 있다(--dry-run 없이 실행 시). 운영 서버 재시작·DB 변경은
하지 않지만 master 브랜치 상태를 바꾸므로, 자동 스크립트/AI 가 사용자 승인 없이 실행하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
VERIFY = ROOT / "scripts" / "ops" / "verify_change.py"


def run(args: list[str], cwd: Path = ROOT, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, **kw)


def tag_name_for(branch: str) -> str:
    """stage/skeleton-gate -> verified/skeleton-gate, 그 외는 verified/<branch>."""
    name = branch.split("/", 1)[1] if branch.startswith("stage/") else branch
    return f"verified/{name}"


def run_verify_change(base: str, branch: str, json_path: Path) -> dict:
    """verify_change.py --base <base> --head <branch> --json <json_path> 실행 결과를 반환."""
    subprocess.run(
        [PY, str(VERIFY), "--base", base, "--head", branch, "--json", str(json_path)],
        cwd=str(ROOT),
    )
    if not json_path.exists():
        return {"ok": False, "report": "[merge_stage] verify_change 가 JSON 결과를 만들지 못했습니다.", "changed": []}
    return json.loads(json_path.read_text(encoding="utf-8"))


def dirty_paths() -> set[str]:
    """메인 작업트리(현재 checkout)의 미커밋 변경 파일 경로 집합."""
    r = run(["git", "status", "--porcelain"])
    out = set()
    for line in r.stdout.splitlines():
        if len(line) > 3:
            out.add(line[3:].strip().split(" -> ")[-1])
    return out


def overlap_with_dirty(changed: list[str]) -> list[str]:
    dirty = dirty_paths()
    return sorted(set(changed) & dirty)


def do_merge(branch: str) -> subprocess.CompletedProcess:
    return run(["git", "merge", "--ff-only", branch])


def do_tag(tag: str, message: str) -> subprocess.CompletedProcess:
    return run(["git", "tag", "-a", tag, "-m", message])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("branch", help="master 로 병합할 stage 브랜치")
    ap.add_argument("--base", default="master")
    ap.add_argument("--dry-run", action="store_true", help="병합·태그 없이 계획만 출력")
    a = ap.parse_args(argv)

    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="merge_stage_")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        result = run_verify_change(a.base, a.branch, tmp)
    finally:
        tmp.unlink(missing_ok=True)

    report = result.get("report", "")
    print(report)

    if not result.get("ok"):
        print("=" * 60)
        print(f"[merge_stage] REFUSED — verify_change FAIL ({a.base}...{a.branch})")
        print("병합하지 않습니다. 리포트의 새 문제를 먼저 고치세요.")
        print("=" * 60)
        return 1

    changed = result.get("changed", [])
    overlap = overlap_with_dirty(changed)
    if overlap:
        print("=" * 60)
        print("[merge_stage] REFUSED — 메인 작업트리에 겹치는 미커밋 변경이 있습니다:")
        for p in overlap[:20]:
            print("  - " + p)
        print("커밋하거나 stash 한 뒤 다시 시도하세요.")
        print("=" * 60)
        return 1

    tag = tag_name_for(a.branch)
    if a.dry_run:
        print("[dry-run] verify_change PASS — 실제로는 다음을 수행합니다:")
        print(f"[dry-run]   git merge --ff-only {a.branch}")
        print(f"[dry-run]   git tag -a {tag} -m <검증표>")
        return 0

    merged = do_merge(a.branch)
    if merged.returncode != 0:
        print("[merge_stage] git merge --ff-only 실패:")
        print(merged.stdout)
        print(merged.stderr)
        return 1
    tagged = do_tag(tag, report)
    if tagged.returncode != 0:
        print("[merge_stage] 병합은 됐으나 태그 생성 실패:")
        print(tagged.stderr)
        return 1
    print(f"[merge_stage] PASS — {a.branch} → {a.base} 병합 완료, 태그 {tag} 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
