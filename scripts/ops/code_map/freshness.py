# module_category: audit
# primary_trade: common
"""map.json 신선도(기준서 §5.3) — 작업트리 지문이 map.meta 와 다르면 재빌드/거부."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXIT_STALE = 5


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True).stdout


def head_full(root: Path = ROOT) -> str:
    return _git(root, "rev-parse", "HEAD").decode().strip()


def fingerprint(root: Path = ROOT) -> str:
    h = hashlib.sha256()
    h.update(_git(root, "rev-parse", "HEAD"))
    h.update(_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=no"))
    for f in _git(root, "diff", "HEAD", "--name-only", "-z", "--", "*.py").decode().split("\0"):
        if f and (root / f).is_file():
            h.update(f.encode() + (root / f).read_bytes())
    return h.hexdigest()


def is_fresh(map_path: Path, root: Path = ROOT) -> bool:
    try:
        meta = json.loads(map_path.read_text(encoding="utf-8")).get("meta", {})
    except Exception:
        return False
    return meta.get("worktree_fingerprint") == fingerprint(root)


def ensure_fresh(map_path: Path | None = None, mode: str = "rebuild", root: Path = ROOT) -> bool:
    """신선하면 True. stale 이면 rebuild(기본, 재빌드 후 판정) 또는 refuse(exit 5)."""
    mp = map_path or root / "data" / "code_map" / "map.json"
    if is_fresh(mp, root):
        return True
    if mode == "refuse":
        print("map.json 이 현재 작업트리와 다릅니다(stale) — build 필요", file=sys.stderr)
        raise SystemExit(EXIT_STALE)
    subprocess.run([sys.executable, str(root / "scripts/ops/code_map/build.py")], cwd=str(root), capture_output=True)
    return is_fresh(mp, root)
