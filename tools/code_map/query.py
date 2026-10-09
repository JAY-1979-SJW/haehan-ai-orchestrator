# module_category: audit
# primary_trade: common
"""코드맵 질문형 조회 — map.json 을 통째로 읽지 않고 답만 짧게 출력.

python -m tools.code_map.query who-imports <파일> | imports-of <파일> | class-of <파일>
    | impact <파일...> | tests-for <파일...>   [--map 경로] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402


def _default_map() -> Path:
    env = os.environ.get("HAEHAN_CODE_MAP")
    if env:
        return Path(env)
    here = repo_root() / "data" / "code_map" / "map.json"
    return here


def load(path: Path | None = None) -> dict:
    return json.loads((path or _default_map()).read_text(encoding="utf-8"))


def _edges(m: dict) -> dict[str, list[str]]:
    return m.get("import_edges") or m.get("edges") or {}


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def who_imports(m: dict, f: str) -> list[str]:
    f = _norm(f)
    return sorted(s for s, ts in _edges(m).items() if f in ts)


def imports_of(m: dict, f: str) -> list[str]:
    return sorted(_edges(m).get(_norm(f), []))


def class_of(m: dict, f: str) -> str:
    return (m.get("files", {}).get(_norm(f)) or {}).get("class", "?")


def impact(m: dict, files: list[str]) -> list[str]:
    """변경 파일을 (역방향 import 로) 직·간접 참조하는 모든 파일."""
    rev: dict[str, list[str]] = {}
    for s, ts in _edges(m).items():
        for t in ts:
            rev.setdefault(t, []).append(s)
    seen = {_norm(f) for f in files}
    q = deque(seen)
    while q:
        for s in rev.get(q.popleft(), []):
            if s not in seen:
                seen.add(s)
                q.append(s)
    return sorted(seen - {_norm(f) for f in files})


def tests_for(m: dict, files: list[str]) -> list[str]:
    def is_test(p: str) -> bool:
        n = p.rsplit("/", 1)[-1]
        return "/tests/" in "/" + p or n.startswith("test_")

    return [p for p in impact(m, files) + [_norm(f) for f in files] if is_test(p)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["who-imports", "imports-of", "class-of", "impact", "tests-for"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--map", type=Path)
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args(argv)
    try:
        m = load(a.map)
    except FileNotFoundError:
        print("map.json 없음 — build 먼저 (또는 --map / HAEHAN_CODE_MAP)", file=sys.stderr)
        return 2
    if a.cmd == "class-of":
        out = [f"{f}: {class_of(m, f)}" for f in a.files]
    else:
        fn = {"who-imports": who_imports, "imports-of": imports_of}.get(a.cmd)
        out = fn(m, a.files[0]) if fn else {"impact": impact, "tests-for": tests_for}[a.cmd](m, a.files)
    print(f"{a.cmd}: {len(out)}건")
    for line in out[: a.limit]:
        print("  " + line)
    if len(out) > a.limit:
        print(f"  ... +{len(out) - a.limit} (--limit 로 확대)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
