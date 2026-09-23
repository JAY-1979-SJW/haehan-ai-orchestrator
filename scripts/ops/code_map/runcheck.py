# module_category: audit
# primary_trade: common
"""코드맵 실행 점검 — 지도의 노드를 실제로 돌려 보고 결과를 실행 기록(run_ledger)에 남긴다.

단계
- R0 import : 파이썬 모듈을 불러오기만 한다(최상단에서 바로 실행되는 스크립트는 SKIP).
- R1 help   : argparse CLI 를 `--help` 로만 실행. main() 에서 parse_args 이전에 다른 동작이 없는
              파일만(문법 트리 확인), 이름에 발송·게시·삭제·결제 계열 단어가 있으면 SKIP.
발송·게시·결제·삭제·유료 AI·로그인 조작은 자동 실행하지 않는다.

사용:
    python scripts/ops/code_map/runcheck.py --levels R0,R1
출력: data/code_map/run_ledger.json (단계별로 병합 저장, git 미추적)
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.code_map import scan  # noqa: E402

MAP = ROOT / "data" / "code_map" / "map.json"
LEDGER = ROOT / "data" / "code_map" / "run_ledger.json"
RISKY_NAME = re.compile(
    r"send|publish|post_|_post|upload|delete|remove|purge|pay|billing|fax|mail_send|sms|kakao_send|"
    r"deploy|login|signup|register|submit|write|push|reset|drop|migrate",
    re.I,
)
ARGPARSE_SETUP = {
    "ArgumentParser",
    "add_argument",
    "add_mutually_exclusive_group",
    "add_subparsers",
    "add_parser",
    "set_defaults",
    "add_argument_group",
    "reconfigure",
    "RawTextHelpFormatter",
}
CHILD_ENV = {
    **os.environ,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "AUTH_ENABLED": "false",
    "HAEHAN_RUNCHECK": "1",  # 코드가 원하면 점검 모드를 감지할 수 있게
}
IMPORT_CHILD = r"""
import importlib.util, json, sys, time, warnings, traceback
warnings.simplefilter("ignore")
root = sys.argv[1]
sys.path.insert(0, root)
out = {}
for rel in json.loads(sys.argv[2]):
    t = time.time()
    try:
        p = root + "/" + rel
        parts = rel[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        mod = ".".join(parts)
        if "-" in mod:  # apps/<hyphen-name>/... : 앱 폴더 기준으로 경로 로드
            app_root = root + "/" + "/".join(rel.split("/")[:2])
            if app_root not in sys.path:
                sys.path.insert(0, app_root)
            spec = importlib.util.spec_from_file_location("rc_" + str(abs(hash(rel))), p)
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        else:
            importlib.import_module(mod)
        out[rel] = ["OK", round(time.time() - t, 2), ""]
    except BaseException as e:
        out[rel] = ["FAIL", round(time.time() - t, 2), (type(e).__name__ + ": " + str(e))[:300]]
print("@@RC@@" + json.dumps(out))
"""


def _load_map() -> dict:
    return json.loads(MAP.read_text(encoding="utf-8"))


def _tree(rel: str) -> ast.Module | None:
    try:
        return ast.parse((ROOT / rel).read_text(encoding="utf-8-sig", errors="replace"))
    except (SyntaxError, ValueError, OSError):
        return None


def _top_level_script(tree: ast.Module) -> bool:
    return any(scan._is_script_stmt(s) for s in tree.body)


def _call_names(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else "?")
    return out


def _help_safe(tree: ast.Module) -> tuple[bool, str]:
    """__main__ 가드 → (main 함수) 에서 parse_args 전까지 argparse 설정 외 호출이 없으면 안전."""
    guard = next(
        (
            s
            for s in tree.body
            if isinstance(s, ast.If)
            and isinstance(s.test, ast.Compare)
            and isinstance(s.test.left, ast.Name)
            and s.test.left.id == "__name__"
        ),
        None,
    )
    if guard is None:
        return False, "no __main__ guard"
    body = guard.body
    called = [n for n in _call_names(ast.Module(body=body, type_ignores=[])) if n not in ("exit", "SystemExit")]
    funcs = {f.name: f for f in tree.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    target = next((funcs[c] for c in called if c in funcs), None)
    stmts = target.body if target else body
    for st in stmts:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue  # docstring
        names = _call_names(st)
        if "parse_args" in names or "parse_known_args" in names:
            return True, "parse_args first"
        if names - ARGPARSE_SETUP:
            return False, "work before parse_args: " + ",".join(sorted(names - ARGPARSE_SETUP))[:80]
    return False, "parse_args not found in entry"


def run_r0(m: dict, workers: int = 4, chunk: int = 25) -> dict[str, dict]:
    targets, res = [], {}
    for rel, info in sorted(m["files"].items()):
        if not rel.endswith(".py") or info["class"] not in ("LIVE", "CLI") or scan.is_test(rel):
            continue
        tree = _tree(rel)
        if tree is None:
            res[rel] = {"status": "FAIL", "sec": 0, "err": "SyntaxError"}
        elif _top_level_script(tree):
            res[rel] = {"status": "SKIP", "sec": 0, "err": "top-level script (import would execute it)"}
        else:
            targets.append(rel)

    def run_chunk(items: list[str], timeout: int) -> dict[str, list]:
        try:
            r = subprocess.run(
                [sys.executable, "-c", IMPORT_CHILD, str(ROOT).replace("\\", "/"), json.dumps(items)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=ROOT,
                env=CHILD_ENV,
            )
            line = next((ln for ln in r.stdout.splitlines() if ln.startswith("@@RC@@")), None)
            if line:
                return json.loads(line[6:])
            return {i: ["FAIL", 0, "no result: " + (r.stderr or r.stdout)[-200:]] for i in items}
        except subprocess.TimeoutExpired:
            if len(items) == 1:
                return {items[0]: ["FAIL", timeout, "TIMEOUT (import hangs)"]}
            out = {}
            for it in items:  # 묶음 시간초과 → 하나씩 재시도
                out.update(run_chunk([it], 60))
            return out

    chunks = [targets[i : i + chunk] for i in range(0, len(targets), chunk)]
    with ThreadPoolExecutor(workers) as ex:
        for part in ex.map(lambda c: run_chunk(c, 180), chunks):
            for rel, (st, sec, err) in part.items():
                res[rel] = {"status": st, "sec": sec, "err": err}
    return res


def run_r1(m: dict, workers: int = 4) -> dict[str, dict]:
    res, jobs = {}, []
    for rel, info in sorted(m["files"].items()):
        if not rel.endswith(".py") or info["class"] not in ("LIVE", "CLI") or scan.is_test(rel):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")
        if "argparse" not in text or "__main__" not in text:
            continue
        if RISKY_NAME.search(PurePosixPath(rel).name):
            res[rel] = {"status": "SKIP", "sec": 0, "err": "risky name (send/publish/delete/...)"}
            continue
        tree = _tree(rel)
        ok, why = _help_safe(tree) if tree else (False, "SyntaxError")
        if not ok:
            res[rel] = {"status": "SKIP", "sec": 0, "err": why}
            continue
        jobs.append(rel)

    def one(rel: str) -> tuple[str, dict]:
        t = time.time()
        try:
            r = subprocess.run(
                [sys.executable, rel, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                cwd=ROOT,
                env=CHILD_ENV,
            )
            ok = r.returncode == 0 and "usage" in (r.stdout + r.stderr).lower()
            err = "" if ok else f"rc={r.returncode} " + (r.stderr or r.stdout)[-250:]
            return rel, {"status": "OK" if ok else "FAIL", "sec": round(time.time() - t, 2), "err": err}
        except subprocess.TimeoutExpired:
            return rel, {"status": "FAIL", "sec": 60, "err": "TIMEOUT (--help did not exit)"}

    with ThreadPoolExecutor(workers) as ex:
        for rel, r in ex.map(one, jobs):
            res[rel] = r
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="R0,R1", help="쉼표 구분: R0,R1")
    a = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    m = _load_map()
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"nodes": {}, "runs": []}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    summary = {}
    for lv in [x.strip().upper() for x in a.levels.split(",") if x.strip()]:
        t = time.time()
        results = {"R0": run_r0, "R1": run_r1}[lv](m)
        for rel, r in results.items():
            ledger["nodes"].setdefault(rel, {})[lv] = {**r, "at": now, "commit": commit}
        cnt = {s: sum(1 for r in results.values() if r["status"] == s) for s in ("OK", "FAIL", "SKIP")}
        summary[lv] = {**cnt, "sec": round(time.time() - t)}
        print(f"[runcheck] {lv}: {cnt}  ({summary[lv]['sec']}s)")
    ledger["runs"].append({"at": now, "commit": commit, "summary": summary})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"[runcheck] 저장: {LEDGER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
