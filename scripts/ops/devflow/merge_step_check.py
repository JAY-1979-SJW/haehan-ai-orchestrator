"""합본 단계 점검 — 한 줄로 '기준 대비 증감 표 1장'을 낸다.

사용:
    python scripts/ops/devflow/merge_step_check.py [--base origin/master] [--no-runcheck] [--json]

하는 일(현재 작업트리 = head, --base = 기준 브랜치):
  1. registry_sync --check            정본(registry)과 추적 파일 일치
  2. 코드맵 build + modules (새 측정: 실제 import 기준 순환·층 역전·금지 import·LIVE import 실패)
     — base 는 임시 worktree 에 head 의 code_map 도구를 복사해 같은 잣대로 잰다(verify_change._checkout 재사용)
  3. move_preflight                   base→head 로 이동한 .py 의 shim 없는 경로 참조(막음)
  4. G5(root_calc) / G11(tool_home) / G12(dup) / G15(flat_root) / G16(folder) 게이트와 기준선 크기

하나라도 '증가'(순환·층 역전·금지 import·LIVE import 실패·기준선 크기·막는 참조) 하거나 게이트·정본 점검이 실패하면 종료코드 1.
기준선 크기는 줄이기만 하는 값이라 늘면 실패, 줄면 개선으로 표시한다. 무거운 작업이므로 HEAVY_SLOT 규칙 안에서 돌린다.
측정 로직은 새로 만들지 않고 기존 도구(code_map/*, verify_change._checkout, move_preflight.report, 각 게이트 CLI)를 그대로 부른다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = sys.executable
PREFLIGHT_SHOW = 25  # 표에 보여 줄 막는 참조 줄 수(나머지는 --json)
# (표시 이름, 기준선 파일, 크기를 읽는 키) — 줄이기만 하는 값
BASELINES = (
    ("G11 tool_home 기준선", "configs/tool_home_baseline.json", "count"),
    ("G15 flat_root 기준선", "configs/flat_root_baseline.json", "count"),
    ("G12 dup 기준선", "configs/dup_baseline.json", "hash_count"),
    ("G16 folder 등록 수", "configs/folder_registry.json", "count"),
)
# (표시 이름, 명령) — head 트리에서 실행, 종료코드 0 이 통과
GATES = (
    ("G11 tool_home", ["scripts/ops/repo_gates/tool_home_gate.py", "--check-all"]),
    ("G12 dup", ["scripts/ops/repo_gates/dup_gate.py", "check", "--all"]),
    ("G15 flat_root", ["scripts/ops/repo_gates/flat_root_gate.py", "--check-all"]),
    ("G16 folder", ["scripts/ops/repo_gates/folder_gate.py", "--check-all"]),
)


def _run(cmd: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, *cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )


def _as_count(v: Any) -> int:
    if isinstance(v, dict):
        return int(v.get("total", len(v)))
    if isinstance(v, list):
        return len(v)
    return int(v or 0)


def measure_tree(tree: Path, runcheck: bool) -> dict[str, int]:
    """한 트리에서 코드맵을 새로 만들고 modules 의 crosscheck 수치를 읽는다(새 측정 — modules.py 가 정의)."""
    _run(["scripts/ops/code_map/build.py"], tree)
    if runcheck:
        _run(["scripts/ops/code_map/runcheck.py", "--levels", "R0"], tree)
    _run(["scripts/ops/code_map/modules.py"], tree)
    cc = json.loads((tree / "data/code_map/modules.json").read_text(encoding="utf-8"))["crosscheck"]
    return {
        "순환(실제 import)": _as_count(cc["module_cycles"]),
        "층 역전": _as_count(cc["layer_inversions"]),
        "금지 import": _as_count(cc["forbidden_import_hits"]),
        "LIVE import 실패": _as_count(cc.get("live_but_import_fails", [])),
    }


def baseline_sizes(tree: Path) -> dict[str, int | None]:
    """기준선 파일 크기. 그 트리에 파일이 없으면 None(이 브랜치에서 새로 생긴 게이트 — 증가로 보지 않는다)."""
    out: dict[str, int | None] = {}
    for name, rel, key in BASELINES:
        p = tree / rel
        out[name] = int(json.loads(p.read_text(encoding="utf-8")).get(key, 0)) if p.exists() else None
    return out


def moved_py(base: str, head: str, root: Path) -> dict[str, str]:
    """base→head 에서 이름이 바뀐 .py (옛 경로 → 새 경로)."""
    r = _git(root, "diff", "--name-status", "-M", "--diff-filter=R", "-z", f"{base}...{head}")
    parts = [p for p in r.stdout.split("\0") if p]
    pairs: dict[str, str] = {}
    i = 0
    while i + 2 < len(parts) and parts[i].startswith("R"):
        pairs[parts[i + 1]] = parts[i + 2]
        i += 3
    return {o: n for o, n in pairs.items() if o.endswith(".py")}


def preflight_blocking(base: str, head: str, root: Path) -> list[str]:
    from scripts.ops.devflow import move_preflight

    pairs = moved_py(base, head, root)
    if not pairs:
        return []
    rows = move_preflight.report(list(pairs), root, pairs)
    return [
        f"{r['file']}: {len(r['blocking'])}건 ({r['blocking'][0]['kind']} {r['blocking'][0]['file']}:{r['blocking'][0]['line']})"
        for r in rows
        if r["blocking"]
    ]


def gate_results(tree: Path) -> dict[str, bool]:
    res = {"registry_sync": _run(["scripts/ops/code_map/registry_sync.py", "--check"], tree).returncode == 0}
    for name, cmd in GATES:
        res[name] = _run(cmd, tree).returncode == 0
    # G5: base 와의 diff 검사는 --base 가 필요해 main() 에서 따로 부른다
    return res


def _verdict(before: int | None, after: int | None) -> str:
    if before is None or after is None:
        return "신규" if before is None else "삭제"  # 기준(또는 현재)에 그 기준선 파일이 없다 — 비교하지 않는다
    return "증가" if after > before else ("개선" if after < before else "동일")


def _cell(v: int | None) -> str:
    return "-" if v is None else str(v)


def _delta(b: int | None, a: int | None) -> str:
    return "-" if b is None or a is None else f"{a - b:+d}"


def _table(rows: list[tuple[str, int | None, int | None, str]]) -> str:
    w = max(len(r[0]) for r in rows)
    lines = [
        f"{'항목'.ljust(w)} | {'기준':>6} | {'현재':>6} | {'증감':>6} | 판정",
        f"{'-' * w}-+--------+--------+--------+-----",
    ]
    lines += [f"{n.ljust(w)} | {_cell(b):>6} | {_cell(a):>6} | {_delta(b, a):>6} | {v}" for n, b, a, v in rows]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/master", help="비교 기준 ref (기본 origin/master)")
    ap.add_argument("--no-runcheck", action="store_true", help="LIVE import 실패(runcheck R0) 측정을 건너뛴다")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    runcheck = not a.no_runcheck

    from scripts.ops.verify_change import (
        _checkout,  # 기준 트리를 임시 worktree 로 꺼내 head 의 code_map 도구를 넣는다(같은 잣대)
    )

    head_m = measure_tree(ROOT, runcheck)
    head_b = baseline_sizes(ROOT)
    with tempfile.TemporaryDirectory(prefix="merge_step_base_") as td:
        base_tree = Path(td) / "base"
        if not _checkout(a.base, base_tree):
            print(f"기준 ref 를 꺼내지 못했다: {a.base}", file=sys.stderr)
            return 2
        try:
            base_m = measure_tree(base_tree, runcheck)
            base_b = baseline_sizes(base_tree)
        finally:
            _git(ROOT, "worktree", "remove", "--force", str(base_tree))

    rows: list[tuple[str, int | None, int | None, str]] = [
        (k, base_m[k], head_m[k], _verdict(base_m[k], head_m[k])) for k in head_m
    ]
    rows += [(k, base_b[k], head_b[k], _verdict(base_b[k], head_b[k])) for k in head_b]
    gates = gate_results(ROOT)
    g5 = _run(["scripts/ops/repo_gates/root_calc_gate.py", "--check-diff", a.base, "HEAD"], ROOT).returncode == 0
    gates["G5 root_calc"] = g5
    blocking = preflight_blocking(a.base, "HEAD", ROOT)

    failed = [r[0] for r in rows if r[3] == "증가"] + [k for k, ok in gates.items() if not ok]
    if blocking:
        failed.append(f"move_preflight 막음 {len(blocking)}건")

    if a.json:
        print(
            json.dumps(
                {"rows": rows, "gates": gates, "preflight_blocking": blocking, "failed": failed},
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        print(_table(rows))
        print()
        print("게이트: " + ", ".join(f"{k} {'통과' if ok else '실패'}" for k, ok in gates.items()))
        print(
            f"move_preflight(이동 {len(moved_py(a.base, 'HEAD', ROOT))}개): "
            + ("막는 참조 없음" if not blocking else f"막는 참조 {len(blocking)}건")
        )
        for b in blocking[:PREFLIGHT_SHOW]:
            print(f"  - {b}")
        if len(blocking) > PREFLIGHT_SHOW:
            print(f"  ... 외 {len(blocking) - PREFLIGHT_SHOW}건 (전체는 --json)")
        print()
        print("결과: " + ("통과" if not failed else "실패 — " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
