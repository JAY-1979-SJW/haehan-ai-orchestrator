"""최상위 평면 금지 게이트(G15) 테스트 — 평면 새 파일은 차단, 기준선 파일·진입점·하위 폴더·삭제는 통과."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.repo_gates import flat_root_gate as gate

REAL_ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


def _w(root: Path, rel: str, text: str = "x = 1\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "configs").mkdir()
    shutil.copy(REAL_ROOT / gate.CONFIG, tmp_path / gate.CONFIG)
    _w(tmp_path, "scripts/legacy_flat.py")  # 이미 평면에 있던 파일(기준선 대상)
    _w(tmp_path, "ai_orchestrator/legacy_core.py")
    _w(tmp_path, "root_shim.py")
    _w(tmp_path, "scripts/browser/already_nested.py")  # 하위 폴더 — 대상 아님
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    assert gate.main(["--init-baseline", "--root", str(tmp_path)]) == 0
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def _staged(root: Path) -> int:
    return gate.main(["--staged", "--root", str(root)])


def test_baseline_contains_existing_flat_files_only(repo):
    base = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    assert base["files"] == ["ai_orchestrator/legacy_core.py", "root_shim.py", "scripts/legacy_flat.py"]
    assert base["count"] == 3


@pytest.mark.parametrize("path", ["scripts/new_tool.py", "ai_orchestrator/new_module.py", "new_root_script.py"])
def test_new_flat_file_is_blocked(repo, capsys, path):
    """① 평면 금지 폴더(scripts·ai_orchestrator·저장소 루트) 바로 아래의 새 파일은 차단된다."""
    _w(repo, path)
    _git(repo, "add", "-A")
    assert _staged(repo) == 1
    err = capsys.readouterr().err
    assert path in err and "하위 폴더" in err


@pytest.mark.parametrize("path", ["scripts/legacy_flat.py", "ai_orchestrator/legacy_core.py", "root_shim.py"])
def test_modifying_a_baseline_file_passes(repo, path):
    """② 기준선 파일은 고쳐도 통과한다(호환 shim 으로 같은 경로에 다시 쓰는 경우 포함)."""
    _w(repo, path, "x = 2\n")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_deleting_a_baseline_file_is_allowed(repo):
    """③ 삭제는 허용된다(오히려 장려) — 기준선에는 남아 있어도 통과하고 --check-all 이 줄이라고 알려 준다."""
    (repo / "scripts/legacy_flat.py").unlink()
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


@pytest.mark.parametrize(
    "path",
    [
        "scripts/browser/cdp/new_cdp.py",
        "ai_orchestrator/core/models.py",
        "scripts/naver/blog/x.py",
        "tests/test_new.py",
    ],
)
def test_files_in_subfolders_are_not_flat(repo, path):
    _w(repo, path)
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


@pytest.mark.parametrize(
    "path",
    ["ai_orchestrator/asgi.py", "ai_orchestrator/router.py", "ai_orchestrator/config.py", "app.py", "conftest.py"],
)
def test_entry_points_are_allowed(repo, path):
    _w(repo, path)
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_non_python_files_are_ignored(repo):
    _w(repo, "scripts/notes.md", "# x\n")
    _w(repo, "scripts/run.bat", "echo hi\n")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_move_to_subfolder_passes_and_move_into_flat_is_blocked(repo):
    (repo / "scripts/legacy_flat.py").rename(repo / "scripts/browser/legacy_flat.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0  # 평면 → 하위 폴더 이동은 통과
    _git(repo, "commit", "-qm", "move out")
    (repo / "scripts/browser/already_nested.py").rename(repo / "scripts/now_flat.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1  # 하위 폴더 → 평면 이동은 새 평면 파일


def test_check_all_fails_on_unbaselined_flat_file_and_reports_stale(repo, capsys):
    assert gate.main(["--check-all", "--root", str(repo)]) == 0
    _w(repo, "scripts/sneaky.py")
    _git(repo, "add", "-A")
    assert gate.main(["--check-all", "--root", str(repo)]) == 1
    assert "scripts/sneaky.py" in capsys.readouterr().err
    _git(repo, "rm", "-q", "-f", "scripts/sneaky.py")
    (repo / "scripts/legacy_flat.py").unlink()
    _git(repo, "add", "-A")
    assert gate.main(["--check-all", "--root", str(repo)]) == 0
    assert "더 이상 평면에 없음" in capsys.readouterr().err


def test_update_baseline_only_shrinks(repo):
    (repo / "scripts/legacy_flat.py").unlink()
    _git(repo, "add", "-A")
    assert gate.main(["--update-baseline", "--root", str(repo)]) == 0
    base = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    assert "scripts/legacy_flat.py" not in base["files"] and base["count"] == 2
    _w(repo, "scripts/added_later.py")
    _git(repo, "add", "-A")
    assert gate.main(["--update-baseline", "--root", str(repo)]) == 1  # 늘리기는 불가
    after = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    assert "scripts/added_later.py" not in after["files"]


def test_init_baseline_refuses_to_overwrite(repo):
    assert gate.main(["--init-baseline", "--root", str(repo)]) == 2


def test_sync_baseline_requires_reason(repo, capsys):
    rc = gate.main(["--sync-baseline", "--root", str(repo)])
    assert rc == 2
    assert "--reason" in capsys.readouterr().err


def test_sync_baseline_rejects_file_not_in_verify_ref(repo, capsys):
    """CI #164 류 재발 방지: 이번 브랜치가 새로 만든 평면 파일은 --sync-baseline 으로
    절대 기준선에 섞여 들어가면 안 된다 — verify-in-ref 에 없으면 거부."""
    _w(repo, "scripts/brandnew_flat.py")
    _git(repo, "add", "-A")
    rc = gate.main([
        "--sync-baseline", "--root", str(repo), "--reason", "테스트", "--verify-in-ref", "HEAD",
    ])
    assert rc == 1
    assert "scripts/brandnew_flat.py" in capsys.readouterr().err
    base = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    assert "scripts/brandnew_flat.py" not in base["files"]


def test_sync_baseline_grows_when_rule_change_adds_preexisting_flat_file(repo):
    """configs/flat_root_gate.json 규칙 변경으로 기존(커밋된) 파일이 새로 flat 이 되면,
    과거 커밋(HEAD)에도 있었다는 전제로 --sync-baseline 이 기준선을 늘려야 한다."""
    _w(repo, "scripts/common/existing_helper.py")  # 지금은 하위 폴더라 대상 아님
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add existing nested file before rule change")

    cfg = json.loads((repo / gate.CONFIG).read_text(encoding="utf-8"))
    cfg["flat_dirs"].append("scripts/common")  # 이제 scripts/common 바로 아래도 평면 금지 대상
    (repo / gate.CONFIG).write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "flat_dirs 확장 — scripts/common/existing_helper.py 가 새로 flat")

    rc = gate.main([
        "--sync-baseline", "--root", str(repo), "--reason", "flat_dirs 확장으로 재분류",
        "--verify-in-ref", "HEAD",
    ])
    assert rc == 0
    files = set(json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))["files"])
    assert "scripts/common/existing_helper.py" in files
    assert "scripts/legacy_flat.py" in files  # 기존 기준선 유지


def test_real_repo_check_all_matches_committed_baseline():
    """이 저장소의 추적 파일 전체가 기준선 안에 있다(새 평면 파일이 몰래 들어오지 않았다)."""
    assert gate.main(["--check-all", "--root", str(REAL_ROOT)]) == 0
