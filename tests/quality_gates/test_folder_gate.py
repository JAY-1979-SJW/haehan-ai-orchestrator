"""폴더 승인 게이트(G16) 테스트 — 승인 목록에 없는 폴더의 코드 파일은 차단, 등록 폴더·삭제·라벨 있는 추가는 통과."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.repo_gates import folder_gate as gate

REAL_ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=True
    ).stdout


def _w(root: Path, rel: str, text: str = "x = 1\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _entry(path: str) -> dict:
    return {
        "path": path,
        "purpose": "시험",
        "kind": "기능",
        "status": "approved",
        "approved_at": "2026-10-07",
        "approved_by": "시험",
    }


def _set_registry(root: Path, paths: list[str]) -> None:
    gate.write_registry(root, [_entry(p) for p in paths])


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _w(tmp_path, "scripts/approved/tool.py")
    _w(tmp_path, "scripts/approved/sub/deep.py")
    _set_registry(tmp_path, ["scripts/approved", "scripts/approved/sub"])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _staged(root: Path) -> int:
    return gate.main(["--staged", "--root", str(root)])


def _head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


# ── 차단 / 통과 ─────────────────────────────────────────────────────────


def test_new_file_in_unregistered_folder_is_blocked(repo, capsys):
    """① 미등록 폴더에 새 코드 파일 → 차단(안내에 승인 절차 포함)."""
    _w(repo, "scripts/sneaky/new_tool.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1
    err = capsys.readouterr().err
    assert "scripts/sneaky/" in err and "folder-approved" in err and "새 폴더 요청" in err


def test_new_file_in_registered_folder_passes(repo):
    """② 등록된 폴더의 새 파일은 통과."""
    _w(repo, "scripts/approved/another.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_subfolders_are_registered_separately(repo, capsys):
    """③ 부모 폴더가 등록돼 있어도 하위 폴더는 별도 등록이 필요하다."""
    _w(repo, "scripts/approved/sub/deeper/x.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1
    assert "scripts/approved/sub/deeper/" in capsys.readouterr().err
    _git(repo, "reset", "-q")
    _w(repo, "scripts/approved/sub/ok.py")  # 등록된 sub 는 통과
    (repo / "scripts/approved/sub/deeper/x.py").unlink()
    (repo / "scripts/approved/sub/deeper").rmdir()
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


@pytest.mark.parametrize("name", ["data.json", "README.md", "notes.txt", "run.bat", "style.css"])
def test_non_code_files_in_unregistered_folders_are_ignored(repo, name):
    _w(repo, f"somewhere/new/{name}", "x\n")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


@pytest.mark.parametrize("ext", [".py", ".ts", ".tsx", ".js"])
def test_all_code_extensions_are_checked(repo, ext):
    _w(repo, f"brand_new_dir/file{ext}")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1


def test_modifying_or_deleting_existing_files_is_not_checked(repo):
    """기존 파일 수정·삭제는 이 게이트가 보지 않는다(삭제는 오히려 자유)."""
    (repo / "scripts/approved/tool.py").write_text("x = 2\n", encoding="utf-8")
    (repo / "scripts/approved/sub/deep.py").unlink()
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_rename_into_unregistered_folder_is_blocked_and_into_registered_passes(repo):
    (repo / "scripts/newplace").mkdir()
    _git(repo, "mv", "scripts/approved/tool.py", "scripts/newplace/tool.py")
    assert _staged(repo) == 1
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "mv", "scripts/approved/tool.py", "scripts/approved/sub/tool.py")
    assert _staged(repo) == 0


def test_repo_root_folder_is_a_folder_too(repo):
    """저장소 루트('.')의 코드 파일도 폴더 '.' 의 승인이 필요하다."""
    _w(repo, "root_script.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1
    _set_registry(repo, [".", "scripts/approved", "scripts/approved/sub"])
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_check_all_fails_on_unregistered_folder_and_passes_after_removal(repo, capsys):
    assert gate.main(["--check-all", "--root", str(repo)]) == 0
    _w(repo, "scripts/hidden/z.py")
    _git(repo, "add", "-A")
    assert gate.main(["--check-all", "--root", str(repo)]) == 1
    assert "scripts/hidden/" in capsys.readouterr().err
    _git(repo, "rm", "-q", "-f", "scripts/hidden/z.py")
    assert gate.main(["--check-all", "--root", str(repo)]) == 0


# ── 승인 증거(라벨) ─────────────────────────────────────────────────────


def _add_folder_commit(repo: Path, new_path: str = "scripts/newtool") -> str:
    base = _head(repo)
    _w(repo, f"{new_path}/impl.py")
    _set_registry(repo, ["scripts/approved", "scripts/approved/sub", new_path])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add folder")
    return base


def _approval(repo: Path, base: str, event: str, labels: str = "", extra: list[str] | None = None) -> int:
    return gate.main(
        [
            "--check-approval",
            "--base",
            base,
            "--head",
            "HEAD",
            "--event",
            event,
            "--labels",
            labels,
            "--root",
            str(repo),
            *(extra or []),
        ]
    )


def test_added_folder_without_label_fails_on_pull_request(repo, capsys):
    """④ 목록에 항목이 추가됐는데 PR 라벨이 없으면 FAIL."""
    base = _add_folder_commit(repo)
    assert _approval(repo, base, "pull_request", labels="bug,docs") == 1
    err = capsys.readouterr().err
    assert "scripts/newtool" in err and "folder-approved" in err


def test_added_folder_with_label_passes_on_pull_request(repo):
    """⑤ 같은 추가라도 라벨 folder-approved 가 있으면 PASS."""
    base = _add_folder_commit(repo)
    assert _approval(repo, base, "pull_request", labels="bug, folder-approved") == 0


def test_removed_folder_needs_no_approval(repo):
    """⑥ 목록에서 항목을 삭제하는 변경은 승인 없이 PASS(줄이는 방향)."""
    base = _head(repo)
    (repo / "scripts/approved/sub/deep.py").unlink()
    _set_registry(repo, ["scripts/approved"])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "shrink")
    assert _approval(repo, base, "pull_request", labels="") == 0


def test_no_registry_change_passes_everywhere(repo):
    base = _head(repo)
    _w(repo, "scripts/approved/more.py")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "code only")
    for event in ("pull_request", "push", "workflow_dispatch"):
        assert _approval(repo, base, event) == 0


def test_added_folder_fails_on_workflow_dispatch_even_with_label_text(repo):
    """수동 실행에는 라벨을 확인할 PR 이 없다 — 추가가 있으면 FAIL(라벨 문자열을 넘겨도)."""
    base = _add_folder_commit(repo)
    assert _approval(repo, base, "workflow_dispatch", labels="folder-approved") == 1


def test_added_folder_on_push_warns_by_default_and_fails_with_flag(repo, capsys):
    """병합 직후 push 실행이 승인된 추가를 다시 막으면 master CI 가 깨진다 — 기본은 경고(통과), 필요하면 --on-push fail."""
    base = _add_folder_commit(repo)
    assert _approval(repo, base, "push") == 0
    assert "병합 전 PR" in capsys.readouterr().out
    assert _approval(repo, base, "push", extra=["--on-push", "fail"]) == 1


def test_initial_registration_when_base_has_no_registry_passes(tmp_path):
    """이 게이트를 처음 넣는 PR: 기준에 목록 파일이 없으면 초기 등록으로 본다(현재 트리·설계서 사전 승인)."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _w(tmp_path, "pkg/a.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "before gate")
    base = _head(tmp_path)
    assert gate.main(["--init-registry", "--root", str(tmp_path)]) == 0
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "gate")
    assert _approval(tmp_path, base, "pull_request", labels="") == 0


