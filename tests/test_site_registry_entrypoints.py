"""사이트 등록표 install 이 진입점마다 불리는지 고정한다.

코어(`scripts/site_engine/site_registry.py`)는 `site_login_registry.install()` 이 불려야 `get_site`/`list_sites` 가 동작한다
(미구성이면 RuntimeError). 진입점이 install 을 빠뜨리면 자동 로그인이 실패하므로:
  1. 아래 ENTRYPOINTS 의 각 파일이 실제로 `site_login_registry.install()` 을 부르는지 확인하고,
  2. 저장소를 정적으로 훑어 `site_registry` 에 닿는 `__main__` 실행 파일이 ENTRYPOINTS 나 EXEMPT(사유 필수)에 없으면 실패시킨다
     — 새 진입점이 생겨도 여기서 잡힌다.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = "scripts/site_engine/site_registry.py"
SOURCE_DIRS = ("scripts", "ai_orchestrator", "local_agent", "orchestrator_v1")

# install() 을 직접 부르는 진입점. module_level=True 면 import 만 해도 설치되는 조합 루트(이것을 import 하는 프로세스는 덮인다).
ENTRYPOINTS = {
    "scripts/entry/cdp_cli.py": "CLI 본체 — 서비스 CLI(naver·google·kakao·eum 등)가 모두 통과",
    "scripts/entry/site_access_cli.py": "python -m 로 사이트 접속",
    "scripts/entry/site_crawl_cli.py": "python -m 로 사이트 크롤",
    "ai_orchestrator/routers/registry.py": "서버 조합 루트(asgi·desktop_entry·서버 시험이 모두 import)",
    "conftest.py": "시험 프로세스",
}
MODULE_LEVEL = {"ai_orchestrator/routers/registry.py"}

# 사이트 등록표에 (정적으로는) 닿지만 로그인·접속을 실제로 부르지 않는 실행 파일. 사유를 적어야 한다.
_EUM_FORM = "cdp_client 의 eval_js·goto_url 만 쓴다(get_site·list_sites·open_site 를 부르지 않음) — 로그인은 eum.auth 가 직접 한다"
EXEMPT: dict[str, str] = {
    "scripts/eum/registration.py": _EUM_FORM,
    "scripts/eum/deregistration.py": _EUM_FORM,
    "scripts/eum/form_analyzer.py": _EUM_FORM,
}

SKIP_PREFIXES = ("scripts/archive/", "tests/", "ai_orchestrator/tests/", "scripts/ops/smoke/")


def _py_files() -> list[str]:
    out = []
    for d in SOURCE_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if "__pycache__" in rel or rel.startswith(SKIP_PREFIXES):
                continue
            out.append(rel)
    return sorted(out)


def _module_of(rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _calls_install(rel: str) -> bool:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "install"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "site_login_registry"
        ):
            return True
    return False


def _install_at_module_level(rel: str) -> bool:
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "install"
                and getattr(f.value, "id", "") == "site_login_registry"
            ):
                return True
        if isinstance(node, ast.FunctionDef | ast.ClassDef):
            continue
    return False


def _graph(files: list[str]) -> dict[str, set[str]]:
    by_module = {_module_of(f): f for f in files}
    edges: dict[str, set[str]] = defaultdict(set)
    for f in files:
        pkg = _module_of(f).split(".")
        if not f.endswith("__init__.py"):
            pkg = pkg[:-1]
        tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = pkg[: len(pkg) - (node.level - 1)] if node.level else []
                mod = ".".join(base + ([node.module] if node.module else [])) if node.level else (node.module or "")
                targets = [mod] + [f"{mod}.{a.name}" for a in node.names]
            for t in targets:
                parts = t.split(".")
                for i in range(1, len(parts) + 1):  # 하위 모듈을 import 하면 상위 패키지 __init__ 도 실행된다
                    dep = by_module.get(".".join(parts[:i]))
                    if dep and dep != f:
                        edges[f].add(dep)
    return edges


def test_every_listed_entrypoint_calls_install():
    assert ENTRYPOINTS
    missing = [f for f in ENTRYPOINTS if not (ROOT / f).is_file() or not _calls_install(f)]
    assert not missing, f"site_login_registry.install() 호출이 없는 진입점: {missing}"
    assert MODULE_LEVEL and MODULE_LEVEL <= set(ENTRYPOINTS)
    not_module_level = [f for f in MODULE_LEVEL if not _install_at_module_level(f)]
    assert not not_module_level, f"import 시점에 install 하기로 한 파일이 함수 안에서만 부른다: {not_module_level}"


def test_the_entrypoint_list_is_complete():
    files = _py_files()
    assert files, "소스 파일을 찾지 못했다"
    edges = _graph(files)
    reverse: dict[str, set[str]] = defaultdict(set)
    for s, ts in edges.items():
        for t in ts:
            reverse[t].add(s)
    covered = {
        f for f in MODULE_LEVEL
    }  # 이것을 import 하는 프로세스는 이미 설치된다 — 그 너머로는 거슬러 오르지 않는다
    reached, stack = {CORE}, [CORE]
    while stack:
        cur = stack.pop()
        for p in reverse[cur]:
            if p not in reached and p not in covered:
                reached.add(p)
                stack.append(p)
    # CORE 를 직접 쓰는 파일이 곧 '등록표에 닿는' 파일이고, 그 위로 올라가며 실행 파일(__main__)을 찾는다.
    assert len(reached) > 1, "등록표에 닿는 파일을 하나도 찾지 못했다(정적 그래프가 비었다)"
    runnable = {f for f in reached if f != CORE and '__name__ == "__main__"' in (ROOT / f).read_text(encoding="utf-8")}
    assert runnable, "직접 실행 파일을 하나도 찾지 못했다(검사가 눈을 잃었다)"
    unknown = sorted(f for f in runnable if f not in ENTRYPOINTS and f not in EXEMPT)
    assert not unknown, (
        "사이트 등록표에 닿는 직접 실행 파일이 ENTRYPOINTS/EXEMPT 에 없다 — 시작 때 "
        f"site_login_registry.install() 을 부르고 ENTRYPOINTS 에 올리거나 EXEMPT 에 사유를 적는다: {unknown}"
    )
    stale = sorted(f for f in EXEMPT if f not in runnable)
    assert not stale, f"더 이상 해당하지 않는 EXEMPT 항목: {stale}"
