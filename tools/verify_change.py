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
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
PY = sys.executable
_T0 = time.monotonic()
PER_TEST_TIMEOUT_S = 300  # pytest-timeout: 시험 하나가 멈추면 90분을 다 쓰지 않고 그 시험 이름으로 실패한다
MAX_XDIST_WORKERS = 4  # pytest-xdist 가 있으면 영향 시험을 이만큼 병렬로
AUDIT_KIT_SLOW_S = 20  # audit-kit 한 파일이 이보다 오래 걸리면 파일 이름을 로그에 남긴다


def _log(msg: str) -> None:
    """단계별 진행 로그(즉시 flush) — 이 도구는 끝날 때까지 출력이 없어서 CI 가 멈췄을 때 어느 단계인지 알 수 없었다(2026-10-08 PR #160)."""
    print(f"[verify +{int(time.monotonic() - _T0):>5}s] {msg}", flush=True)


def _pytest_extra_args() -> list[str]:
    """있으면 쓰는 pytest 플러그인 인자: 시험별 시간 상한(pytest-timeout)·병렬(pytest-xdist). 없으면 빈 목록(설치 안 된 PC 에서도 그대로 동작)."""
    extra: list[str] = []
    if importlib.util.find_spec("pytest_timeout") is not None:
        extra += [f"--timeout={PER_TEST_TIMEOUT_S}"]
    if importlib.util.find_spec("xdist") is not None:
        extra += ["-n", str(MAX_XDIST_WORKERS)]
    return extra


# 2026-09-30 수정(defect_index 신규 항목): "바뀐 파일 ruff" 체크가 head 쪽 ruff 결과를
# base 와 비교 없이 그대로 "새로 생긴 문제"로 보고해, 손 안 댄 줄의 기존(pre-existing)
# 위반까지 전부 이번 커밋 탓으로 돌려 CI를 FAIL시키고 있었다(실측: dry_run_approved_
# browser_instruction_api.py 에 docstring 5줄만 추가한 커밋이 그 함수의 기존 복잡도
# 위반 3건 때문에 CI FAIL — 로컬 pre-commit 훅은 이미 ruff_new_only_gate.py 로 같은
# 문제를 정확히 처리하고 있어 그 로직을 재사용한다.
sys.path.insert(0, str(ROOT))
from scripts.ops.repo_gates.ruff_new_only_gate import changed_lines_between  # noqa: E402

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
    """명령 실행. 시간 초과면 자손(CDP 데몬·Chrome 등)까지 종료하고 TimeoutExpired — 파이프를 문 자손 때문에 영원히 멈추지 않는다."""
    from tools.code_map.proc_tree import run_tree_killed

    return run_tree_killed(cmd, cwd=cwd, timeout=timeout, env=ENV)


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


def _string_token_spans(src: str) -> dict[int, list[tuple[int, int]]]:
    """src 를 tokenize 해서 '줄 번호 → [그 줄에서 STRING 토큰이 덮는 (시작열, 끝열) 범위]'를 만든다.

    주석 속 인용부호·삼중따옴표가 끼면 "앞쪽 인용부호 개수가 홀수면 문자열 안"식 어림짐작이
    틀린다(총괄 지적, run38009465088) — 진짜 토크나이저로 STRING 토큰 범위를 구해 좌표로 본다.
    토큰화 자체가 실패하면(문법이 깨진 파일 등) 빈 dict — 아무 줄도 '문자열 안'으로 안 쳐서
    원래 동작(모두 검사)으로 안전하게 되돌아간다.
    """
    spans: dict[int, list[tuple[int, int]]] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.STRING:
                continue
            (sr, sc), (er, ec) = tok.start, tok.end
            if sr == er:
                spans.setdefault(sr, []).append((sc, ec))
                continue
            spans.setdefault(sr, []).append((sc, 1 << 30))
            for r in range(sr + 1, er):
                spans.setdefault(r, []).append((0, 1 << 30))
            spans.setdefault(er, []).append((0, ec))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return {}
    return spans


