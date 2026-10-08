"""자격증명/세션 경로 정책 검증."""
from __future__ import annotations

from pathlib import Path

from ai_orchestrator.sites import secrets_policy


def test_is_safe_site_name_accepts_reasonable_names():
    assert secrets_policy.is_safe_site_name("dummy")
    assert secrets_policy.is_safe_site_name("example_portal")
    assert secrets_policy.is_safe_site_name("g2b-main")


def test_is_safe_site_name_rejects_path_traversal_and_weird_chars():
    for bad in ["", "..", "../x", "x/y", "a\\b", "a b", ".hidden", "-leading", "has$dollar", "x" * 200]:
        assert not secrets_policy.is_safe_site_name(bad), bad


def test_credentials_and_session_paths_follow_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    cp = secrets_policy.credentials_path("alpha")
    sp = secrets_policy.session_state_path("alpha")
    assert cp == Path(tmp_path) / "sites" / "alpha.env"
    assert sp == Path(tmp_path) / "browser_state" / "alpha.json"


def test_present_flags_return_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    assert secrets_policy.credentials_present("nothing") is False
    assert secrets_policy.session_state_present("nothing") is False


def test_present_flags_true_when_files_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path))
    (tmp_path / "sites").mkdir(parents=True)
    (tmp_path / "browser_state").mkdir(parents=True)
    (tmp_path / "sites" / "site1.env").write_text("X=1", encoding="utf-8")
    (tmp_path / "browser_state" / "site1.json").write_text("{}", encoding="utf-8")
    assert secrets_policy.credentials_present("site1") is True
    assert secrets_policy.session_state_present("site1") is True


def test_invalid_site_name_raises_valueerror():
    try:
        secrets_policy.credentials_path("../escape")
    except ValueError:
        return
    raise AssertionError("ValueError expected for invalid site_name")


def test_gitignore_blocks_secrets_paths():
    # .gitignore 내용에 정책 경로가 명시되어 있어야 한다.
    root = Path(__file__).resolve().parents[2]
    content = (root / ".gitignore").read_text(encoding="utf-8")
    assert "secrets/" in content
    assert "browser_state" in content or "secrets/" in content
