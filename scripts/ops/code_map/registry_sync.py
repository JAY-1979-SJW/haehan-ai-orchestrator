# module_category: audit
# primary_trade: common
"""정본(configs/module_registry.json) ↔ git 추적 코드 파일 자동 동기화.

지도↔골격 대조 의무화(결함 #34 후속, docs/specs/2026-09-24_skeleton_map_crosscheck_gate.md)의
② 동기화 도구. skeleton_gate.py(커밋 게이트, ①)가 FAIL 시 알려주는 고치는 명령이 이 스크립트다.

--check (기본): 정본 files 키 집합 ↔ `git ls-files` 코드 파일 집합 불일치를 출력. 불일치 있으면 exit 1.
--fix        : classify.py 의 분류 규칙(classify_one)을 그대로 재사용해
               - 새 파일 → 규칙대로 분류해 정본에 추가 (overrides 있으면 적용)
               - 삭제된 파일 → 정본에서 제거
               - 이동(rename) → 값은 유지한 채 키만 이동 (git diff --cached -M 로 감지)
               기존 키 순서는 보존하고 새 키는 끝에 추가한다(JSON diff 최소화).

사용: python scripts/ops/code_map/registry_sync.py [--check|--fix]
읽기 전용 아님(--fix 는 configs/module_registry.json, configs/module_registry.overrides.json 을 수정).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "configs" / "module_registry.json"
OVERRIDES = ROOT / "configs" / "module_registry.overrides.json"
CODE_SUFFIX = (".py", ".ts", ".tsx", ".js", ".mjs")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.code_map.classify import _domain, classify_one  # noqa: E402


def tracked_code_files(root: Path = ROOT) -> set[str]:
    """git 인덱스(스테이지 반영) 기준 추적 코드 파일 집합."""
    r = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True, text=True, check=True)
    return {f for f in r.stdout.splitlines() if PurePosixPath(f).suffix in CODE_SUFFIX}


def load_registry(root: Path = ROOT) -> dict:
    return json.loads((root / "configs" / "module_registry.json").read_text(encoding="utf-8"))


def save_registry(doc: dict, root: Path = ROOT) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    (root / "configs" / "module_registry.json").write_text(text, encoding="utf-8", newline="\n")


def load_overrides(root: Path = ROOT) -> dict:
    p = root / "configs" / "module_registry.overrides.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_overrides(doc: dict, root: Path = ROOT) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    (root / "configs" / "module_registry.overrides.json").write_text(text, encoding="utf-8", newline="\n")


def detect_renames(root: Path = ROOT) -> dict[str, str]:
    """스테이지된 이동(old -> new) + HEAD..index 이동(직접 mv 후 add 한 경우도 포함)."""
    renames: dict[str, str] = {}
    for args in (
        ["git", "diff", "--cached", "-M", "--name-status"],
        ["git", "diff", "HEAD", "--cached", "-M", "--name-status"],
    ):
        with contextlib.suppress(subprocess.CalledProcessError):
            r = subprocess.run(args, cwd=str(root), capture_output=True, text=True, check=True)
            for line in r.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 3 and parts[0].startswith("R"):
                    renames[parts[1]] = parts[2]
    return renames


def diff_registry(reg_files: set[str], tracked: set[str]) -> tuple[set[str], set[str]]:
    """(missing: tracked 인데 정본에 없음, ghost: 정본에 있는데 추적 안 됨)."""
    return tracked - reg_files, reg_files - tracked


def check(root: Path = ROOT) -> int:
    doc = load_registry(root)
    reg_files = set(doc.get("files", {}).keys())
    tracked = tracked_code_files(root)
    missing, ghost = diff_registry(reg_files, tracked)
    if not missing and not ghost:
        print(f"OK: registry({len(reg_files)}) matches tracked code files({len(tracked)})")
        return 0
    if missing:
        print(f"MISSING in registry ({len(missing)}) — tracked but no registry entry:")
        for f in sorted(missing)[:80]:
            print("  + " + f)
    if ghost:
        print(f"GHOST in registry ({len(ghost)}) — registry entry but not tracked:")
        for f in sorted(ghost)[:80]:
            print("  - " + f)
    print("fix: python scripts/ops/code_map/registry_sync.py --fix")
    return 1


def _classify_new(p: str, overrides: dict, root: Path = ROOT) -> dict:
    try:
        text = (root / p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    layer, role, reason, conf = classify_one(p, text, False)
    entry = {
        "layer": layer,
        "role": role,
        "domain": _domain(p),
        "reason": reason,
        "confidence": conf,
        "source": "rule",
    }
    if p in overrides:
        entry.update(overrides[p])
        entry["source"] = "confirmed"
        entry["confidence"] = "high"
    return entry


def fix(root: Path = ROOT) -> int:
    doc = load_registry(root)
    files: dict = doc.setdefault("files", {})
    overrides = load_overrides(root)

    # 1) 이동: 값 유지한 채 키만 옮김. overrides 도 같이 옮김.
    moved = 0
    for old, new in detect_renames(root).items():
        if old in files and new not in files:
            files[new] = files.pop(old)
            moved += 1
        if old in overrides and new not in overrides:
            overrides[new] = overrides.pop(old)

    tracked = tracked_code_files(root)
    reg_files = set(files.keys())
    missing, ghost = diff_registry(reg_files, tracked)

    # 2) 추가: classify.py 규칙 재사용
    added = 0
    for p in sorted(missing):
        files[p] = _classify_new(p, overrides, root)
        added += 1

    # 3) 제거: 추적되지 않는(미커밋/임시) 항목
    removed = 0
    for p in sorted(ghost):
        del files[p]
        removed += 1

    save_registry(doc, root)
    if overrides:
        save_overrides(overrides, root)
    print(json.dumps({"added": added, "removed": removed, "moved": moved}, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true", help="정본을 실제로 고침(기본은 --check)")
    ap.add_argument("--check", action="store_true", help="불일치만 출력(기본값)")
    args = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if args.fix:
        return fix()
    return check()


if __name__ == "__main__":
    sys.exit(main())
