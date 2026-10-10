"""verify_change.moved_location_deps — __file__ 단독(self-relaunch)은 이동 깊이와 무관해 오탐이면 안 되고,
.parent/.parents 체인(진짜 위치의존)은 그대로 잡혀야 한다 (PR #160 재검증: browser_rpc_server.py·
cdp_daemon.py 의 self-relaunch 줄이 이동마다 오탐했던 결함 재발 방지).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tools import verify_change as vc


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@test")
    _git(repo, "config", "user.name", "test")
    return repo


def test_self_relaunch_not_flagged_but_parent_chain_still_is(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)

    old_dir = repo / "scripts"
    old_dir.mkdir()
    old_file = old_dir / "daemon.py"
    old_file.write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parent.parent\n\n"
        "def relaunch():\n"
        "    script = Path(__file__).resolve()\n"
        "    return sys.executable, str(script)\n",
        encoding="utf-8",
    )
    _git(repo, "add", "scripts/daemon.py")
    _git(repo, "commit", "-q", "-m", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()

    new_dir = repo / "scripts" / "browser" / "cdp"
    new_dir.mkdir(parents=True)
    _git(repo, "mv", "scripts/daemon.py", "scripts/browser/cdp/daemon.py")
    _git(repo, "commit", "-q", "-m", "move 1->3 depth, 내용 변경 없음(의도된 결함 재현)")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()

    monkeypatch.setattr(vc, "ROOT", repo)
    out = vc.moved_location_deps(base, head)

    assert not any("script = Path(__file__).resolve()" in ln for ln in out), f"self-relaunch 오탐: {out}"
    assert any("parent.parent" in ln for ln in out), f"진짜 위치의존(parent.parent)이 잡혀야 한다: {out}"