def _in_string_span(spans: dict[int, list[tuple[int, int]]], line_no: int, col: int) -> bool:
    return any(sc <= col < ec for sc, ec in spans.get(line_no, []))


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
        string_spans = _string_token_spans(new_src)
        for i, line in enumerate(new_src.splitlines(), 1):
            s = line.strip()
            if s.startswith("#"):
                continue
            # 결함(2026-10-10, PR165 verify FAIL — 이동으로 깊이가 바뀐 테스트 파일의 docstring
            # 이 과거에 고친 순환/층간위반을 "from .x import y" 같은 실제 문장 모양 그대로 설명
            # 하고 있어서, 옛 "문자열에 from . 가 있으면" 식 부분일치 검사가 그 설명을 진짜
            # import 문으로 오판했다(browser_approval_errors.py·test_backend_router_server_
            # cycle_break_20260516.py 의 역사 설명 docstring 이 매번 "새 위치의존 미조정"으로
            # 잡힘). 실제 import 문은 항상 줄 맨 앞이 from ./import . 로 시작하므로 그 모양만
            # 본다(문장 중간·주석·docstring 안의 같은 글자는 더는 안 잡힌다).
            is_rel_import = s.startswith("from .") or s.startswith("import .")
            # "__file__" 단독(.parent/.parents 체인 없음)은 자기 경로를 그대로 재실행/참조하는
            # 용도라 이동 깊이와 무관 — .parent 체인이 있는 것만 본다(실측: browser_rpc_server.py·
            # cdp_daemon.py 의 자기 재실행 줄이 깊이 변화마다 오탐).
            # 결함(2026-10-10, run38009465088): "Path(__file__)" 요구 없이 "__file__"+".parent"만
            # 보면 (a) docstring 설명문("Path(__file__).resolve().parents[N]" 같은 예시 문장,
            # test_repo_root_canonical.py:3)과 (b) 형제 파일 하나를 찾는 단일 .parent(이동 깊이와
            # 무관, test_audit_kit_gate.py:26 의 "pathlib.Path(__file__).parent / 'plan.json'")
            # 까지 잡는다. 저장소 루트까지 올라가는 진짜 깊이의존 줄만 본다: parents[digit] 또는
            # .parent 가 2번 이상 이어지는 체인.
            has_parents_index = bool(re.search(r"parents\[\d+\]", s))
            has_parent_chain = s.count(".parent") >= 2
            # "Path(__file__).resolve().parents[2]" 가 실제 코드가 아니라 시험 데이터 문자열
            # 그대로(test_root_calc_gate.py 의 (경로, 코드문자열) 튜플, test_move_guardrails.py
            # 의 예시 줄)로 등장하면 깊이의존이 아니라 "그 패턴을 검사하는 시험 자체의 데이터"다.
            # 인용부호 개수의 홀짝은 주석 속 인용부호·삼중따옴표에서 오판하므로(총괄 지적),
            # tokenize 로 실제 STRING 토큰 범위(원본 줄 기준)인지를 본다.
            _col = line.find("Path(__file__)")
            _in_string = _col >= 0 and _in_string_span(string_spans, i, _col)
            has_file_dep = _col >= 0 and (has_parents_index or has_parent_chain) and not _in_string
            if not (is_rel_import or has_file_dep):
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


def _read_at(ref: str | None, path: str) -> str | None:
    if ref is None:
        return (ROOT / path).read_text("utf-8") if (ROOT / path).exists() else None
    r = run(["git", "show", f"{ref}:{path}"], ROOT)
    return r.stdout if r.returncode == 0 else None


def _shim_points_to(old: str, new: str, head: str | None) -> bool:
    """old 가 (head 시점에) `# haehan-shim: <dotted>` shim 이고 그 dotted 가 new 와 같은 파일을 가리키면 참.

    예: ai_orchestrator/config.py(shim) → ai_orchestrator.core.config(실제) 처럼, 옮긴 파일과
    옛 경로의 shim 이 같은 대상을 가리키는 경우 git rename 추적(moved)엔 안 잡히지만 실제로는
    같은 모듈이라 '미조정'이 아니다.
    """
    content = _read_at(head, old)
    if not content:
        return False
    first = content.splitlines()[0].strip() if content.splitlines() else ""
    marker = "# haehan-shim:"
    if not first.startswith(marker):
        return False
    dotted = first[len(marker):].strip()
    stem = new[:-3] if new.endswith(".py") else new
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return dotted == stem.replace("/", ".")


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
    return bool(olds) and len(olds) == len(news) and all(
        moved.get(n, n) == o or _shim_points_to(o, n, head) for n, o in zip(news, olds, strict=False)
    )


def _checkout(ref: str, dest: Path) -> bool:
    """ref 를 임시 worktree 로 꺼내고 현재의 측정 도구를 넣는다(같은 잣대로 재기 위함).

    결함(2026-10-10, PR165 verify FAIL — "기준 트리 측정 예외: map.json 없음" 조사 중 발견):
    scripts/ops/code_map/* 는 지금 전부 호환 shim(tools.code_map.* 로 재노출)이라 shim만
    복사해 넣으면 import_module("tools.code_map.build") 가 base tree 에 없는 tools/code_map/
    을 찾다 실패해 build.py 가 조용히 아무것도 안 하고 끝났다(map.json 이 끝내 안 생김).
    실제 구현(tools/code_map/)도 같이 넣어야 shim 이 제대로 리다이렉트된다.
    """
    if run(["git", "worktree", "add", "--detach", str(dest), ref], ROOT).returncode != 0:
        return False
    shutil.copytree(ROOT / "scripts/ops/code_map", dest / "scripts/ops/code_map", dirs_exist_ok=True)
    shutil.copytree(ROOT / "tools/code_map", dest / "tools/code_map", dirs_exist_ok=True)
    # tools/code_map/* 전부가 repo_root() 를 scripts.common.app_paths 에서 가져온다 — base tree
    # 가 그 파일이 생기기 전 커밋이면 이것도 같이 넣어야 한다. ai_orchestrator.paths 는 base
    # tree 에도 이미 있지만 더 오래된 버전일 수 있어(여기서는 atomic_write_bytes 등이 아직
    # 없던 버전) 지금 app_paths.py 가 기대하는 API 와 안 맞을 수 있다 — 같이 최신으로 덮는다.
    shutil.copytree(ROOT / "scripts/common", dest / "scripts/common", dirs_exist_ok=True)
    shutil.copytree(ROOT / "ai_orchestrator/paths", dest / "ai_orchestrator/paths", dirs_exist_ok=True)
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


