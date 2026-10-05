# module_category: audit
# primary_trade: common
"""변경 검증(로컬 CI) — 작업 트리의 변경을 기준 커밋과 같은 방식으로 재서 PASS/FAIL 판정.

판정 항목(모두 기준 대비 '나빠지지 않을 것')
  1 pytest 수집 오류   2 LIVE 모듈 import 실패   3 서버 라우트 수
  4 영향 테스트 실패(코드맵 역방향으로 바뀐 파일에 닿는 테스트만)   5 층간 위반 수   6 모듈 순환 수
  7 바뀐 파이썬 파일 ruff 0   8 폴더 깊이가 바뀐 이동 파일의 위치의존 줄(__file__·상대 import) 미조정 0
  9 지도↔골격 대조: 분류 정본에만 있는 파일·정본 누락 코드 파일·금지 import·선언 모듈의 없는 경로
기준값은 기준 커밋을 임시 폴더(git worktree)에 꺼내 같은 명령으로 잰다.
저장소별 설정은 configs/verify_change.json(없으면 기본값) — 다른 저장소에서도 그대로 쓰기 위함.

사용:
    python scripts/ops/verify_change.py --base master            # 현재 작업트리 vs master
    python scripts/ops/verify_change.py --base master --head stage/x   # 커밋끼리(미커밋 WIP 제외, 권장)
    python scripts/ops/verify_change.py --base master --json out.json
종료코드 0 = PASS, 1 = FAIL, 2 = 기준 트리 생성 실패. 결과표는 커밋 메시지에 붙일 수 있게 markdown 으로 출력.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

# 2026-09-30 수정(defect_index 신규 항목): "바뀐 파일 ruff" 체크가 head 쪽 ruff 결과를
# base 와 비교 없이 그대로 "새로 생긴 문제"로 보고해, 손 안 댄 줄의 기존(pre-existing)
# 위반까지 전부 이번 커밋 탓으로 돌려 CI를 FAIL시키고 있었다(실측: dry_run_approved_
# browser_instruction_api.py 에 docstring 5줄만 추가한 커밋이 그 함수의 기존 복잡도
# 위반 3건 때문에 CI FAIL — 로컬 pre-commit 훅은 이미 ruff_new_only_gate.py 로 같은
# 문제를 정확히 처리하고 있어 그 로직을 재사용한다.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ruff_new_only_gate import changed_lines_between  # type: ignore[import-not-found]  # noqa: E402

ENV = {
    **os.environ,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "AUTH_ENABLED": "false",
    # 측정 중 테스트가 실제 브라우저(CDP)를 띄우지 않게 — browser_sandbox_gate 의 차단 표시.
    # 옛 기준 커밋에는 새 표시가 없으므로 기존 표시(CODEX_SANDBOX_NETWORK_DISABLED)도 함께 켠다.
    "HAEHAN_NO_BROWSER_LAUNCH": "1",
    "CODEX_SANDBOX_NETWORK_DISABLED": "1",
}


def kill_leftovers(path_marker: str) -> list[int]:
    """측정 폴더에서 떠서 남은 프로세스(분리 실행된 데몬 등) 종료 — 명령줄에 폴더 경로가 든 것만."""
    if os.name != "nt":
        return []
    # 자기 자신과 조상(이 검증을 띄운 셸 등)은 제외 — 조상의 명령줄에 표시 문자열이 들어 있어도 죽이지 않는다
    ps = (
        "$all = Get-CimInstance Win32_Process; $keep = @{}; $cur = [int]$env:VC_SELF;"
        " while ($cur -and -not $keep.ContainsKey($cur)) { $keep[$cur] = 1;"
        " $cur = ($all | Where-Object ProcessId -eq $cur | Select-Object -First 1).ParentProcessId }"
        " $all | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:VC_MARK)"
        " -and -not $keep.ContainsKey([int]$_.ProcessId) -and $_.ProcessId -ne $PID }"
        " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    env = {**os.environ, "VC_MARK": path_marker, "VC_SELF": str(os.getpid())}
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    ).stdout
    return [int(x) for x in out.split() if x.isdigit()]


CONFIG = ROOT / "configs" / "verify_change.json"
CFG = {"route_check": None, "ruff_config": None, "test_timeout": 120}
if CONFIG.exists():
    CFG.update(json.loads(CONFIG.read_text(encoding="utf-8")))
TEST_TIMEOUT = int(CFG["test_timeout"])  # 테스트 파일 하나당 상한(멈추는 테스트 차단)
CHUNK = int(CFG.get("test_chunk", 25))  # 한 pytest 프로세스에 묶는 테스트 파일 수
CODE_EXT = tuple(CFG.get("code_ext", [".py"]))  # 분류 정본에 있어야 하는 코드 파일 확장자


def run(cmd: list[str], cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=ENV
    )


def changed_files(base: str, head: str | None) -> list[str]:
    if head:  # 커밋끼리 비교 — 작업트리의 다른 작업분(미커밋 WIP)이 섞이지 않는다
        return sorted(set(run(["git", "diff", "--name-only", f"{base}...{head}"], ROOT).stdout.split()))
    out = run(["git", "diff", "--name-only", base], ROOT).stdout.split()
    out += run(["git", "ls-files", "--others", "--exclude-standard"], ROOT).stdout.split()
    return sorted(set(out))


LOCATION_DEP = ("__file__", "from .", "import .")  # 파일 위치에 따라 뜻이 바뀌는 코드


def renames(base: str, head: str | None) -> dict[str, str]:
    """이동(R)된 파일 {새 경로: 옛 경로} — 이동만으로 '새 문제'가 생긴 것처럼 보이는 것을 막는 데 쓴다."""
    diff = ["git", "diff", "-M", "--name-status", base] + ([head] if head else [])
    out = {}
    for ln in run(diff, ROOT).stdout.splitlines():
        parts = ln.split("\t")
        if parts[0].startswith("R") and len(parts) == 3:
            out[parts[2]] = parts[1]
    return out


def _mod_dir(path: str) -> str:
    return "/".join(path.split("/")[:-1][:3])


def normalize_renamed(after: dict, moved: dict[str, str]) -> dict:
    """변경 후 층간 위반의 경로를 옛 경로로 되돌린 사본 — 이동만으로 '새 위반'처럼 보이는 것을 막는다."""
    if not moved:
        return after
    viol = set()
    for v in after["violations"]:
        s, t = v.split(" -> ")
        viol.add(f"{moved.get(s, s)} -> {moved.get(t, t)}")
    return {**after, "violations": sorted(viol)}


def moved_location_deps(base: str, head: str | None) -> list[str]:
    """폴더 깊이가 바뀐 이동 파일에서, 위치 의존 줄(__file__ 경로·상대 import)이 손대지 않은 채 남은 곳.

    실제 사례(허브 분리 1단계): import·테스트는 모두 통과했는데 users.db 경로가 한 칸 어긋나 가입·로그인이 깨질 뻔함.
    줄이 고쳐졌으면(내용이 달라졌으면) 조정한 것으로 보고 넘긴다 — 남은 것은 사람이 확인할 후보.
    """
    diff = ["git", "diff", "-M", "--name-status", base] + ([head] if head else [])
    out = []
    moved = renames(base, head)
    for ln in run(diff, ROOT).stdout.splitlines():
        parts = ln.split("\t")
        if not parts[0].startswith("R") or len(parts) != 3 or not parts[2].endswith(".py"):
            continue
        old, new = parts[1], parts[2]
        if old.count("/") == new.count("/"):
            continue
        old_lines = set(run(["git", "show", f"{base}:{old}"], ROOT).stdout.splitlines())
        new_src = run(["git", "show", f"{head}:{new}"], ROOT).stdout if head else (ROOT / new).read_text("utf-8")
        for i, line in enumerate(new_src.splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or not any(k in s for k in LOCATION_DEP):
                continue
            if line in old_lines and not _same_relative_target(s, old, new, base, head, moved):
                out.append(f"{new}:{i}: {s[:100]}")
    return out


def _resolve_rel(stmt: str, file: str) -> list[str]:
    """'from .x import y' / 'from . import x' → 가리킬 수 있는 파일 경로 후보(모듈·패키지)."""
    parts = stmt.split()
    if len(parts) < 4 or parts[0] != "from" or not parts[1].startswith("."):
        return []
    spec = parts[1]
    dots = len(spec) - len(spec.lstrip("."))
    base_dir = file.split("/")[:-1]
    if dots > 1:
        base_dir = base_dir[: len(base_dir) - (dots - 1)]
    mod = spec.lstrip(".")
    names = [mod] if mod else [n.strip(" ,()") for n in stmt.split(" import ", 1)[1].split(",")]
    out = []
    for n in names:
        n = n.split(" as ")[0].strip()
        if n:
            stem = "/".join(base_dir + n.split("."))
            out += [stem + ".py", stem + "/__init__.py"]
    return out


def _same_relative_target(stmt: str, old: str, new: str, base: str, head: str | None, moved: dict[str, str]) -> bool:
    """상대 import 가 이동 전후에 '같은 파일'을 가리키면(함께 이동한 형제 등) 미조정이 아니다."""
    if "__file__" in stmt or not stmt.startswith("from ."):
        return False

    def exists(ref: str | None, path: str) -> bool:
        if ref is None:
            return (ROOT / path).exists()
        return run(["git", "cat-file", "-e", f"{ref}:{path}"], ROOT).returncode == 0

    olds = [t for t in _resolve_rel(stmt, old) if exists(base, t)]
    news = [t for t in _resolve_rel(stmt, new) if exists(head, t)]
    return bool(olds) and len(olds) == len(news) and all(moved.get(n, n) == o for n, o in zip(news, olds, strict=False))


def _checkout(ref: str, dest: Path) -> bool:
    """ref 를 임시 worktree 로 꺼내고 현재의 측정 도구를 넣는다(같은 잣대로 재기 위함)."""
    if run(["git", "worktree", "add", "--detach", str(dest), ref], ROOT).returncode != 0:
        return False
    shutil.copytree(ROOT / "scripts/ops/code_map", dest / "scripts/ops/code_map", dirs_exist_ok=True)
    return True


def _measure_collect_errors(tree: Path) -> list[str]:
    col = run([PY, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], tree)
    return sorted(ln.split()[1] for ln in col.stdout.splitlines() if ln.startswith("ERROR "))


def _measure_code_map_and_import_fail(tree: Path) -> tuple[dict, dict | None, list[str]]:
    """code_map 빌드 + classify + runcheck 실행 후 (map.json, 커밋된 정본, import_fail 목록)."""
    run([PY, "scripts/ops/code_map/build.py"], tree)
    reg_p = tree / "configs/module_registry.json"
    # 커밋된 정본(골격) — classify.py 가 다시 쓰기 전 상태로 대조해야 '정본 갱신 누락'이 보인다
    committed = json.loads(reg_p.read_text(encoding="utf-8"))["files"] if reg_p.exists() else None
    if (tree / "scripts/ops/code_map/classify.py").exists():
        run([PY, "scripts/ops/code_map/classify.py"], tree)
    run([PY, "scripts/ops/code_map/runcheck.py", "--levels", "R0"], tree, timeout=1800)
    led_p = tree / "data/code_map/run_ledger.json"
    led = json.loads(led_p.read_text(encoding="utf-8"))["nodes"] if led_p.exists() else {}
    m = json.loads((tree / "data/code_map/map.json").read_text(encoding="utf-8"))
    import_fail = sorted(p for p, v in led.items() if v.get("R0", {}).get("status") == "FAIL")
    return m, committed, import_fail


def _route_check_for(tree: Path) -> str | None:
    """그 트리 자신의 configs/verify_change.json 의 route_check.

    서버 진입점 모듈 이름을 바꾸는 변경(예: server.py → asgi.py)에서 기준 트리에 '변경 후' 명령을
    돌리면 기준 측정이 항상 실패(`?`)해 "라우트 수 변경"으로 오판된다(2026-09-30 PR #55).
    트리에 설정이 없거나 읽을 수 없으면 현재 설정으로 되돌린다.
    """
    cfg_path = tree / "configs" / "verify_change.json"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8")).get("route_check") or CFG["route_check"]
    except (OSError, ValueError):
        return CFG["route_check"]


def _measure_routes(tree: Path) -> str:
    check = _route_check_for(tree)
    if check:  # 서버 앱의 라우트 수를 출력하는 파이썬 한 줄
        routes = run([PY, "-c", check], tree)
        return (routes.stdout.strip().splitlines() or ["?"])[-1]
    return "-"


def _measure_violations(tree: Path, m: dict) -> list[str]:
    """층간 위반 — configs/module_registry.json 의 allowed_deps 기준."""
    reg_p = tree / "configs/module_registry.json"
    viol = set()
    if reg_p.exists():
        reg = json.loads(reg_p.read_text(encoding="utf-8"))
        files, allowed = reg["files"], reg.get("allowed_deps", {})
        for s, ts in m.get("import_edges", m["all_edges"]).items():  # 실제 import 만(문자열 언급 제외)
            if s in files and not s.endswith("__init__.py") and files[s]["layer"] in allowed:
                for t in ts:
                    if t in files and not t.endswith("__init__.py"):
                        lt = files[t]["layer"]
                        if lt in allowed and lt not in allowed[files[s]["layer"]]:
                            viol.add(f"{s} -> {t}")
    return sorted(viol)


def _measure_skeleton_and_cycles(tree: Path, m: dict, committed: dict | None) -> tuple[list[str], list[str]]:
    """지도 ↔ 골격 대조(분류 정본이 실제 파일과 어긋난 곳) + 모듈 순환·금지 import·선언 모듈 경로."""
    skel = []
    if committed is not None:
        code = {p for p in m.get("all_nodes", {}) if p.endswith(CODE_EXT)}
        skel += [f"정본에만 있음(파일 없음): {p}" for p in committed if not (tree / p).exists()]
        skel += [f"정본 누락(분류 안 됨): {p}" for p in sorted(code - set(committed))]
    cycles: list[str] = []
    if (tree / "scripts/ops/code_map/modules.py").exists():
        run([PY, "scripts/ops/code_map/modules.py"], tree)
        cc = json.loads((tree / "data/code_map/modules.json").read_text(encoding="utf-8"))["crosscheck"]
        cycles = [" <-> ".join(c) for c in cc["module_cycles"]]
        skel += [f"금지 import: {h['src']} -> {h['dst']}" for h in cc.get("forbidden_import_hits", [])]
        for d in cc.get("declared_modules", []):
            skel += [f"선언 모듈 {d['name']} 경로 없음: {x}" for x in d.get("missing_paths", [])]
    return sorted(set(skel)), cycles


def _measure_affected_test_results(tree: Path, tests: list[str]) -> tuple[list[str], list[str]]:
    """영향 테스트 — CHUNK 파일씩 묶어 한 프로세스로(속도), 묶음이 시간 상한을 넘으면 그 묶음만 파일별로 재실행(멈춤 차단)."""
    present = [t for t in tests if (tree / t).exists()]
    fails, timeouts = [], []
    for i in range(0, len(present), CHUNK):
        chunk = present[i : i + CHUNK]
        try:
            fails += _pytest(tree, chunk, TEST_TIMEOUT * len(chunk) // 2 + TEST_TIMEOUT)
        except subprocess.TimeoutExpired:
            for t in chunk:
                try:
                    fails += _pytest(tree, [t], TEST_TIMEOUT)
                except subprocess.TimeoutExpired:
                    timeouts.append(t)
    return sorted(set(fails)), timeouts


def measure(tree: Path, tests: list[str]) -> dict:
    """한 작업트리에서 판정 항목을 잰다.

    2026-09-29 STD-08(복잡도) 리팩터: 각 판정 항목을 _measure_*() 함수로 분리(순서·조건·
    문자열 그대로, m/committed 등 다음 단계가 쓰는 값은 반환해 넘긴다).
    """
    r: dict = {}
    r["collect_errors"] = _measure_collect_errors(tree)
    m, committed, r["import_fail"] = _measure_code_map_and_import_fail(tree)
    r["routes"] = _measure_routes(tree)
    r["violations"] = _measure_violations(tree, m)
    r["skeleton"], r["cycles"] = _measure_skeleton_and_cycles(tree, m, committed)
    r["test_failures"], r["test_timeouts"] = _measure_affected_test_results(tree, tests)
    return r


def _is_pytest_id(token: str) -> bool:
    """pytest 요약 줄의 id 인가 — 'path::test' 이거나 수집 오류의 'path.py'. 로그 줄의 '모듈:파일.py:줄'은 아니다."""
    return "::" in token or token.endswith(".py")


def _pytest(tree: Path, files: list[str], timeout: int) -> list[str]:
    """테스트 파일 묶음 실행 → 실패 id 목록. 수집 오류가 나도 나머지는 계속 돈다."""
    p = run(
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE", "--continue-on-collection-errors", *files],
        tree,
        timeout=timeout,
    )
    # pytest 요약 줄("FAILED path::test", "ERROR path.py")만 센다. 실패한 시험의 캡처 로그
    # ("ERROR    모듈:파일.py:줄 메시지")도 같은 접두어라 그대로 세면 로그 줄이 가짜 실패 id 로 잡힌다.
    out = [
        ln.split()[1]
        for ln in p.stdout.splitlines()
        if ln.startswith(("FAILED ", "ERROR ")) and len(ln.split()) > 1 and _is_pytest_id(ln.split()[1])
    ]
    if p.returncode not in (0, 1, 5) and not out:
        out.append(f"{files[0]}..(+{len(files) - 1})::<rc={p.returncode}>")
    return out


def affected_tests(changed: list[str]) -> list[str]:
    """코드맵 역방향 BFS — 바뀐 파일에 (간접적으로라도) 닿는 테스트 파일."""
    m = json.loads((ROOT / "data/code_map/map.json").read_text(encoding="utf-8"))
    rev: dict[str, set[str]] = {}
    for s, ts in m["all_edges"].items():
        for t in ts:
            rev.setdefault(t, set()).add(s)
    seen, q = set(changed), deque(changed)
    while q:
        cur = q.popleft()
        for s in rev.get(cur, ()):
            if s not in seen:
                seen.add(s)
                q.append(s)

    def is_test(p: str) -> bool:
        n = p.rsplit("/", 1)[-1]
        return p.endswith(".py") and (p.startswith("tests/") or "/tests/" in p) and n.startswith("test_")

    return sorted(p for p in seen if is_test(p))


def _diff_key(key: str, before: dict, after: dict, after_n: dict, moved: dict[str, str], receiving: set) -> list[str]:
    """new() 클로저 분리(2026-09-29 STD-08) — before/after/moved/receiving 을 인자로 받는다."""
    if key == "violations":
        return sorted(set(after_n[key]) - set(before[key]))
    if key == "skeleton":  # 이동 파일은 옛 경로로 바꿔 비교

        def old(x: str) -> str:
            for n, o in moved.items():
                x = x.replace(n, o)
            return x

        return sorted({old(x) for x in after.get(key, [])} - set(before.get(key, [])))
    if key == "cycles":
        raw = sorted(set(after[key]) - set(before[key]))
        extra = [c for c in raw if not receiving & set(c.split(" <-> "))]
        if len(after[key]) > len(before[key]):
            extra += [f"순환 수 증가 {len(before[key])} → {len(after[key])} (이동 폴더 관련: {len(raw) - len(extra)})"]
        return extra
    return sorted(set(after[key]) - set(before[key]))


def _build_verify_report(
    a: argparse.Namespace,
    changed: list[str],
    tests: list[str],
    measurements: dict,
) -> tuple[bool, str]:
    """checks 표 + 새 문제 섹션 조립 — main() 의 리포트 조립부 분리(2026-09-29 STD-08:
    PLR0913=9>6 라서 before/after/ruff_errors/loc_deps/moved/receiving 을 dict 하나로 묶었다)."""
    before = measurements["before"]
    after = measurements["after"]
    ruff_errors = measurements["ruff_errors"]
    loc_deps = measurements["loc_deps"]
    moved = measurements["moved"]
    receiving = measurements["receiving"]
    after_n = normalize_renamed(after, moved)

    def new(key: str) -> list[str]:
        return _diff_key(key, before, after, after_n, moved, receiving)

    new_timeouts = [f"TIMEOUT {t}" for t in after["test_timeouts"] if t not in before["test_timeouts"]]
    if a.expect_routes:  # 기준서가 약속한 라우트 수로 판정(의도된 추가·삭제)
        ok_routes = str(after["routes"]) == str(a.expect_routes)
        route_diff = [] if ok_routes else [f"라우트 수 {after['routes']} ≠ 기준서 약속 {a.expect_routes}"]
    else:
        route_diff = [] if before["routes"] == after["routes"] else ["라우트 수 변경"]
    checks = [
        ("pytest 수집 오류", len(before["collect_errors"]), len(after["collect_errors"]), new("collect_errors")),
        ("LIVE import 실패", len(before["import_fail"]), len(after["import_fail"]), new("import_fail")),
        ("서버 라우트", before["routes"], after["routes"], route_diff),
        (
            f"영향 테스트 실패({len(tests)}파일)",
            len(before["test_failures"]),
            len(after["test_failures"]),
            new("test_failures") + new_timeouts,
        ),
        ("층간 위반", len(before["violations"]), len(after["violations"]), new("violations")),
        ("모듈 순환", len(before["cycles"]), len(after["cycles"]), new("cycles")),
        ("지도↔골격 대조", len(before.get("skeleton", [])), len(after.get("skeleton", [])), new("skeleton")),
        ("바뀐 파일 ruff", "-", len(ruff_errors), ruff_errors),
        ("audit-kit 기준서(바뀐 파일)", "-", len(measurements["kit_errors"]), measurements["kit_errors"]),
        ("이동 파일 위치의존 미조정", "-", len(loc_deps), loc_deps),
    ]
    ok = all(not c[3] for c in checks)
    lines = [
        f"## 변경 검증: {'PASS' if ok else 'FAIL'} (기준 {a.base} → {a.head or '작업트리'}, 바뀐 파일 {len(changed)})",
        "",
        "| 항목 | 기준 | 변경 후 | 새로 생긴 문제 |",
        "|---|---|---|---|",
    ]
    for name, b, af, nw in checks:
        lines.append(f"| {name} | {b} | {af} | {len(nw)} |")
    for name, _, _, nw in checks:
        if nw:
            lines += ["", f"### {name} — 새 문제", *[f"- {x}" for x in nw[:30]]]
    return ok, "\n".join(lines)


def _audit_kit_new_findings(py_changed: list[str], base_tree: Path, head_tree: Path) -> tuple[list[str], str]:
    """audit-kit 의 파일 단위 개발 기준서·순환 검사에서 "이번 변경이 새로 만든" 문제 (기준 트리 결과와의 차이).

    audit-kit 이 없는 PC·CI 에서는 검사를 생략하고 그 사실을 알린다(설치된 PC 에서는 필수: 새 문제가 있으면 FAIL).
    """
    from audit_kit_gate import (  # scripts/ops 안의 형제 모듈
        find_audit_kit,
        finding_key,
        is_real_kit,
        mypy_new,
        mypy_python,
        raw_findings,
    )

    kit = find_audit_kit(ROOT)
    if kit is None or not py_changed:
        return [], "[verify] audit-kit 를 찾지 못해 기준서 검사를 생략합니다 (AUDIT_KIT_BIN 으로 위치 지정)" if kit is None else ""

    def one(rel: str) -> list[str]:
        head = raw_findings(kit, head_tree / rel, head_tree)
        if head is None:
            return [f"{rel}: audit-kit 검사를 하지 못했습니다"]
        base = raw_findings(kit, base_tree / rel, base_tree) if (base_tree / rel).exists() else []
        known = {finding_key(x) for x in (base or [])}
        out = [f"{rel}: {x}" for x in head if finding_key(x) not in known]
        py = mypy_python(kit)
        if py is not None:  # mypy: 기준 트리의 같은 파일에 없던 타입 오류만
            typed, why = mypy_new(py, head_tree / rel, base_tree / rel if (base_tree / rel).exists() else None, head_tree)
            out += [f"{rel}: {x}" for x in typed] + ([f"{rel}: {why}"] if why else [])
        return out

    with ThreadPoolExecutor(4) as pool:
        found = [item for items in pool.map(one, py_changed) for item in items]
    if is_real_kit(kit) and mypy_python(kit) is None:  # 진짜 audit-kit 인데 mypy 를 돌릴 파이썬이 없다 = 타입 검사가 조용히 빠진다 → 실패로 취급
        found.append("mypy 실행 환경(audit-kit 가상환경의 python)을 찾지 못해 타입 검사를 할 수 없습니다 — audit-kit 를 다시 설치하세요")
    return found, ""


def _new_ruff_findings(
    ruff: subprocess.CompletedProcess | None, head_tree: Path, base_ref: str, head_ref: str | None
) -> list[str]:
    """head 쪽 ruff(JSON) 결과에서 "이번 커밋으로 새로 생긴" finding만 골라 문자열로 반환.

    로컬 pre-commit 훅의 ruff_new_only_gate.py 와 동일 원칙(git diff hunk 기준 바뀐 줄
    번호에 걸리는 finding만 new로 판정) — 단순히 head 쪽 ruff 결과를 통째로 쓰면 그
    파일의 기존 부채까지 전부 이번 커밋 탓이 된다(2026-09-30 실측 발견 버그).
    """
    try:
        findings = json.loads(ruff.stdout) if ruff and ruff.stdout else []
    except json.JSONDecodeError:
        findings = []
    changed_lines = changed_lines_between(base_ref, head_ref)
    result = []
    for f in findings:
        try:
            rel = Path(f["filename"]).resolve().relative_to(head_tree).as_posix()
        except ValueError:
            rel = f["filename"]
        row = f.get("location", {}).get("row")
        # 2026-09-30 pre-push AI 리뷰 지적 반영: row 가 None(위치를 특정 못하는 ruff
        # 진단, 드물지만 가능)이면 "None in set[int]"가 항상 False라 조용히 pre-existing
        # 으로 숨겨져 진짜 새 문제를 놓칠 위험이 있었다 — 위치 불명은 안전한 쪽(새 문제로
        # 간주해 사람이 보게)으로 처리한다.
        is_new = row is None or changed_lines is None or (rel in changed_lines and row in changed_lines[rel])
        if is_new:
            result.append(f"{rel}:{row}:{f.get('location', {}).get('column')}: {f.get('code')} {f.get('message')}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="master", help="비교 기준 커밋/브랜치")
    ap.add_argument("--head", help="비교 대상 커밋/브랜치(생략 = 현재 작업트리). 지정하면 미커밋 WIP 가 섞이지 않음")
    ap.add_argument(
        "--expect-routes",
        help="의도된 라우트 수(기준서에 적힌 값). 지정하면 '변경 후 = 이 값'일 때 통과, 기준과 같아야 한다는 규칙 대신",
    )
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    a = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    changed = changed_files(a.base, a.head)
    loc_deps = moved_location_deps(a.base, a.head)
    run([PY, "scripts/ops/code_map/build.py"], ROOT)
    tests = affected_tests(changed)
    tmp = Path(tempfile.mkdtemp(prefix="verify_base_"))
    trees = [tmp / "base"] + ([tmp / "head"] if a.head else [])
    try:
        for ref, dest in zip([a.base, a.head], trees, strict=False):
            if not _checkout(ref, dest):
                print(f"[verify] 트리 생성 실패: {ref}")
                return 2
        head_tree = trees[1] if a.head else ROOT
        # 작업트리를 잴 때 classify.py 가 추적 파일(분류 정본)을 다시 쓰므로 원본을 보관했다가 되돌린다
        reg = ROOT / "configs/module_registry.json"
        reg_bytes = reg.read_bytes() if head_tree == ROOT and reg.exists() else None
        # 기준·변경 후는 서로 다른 폴더라 동시에 잰다(대기 시간 절반)
        try:
            with ThreadPoolExecutor(2) as ex:
                fb, fa = ex.submit(measure, trees[0], tests), ex.submit(measure, head_tree, tests)
                before, after = fb.result(), fa.result()
        finally:
            if reg_bytes is not None:
                reg.write_bytes(reg_bytes)
        py_changed = [c for c in changed if c.endswith(".py") and (head_tree / c).exists()]
        kit_errors, kit_note = _audit_kit_new_findings(py_changed, trees[0], head_tree)
        if kit_note:
            print(kit_note)
        ruff_cfg = ["--config", str(ROOT / CFG["ruff_config"])] if CFG["ruff_config"] else []
        ruff = (
            run(
                [PY, "-m", "ruff", "check", *ruff_cfg, "--no-cache", "--output-format", "json", *py_changed],
                head_tree,
            )
            if py_changed
            else None
        )
    finally:
        killed = kill_leftovers(tmp.name)  # 측정 폴더 경로가 명령줄에 든 잔여 프로세스
        if killed:
            print(f"[verify] 측정 중 남은 프로세스 {len(killed)}개 종료: {killed}")
        for dest in trees:
            run(["git", "worktree", "remove", "--force", str(dest)], ROOT)
        shutil.rmtree(tmp, ignore_errors=True)
    ruff_errors = _new_ruff_findings(ruff, head_tree, a.base, a.head)

    moved = renames(a.base, a.head)
    # 순환은 모듈(폴더) 단위라 이동을 받은 폴더가 끼면 이름만 바뀐 것과 진짜 새 순환을 가를 수 없다
    # → 그런 순환은 '순환 수가 늘었을 때만' FAIL, 이동과 무관한 폴더끼리의 새 순환은 항상 FAIL
    receiving = {_mod_dir(n) for n in moved}
    measurements = {
        "before": before,
        "after": after,
        "ruff_errors": ruff_errors,
        "kit_errors": kit_errors,
        "loc_deps": loc_deps,
        "moved": moved,
        "receiving": receiving,
    }
    ok, report = _build_verify_report(a, changed, tests, measurements)
    print(report)
    if a.json:
        Path(a.json).write_text(
            json.dumps(
                {
                    "ok": ok,
                    "changed": changed,
                    "tests": tests,
                    "before": before,
                    "after": after,
                    "ruff": ruff_errors,
                    "report": report,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
