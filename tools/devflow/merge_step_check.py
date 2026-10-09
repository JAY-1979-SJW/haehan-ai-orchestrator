"""합본 단계 점검 — 한 줄로 '기준 대비 증감 표 1장'을 낸다.

사용:
    python tools/devflow/merge_step_check.py [--base origin/master] [--no-runcheck] [--json]

하는 일(현재 작업트리 = head, --base = 기준 브랜치):
  1. registry_sync --check            정본(registry)과 추적 파일 일치
  2. 코드맵 build + modules (새 측정: 실제 import 기준 순환·층 역전·금지 import·LIVE import 실패)
     — base 는 임시 worktree 에 head 의 code_map 도구를 복사해 같은 잣대로 잰다(verify_change._checkout 재사용)
  3. move_preflight                   base→head 로 이동한 .py 의 shim 없는 경로 참조(막음)
  4. G5(root_calc) / G11(tool_home) / G12(dup) / G15(flat_root) / G16(folder) 게이트와 기준선 크기

하나라도 '증가'(순환·층 역전·금지 import·LIVE import 실패·기준선 크기·막는 참조) 하거나 게이트·정본 점검이 실패하면 종료코드 1.
기준선 크기는 줄이기만 하는 값이라 늘면 실패, 줄면 개선으로 표시한다. 무거운 작업이므로 HEAVY_SLOT 규칙 안에서 돌린다.
--impacted-tests 를 주면 영향 시험도 돌린다: 바뀐 .py(base...HEAD) → 코드맵 간선으로 그 모듈에 닿는 시험 파일(verify_change.affected_tests)만 실행.
  대상이 0개면 실행하지 않는다(빈 목록이 전체 실행이 되는 사고 방지). 시험 파일이 --max-test-files(기본 400)를 넘으면 실행하지 않고 목록만 보여 준다.
  병렬은 pytest-xdist 최대 4(-n). 100개 이상이면 HEAVY_SLOT 을 잡고 돌리라고 안내한다. 새 실패만 판정에 넣고, 기준(base)에서도 실패하는 시험은 '기존 실패'로 따로 표시한다.
  로컬 전체 verify 는 여전히 금지 — 이 옵션은 영향 범위만 돈다.
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

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = sys.executable
IMPACTED_MAX_FILES = 400  # 영향 시험 파일이 이보다 많으면 실행하지 않고 목록만
IMPACTED_SLOT_NOTICE = 100  # 이 개수 이상이면 HEAVY_SLOT 안내
IMPACTED_MAX_WORKERS = 4  # pytest-xdist 상한
IMPACTED_CHUNK = 100  # 한 pytest 프로세스에 넘기는 시험 파일 수(윈도우 명령줄 길이 제한 여유)
IMPACTED_TIMEOUT_S = 3600
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
    ("G11 tool_home", ["tools/repo_gates/tool_home_gate.py", "--check-all"]),
    ("G12 dup", ["tools/repo_gates/dup_gate.py", "check", "--all"]),
    ("G15 flat_root", ["tools/repo_gates/flat_root_gate.py", "--check-all"]),
    ("G16 folder", ["tools/repo_gates/folder_gate.py", "--check-all"]),
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
    _run(["tools/code_map/build.py"], tree)
    if runcheck:
        _run(["tools/code_map/runcheck.py", "--levels", "R0"], tree)
    _run(["tools/code_map/modules.py"], tree)
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
    from tools.devflow import move_preflight

    pairs = moved_py(base, head, root)
    if not pairs:
        return []
    rows = move_preflight.report(list(pairs), root, pairs)
    return [
        f"{r['file']}: {len(r['blocking'])}건 ({r['blocking'][0]['kind']} {r['blocking'][0]['file']}:{r['blocking'][0]['line']})"
        for r in rows
        if r["blocking"]
    ]


def impacted_test_files(base: str, head: str, root: Path) -> list[str]:
    """바뀐 파일(base...head)에 닿는 시험 파일(현재 트리에 있는 것만). 선별은 CI 의 verify_change.affected_tests 와 같은 함수:
    출발점 = 바뀐 파일 + 바뀐 비-.py 를 문자열로 읽는 .py(code_map/ref_seeds), 거기서 코드맵 간선으로 역탐색."""
    from tools import verify_change as vc

    changed_all = vc.changed_files(base, head)
    if not changed_all:
        return []
    return [t for t in vc.affected_tests(changed_all) if (root / t).is_file()]


def plan_impacted(files: list[str], max_files: int = IMPACTED_MAX_FILES) -> str:
    """'empty'(실행 안 함) · 'list_only'(너무 많아 목록만) · 'run'. 빈 목록을 절대 '전체 실행'으로 바꾸지 않는다."""
    if not files:
        return "empty"
    return "list_only" if len(files) > max_files else "run"


def _xdist_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("xdist") is not None


def run_impacted(tree: Path, files: list[str], workers: int) -> list[str]:
    """시험 파일을 묶음으로 실행하고 실패·수집오류 id 목록을 돌려준다. 병렬은 xdist 가 있을 때 최대 IMPACTED_MAX_WORKERS."""
    from tools import verify_change as vc

    workers = max(1, min(workers, IMPACTED_MAX_WORKERS))
    extra = ["-n", str(workers)] if workers > 1 and _xdist_available() else []
    failures: list[str] = []
    for i in range(0, len(files), IMPACTED_CHUNK):
        chunk = files[i : i + IMPACTED_CHUNK]
        proc = vc.run(
            [
                PY,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "-rfE",
                "--continue-on-collection-errors",
                *extra,
                *chunk,
            ],
            tree,
            timeout=IMPACTED_TIMEOUT_S,
        )
        found = [
            ln.split()[1]
            for ln in proc.stdout.splitlines()
            if ln.startswith(("FAILED ", "ERROR ")) and len(ln.split()) > 1 and vc._is_pytest_id(ln.split()[1])
        ]
        if proc.returncode not in (0, 1, 5) and not found:
            found.append(f"{chunk[0]}..(+{len(chunk) - 1})::<rc={proc.returncode}>")
        failures += found
    return sorted(set(failures))


def split_failures(head_fail: list[str], base_fail: set[str]) -> tuple[list[str], list[str]]:
    """(새 실패, 기존 실패) — 기준(base)에서도 같은 id 로 실패한 것만 기존 실패. 기준에 없는 시험 파일의 실패는 새 실패."""
    return [f for f in head_fail if f not in base_fail], [f for f in head_fail if f in base_fail]


def impacted_section(base: str, base_tree: Path, workers: int, max_files: int) -> dict:
    """영향 시험 실행 전체 흐름. 결과 dict: status(empty|list_only|run), files, new_failures, existing_failures, notice."""
    files = impacted_test_files(base, "HEAD", ROOT)
    plan = plan_impacted(files, max_files)
    out: dict = {"status": plan, "files": files, "new_failures": [], "existing_failures": [], "notice": ""}
    if plan != "run":
        return out
    if len(files) >= IMPACTED_SLOT_NOTICE:
        out["notice"] = f"영향 시험 파일 {len(files)}개 — 무거운 작업이니 HEAVY_SLOT 슬롯을 잡고 돌리세요."
    head_fail = run_impacted(ROOT, files, workers)
    # 기준(base) 비교는 실패한 파일만이 아니라 같은 영향 시험 묶음 전체(기준에 있는 것)를 다시 돈다 — 시험끼리의 순서·상태 간섭으로
    # 묶음 안에서만 실패하는 기존 실패(2026-10-08 root-cleanup: kakao·message_classifier 21건)를 '새 실패'로 오판하지 않기 위해서다.
    in_base = [f for f in files if (base_tree / f).is_file()]
    base_fail = set(run_impacted(base_tree, in_base, workers)) if head_fail and in_base else set()
    out["new_failures"], out["existing_failures"] = split_failures(head_fail, base_fail)
    return out


def gate_results(tree: Path) -> dict[str, bool]:
    res = {"registry_sync": _run(["tools/code_map/registry_sync.py", "--check"], tree).returncode == 0}
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


def _impacted_text(r: dict) -> str:
    n = len(r["files"])
    if r["status"] == "empty":
        return "영향 시험: 대상 0개 — 실행하지 않음(빈 목록을 전체 실행으로 바꾸지 않는다)"
    if r["status"] == "list_only":
        lines = [f"영향 시험: 시험 파일 {n}개로 상한 초과 — 실행하지 않고 목록만 표시"]
        lines += [f"  - {f}" for f in r["files"][:PREFLIGHT_SHOW]]
        if n > PREFLIGHT_SHOW:
            lines.append(f"  ... 외 {n - PREFLIGHT_SHOW}개 (전체는 --json)")
        return chr(10).join(lines)
    lines = [
        f"영향 시험: 시험 파일 {n}개 실행 — 새 실패 {len(r['new_failures'])}건, "
        f"기존 실패 {len(r['existing_failures'])}건(기준에서도 실패, 판정 제외)"
    ]
    if r["notice"]:
        lines.insert(0, r["notice"])
    lines += [f"  새 실패: {f}" for f in r["new_failures"][:PREFLIGHT_SHOW]]
    lines += [f"  기존 실패: {f}" for f in r["existing_failures"][:PREFLIGHT_SHOW]]
    return chr(10).join(lines)


def main(argv: list[str] | None = None) -> int:  # noqa: C901, PLR0915 - 이동 전부터 있던 기존 복잡도, 이동과 무관
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/master", help="비교 기준 ref (기본 origin/master)")
    ap.add_argument("--no-runcheck", action="store_true", help="LIVE import 실패(runcheck R0) 측정을 건너뛴다")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--impacted-tests", action="store_true", help="바뀐 모듈에 닿는 시험 파일만 실행(새 실패만 판정)")
    ap.add_argument("--max-test-files", type=int, default=IMPACTED_MAX_FILES, help="이보다 많으면 실행하지 않고 목록만")
    ap.add_argument("--workers", type=int, default=1, help=f"pytest-xdist 워커 수(최대 {IMPACTED_MAX_WORKERS})")
    a = ap.parse_args(argv)
    runcheck = not a.no_runcheck

    from tools.verify_change import (
        _checkout,  # 기준 트리를 임시 worktree 로 꺼내 head 의 code_map 도구를 넣는다(같은 잣대)
    )

    head_m = measure_tree(ROOT, runcheck)
    head_b = baseline_sizes(ROOT)
    impacted: dict | None = None
    with tempfile.TemporaryDirectory(prefix="merge_step_base_") as td:
        base_tree = Path(td) / "base"
        if not _checkout(a.base, base_tree):
            print(f"기준 ref 를 꺼내지 못했다: {a.base}", file=sys.stderr)
            return 2
        try:
            base_m = measure_tree(base_tree, runcheck)
            base_b = baseline_sizes(base_tree)
            if a.impacted_tests:
                impacted = impacted_section(a.base, base_tree, a.workers, a.max_test_files)
        finally:
            _git(ROOT, "worktree", "remove", "--force", str(base_tree))

    rows: list[tuple[str, int | None, int | None, str]] = [
        (k, base_m[k], head_m[k], _verdict(base_m[k], head_m[k])) for k in head_m
    ]
    rows += [(k, base_b[k], head_b[k], _verdict(base_b[k], head_b[k])) for k in head_b]
    gates = gate_results(ROOT)
    g5 = _run(["tools/repo_gates/root_calc_gate.py", "--check-diff", a.base, "HEAD"], ROOT).returncode == 0
    gates["G5 root_calc"] = g5
    blocking = preflight_blocking(a.base, "HEAD", ROOT)

    failed = [r[0] for r in rows if r[3] == "증가"] + [k for k, ok in gates.items() if not ok]
    if blocking:
        failed.append(f"move_preflight 막음 {len(blocking)}건")
    if impacted and impacted["new_failures"]:
        failed.append(f"영향 시험 새 실패 {len(impacted['new_failures'])}건")

    if a.json:
        print(
            json.dumps(
                {"rows": rows, "gates": gates, "preflight_blocking": blocking, "impacted": impacted, "failed": failed},
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
        if impacted is not None:
            print()
            print(_impacted_text(impacted))
        print()
        print("결과: " + ("통과" if not failed else "실패 — " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