def _is_shim_file(tree: Path, rel: str) -> bool:
    """`# haehan-shim:` 마커로 시작하는 1줄 경로-포워딩 호환 파일인가(scripts/ops/make_shim.py 가
    만듦). shim 은 메커니즘상 항상 '낮은 층 shim → 실제 모듈'로 보여 층 규칙과 무관하게 위반으로
    잡힌다(PR #165 분석, 2026-10-09) — 층 위반 판정에서 제외한다."""
    try:
        with (tree / rel).open(encoding="utf-8", errors="replace") as f:
            return f.readline().startswith("# haehan-shim:")
    except OSError:
        return False


def _is_smoke_or_verify_script(rel: str) -> bool:
    """tools/smoke/·tools/verify/ 의 한번용 스모크·드라이런 스크립트는 설계상 런타임 내부를
    깊이 가로질러 가져와 실제 동작을 끝까지 exercise 한다(사람/CI 가 직접 돌리는 진입점,
    프로덕션 코드에서 import 되지 않음) — 층 규칙과 무관하게 항상 위반으로 잡힌다(PR165
    layer-violation 조사, 2026-10-10, sonnet 서브에이전트 확인: tools/smoke 10개·tools/verify
    13개 중 실제로 깊은 import 를 하는 것만 걸림, 디렉터리 전체 오분류 아님) — 위반 판정의
    소스로만 제외(다른 코드가 이 스크립트를 import 하는 경우는 그대로 검사)."""
    return rel.startswith("tools/smoke/") or rel.startswith("tools/verify/")


def _measure_violations(tree: Path, m: dict) -> list[str]:
    """층간 위반 — configs/module_registry.json 의 allowed_deps 기준. 호환 shim 파일과
    smoke/verify 스크립트는 제외(위 _is_shim_file·_is_smoke_or_verify_script 참고)."""
    reg_p = tree / "configs/module_registry.json"
    viol = set()
    if reg_p.exists():
        reg = json.loads(reg_p.read_text(encoding="utf-8"))
        files, allowed = reg["files"], reg.get("allowed_deps", {})
        for s, ts in m.get("import_edges", m["all_edges"]).items():  # 실제 import 만(문자열 언급 제외)
            if (
                s in files
                and not s.endswith("__init__.py")
                and files[s]["layer"] in allowed
                and not _is_shim_file(tree, s)
                and not _is_smoke_or_verify_script(s)
            ):
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


