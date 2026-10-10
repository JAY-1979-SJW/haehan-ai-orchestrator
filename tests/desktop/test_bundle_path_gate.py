"""번들 경로 일관성 게이트(G17) 테스트 — spec·electron·워크플로의 깨진 경로/모듈 참조는 FAIL, 정상 저장소는 PASS."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.repo_gates import bundle_path_gate as gate

REAL_ROOT = Path(__file__).resolve().parents[2]

SPEC_TMPL = """
from pathlib import Path
ROOT = Path(SPECPATH)
hidden_imports = {hidden!r}
a = Analysis(
    [str(ROOT / {entry})],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / 'configs'), 'configs')],
    hiddenimports=hidden_imports,
)
exe = EXE(a.scripts, name={name!r})
coll = COLLECT(exe, name={name!r})
"""

JS_OK = """
const path = require("path");
const exe = path.join(process.resourcesPath, "server", "haehan-server", "haehan-server.exe");
const dev = path.join(process.resourcesPath, "..", "..", "data");
"""

WORKFLOW = """
jobs:
  build:
    steps:
      - name: PyInstaller
        shell: bash
        run: python -m PyInstaller haehan-server.spec --noconfirm --distpath dist
      - name: electron
        working-directory: admin-web/electron
        run: npx playwright test -c playwright.electron.config.ts
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), capture_output=True, check=True)


