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

사용: python tools/code_map/registry_sync.py [--check|--fix]
읽기 전용 아님(--fix 는 configs/module_registry.json, configs/module_registry.overrides.json 을 수정).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
REGISTRY = ROOT / "configs" / "module_registry.json"
OVERRIDES = ROOT / "configs" / "module_registry.overrides.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.code_map.classify import CODE_SUFFIX, _domain, classify_one  # noqa: E402


def tracked_code_files(root: Path = ROOT) -> set[str]:
    """git 인덱스(스테이지 반영) 기준 추적 코드 파일 집합."""
    r = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
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
    """스테이지된 이동(old -> new) 감지. 단일 git 호출(예전엔 두 번 호출하던 중복 구현이었음)."""
    renames: dict[str, str] = {}
    with contextlib.suppress(subprocess.CalledProcessError):
        r = subprocess.run(
            ["git", "-c", "core.quotepath=false", "diff", "--cached", "-M", "--name-status"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                renames[parts[1]] = parts[2]
    return renames


def _move_key_preserve_order(d: dict, old: str, new: str) -> None:
    """d[old] 를 d[new] 로 옮기되, 원래 키 위치(순서)를 보존한다(끝에 추가하지 않음)."""
    if old not in d or new in d:
        return
    value = d[old]
    keys = list(d.keys())
    idx = keys.index(old)
    items = list(d.items())
    items[idx] = (new, value)
    d.clear()
    d.update(items)


def diff_registry(reg_files: set[str], tracked: set[str]) -> tuple[set[str], set[str]]:
    """(missing: tracked 인데 정본에 없음, ghost: 정본에 있는데 추적 안 됨)."""
    return tracked - reg_files, reg_files - tracked


def expected_with_override(entry: dict, override: dict) -> dict:
    """정본 항목에 사람이 확정한 override 를 덮은 기대값 — classify.py 재생성 결과와 같은 규칙(source=confirmed, confidence=high)."""
    out = dict(entry)
    out.update(override)
    out["source"] = "confirmed"
    out["confidence"] = "high"
    return out


def override_drift(files: dict, overrides: dict) -> list[str]:
    """정본에 이미 있는 항목인데 override 가 반영되지 않은 키(예전 --fix 는 새 파일에만 overrides 를 적용해 기존 키의 변경을 놓쳤다)."""
    return sorted(p for p, ov in overrides.items() if p in files and expected_with_override(files[p], ov) != files[p])


def stale_overrides(overrides: dict, tracked: set[str]) -> list[str]:
    """추적되는 코드 파일이 아닌데(이미 삭제·이동된) 남아 있는 override 키."""
    return sorted(p for p in overrides if p not in tracked)


def check(root: Path = ROOT) -> int:
    doc = load_registry(root)
    reg_files = set(doc.get("files", {}).keys())
    tracked = tracked_code_files(root)
    missing, ghost = diff_registry(reg_files, tracked)
    overrides = load_overrides(root)
    drift = override_drift(doc.get("files", {}), overrides)
    stale = stale_overrides(overrides, tracked)
    if not missing and not ghost and not drift and not stale:
        print(
            f"OK: registry({len(reg_files)}) matches tracked code files({len(tracked)}), overrides({len(overrides)}) reflected"
        )
        return 0
    if drift:
        print(f"OVERRIDE not reflected in registry ({len(drift)}):")
        for f in drift[:40]:
            print("  ~ " + f)
    if stale:
        print(f"STALE overrides — file no longer tracked ({len(stale)}):")
        for f in stale[:40]:
            print("  x " + f)
    if not missing and not ghost:
        print("fix: python tools/code_map/registry_sync.py --fix")
        return 1
    if missing:
        print(f"MISSING in registry ({len(missing)}) — tracked but no registry entry:")
        for f in sorted(missing)[:80]:
            print("  + " + f)
    if ghost:
        print(f"GHOST in registry ({len(ghost)}) — registry entry but not tracked:")
        for f in sorted(ghost)[:80]:
            print("  - " + f)
    print("fix: python tools/code_map/registry_sync.py --fix")
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

    # 1) 이동: 값 유지한 채 키만 옮김(원래 위치 보존). overrides 도 같이 옮김.
    moved = 0
    overrides_changed = False
    for old, new in detect_renames(root).items():
        if old in files and new not in files:
            _move_key_preserve_order(files, old, new)
            moved += 1
        if old in overrides and new not in overrides:
            _move_key_preserve_order(overrides, old, new)
            overrides_changed = True

    tracked = tracked_code_files(root)
    reg_files = set(files.keys())
    missing, ghost = diff_registry(reg_files, tracked)

    # 2) 추가: classify.py 규칙 재사용
    added = 0
    for p in sorted(missing):
        files[p] = _classify_new(p, overrides, root)
        added += 1

    # 3) 제거: 추적되지 않는(미커밋/임시) 항목. overrides 에 남은 참조도 같이 제거.
    removed = 0
    for p in sorted(ghost):
        del files[p]
        removed += 1
        if p in overrides:
            del overrides[p]
            overrides_changed = True

    # 4) 기존 항목에 overrides 반영 — 예전에는 새로 추가되는 파일에만 적용돼, overrides 를 고쳐도 정본이 안 바뀌었다
    reflected = 0
    for p in override_drift(files, overrides):
        files[p] = expected_with_override(files[p], overrides[p])
        reflected += 1

    # 5) 이미 없는 파일의 낡은 override 제거(삭제·이동 뒤 남은 것)
    stale = stale_overrides(overrides, tracked)
    for p in stale:
        del overrides[p]
        overrides_changed = True

    save_registry(doc, root)
    if overrides or overrides_changed:
        save_overrides(overrides, root)
    print(
        json.dumps(
            {
                "added": added,
                "removed": removed,
                "moved": moved,
                "overrides_reflected": reflected,
                "stale_overrides_removed": len(stale),
            },
            ensure_ascii=False,
        )
    )
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
