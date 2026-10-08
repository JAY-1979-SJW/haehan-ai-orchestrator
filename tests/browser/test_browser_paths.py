"""scripts.browser.session.browser_paths — Chrome/Edge/ffmpeg 위치 탐색 (결함 #17)."""

from __future__ import annotations

from scripts.browser.session import browser_paths as bp


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
    assert bp.CHROME_CANDIDATES[0].startswith(r"%ProgramFiles%\Google")
    assert bp.CHROME_CANDIDATES[1].startswith(r"%ProgramFiles(x86)%\Google")
    assert bp.CHROME_CANDIDATES[2].startswith("%LOCALAPPDATA%")
    assert bp.EDGE_CANDIDATES[0].startswith(r"%ProgramFiles(x86)%\Microsoft")
    assert bp.EDGE_CANDIDATES[1].startswith(r"%ProgramFiles%\Microsoft")
    assert bp.EDGE_CANDIDATES[2].startswith("%LOCALAPPDATA%")


def test_candidates_expand_to_absolute_paths_on_this_pc():
    # STD-02(절대경로 하드코딩) 해소 — 환경변수 기반으로 바꿔도 각 후보가 실제 절대경로로
    # 펼쳐지는지(변수가 안 남고, Program Files 계열 아래 exe로 끝나는지) 확인한다.
    # 기대값 자체를 하드코딩하지 않는다 — 비교 대상도 같은 환경변수로 조립해 STD-02를 다시 어기지 않는다.
    import os

    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    assert program_files and program_files_x86, "이 시험은 Windows 전용(ProgramFiles 환경변수 필요)"

    for candidate, root in zip(bp.CHROME_CANDIDATES[:2], (program_files, program_files_x86), strict=True):
        expanded = os.path.expandvars(candidate)
        assert "%" not in expanded
        assert expanded == root + r"\Google\Chrome\Application\chrome.exe"
    for candidate, root in zip(bp.EDGE_CANDIDATES[:2], (program_files_x86, program_files), strict=True):
        expanded = os.path.expandvars(candidate)
        assert "%" not in expanded
        assert expanded == root + r"\Microsoft\Edge\Application\msedge.exe"


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


def test_find_chrome_prefers_env_override_for_nonstandard_install(tmp_path, monkeypatch):
    custom = tmp_path / "portable" / "chrome.exe"
    custom.parent.mkdir()
    custom.write_text("x")
    monkeypatch.setenv("HAEHAN_CHROME_PATH", str(custom))
    assert bp.find_chrome() == str(custom)  # 표준 위치에 설치돼 있어도 지정한 경로가 우선


def test_find_chrome_ignores_env_override_that_does_not_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("HAEHAN_CHROME_PATH", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(bp, "first_existing", lambda _c: "STANDARD")
    assert bp.find_chrome() == "STANDARD"  # 잘못 지정했으면 조용히 기본 탐색으로 돌아간다(없는 경로로 실행하지 않음)


def test_naver_browser_gate_honors_chrome_path_env_and_reports_missing(tmp_path, monkeypatch):
    """browser_gate 는 L2 로 분류돼 browser_paths(L4)를 import 할 수 없어 자체 목록을 둔다 — 환경변수 인식은 같아야 한다."""
    from scripts.naver import browser_gate

    custom = tmp_path / "portable" / "chrome.exe"
    custom.parent.mkdir()
    custom.write_text("x")
    monkeypatch.setenv("HAEHAN_CHROME_PATH", str(custom))
    assert browser_gate._find_chrome_exe() == str(custom)
    monkeypatch.delenv("HAEHAN_CHROME_PATH")
    monkeypatch.setattr(browser_gate.Path, "exists", lambda _self: False)
    try:
        browser_gate._find_chrome_exe()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Chrome 이 없으면 FileNotFoundError 여야 한다")