def _w(root: Path, rel: str, text: str = "x = 1\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _spec(entry: str, name: str, hidden: list[str]) -> str:
    quoted = " / ".join(repr(s) for s in entry.split("/"))
    return SPEC_TMPL.format(entry=quoted, name=name, hidden=hidden)


def _package_json(extra: list[dict] | None = None) -> str:
    res = [
        {"from": "../../scripts", "to": "scripts", "filter": ["local_agent.py"]},
        {"from": "../../dist/haehan-server", "to": "server/haehan-server"},
        {"from": "../.next/standalone", "to": "nextjs", "filter": ["**/*"]},
        *(extra or []),
    ]
    return json.dumps({"build": {"files": ["main.js", "lib/**/*"], "extraResources": res}})


@pytest.fixture()
def repo(tmp_path):
    """세 spec·electron·워크플로가 서로 맞는 최소 저장소."""
    _git(tmp_path, "init", "-q")
    for rel in (
        "ai_orchestrator/__init__.py",
        "ai_orchestrator/server/__init__.py",
        "ai_orchestrator/server/desktop_entry.py",
        "ai_orchestrator/server/mcp_server.py",
        "core/agent_runtime/runtime/local_agent.py",
        "scripts/local_agent.py",  # electron extraResources 는 지금도 이 옛경로(호환 shim)를 패키징 대상으로 씀
        "scripts/naver/smartstore/__init__.py",
        "logging_utils.py",
        "configs/app.json",
        "admin-web/electron/lib/agent.js",
        "admin-web/electron/playwright.electron.config.ts",
    ):
        _w(tmp_path, rel)
    hidden = ["ai_orchestrator.server", "scripts.naver.smartstore", "logging_utils", "fastapi"]
    _w(tmp_path, "haehan-server.spec", _spec("ai_orchestrator/server/desktop_entry.py", "haehan-server", hidden))
    _w(tmp_path, "local-agent.spec", _spec("core/agent_runtime/runtime/local_agent.py", "local-agent", ["playwright"]))
    _w(tmp_path, "mcp-server.spec", _spec("ai_orchestrator/server/mcp_server.py", "haehan-mcp", ["mcp.server"]))
    _w(tmp_path, gate.PACKAGE_JSON, _package_json())
    _w(tmp_path, "admin-web/electron/main.js", JS_OK)
    _w(tmp_path, gate.WORKFLOW, WORKFLOW)
    _git(tmp_path, "add", "-A")
    return tmp_path


def _fails(root: Path) -> list[gate.Finding]:
    return [f for f in gate.check_all(root) if f.status == "FAIL"]


def test_valid_repo_passes(repo):
    assert _fails(repo) == []
    assert gate.main(["--check-all", "--root", str(repo)]) == 0


def test_broken_hiddenimport_of_our_module_fails(repo):
    hidden = ["ai_orchestrator.server", "ai_orchestrator.auth"]  # auth 는 옮겨져 없다
    _w(repo, "haehan-server.spec", _spec("ai_orchestrator/server/desktop_entry.py", "haehan-server", hidden))
    fails = _fails(repo)
    assert [f.ref for f in fails] == ["hiddenimport ai_orchestrator.auth"]
    assert gate.main(["--check-all", "--root", str(repo)]) == 1


def test_missing_entry_file_fails(repo):
    _w(repo, "mcp-server.spec", _spec("ai_orchestrator/gone_server.py", "haehan-mcp", []))
    assert [(f.source, f.ref) for f in _fails(repo)] == [("mcp-server.spec", "entry ai_orchestrator/gone_server.py")]


def test_third_party_hiddenimport_ignored(repo):
    hidden = ["totally_unknown_lib.sub", "uvicorn.loops.auto", "fastapi"]
    _w(repo, "local-agent.spec", _spec("core/agent_runtime/runtime/local_agent.py", "local-agent", hidden))
    findings = gate.check_all(repo)
    assert not any("totally_unknown_lib" in f.ref for f in findings)
    assert [f for f in findings if f.status == "FAIL"] == []


def test_resources_path_without_extra_resources_fails(repo):
    js = JS_OK + 'const mcp = path.join(process.resourcesPath, "mcp", "haehan-mcp");\n'
    _w(repo, "admin-web/electron/main.js", js)
    fails = _fails(repo)
    assert [f.ref for f in fails] == ["resourcesPath/mcp/haehan-mcp"]


def test_resources_exe_name_must_match_spec(repo):
    js = 'path.join(process.resourcesPath, "server", "haehan-server", "old-server.exe");\n'
    _w(repo, "admin-web/electron/lib/agent.js", js)
    assert [f.detail for f in _fails(repo)] == ["spec EXE name 은 haehan-server.exe"]


def test_dist_resource_without_spec_fails_and_next_output_skipped(repo):
    _w(repo, gate.PACKAGE_JSON, _package_json([{"from": "../../dist/old-agent", "to": "old-agent"}]))
    findings = gate.check_all(repo)
    assert [f.ref for f in findings if f.status == "FAIL"] == ["extraResources ../../dist/old-agent → old-agent"]
    skipped = [f for f in findings if f.status == "SKIP" and "nextjs" in f.ref]
    assert skipped and skipped[0].detail == "build output, not checked"


def test_missing_extra_resources_source_fails(repo):
    (repo / "core" / "agent_runtime" / "runtime" / "local_agent.py").unlink()
    (repo / "scripts" / "local_agent.py").unlink()
    _git(repo, "add", "-A")
    refs = {f.ref for f in _fails(repo)}
    assert "extraResources ../../scripts → scripts filter local_agent.py" in refs
    assert "entry core/agent_runtime/runtime/local_agent.py" in refs


def test_workflow_missing_spec_fails(repo):
    _w(repo, gate.WORKFLOW, WORKFLOW.replace("haehan-server.spec", "old-server.spec"))
    assert [f.ref for f in _fails(repo)] == ["spec old-server.spec"]


def test_untracked_file_does_not_count(repo):
    """존재 판정은 git 추적 기준 — 로컬에만 있는 파일로 통과했다가 CI 에서 깨지는 일 방지."""
    hidden = ["ai_orchestrator.local_only"]
    _w(repo, "ai_orchestrator/local_only.py")  # add 하지 않음
    _w(repo, "local-agent.spec", _spec("core/agent_runtime/runtime/local_agent.py", "local-agent", hidden))
    assert [f.ref for f in _fails(repo)] == ["hiddenimport ai_orchestrator.local_only"]


def test_parse_spec_root_chain_and_collect_loop():
    text = (
        "ROOT = Path(SPECPATH)\n"
        "h = ['a']\n"
        "for _pkg in ('ai_orchestrator', 'orchestrator_v1'):\n"
        "    h += collect_submodules(_pkg)\n"
        "a = Analysis([str(ROOT / 'x' / 'y.py')], datas=[(str(ROOT / 'd' / 'e'), 'd'), ('rel/dir', 'r')],"
        " hiddenimports=h)\n"
        "exe = EXE(name='n1')\ncoll = COLLECT(name='n2')\n"
    )
    info = gate.parse_spec(text, "t.spec")
    assert info.entries == ["x/y.py"]
    assert info.hidden == ["a"]
    assert info.collect == ["ai_orchestrator", "orchestrator_v1"]
    assert sorted(info.paths) == ["d/e", "rel/dir"]
    assert (info.exe_name, info.collect_name) == ("n1", "n2")


def test_needs_check_staged_filter(repo):
    assert gate.needs_check(["haehan-server.spec"], repo)
    assert gate.needs_check(["admin-web/electron/lib/agent.js"], repo)
    assert gate.needs_check([".github/workflows/ci.yml"], repo)
    assert gate.needs_check(["ai_orchestrator/server/__init__.py"], repo)  # spec hiddenimport 에 이름이 있다
    assert gate.needs_check(["core/agent_runtime/runtime/local_agent.py"], repo)  # spec 진입 파일 이름
    assert not gate.needs_check(["ai_orchestrator/other.py", "docs/a.md"], repo)


def test_staged_mode_skips_unrelated_and_blocks_broken(repo):
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    _w(repo, "docs/a.md", "x")
    _git(repo, "add", "-A")
    assert gate.main(["--staged", "--root", str(repo)]) == 0
    _w(repo, "mcp-server.spec", _spec("ai_orchestrator/gone.py", "haehan-mcp", []))
    _git(repo, "add", "-A")
    assert gate.main(["--staged", "--root", str(repo)]) == 1


def test_real_repo_passes():
    assert [f for f in gate.check_all(REAL_ROOT) if f.status == "FAIL"] == []
