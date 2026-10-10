"""scripts.common.app_paths — 윈도우 표준 저장소 경로 해석기 (결함 #17)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.common import app_paths as ap


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (ap.ENV_DATA_ROOT, ap.ENV_CONFIG_ROOT):
        monkeypatch.delenv(name, raising=False)


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv(ap.ENV_DATA_ROOT, str(tmp_path / "custom"))
    assert ap.data_root() == tmp_path / "custom"


def test_windows_default_is_localappdata_suite_product(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert ap.data_root() == tmp_path / "HaehanAI" / "Orchestrator"


def test_never_writes_directly_under_suite_folder(monkeypatch, tmp_path):
    # HaehanAI 는 CADQuantity·runtime·inventory 가 있는 제품군 공용 폴더 — 그 바로 아래에는 쓰지 않는다
    monkeypatch.setattr(ap, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert ap.data_root().parent == tmp_path / "HaehanAI"
    assert ap.data_root().name == "Orchestrator"


def test_config_root_is_roaming_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_is_windows", lambda: True)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roam"))
    assert ap.config_root() == tmp_path / "roam" / "HaehanAI" / "Orchestrator"


def test_config_root_follows_data_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ap.ENV_DATA_ROOT, str(tmp_path / "iso"))
    assert ap.config_root() == tmp_path / "iso" / "config"


def test_install_root_is_per_user_programs(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_is_windows", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert ap.install_root() == tmp_path / "Programs" / "HaehanAI Orchestrator"


def test_missing_localappdata_raises_instead_of_writing_elsewhere(monkeypatch):
    monkeypatch.setattr(ap, "_is_windows", lambda: True)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(ap.AppPathsError):
        ap.data_root()


def test_no_repository_relative_fallback(monkeypatch, tmp_path):
    # 저장소(소스 폴더) 아래로 폴백하면 안 된다
    monkeypatch.setattr(ap, "_is_windows", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    repo = Path(__file__).resolve().parents[2]
    assert repo not in ap.data_root().parents and ap.data_root() != repo


def test_non_windows_fallback_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_is_windows", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert ap.data_root() == tmp_path / "xdg" / "haehanai" / "orchestrator"


def test_ensure_layout_creates_standard_subdirs(monkeypatch, tmp_path):
    monkeypatch.setenv(ap.ENV_DATA_ROOT, str(tmp_path / "root"))
    root = ap.ensure_layout()
    for name in ("data", "db", "logs", "cache", "sessions", "browser_profile", "secrets", "migration"):
        assert (root / name).is_dir()


def test_path_builders_use_standard_subfolders(monkeypatch, tmp_path):
    monkeypatch.setenv(ap.ENV_DATA_ROOT, str(tmp_path / "r"))
    root = tmp_path / "r"
    assert ap.db_path("x.db") == root / "db" / "x.db"
    assert ap.app_dir("cafe") == root / "data" / "cafe"
    assert ap.app_dir("cafe", "img") == root / "data" / "cafe" / "img"
    assert ap.logs_dir() == root / "logs"
    assert ap.browser_profile_dir() == root / "browser_profile" / "ai_chrome"
    assert ap.secrets_dir() == root / "secrets"


def test_create_false_does_not_touch_disk(monkeypatch, tmp_path):
    monkeypatch.setenv(ap.ENV_DATA_ROOT, str(tmp_path / "none"))
    ap.logs_dir(create=False)
    ap.db_path("a.db", create_parent=False)
    assert not (tmp_path / "none").exists()


def test_known_folder_rejects_unknown_name():
    with pytest.raises(ValueError):
        ap.known_folder("temp")


def test_known_folder_fallback_to_home(monkeypatch):
    monkeypatch.setattr(ap, "_is_windows", lambda: False)
    assert ap.known_folder("downloads") == Path.home() / "Downloads"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Known Folder API")
def test_known_folder_on_windows_returns_existing_directory():
    # 하드코딩(C:\Users\<이름>\Documents)이 아니라 API 가 OneDrive 리디렉션까지 반영한 실제 위치를 돌려준다
    for name in ("downloads", "documents", "desktop"):
        folder = ap.known_folder(name)
        assert folder.is_absolute()
