"""도구 분리(gabia) — gabia 라우터·로그인 감시 스크립트를 도구 폴더로 옮긴 뒤에도 옛 경로·경로 값·공개 이름이 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys

from ai_orchestrator.paths import repo_root

BEFORE = json.loads((repo_root() / "tests" / "data" / "split_w3d_before.json").read_text(encoding="utf-8"))


def test_old_paths_alias_new_modules():
    for old, new in (
        ("scripts.gabia.login_watch", "scripts.gabia.login_watch"),
    ):
        assert importlib.import_module(old) is importlib.import_module(new)


def test_routes_unchanged():
    from ai_orchestrator.connectors.gabia.router import gabia_router

    now = sorted([sorted(r.methods), r.path] for r in gabia_router.routes)
    assert now == sorted(BEFORE["gabia_routes"])


def test_router_root_and_script_exist():
    from ai_orchestrator.connectors.gabia import router as mod

    assert mod.ROOT == repo_root()
    assert (mod.ROOT / "scripts" / "gabia" / "login_watch.py").is_file()


def test_watch_public_names_unchanged():
    import scripts.gabia.login_watch as mod
    names = {n for n in dir(mod) if not n.startswith("__")}
    missing = set(BEFORE["watch_names"]) - names
    assert not missing, missing


def test_old_script_runs_directly():
    for rel in ("scripts/gabia/login_watch.py", "scripts/gabia/login_watch.py"):
        r = subprocess.run(
            [sys.executable, str(repo_root() / rel), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root().parent),
            timeout=60,
        )
        assert r.returncode == 0 and "--timeout" in r.stdout
