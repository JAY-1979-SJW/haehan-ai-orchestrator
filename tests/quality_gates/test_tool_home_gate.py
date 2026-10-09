"""도구 집 게이트(G11) 테스트 — 집 밖 새 파일은 차단, 집 안·예외·기준선 수정·이동(집 안)은 통과."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.repo_gates import tool_home_gate as gate

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
    _w(tmp_path, "scripts/instagram/old_ig.py")  # 이미 집 안인 기존 파일
    _w(tmp_path, "scripts/ig_legacy.py")  # 기존 집 밖 파일(기준선 대상)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    assert gate.main(["--init-baseline", "--root", str(tmp_path)]) == 0
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def _staged(root: Path) -> int:
    return gate.main(["--staged", "--root", str(root)])


def test_baseline_contains_existing_leak_only(repo):
    base = json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))
    assert base["files"] == ["scripts/ig_legacy.py"] and base["count"] == 1


def test_new_file_outside_home_is_blocked(repo, capsys):
    _w(repo, "scripts/ig_new_tool.py")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1
    err = capsys.readouterr().err
    assert "scripts/ig_new_tool.py" in err and "scripts/instagram/" in err


@pytest.mark.parametrize(
    "path",
    [
        "scripts/instagram/new_ok.py",  # 구현 집
        "ai_orchestrator/connectors/instagram/router.py",  # API 집
        "admin-web/src/app/hanafax/page.tsx",  # 화면 집
        "scripts/naver/smartstore/api/new.py",
    ],
)
def test_new_file_inside_home_passes(repo, path):
    _w(repo, path)
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_instagram_new.py",
        "ai_orchestrator/tests/test_hanafax_x.py",
        "docs/instagram_note.py",
        "scripts/archive/instagram_old.py",
        "apps/instagram-standalone/cli.py",
        "scripts/google/youtube/new_tab.py",  # 도메인 계약 소유(google 의 youtube 하위 탭)
        "ai_orchestrator/persistence/instagram_store.py",  # 층 표준 폴더
        "ai_orchestrator/services/hanafax_service.py",
        "admin-web/src/lib/hanafax/client.ts",
        "admin-web/src/app/hanafax/page.test.tsx",
    ],
)
def test_exempt_folders_pass(repo, path):
    _w(repo, path)
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_modifying_baseline_file_passes(repo):
    _w(repo, "scripts/ig_legacy.py", "x = 2\n")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_staged_shim_outside_home_passes(repo):
    """새 shim(# haehan-shim:) 파일은 집 밖이어도 통과한다 — shim 은 메커니즘상 항상
    '옛 경로(집 밖) -> 실제 모듈'이라 집 밖이 정상이다."""
    _w(repo, "scripts/ig_old_shim.py", "# haehan-shim: scripts.instagram.ig_old_shim\nimport sys\n")
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_existing_shim_excluded_from_leaks_and_baseline(repo):
    """shim 은 current_leaks()/기준선 집계에서도 빠진다 — --update-baseline 으로 줄어든다."""
    _w(repo, "scripts/ig_old_shim.py", "# haehan-shim: scripts.instagram.ig_old_shim\nimport sys\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add shim")
    cfg = gate.load_config(repo)
    assert "scripts/ig_old_shim.py" not in gate.current_leaks(repo, cfg)


def test_rename_into_home_passes_and_out_of_home_blocked(repo):
    _git(repo, "mv", "scripts/ig_legacy.py", "scripts/instagram/ig_legacy.py")
    assert _staged(repo) == 0
    _git(repo, "reset", "-q", "--hard")
    _git(repo, "mv", "scripts/instagram/old_ig.py", "scripts/ig_elsewhere.py")  # 집 밖으로 나가는 이동
    assert _staged(repo) == 1


def test_non_tool_and_non_code_files_are_ignored(repo):
    _w(repo, "scripts/ops/some_helper.py")
    _w(repo, "scripts/ig_notes.md", "# note\n")
    _w(repo, "scripts/ig_helper.js", "var a;\n")  # .js 는 대상 아님
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_ts_and_tsx_are_checked(repo):
    _w(repo, "admin-web/src/app/instagram_panel/Panel.tsx")
    _git(repo, "add", "-A")
    assert _staged(repo) == 1


def test_file_inside_other_tools_home_passes(repo):
    _w(repo, "scripts/hanafax/kakao_notify.py")  # 키워드 kakao 가 우연히 들어간 hanafax 집 파일
    _git(repo, "add", "-A")
    assert _staged(repo) == 0


def test_check_all_fails_on_unbaselined_leak_and_reports_stale(repo, capsys):
    assert gate.main(["--check-all", "--root", str(repo)]) == 0
    _w(repo, "scripts/ig_second_leak.py")
    _git(repo, "add", "-A")
    assert gate.main(["--check-all", "--root", str(repo)]) == 1
    _git(repo, "rm", "-qf", "scripts/ig_second_leak.py")
    _git(repo, "rm", "-qf", "scripts/ig_legacy.py")
    capsys.readouterr()
    assert gate.main(["--check-all", "--root", str(repo)]) == 0
    assert "더 이상 집 밖이 아님" in capsys.readouterr().err


def test_update_baseline_only_shrinks(repo):
    _git(repo, "mv", "scripts/ig_legacy.py", "scripts/instagram/ig_legacy.py")
    assert gate.main(["--update-baseline", "--root", str(repo)]) == 0
    assert json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))["files"] == []
    _w(repo, "scripts/ig_added.py")
    _git(repo, "add", "-A")
    assert gate.main(["--update-baseline", "--root", str(repo)]) == 1  # 늘리기는 거부


def test_sync_baseline_requires_reason(repo, capsys):
    rc = gate.main(["--sync-baseline", "--root", str(repo)])
    assert rc == 2
    assert "--reason" in capsys.readouterr().err


def test_sync_baseline_rejects_file_not_in_verify_ref(repo, capsys):
    """A-1(CI #164) 재발 방지: 이번 브랜치가 새로 만든 leak 은 --sync-baseline 으로
    절대 기준선에 섞여 들어가면 안 된다(판정 완화 금지) — verify-in-ref 에 없으면 거부."""
    _w(repo, "scripts/ig_brandnew_leak.py")  # 커밋도 안 한 새 leak
    _git(repo, "add", "-A")
    rc = gate.main([
        "--sync-baseline", "--root", str(repo), "--reason", "테스트",
        "--verify-in-ref", "HEAD",  # HEAD 에는 없음(아직 커밋 전)
    ])
    assert rc == 1
    err = capsys.readouterr().err
    assert "scripts/ig_brandnew_leak.py" in err
    # 거부됐으니 기준선은 바뀌지 않아야 한다
    assert json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))["files"] == ["scripts/ig_legacy.py"]


def test_sync_baseline_grows_when_rule_change_adds_preexisting_leak(repo):
    """configs/tool_home.json 에 새 도구/규칙이 생겨 기존(커밋된) 파일이 새로 leak 이 되면,
    그 파일이 과거 커밋(HEAD)에도 있었다는 전제로 --sync-baseline 이 기준선을 늘려야 한다."""
    _w(repo, "scripts/kakao_existing.py")  # 아직 아무 도구에도 안 걸리는 평범한 파일
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add existing file before rule change")

    cfg = json.loads((repo / gate.CONFIG).read_text(encoding="utf-8"))
    cfg["tools"].append({"name": "kakao", "keyword": "kakao", "homes": ["scripts/kakao/"]})
    (repo / gate.CONFIG).write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add kakao tool rule — scripts/kakao_existing.py 가 새로 leak")

    rc = gate.main([
        "--sync-baseline", "--root", str(repo), "--reason", "kakao 규칙 추가로 재분류",
        "--verify-in-ref", "HEAD",
    ])
    assert rc == 0
    files = set(json.loads((repo / gate.BASELINE).read_text(encoding="utf-8"))["files"])
    assert "scripts/kakao_existing.py" in files
    assert "scripts/ig_legacy.py" in files  # 기존 기준선 유지


def test_real_repo_check_all_matches_committed_baseline():
    """실제 저장소: 지금 집 밖 파일은 모두 기준선 안(새 이탈 0) — CI 의 --check-all 과 같은 판정."""
    assert gate.main(["--check-all", "--root", str(REAL_ROOT)]) == 0


def test_shim_file_outside_home_is_not_a_leak(repo):
    """PR #165 tool_home 작업(2026-10-09): `# haehan-shim:` 호환 파일은 메커니즘상 늘 "도구
    키워드가 들어간 옛 경로"에 남아 집 밖처럼 보인다 — leak 으로 잡으면 안 된다."""
    _w(
        repo, "scripts/ig_shim.py",
        "# haehan-shim: tools.ig_shim\n# 호환 shim\nimport importlib as _il\n",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add ig shim outside home")

    leaks = gate.current_leaks(repo, gate.load_config(repo))

    assert "scripts/ig_shim.py" not in leaks


def test_non_shim_file_outside_home_is_still_a_leak(repo):
    """shim 예외가 전체 판정을 꺼버리는 게 아님을 증명하는 양성 대조."""
    _w(repo, "scripts/ig_not_a_shim.py", "import instagram_api\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add non-shim leak outside home")

    leaks = gate.current_leaks(repo, gate.load_config(repo))

    assert "scripts/ig_not_a_shim.py" in leaks


def test_staged_shim_file_outside_home_passes(repo):
    """--staged 경로(violations())도 shim 을 제외해야 한다."""
    _w(
        repo, "scripts/ig_shim2.py",
        "# haehan-shim: tools.ig_shim2\n# 호환 shim\nimport importlib as _il\n",
    )
    _git(repo, "add", "-A")

    assert _staged(repo) == 0
