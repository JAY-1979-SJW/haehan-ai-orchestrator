"""'저장소 루트 직접 계산' 차단 게이트(G5) 테스트 — 경계(자기 폴더 허용 / 루트 도달 차단 / 예외)를 고정한다."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.devflow.make_shim import make_shim
from tools.repo_gates import root_calc_gate as gate

REAL_ROOT = Path(__file__).resolve().parents[2]
CFG = gate.load_config(REAL_ROOT)


def _bad(path: str, code: str) -> list:
    lines = code.splitlines()
    return gate.check_file(path, [(i + 1, ln) for i, ln in enumerate(lines)], code, CFG)


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("scripts/ops/x.py", "Path(__file__).resolve().parents[2]"),  # scripts/ops → 루트
        ("scripts/ops/x.py", "ROOT = Path(__file__).parent.parent.parent"),
        ("scripts/ops/x.py", "ROOT = Path(__file__).resolve().parent.parent.parent"),
        ("ai_orchestrator/connectors/a.py", "R = Path(__file__).resolve().parents[2]"),
        ("ai_orchestrator/connectors/a.py", "R = pathlib.Path(__file__).absolute().parents[2]"),
        ("scripts/x.py", "R = Path(__file__).resolve().parents[1]"),  # scripts/x.py → 루트
        ("scripts/x.py", "R = Path(__file__).parent.parent"),
        ("scripts/x.py", "R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"),
        ("scripts/ops/x.py", "R = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))"),
        ("root_mod.py", "R = Path(__file__).parent.parent"),  # 루트 파일에서 한 칸 더 = 저장소 밖
        ("scripts/x.py", "R = Path(os.path.abspath(__file__)).parents[1]"),
    ],
)
def test_root_reaching_expression_is_blocked(path, line):
    assert _bad(path, line), f"{path}: {line}"


@pytest.mark.parametrize(
    ("path", "line"),
    [
        ("scripts/ops/x.py", "HERE = Path(__file__).parent"),  # 자기 폴더 한 단계
        ("scripts/ops/x.py", "HERE = Path(__file__).resolve().parent"),
        ("scripts/ops/x.py", "HERE = Path(__file__).resolve().parents[0]"),
        ("scripts/ops/x.py", "HERE = os.path.dirname(__file__)"),
        ("scripts/ops/x.py", "HERE = os.path.dirname(os.path.abspath(__file__))"),
        ("scripts/ops/x.py", "S = Path(__file__).resolve().parents[1]"),  # scripts/ 폴더 — 루트 아님
        ("ai_orchestrator/connectors/a.py", "T = Path(__file__).resolve().parents[1]"),  # ai_orchestrator/
        ("ai_orchestrator/connectors/a.py", "T = Path(__file__).parent.parent"),
        ("scripts/x.py", "HERE = Path(__file__).parent"),
        ("root_mod.py", "HERE = Path(__file__).parent"),  # 루트 파일의 한 단계는 허용(자기 폴더)
        ("scripts/ops/x.py", "# ROOT = Path(__file__).resolve().parents[2]  (주석 속 예시)"),
        ("scripts/ops/x.py", "x = repo_root()"),
    ],
)
def test_own_folder_and_non_root_expression_is_allowed(path, line):
    assert not _bad(path, line), f"{path}: {line}"


def test_non_python_and_exempt_paths_are_ignored():
    code = "ROOT = Path(__file__).resolve().parents[2]\n"
    for path in (
        "tests/test_a.py",
        "ai_orchestrator/tests/test_a.py",
        "apps/foo/sub/x.py",
        "docs/example.py",
        "scripts/archive/old.py",
        "ai_orchestrator/paths/__init__.py",
        "scripts/common/app_paths.py",
        "scripts/data_paths.py",
        "scripts/browser/session/browser_paths.py",
        "scripts/some/tests/conftest.py",
    ):
        assert not gate.check_file(path, [(1, code.strip())], code, CFG), path
    assert not gate.check_file("scripts/ops/readme.md", [(1, code.strip())], code, CFG)


def test_sys_path_bootstrap_allowed_in_scripts_only():
    code = "import sys\nfrom pathlib import Path\nROOT = Path(__file__).resolve().parents[2]\nsys.path.insert(0, str(ROOT))\n"
    assert not gate.check_file("scripts/ops/x.py", [(3, code.splitlines()[2])], code, CFG)
    # 같은 줄 부트스트랩
    same = "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))"
    assert not gate.check_file("scripts/ops/x.py", [(1, same)], same, CFG)
    # ai_orchestrator 는 항상 패키지로 import 되므로 부트스트랩 예외 없음
    assert gate.check_file(
        "ai_orchestrator/connectors/a.py", [(3, "ROOT = Path(__file__).resolve().parents[2]")], code, CFG
    )
    # sys.path 에 쓰이지 않는 루트 계산은 scripts/ 라도 차단(데이터 경로 계산 등)
    data = "ROOT = Path(__file__).resolve().parents[2]\nDB = ROOT / 'data' / 'x.db'\n"
    assert gate.check_file("scripts/ops/x.py", [(1, data.splitlines()[0])], data, CFG)


def test_make_shim_bootstrap_marker_is_exempt_everywhere(tmp_path):
    (tmp_path / "scripts" / "instagram").mkdir(parents=True)
    (tmp_path / "scripts" / "instagram" / "demo_batch.py").write_text(
        "if __name__ == '__main__':\n    pass\n", encoding="utf-8"
    )
    make_shim(
        "ai_orchestrator/tools/demo_batch.py", "scripts/instagram/demo_batch.py", tmp_path
    )  # 폴더 깊이 2 → parents[2]
    body = (tmp_path / "ai_orchestrator" / "tools" / "demo_batch.py").read_text(encoding="utf-8")
    assert "parents[2]" in body
    lines = body.splitlines()
    added = [(i + 1, ln) for i, ln in enumerate(lines)]
    assert not gate.check_file("ai_orchestrator/tools/demo_batch.py", added, body, CFG)
    # 마커를 지우면 같은 줄이 차단된다(마커가 예외의 근거라는 대조)
    stripped = body.replace("haehan-root-bootstrap", "removed")
    assert gate.check_file(
        "ai_orchestrator/tools/demo_batch.py", [(i + 1, ln) for i, ln in enumerate(stripped.splitlines())], stripped, CFG
    )


# ── git diff 연동: 새 줄만 막는다 ─────────────────────────────────────


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "configs").mkdir()
    shutil.copy(REAL_ROOT / gate.CONFIG, tmp_path / gate.CONFIG)
    (tmp_path / "ai_orchestrator" / "connectors").mkdir(parents=True)
    # 기존(옛) 위반 줄 — 기준선 없이도 막지 않아야 한다
    (tmp_path / "ai_orchestrator/connectors/old.py").write_text(
        "from pathlib import Path\nROOT = Path(__file__).resolve().parents[2]\n", encoding="utf-8"
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_existing_violation_lines_are_not_blocked_but_new_ones_are(repo, capsys):
    f = repo / "ai_orchestrator/connectors/old.py"
    f.write_text(f.read_text(encoding="utf-8") + "X = 1\n", encoding="utf-8")  # 기존 줄은 그대로, 무관한 새 줄
    _git(repo, "add", "-A")
    assert gate.main(["--staged", "--root", str(repo)]) == 0
    f.write_text(f.read_text(encoding="utf-8") + "ROOT2 = Path(__file__).resolve().parents[2]\n", encoding="utf-8")
    _git(repo, "add", "-A")
    assert gate.main(["--staged", "--root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert "old.py:4" in err and "ai_orchestrator.paths import repo_root" in err


def test_new_file_in_scripts_blocked_with_scripts_guidance(repo, capsys):
    (repo / "scripts/ops").mkdir(parents=True)
    (repo / "scripts/ops/new.py").write_text("DB = Path(__file__).resolve().parents[2] / 'data'\n", encoding="utf-8")
    _git(repo, "add", "-A")
    assert gate.main(["--staged", "--root", str(repo)]) == 1
    assert "scripts.common.app_paths import repo_root" in capsys.readouterr().err


def test_check_diff_base_head(repo):
    base = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "ai_orchestrator/connectors/new2.py").write_text(
        "from pathlib import Path\nHERE = Path(__file__).parent\nROOT = Path(__file__).parents[2]\n", encoding="utf-8"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "new")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert gate.main(["--check-diff", base, head, "--root", str(repo)]) == 1
    assert gate.main(["--check-diff", head, head, "--root", str(repo)]) == 0


def _integration_base_ref() -> str | None:
    """이 브랜치가 갈라져 나온 기준(master)의 ref. CI 러너에는 로컬 브랜치가 없고 origin/<이름> 만 있다."""
    for ref in ("origin/master", "master"):
        r = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=str(REAL_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if r.returncode == 0:
            return ref
    return None


def test_real_repo_has_no_violation_in_own_branch_diff():
    """이 브랜치가 master 위에 새로 추가한 줄도 통과(자기 도구들이 repo_root 를 쓰는지).

    예전에는 기준을 로컬 브랜치 이름(stage/t-base-w4)으로 박아 뒀다 — CI 러너에는 그 로컬 브랜치가 없어 기준을 못 찾고 죽었고,
    로컬에서는 오래된 merge-base 때문에 이미 master 에 있던 줄까지 새 줄로 잡혔다. master 와의 merge-base 를 쓴다.
    """
    ref = _integration_base_ref()
    if ref is None:  # master 이력이 없는 얕은 복제에서는 기준을 정할 수 없다(CI 는 fetch-depth: 0 이라 origin/master 가 있다)
        pytest.skip("origin/master 도 master 도 없어 브랜치 기준을 정할 수 없음")
    base = _git(REAL_ROOT, "merge-base", "HEAD", ref).strip()
    assert gate.main(["--check-diff", base, "HEAD", "--root", str(REAL_ROOT)]) == 0
