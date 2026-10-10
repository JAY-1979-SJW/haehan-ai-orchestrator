from pathlib import Path

from scripts.naver import browser_gate as gate


def _cmd(profile: Path, port: int = gate.NAVER_CDP_PORT) -> str:
    return (
        f'"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
        f"--remote-debugging-port={port} "
        f'--user-data-dir="{profile}" '
        "https://www.naver.com/"
    )


def test_naver_browser_command_requires_cdp_port_not_fixed_profile(tmp_path):
    profile = tmp_path / "naver"

    assert gate.command_matches_naver_browser(_cmd(profile))
    assert gate.command_matches_naver_browser(
        f"chrome.exe --remote-debugging-port=9222 --user-data-dir={tmp_path / 'other'} https://www.naver.com/"
    )
    assert not gate.command_matches_naver_browser(_cmd(profile, port=9333))


def test_gate_passes_with_single_matching_browser(tmp_path):
    profile = tmp_path / "naver"

    report = gate.evaluate_conditions(
        [(101, _cmd(profile))],
        cdp_available=True,
        tab_urls=["https://www.naver.com/"],
    )

    assert report.ok is True
    assert report.code == gate.CODE_OK
    assert report.matched_pids == [101]


def test_gate_allows_alive_cdp_when_profile_is_unknown():
    report = gate.evaluate_conditions(
        [],
        cdp_available=True,
        tab_urls=["about:blank"],
    )

    assert report.ok is True
    assert report.code == gate.CODE_OK


def test_gate_blocks_multiple_matching_browsers(tmp_path):
    profile = tmp_path / "naver"

    report = gate.evaluate_conditions(
        [(101, _cmd(profile)), (102, _cmd(tmp_path / "other"))],
        cdp_available=True,
        tab_urls=["https://www.naver.com/"],
    )

    assert report.ok is False
    assert report.code == gate.CODE_MULTIPLE
    assert report.matched_pids == [101, 102]


def test_gate_blocks_single_direct_nid_login_entry(tmp_path):
    profile = tmp_path / "naver"

    report = gate.evaluate_conditions(
        [(101, _cmd(profile))],
        cdp_available=True,
        tab_urls=["https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fmail.naver.com%2F"],
    )

    assert report.ok is False
    assert report.code == gate.CODE_DIRECT_LOGIN


def test_launch_command_uses_naver_profile_and_main_url(tmp_path, monkeypatch):
    profile = tmp_path / "naver"
    monkeypatch.setattr(gate, "NAVER_DEFAULT_PROFILE_DIR", profile)

    command = gate.build_launch_command("C:/Chrome/chrome.exe")

    assert command[0] == "C:/Chrome/chrome.exe"
    assert f"--remote-debugging-port={gate.NAVER_CDP_PORT}" in command
    assert f"--user-data-dir={profile}" in command
    assert command[-1] == "https://www.naver.com/"


def test_ensure_blocks_launch_inside_sandbox(tmp_path, monkeypatch):
    profile = tmp_path / "naver"
    monkeypatch.setattr(gate, "NAVER_DEFAULT_PROFILE_DIR", profile)
    monkeypatch.setenv("CODEX_SANDBOX_NETWORK_DISABLED", "1")
    monkeypatch.setattr(gate, "list_chrome_processes", lambda: [])
    monkeypatch.setattr(gate, "is_cdp_available", lambda: False)
    monkeypatch.setattr(gate, "list_cdp_tab_urls", lambda: [])
    monkeypatch.setattr(
        gate,
        "launch_naver_browser",
        lambda: (_ for _ in ()).throw(AssertionError("must not launch in sandbox")),
    )

    report = gate.ensure_naver_browser()

    assert report.ok is False
    assert report.code == gate.CODE_SANDBOX_BLOCKED