# ── 생성·조회 ───────────────────────────────────────────────────────────


def test_init_registry_covers_current_tree_and_pre_approved_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "LEGACY_TO_REMOVE", frozenset({"notice_radar"}))
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _w(tmp_path, "scripts/a/x.py")
    _w(tmp_path, "notice_radar/legacy.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "i")
    assert gate.main(["--init-registry", "--root", str(tmp_path)]) == 0
    reg = gate.load_registry(tmp_path)
    assert {"scripts/a", "notice_radar"} <= set(reg)  # 현재 트리
    assert {"scripts/browser/cdp", "ai_orchestrator/site_work", "ai_orchestrator/connectors/naver_mail"} <= set(
        reg
    )  # 사전 승인 목표
    assert reg["notice_radar"]["status"] == "legacy_to_remove" and reg["scripts/a"]["status"] == "approved"
    assert all({"path", "purpose", "kind", "status", "approved_at", "approved_by"} <= set(e) for e in reg.values())
    assert gate.main(["--init-registry", "--root", str(tmp_path)]) == 2  # 이미 있으면 덮어쓰지 않는다


def test_missing_registry_is_an_error_not_a_silent_pass(tmp_path, capsys):
    _git(tmp_path, "init", "-q")
    assert gate.main(["--check-all", "--root", str(tmp_path)]) == 2
    assert "--init-registry" in capsys.readouterr().err


def test_classify_reports_registered_and_unregistered(repo, capsys):
    assert gate.main(["--classify", "scripts/approved/tool.py", "scripts/zzz/y.py", "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "등록됨" in out and "미등록" in out


# ── 이 저장소 ───────────────────────────────────────────────────────────


def test_real_repo_check_all_passes():
    """⑦ 현재 저장소의 모든 코드 폴더가 승인 목록 안에 있다."""
    assert gate.main(["--check-all", "--root", str(REAL_ROOT)]) == 0


def test_real_registry_is_well_formed():
    reg = json.loads((REAL_ROOT / gate.REGISTRY).read_text(encoding="utf-8"))
    entries = reg["folders"]
    assert reg["count"] == len(entries)
    paths = [e["path"] for e in entries]
    assert len(paths) == len(set(paths)), "중복 등록"
    assert paths == sorted(paths), "정렬되어 있지 않다(diff 가 읽기 쉽도록 정렬 유지)"
    assert {e["status"] for e in entries} <= {"approved", "legacy_to_remove"}
    assert {e["kind"] for e in entries} <= {"도구", "기능", "공용 기반", "레거시", "시험", "앱"}
