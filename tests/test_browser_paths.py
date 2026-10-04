"""scripts.browser_paths — Chrome/Edge/ffmpeg 위치 탐색 (결함 #17)."""

from __future__ import annotations

from scripts import browser_paths as bp


def test_first_existing_returns_first_candidate_that_exists(tmp_path):
    a = tmp_path / "a.exe"
    b = tmp_path / "b.exe"
    b.write_text("x")
    assert bp.first_existing([str(a), str(b)]) == str(b)


def test_first_existing_keeps_candidate_order(tmp_path):
    a = tmp_path / "a.exe"
    b = tmp_path / "b.exe"
    a.write_text("x")
    b.write_text("x")
    assert bp.first_existing([str(a), str(b)]) == str(a)


def test_first_existing_returns_none_when_nothing_exists(tmp_path):
    assert bp.first_existing([str(tmp_path / "nope.exe")]) is None


def test_first_existing_expands_environment_variables(tmp_path, monkeypatch):
    target = tmp_path / "Google" / "Chrome" / "Application"
    target.mkdir(parents=True)
    (target / "chrome.exe").write_text("x")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    found = bp.first_existing([r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"])
    assert found is not None and found.endswith("chrome.exe")


def test_candidate_order_matches_previous_implementation():
    # 기존 3곳(cdp_daemon·cdp_force_start·start_chrome_with_cdp)의 순서를 유지해야 같은 브라우저가 선택된다
    assert bp.CHROME_CANDIDATES[0].startswith(r"C:\Program Files\Google")
    assert bp.CHROME_CANDIDATES[1].startswith(r"C:\Program Files (x86)\Google")
    assert bp.CHROME_CANDIDATES[2].startswith("%LOCALAPPDATA%")
    assert bp.EDGE_CANDIDATES[0].startswith(r"C:\Program Files (x86)\Microsoft")
    assert bp.EDGE_CANDIDATES[1].startswith(r"C:\Program Files\Microsoft")
    assert bp.EDGE_CANDIDATES[2].startswith("%LOCALAPPDATA%")


def test_candidates_do_not_hardcode_a_user_name():
    for candidate in (*bp.CHROME_CANDIDATES, *bp.EDGE_CANDIDATES):
        assert "\\Users\\" not in candidate


def test_find_ffmpeg_prefers_env_then_path(tmp_path, monkeypatch):
    env_exe = tmp_path / "env_ffmpeg.exe"
    env_exe.write_text("x")
    path_exe = tmp_path / "path_ffmpeg.exe"
    path_exe.write_text("x")
    monkeypatch.setenv("FFMPEG_PATH", str(env_exe))
    monkeypatch.setattr(bp.shutil, "which", lambda name: str(path_exe))
    assert bp.find_ffmpeg() == str(env_exe)
    monkeypatch.delenv("FFMPEG_PATH")
    assert bp.find_ffmpeg() == str(path_exe)


def test_find_ffmpeg_ignores_env_path_that_does_not_exist(tmp_path, monkeypatch):
    path_exe = tmp_path / "path_ffmpeg.exe"
    path_exe.write_text("x")
    monkeypatch.setenv("FFMPEG_PATH", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(bp.shutil, "which", lambda name: str(path_exe))
    assert bp.find_ffmpeg() == str(path_exe)


def test_find_ffmpeg_falls_back_to_newest_winget_package(tmp_path, monkeypatch):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(bp.shutil, "which", lambda name: None)
    base = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Test"
    for version in ("ffmpeg-7.0-full_build", "ffmpeg-8.1-full_build"):
        exe = base / version / "bin" / "ffmpeg.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    found = bp.find_ffmpeg()
    assert found is not None and "ffmpeg-8.1" in found


def test_find_ffmpeg_returns_none_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(bp.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert bp.find_ffmpeg() is None