def _measure_affected_test_results(tree: Path, tests: list[str]) -> tuple[list[str], list[str], dict[str, str]]:
    """영향 테스트 — CHUNK 파일씩 묶어 한 프로세스로(속도), 묶음이 시간 상한을 넘으면 그 묶음만 파일별로 재실행(멈춤 차단)."""
    present = [t for t in tests if (tree / t).exists()]
    fails, timeouts = [], []
    reasons: dict[str, str] = {}
    for i in range(0, len(present), CHUNK):
        chunk = present[i : i + CHUNK]
        try:
            fails += _pytest(tree, chunk, TEST_TIMEOUT * len(chunk) // 2 + TEST_TIMEOUT, reasons)
        except subprocess.TimeoutExpired:
            for t in chunk:
                try:
                    fails += _pytest(tree, [t], TEST_TIMEOUT, reasons)
                except subprocess.TimeoutExpired:
                    timeouts.append(t)
    return sorted(set(fails)), timeouts, reasons


def measure(tree: Path, tests: list[str]) -> dict:
    """한 작업트리에서 판정 항목을 잰다.

    2026-09-29 STD-08(복잡도) 리팩터: 각 판정 항목을 _measure_*() 함수로 분리(순서·조건·
    문자열 그대로, m/committed 등 다음 단계가 쓰는 값은 반환해 넘긴다).
    """
    r: dict = {}
    name = tree.name
    _log(f"[{name}] pytest 수집")
    r["collect_errors"] = _measure_collect_errors(tree)
    _log(f"[{name}] 코드맵·LIVE import")
    m, committed, r["import_fail"] = _measure_code_map_and_import_fail(tree)
    r["routes"] = _measure_routes(tree)
    r["violations"] = _measure_violations(tree, m)
    r["skeleton"], r["cycles"] = _measure_skeleton_and_cycles(tree, m, committed)
    _log(f"[{name}] 영향 시험 {len(tests)}개 실행")
    r["test_failures"], r["test_timeouts"], r["test_failure_reasons"] = _measure_affected_test_results(tree, tests)
    _log(f"[{name}] 측정 끝 (시험 실패 {len(r['test_failures'])}건, 시간 초과 {len(r['test_timeouts'])}건)")
    return r


_EMPTY_MEASURE: dict = {
    "collect_errors": [],
    "import_fail": [],
    "routes": "-",
    "violations": [],
    "skeleton": [],
    "cycles": [],
    "test_failures": [],
    "test_timeouts": [],
    "test_failure_reasons": {},
}


def _collect_static_results(fb, fa, fk) -> tuple[dict, dict, list[str], str]:
    """측정 future 3개(기준·변경 후 measure(), audit-kit)의 결과를 모은다 — 하나가 예외를 던져도
    프로세스를 죽이지 않고 그 측정의 오류로 기록해 나머지 결과·보고가 끝까지 나오게 한다
    ("추가 5", 2026-10-09: 5차 CI 에서 audit-kit 의 ModuleNotFoundError 가 verify_change 전체를
    중단시켜 뒤 단계(ruff·보고)결과가 통째로 가려졌다). kit_errors 가 비어있지 않으면 기존처럼
    FAIL 이 유지된다 — "예외로 중단"을 "정상 실패 보고"로 바꾸는 것일 뿐 완화가 아니다."""
    kit_errors: list[str] = []
    try:
        before = fb.result()
    except Exception as exc:  # noqa: BLE001 - 측정 자체의 예외도 결과로 기록(kit_errors)하고 계속한다
        before = dict(_EMPTY_MEASURE)
        kit_errors.append(f"기준 트리 측정 예외: {type(exc).__name__}: {exc}")
    try:
        after = fa.result()
    except Exception as exc:  # noqa: BLE001
        after = dict(_EMPTY_MEASURE)
        kit_errors.append(f"변경 트리 측정 예외: {type(exc).__name__}: {exc}")
    kit_note = ""
    try:
        fk_errors, kit_note = fk.result()
        kit_errors += fk_errors
    except Exception as exc:  # noqa: BLE001
        kit_errors.append(f"audit-kit 측정 예외: {type(exc).__name__}: {exc}")
    return before, after, kit_errors, kit_note


def _is_pytest_id(token: str) -> bool:
    """pytest 요약 줄의 id 인가 — 'path::test' 이거나 수집 오류의 'path.py'. 로그 줄의 '모듈:파일.py:줄'은 아니다."""
    return "::" in token or token.endswith(".py")


def _failure_reason(line: str, test_id: str) -> str:
    """'FAILED path::test - AssertionError: ...' 요약 줄에서 id 뒤 사유 텍스트만 뽑는다.
    ' - '가 없으면(긴 id 로 pytest 가 사유를 못 붙인 줄 등) 빈 문자열 — 호출 쪽이 그냥 id만 쓴다."""
    rest = line.split(test_id, 1)[1].lstrip() if test_id in line else ""
    return rest[2:].strip() if rest.startswith("- ") else ""


def _pytest(tree: Path, files: list[str], timeout: int, reasons: dict[str, str] | None = None) -> list[str]:
    """테스트 파일 묶음 실행 → 실패 id 목록. 수집 오류가 나도 나머지는 계속 돈다.

    reasons 를 주면 실패 id별 pytest 요약 줄의 사유(짧게 잘릴 수 있음)를 채워 넣는다 — 로컬에서
    재현되지 않는 CI 전용 실패가 나왔을 때, 보고서만 보고도 마지막 assert/예외 줄을 바로 알 수
    있게 한다(2026-10-08, gabia_router_clean 재현 실패 조사 중 보고서가 id 만 남겨 원인 추적이
    막혔던 것의 재발 방지).
    """
    p = run(
        [
            PY,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-rfE",
            "--continue-on-collection-errors",
            *_pytest_extra_args(),
            *files,
        ],
        tree,
        timeout=timeout,
    )
    # pytest 요약 줄("FAILED path::test", "ERROR path.py")만 센다. 실패한 시험의 캡처 로그
    # ("ERROR    모듈:파일.py:줄 메시지")도 같은 접두어라 그대로 세면 로그 줄이 가짜 실패 id 로 잡힌다.
    out = []
    for ln in p.stdout.splitlines():
        if not ln.startswith(("FAILED ", "ERROR ")):
            continue
        parts = ln.split()
        if len(parts) <= 1 or not _is_pytest_id(parts[1]):
            continue
        test_id = parts[1]
        out.append(test_id)
        if reasons is not None:
            reason = _failure_reason(ln, test_id)
            if reason:
                reasons[test_id] = reason
    if p.returncode not in (0, 1, 5) and not out:
        synthetic_id = f"{files[0]}..(+{len(files) - 1})::<rc={p.returncode}>"
        out.append(synthetic_id)
        if reasons is not None:
            # pytest 요약 줄이 안 남는 비정상 종료(INTERNALERROR 등, rc=3)는 id 만으론 원인을
            # 전혀 못 찾는다(2026-10-10, run38009465088 tests/google rc=3 재현 조사 중 CI 로그에
            # 트레이스백이 안 남아 원인 추적이 막혔음) — 재발 대비로 출력 꼬리(최대 30줄)를 남긴다.
            tail = (p.stdout or "").splitlines()[-30:]
            if (p.stderr or "").strip():
                tail += ["--- stderr ---", *p.stderr.splitlines()[-10:]]
            reasons[synthetic_id] = " | ".join(tail)[:2000]
    return out


def affected_tests(changed: list[str]) -> list[str]:
    """코드맵 역방향 BFS — 바뀐 파일에 (간접적으로라도) 닿는 테스트 파일.

    출발점은 바뀐 파일 + 바뀐 비-.py(설정·정본 json 등)를 문자열로 읽는 .py 다 — 코드맵 간선은 .py import 만 따라가서, 설정만 바뀌면
    그 설정을 여는 도구(와 그 도구를 import 하는 시험)가 빠졌다(2026-10-08 configs/folder_registry.json ↔ test_folder_gate).
    """
    from tools.code_map.ref_seeds import seeds_for

    m = json.loads((ROOT / "data/code_map/map.json").read_text(encoding="utf-8"))
    rev: dict[str, set[str]] = {}
    for s, ts in m["all_edges"].items():
        for t in ts:
            rev.setdefault(t, set()).add(s)
    tracked = run(["git", "ls-files"], ROOT).stdout.splitlines()
    seeds = seeds_for(ROOT, changed, tracked)
    seen, q = set(seeds), deque(seeds)
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
    # 새로 생긴 시험 실패 id 뒤에 pytest 요약 줄의 사유를 붙인다 — 사유가 없는 id(긴 id 로 pytest 가
    # 못 붙였거나 rc 로만 잡힌 합성 id)는 그냥 id만 남아 안전하다.
    after_reasons = after.get("test_failure_reasons", {})
    new_test_failures = [
        f"{tid} — {after_reasons[tid]}" if tid in after_reasons else tid for tid in new("test_failures")
    ]
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
            new_test_failures + new_timeouts,
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


def _audit_kit_new_findings(
    py_changed: list[str], base_tree: Path, head_tree: Path, moved: dict[str, str] | None = None
) -> tuple[list[str], str]:
    """audit-kit 의 파일 단위 개발 기준서·순환 검사에서 "이번 변경이 새로 만든" 문제 (기준 트리 결과와의 차이).

    audit-kit 이 없는 PC·CI 에서는 검사를 생략하고 그 사실을 알린다(설치된 PC 에서는 필수: 새 문제가 있으면 FAIL).

    결함(2026-10-10, PR165 verify FAIL — core/agent_runtime/browser/approval/browser_approval_
    errors.py 의 설명 docstring이 매번 "신규" 로 잡히는 원인 조사 중 발견): moved(새경로→옛경로,
    이동표)를 안 받아서 새 경로가 base tree 에 없으면(흔함 — 이 PR 기간에 옮겨진 파일) 무조건
    "base 에 아무것도 없음(전부 신규)"으로 봤다. 다른 측정 항목(violations·cycles 등)은 전부
    moved 를 받아 옛 경로로 base 와 대조하는데 audit-kit 경로만 빠져 있었다 — 같은 방식으로
    옛 경로를 찾아 대조한다.
    """
    moved = moved or {}

    def _base_rel(rel: str) -> str | None:
        if (base_tree / rel).exists():
            return rel
        old = moved.get(rel)
        if old and (base_tree / old).exists():
            return old
        return None
    from scripts.ops.hooks.audit_kit_gate import (
        BATCH_SCRIPT,
        _new_typed,
        batch_raw_findings,
        find_audit_kit,
        finding_key,
        is_real_kit,
        mypy_keys_batch,
        mypy_python,
        raw_findings,
    )

    kit = find_audit_kit(ROOT)
    if kit is None or not py_changed:
        return (
            [],
            "[verify] audit-kit 를 찾지 못해 기준서 검사를 생략합니다 (AUDIT_KIT_BIN 으로 위치 지정)"
            if kit is None
            else "",
        )

    base_rels = {rel: _base_rel(rel) for rel in py_changed}

    # mypy 는 파일마다 따로 돌리면 전역 잠금 때문에 직렬이라 변경 파일 1065개(PR #160)에서 90분을 넘겼다 → 기준 폴더별 1회씩 일괄 실행한다
    # (head·base 각각). 파일별 결과(오류 문장 집합)는 같고, 신규 판정은 파일마다 같은 규칙(_new_typed)을 쓴다.
    py = mypy_python(kit)
    head_keys: dict = {}
    base_keys: dict = {}
    if py is not None:
        _log(f"mypy 일괄 검사 시작: 변경 {len(py_changed)}개 (head·base)")
        head_keys = mypy_keys_batch(py, [head_tree / rel for rel in py_changed], head_tree)
        base_keys = mypy_keys_batch(py, [base_tree / r for r in base_rels.values() if r is not None], base_tree)
        _log("mypy 일괄 검사 끝")

    # audit-kit hook 은 호출마다 프로젝트 그래프를 새로 만들어 파일당 ~8초라서 변경 1000개면 90분을 넘겼다(PR #160) →
    # 한 프로세스에서 여러 파일을 묶어 돌려(그래프 1회) 파일당 ~1초 이하로. 묶음이 못 낸 파일만 단독 호출로 다시 시도한다.
    batch_missing_warning = []
    if not BATCH_SCRIPT.is_file():  # 2026-10-09(PR #165 7차 CI): 경로가 안 맞으면 묶음이 매번 조용히
        # 빈 결과를 내 변경 전체가 단독 재시도로 폭주해 90분 제한을 넘겼다 — 눈에 보이게 남긴다.
        batch_missing_warning = [
            f"audit-kit 묶음 스크립트를 찾지 못했습니다({BATCH_SCRIPT}) — 파일마다 단독 재시도로 느려집니다"
        ]
    _log(f"audit-kit 묶음 검사 시작: 변경 {len(py_changed)}개 (head·base)")
    head_batch = batch_raw_findings(kit, head_tree, py_changed)
    base_batch = batch_raw_findings(kit, base_tree, [r for r in base_rels.values() if r is not None])
    _log(f"audit-kit 묶음 검사 끝: head {len(head_batch)}개·base {len(base_batch)}개 (나머지는 단독 재시도)")
    done = [0]

    def one(rel: str) -> list[str]:
        started = time.monotonic()
        try:
            return _one(rel)
        finally:
            done[0] += 1
            if time.monotonic() - started > AUDIT_KIT_SLOW_S:  # 느린 파일은 이름을 남긴다 — 멈춤 추적용(PR #160)
                _log(f"audit-kit 느린 파일 {time.monotonic() - started:.0f}s: {rel}")
            if done[0] % 100 == 0:
                _log(f"audit-kit 파일 검사 진행 {done[0]}/{len(py_changed)}")

    def _one(rel: str) -> list[str]:
        head = head_batch[rel] if rel in head_batch else raw_findings(kit, head_tree / rel, head_tree)
        if head is None:
            return [f"{rel}: audit-kit 검사를 하지 못했습니다"]
        base_rel = base_rels.get(rel)
        has_base = base_rel is not None
        if not has_base:
            base: list[str] | None = []
        else:
            base = base_batch[base_rel] if base_rel in base_batch else raw_findings(kit, base_tree / base_rel, base_tree)
        known = {finding_key(x) for x in (base or [])}
        out = [f"{rel}: {x}" for x in head if finding_key(x) not in known]
        if py is not None:  # mypy: 기준 트리의 같은 파일(이동했으면 옛 경로)에 없던 타입 오류만
            typed, why = _new_typed(
                head_tree / rel,
                head_keys.get(head_tree / rel),
                has_base,
                base_keys.get(base_tree / base_rel) if has_base else None,
            )
            out += [f"{rel}: {x}" for x in typed] + ([f"{rel}: {why}"] if why else [])
        return out

    _log(f"audit-kit 파일 검사 시작: {len(py_changed)}개")
    with ThreadPoolExecutor(4) as pool:
        found = [item for items in pool.map(one, py_changed) for item in items]
    found += batch_missing_warning
    _log("audit-kit 파일 검사 끝")
    if (
        is_real_kit(kit) and mypy_python(kit) is None
    ):  # 진짜 audit-kit 인데 mypy 를 돌릴 파이썬이 없다 = 타입 검사가 조용히 빠진다 → 실패로 취급
        found.append(
            "mypy 실행 환경(audit-kit 가상환경의 python)을 찾지 못해 타입 검사를 할 수 없습니다 — audit-kit 를 다시 설치하세요"
        )
    return found, ""


RUFF_CHUNK = 150  # 한 ruff 호출에 넘기는 파일 수 — 변경 1000개를 한 명령줄에 넣으면 윈도우 한도(32767자)를 넘는다(PR #160, WinError 206)


def _run_ruff(ruff_cfg: list[str], files: list[str], head_tree: Path) -> subprocess.CompletedProcess:
    """바뀐 파일에 ruff(JSON)를 묶음으로 나눠 돌리고 결과를 하나의 JSON 배열로 합친다.

    한 묶음이라도 ruff 가 못 돌았으면(종료코드 2 이상·출력 비었음·JSON 아님) 그 묶음의 결과를 그대로 돌려줘서 `_new_ruff_findings` 가
    '검사가 수행되지 않았다'로 드러내게 한다(조용히 0건 처리하지 않는다).
    """
    merged: list = []
    worst = 0
    for i in range(0, len(files), RUFF_CHUNK):
        chunk = files[i : i + RUFF_CHUNK]
        proc = run([PY, "-m", "ruff", "check", *ruff_cfg, "--no-cache", "--output-format", "json", *chunk], head_tree)
        out = (proc.stdout or "").strip()
        try:
            rows = json.loads(out) if out else None
        except json.JSONDecodeError:
            rows = None
        if proc.returncode >= 2 or rows is None:
            return proc
        merged += rows
        worst = max(worst, proc.returncode)
    return subprocess.CompletedProcess(["ruff", "check"], worst, json.dumps(merged), "")


def _new_ruff_findings(
    ruff: subprocess.CompletedProcess | None, head_tree: Path, base_ref: str, head_ref: str | None
) -> list[str]:
    """head 쪽 ruff(JSON) 결과에서 "이번 커밋으로 새로 생긴" finding만 골라 문자열로 반환.

    로컬 pre-commit 훅의 ruff_new_only_gate.py 와 동일 원칙(git diff hunk 기준 바뀐 줄
    번호에 걸리는 finding만 new로 판정) — 단순히 head 쪽 ruff 결과를 통째로 쓰면 그
    파일의 기존 부채까지 전부 이번 커밋 탓이 된다(2026-09-30 실측 발견 버그).
    """
    findings: list[dict] = []
    if ruff is not None:
        # ruff 는 finding 이 없어도 JSON '[]' 를 출력한다. 출력이 비었거나 JSON 이 아니거나 종료코드가 2 이상(ruff 자체 오류)이면
        # ruff 가 돌지 못한 것이다 — 예전에는 이를 조용히 '0건'으로 처리해, ruff 가 설치되지 않은 CI 러너에서 이 검사가 통째로
        # 건너뛰어지고 있었다(2026-10-07). 돌지 못했으면 FAIL 로 드러낸다.
        out = (ruff.stdout or "").strip()
        tail = (ruff.stderr or "").strip().splitlines()[-1:] or [""]
        if ruff.returncode >= 2 or not out:
            return [
                f"ruff 실행 실패(종료코드 {ruff.returncode}, 출력 {'없음' if not out else '있음'}) — 검사가 수행되지 않았다: {tail[0][:160]}"
            ]
        try:
            findings = json.loads(out)
        except json.JSONDecodeError:
            return [f"ruff 출력이 JSON 이 아니다(종료코드 {ruff.returncode}) — 검사가 수행되지 않았다: {tail[0][:160]}"]
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


def _parse_shard(spec: str | None) -> tuple[int, int]:
    """'I/N' → (I, N) (1부터). 없으면 (1, 1)."""
    if not spec:
        return 1, 1
    index, _, count = spec.partition("/")
    i, n = int(index), int(count)
    if not (1 <= i <= n):
        raise SystemExit(f"--shard {spec}: 1 <= I <= N 이어야 한다")
    return i, n


def shard_slice(tests: list[str], index: int, count: int) -> list[str]:
    """영향 시험 파일을 N 개 묶음으로 나눈다(라운드 로빈 — 큰 폴더가 한 묶음에 몰리지 않게). 모든 묶음을 합치면 원래 목록과 같다."""
    return tests[index - 1 :: count]


def _checkout_trees(a: argparse.Namespace, tmp: Path) -> list[Path] | None:
    trees = [tmp / "base"] + ([tmp / "head"] if a.head else [])
    for ref, dest in zip([a.base, a.head], trees, strict=False):
        if not _checkout(ref, dest):
            print(f"[verify] 트리 생성 실패: {ref}")
            return None
    return trees


def _cleanup_trees(tmp: Path, trees: list[Path]) -> None:
    killed = kill_leftovers(tmp.name)  # 측정 폴더 경로가 명령줄에 든 잔여 프로세스
    if killed:
        print(f"[verify] 측정 중 남은 프로세스 {len(killed)}개 종료: {killed}")
    for dest in trees:
        run(["git", "worktree", "remove", "--force", str(dest)], ROOT)
    shutil.rmtree(tmp, ignore_errors=True)


def _phase_tests(a: argparse.Namespace) -> int:
    """phase=tests: 영향 시험의 한 묶음(shard)만 base·head 트리에서 돌려 실패 목록을 JSON 으로 남긴다(판정은 report 가 한다)."""
    index, count = _parse_shard(a.shard)
    changed = changed_files(a.base, a.head)
    _log(f"[tests {index}/{count}] 변경 파일 {len(changed)}개 — 코드맵 빌드")
    run([PY, "scripts/ops/code_map/build.py"], ROOT)
    all_tests = affected_tests(changed)
    mine = shard_slice(all_tests, index, count)
    _log(f"[tests {index}/{count}] 영향 시험 {len(all_tests)}개 중 이 묶음 {len(mine)}개")
    tmp = Path(tempfile.mkdtemp(prefix="verify_base_"))
    trees: list[Path] = []
    try:
        trees = _checkout_trees(a, tmp) or []
        if not trees:
            return 2
        head_tree = trees[1] if a.head else ROOT
        with ThreadPoolExecutor(2) as ex:
            fb, fa = (
                ex.submit(_measure_affected_test_results, trees[0], mine),
                ex.submit(_measure_affected_test_results, head_tree, mine),
            )
            (b_fail, b_to, b_reasons), (a_fail, a_to, a_reasons) = fb.result(), fa.result()
    finally:
        _cleanup_trees(tmp, trees)
    _log(f"[tests {index}/{count}] 끝: base 실패 {len(b_fail)}·head 실패 {len(a_fail)}")
    out = {
        "shard": index,
        "count": count,
        "tests": mine,
        "all_tests": all_tests,
        "before": {"test_failures": b_fail, "test_timeouts": b_to, "test_failure_reasons": b_reasons},
        "after": {"test_failures": a_fail, "test_timeouts": a_to, "test_failure_reasons": a_reasons},
    }
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _phase_report(a: argparse.Namespace) -> int:
    """phase=report: static 결과 1개 + tests 묶음 결과들을 합쳐 판정한다(시험은 돌리지 않는다)."""
    static = json.loads(Path(a.static_json).read_text(encoding="utf-8"))
    before, after = static["before"], static["after"]
    before["test_failures"], before["test_timeouts"], after["test_failures"], after["test_timeouts"] = [], [], [], []
    before["test_failure_reasons"], after["test_failure_reasons"] = {}, {}
    seen_shards: set[int] = set()
    count = 0
    for path in a.test_json or []:
        part = json.loads(Path(path).read_text(encoding="utf-8"))
        seen_shards.add(part["shard"])
        count = part["count"]
        before["test_failures"] += part["before"]["test_failures"]
        before["test_timeouts"] += part["before"]["test_timeouts"]
        before["test_failure_reasons"].update(part["before"].get("test_failure_reasons", {}))
        after["test_failures"] += part["after"]["test_failures"]
        after["test_timeouts"] += part["after"]["test_timeouts"]
        after["test_failure_reasons"].update(part["after"].get("test_failure_reasons", {}))
    if static["tests"] and seen_shards != set(
        range(1, count + 1)
    ):  # 묶음이 하나라도 빠지면 시험이 조용히 건너뛰어진 것 → 실패로 드러낸다
        print(f"[verify] 시험 묶음이 모자란다: 받은 {sorted(seen_shards)} / 기대 1..{count}")
        return 1
    for key in ("test_failures", "test_timeouts"):
        before[key], after[key] = sorted(set(before[key])), sorted(set(after[key]))
    measurements = {
        "before": before,
        "after": after,
        "ruff_errors": static["ruff_errors"],
        "kit_errors": static["kit_errors"],
        "loc_deps": static["loc_deps"],
        "moved": static["moved"],
        "receiving": set(static["receiving"]),
    }
    ok, report = _build_verify_report(a, static["changed"], static["tests"], measurements)
    print(report)
    if a.json:
        Path(a.json).write_text(
            json.dumps(
                {
                    "ok": ok,
                    "changed": static["changed"],
                    "tests": static["tests"],
                    "before": before,
                    "after": after,
                    "ruff": static["ruff_errors"],
                    "report": report,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="master", help="비교 기준 커밋/브랜치")
    ap.add_argument("--head", help="비교 대상 커밋/브랜치(생략 = 현재 작업트리). 지정하면 미커밋 WIP 가 섞이지 않음")
    ap.add_argument(
        "--expect-routes",
        help="의도된 라우트 수(기준서에 적힌 값). 지정하면 '변경 후 = 이 값'일 때 통과, 기준과 같아야 한다는 규칙 대신",
    )
    ap.add_argument("--json", help="결과 JSON 저장 경로")
    ap.add_argument(
        "--phase",
        choices=["all", "static", "tests", "report"],
        default="all",
        help="all=전부(기본) · static=시험 빼고 측정(코드맵·audit-kit·mypy·ruff) · tests=영향 시험 한 묶음만 · report=위 결과들을 합쳐 판정 (CI 가 job 을 나눠 병렬로 돌린다)",
    )
    ap.add_argument("--shard", help="phase=tests: 'I/N' — 영향 시험을 N 묶음으로 나눈 I 번째(1부터)")
    ap.add_argument("--static-json", help="phase=report: static 단계 결과 JSON")
    ap.add_argument("--test-json", nargs="*", help="phase=report: tests 단계 결과 JSON 들(묶음마다 하나)")
    a = ap.parse_args()
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if a.phase == "tests":
        return _phase_tests(a)
    if a.phase == "report":
        return _phase_report(a)
    _log(f"시작: base={a.base} head={a.head or '작업트리'} (phase={a.phase})")
    changed = changed_files(a.base, a.head)
    moved = renames(a.base, a.head)
    loc_deps = moved_location_deps(a.base, a.head)
    _log(f"변경 파일 {len(changed)}개 — 코드맵 빌드")
    run([PY, "scripts/ops/code_map/build.py"], ROOT)
    tests = affected_tests(changed)
    _log(f"영향 시험 파일 {len(tests)}개")
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
        py_changed = [c for c in changed if c.endswith(".py") and (head_tree / c).exists()]
        try:
            _log("기준·변경 후 측정 + audit-kit 파일 검사 시작(셋을 동시에: 서로 파일을 읽기만 한다)")
            with ThreadPoolExecutor(3) as ex:
                measured = [] if a.phase == "static" else tests  # static: 시험은 다른 job(phase=tests)이 돌린다
                fb, fa = ex.submit(measure, trees[0], measured), ex.submit(measure, head_tree, measured)
                fk = ex.submit(
                    _audit_kit_new_findings, py_changed, trees[0], head_tree, moved
                )  # 시험(약 20분)과 겹쳐 돌려 직렬 대기를 없앤다
                before, after, kit_errors, kit_note = _collect_static_results(fb, fa, fk)
            _log("기준·변경 후 측정 + audit-kit 끝")
        finally:
            if reg_bytes is not None:
                reg.write_bytes(reg_bytes)
        if kit_note:
            print(kit_note)
        _log("ruff 검사")
        ruff_cfg = ["--config", str(ROOT / CFG["ruff_config"])] if CFG["ruff_config"] else []
        ruff = _run_ruff(ruff_cfg, py_changed, head_tree) if py_changed else None
    finally:
        killed = kill_leftovers(tmp.name)  # 측정 폴더 경로가 명령줄에 든 잔여 프로세스
        if killed:
            print(f"[verify] 측정 중 남은 프로세스 {len(killed)}개 종료: {killed}")
        for dest in trees:
            run(["git", "worktree", "remove", "--force", str(dest)], ROOT)
        shutil.rmtree(tmp, ignore_errors=True)
    ruff_errors = _new_ruff_findings(ruff, head_tree, a.base, a.head)

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
    if a.phase == "static":  # 판정은 phase=report 가 시험 묶음 결과와 합쳐서 한다
        if a.json:
            dump = {**measurements, "receiving": sorted(receiving), "changed": changed, "tests": tests}
            Path(a.json).write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
        _log("static 단계 끝")
        return 0
    _log("판정 보고서 작성")
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
