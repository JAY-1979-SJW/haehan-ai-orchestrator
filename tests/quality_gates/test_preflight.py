"""설치 점검(tools/verify/preflight.py) — 가짜 환경으로 PASS/WARN/FAIL 판정을 확인한다. 실제 Chrome·네트워크·설치 상태에 기대지 않는다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.verify import preflight as pf

GOOD_PACKAGES = {name: "1.0.0" for name in pf.REQUIRED_PACKAGES}
REAL_ENV = pf.Env  # 시험에서 pf.Env 를 바꿔도 도우미가 진짜 클래스를 쓰도록 미리 잡아 둔다


def make_env(tmp_path: Path, **over) -> pf.Env:
    """모든 검사가 통과하는 가짜 환경. 필요한 부분만 바꿔 넣는다."""
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "ai_orchestrator" / "storage").mkdir(parents=True, exist_ok=True)
    (tmp_path / "admin-web" / "node_modules").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"command": 'py -3 -c "pass"'}]}]}}), encoding="utf-8")
    base: dict[str, Any] = {
        "root": tmp_path,
        "python_version": (3, 14, 0),
        "environ": {},
        "package_version": lambda name: GOOD_PACKAGES.get(name),
        "which": lambda _name: "/bin/x",
        "run": lambda cmd: (0, "154.0.1.2" if cmd and "powershell" in cmd[0].lower() else ("/repo/.githooks" if "core.hooksPath" in cmd else "ok")),
        "http_get": lambda _url: (200, "{}"),
        "port_in_use": lambda _h, _p: False,
        "find_chrome": lambda: "chrome-bin/chrome.exe",
    }
    base.update(over)
    return REAL_ENV(**base)


def by_name(results, name):
    return next(r for r in results if r.name == name)


def test_all_good_environment_has_no_fail(tmp_path):
    (tmp_path / ".env").write_text("A=1\n# c\nB=2\n", encoding="utf-8")
    results = pf.run_checks(make_env(tmp_path))
    assert results  # 원본이 비어 있지 않다(비어 있으면 아래 '실패 없음' 비교가 항상 통과해 버린다)
    assert len(results) == len(pf.CHECKS)  # 모든 점검이 돌았다
    assert [r.name for r in results if r.status == pf.FAIL] == []
    assert by_name(results, ".env").detail.startswith("키 2개")  # 이름만 센다


def test_env_values_are_never_printed(tmp_path):
    (tmp_path / ".env").write_text("SECRET_TOKEN=super-secret-value-123\n", encoding="utf-8")
    text = pf.render(pf.run_checks(make_env(tmp_path)))
    assert "super-secret-value-123" not in text and "SECRET_TOKEN" not in text


@pytest.mark.parametrize(("version", "status"), [((3, 10, 9), pf.FAIL), ((3, 11, 0), pf.PASS), ((3, 14, 7), pf.PASS)])
def test_python_version_boundary(tmp_path, version, status):
    assert pf.check_python(make_env(tmp_path, python_version=version)).status == status


def test_missing_package_is_fail_with_fix_hint(tmp_path):
    env = make_env(tmp_path, package_version=lambda n: None if n == "playwright" else "1.0")
    got = pf.check_packages(env)
    assert got.status == pf.FAIL and "playwright" in got.detail and "constraints.txt" in got.detail


def test_constraints_drift_and_absence(tmp_path):
    env = make_env(tmp_path, package_version=lambda n: "2.0.0" if n == "fastapi" else "1.0.0")
    assert pf.check_constraints(env).status == pf.WARN  # 파일 없음
    (tmp_path / "constraints.txt").write_text("fastapi==1.5.0\nuvicorn[standard]==1.0.0\n# 주석\n", encoding="utf-8")
    drift = pf.check_constraints(env)
    assert drift.status == pf.WARN and "fastapi 2.0.0≠1.5.0" in drift.detail and "uvicorn" not in drift.detail
    same = make_env(tmp_path, package_version=lambda n: {"fastapi": "1.5.0"}.get(n, "1.0.0"))
    assert pf.check_constraints(same).status == pf.PASS


def test_chrome_missing_and_unreadable_version(tmp_path):
    assert pf.check_chrome(make_env(tmp_path, find_chrome=lambda: None)).status == pf.FAIL
    assert pf.check_chrome(make_env(tmp_path, run=lambda _c: (1, ""))).status == pf.WARN
    ok = pf.check_chrome(make_env(tmp_path))
    assert ok.status == pf.PASS


def test_cdp_profile_rejects_default_chrome_profile(tmp_path):
    local = tmp_path / "Local"
    default = local / "Google" / "Chrome" / "User Data"
    default.mkdir(parents=True)
    env = make_env(tmp_path, environ={"LOCALAPPDATA": str(local), "HAEHAN_CDP_PROFILE": str(default)})
    got = pf.check_cdp_profile(env)
    assert got.status == pf.FAIL and "조용히 무시" in got.detail
    inside = make_env(tmp_path, environ={"LOCALAPPDATA": str(local), "HAEHAN_CDP_PROFILE": str(default / "Profile 1")})
    assert pf.check_cdp_profile(inside).status == pf.FAIL  # 기본 폴더 안쪽도 같다
    custom = make_env(tmp_path, environ={"LOCALAPPDATA": str(local), "HAEHAN_CDP_PROFILE": str(tmp_path / "my_profile")})
    assert pf.check_cdp_profile(custom).status == pf.PASS
    assert pf.check_cdp_profile(make_env(tmp_path)).status == pf.PASS  # 기본값 data/cdp_profile/ai_chrome


def test_cdp_port_states(tmp_path):
    assert pf.check_cdp_port(make_env(tmp_path)).status == pf.PASS
    down = make_env(tmp_path, http_get=lambda _u: None)
    assert pf.check_cdp_port(down).status == pf.WARN  # 꺼져 있을 뿐(읽기 전용 점검이라 켜지 않음)
    taken = make_env(tmp_path, http_get=lambda _u: None, port_in_use=lambda _h, _p: True)
    got = pf.check_cdp_port(taken)
    assert got.status == pf.FAIL and "다른 프로그램" in got.detail  # 다른 프로그램이 포트를 점유


def test_hook_interpreter_flags_pinned_minor_version(tmp_path):
    env = make_env(tmp_path)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": 'py -3.14 -c "pass"'}]}]}}), encoding="utf-8")
    got = pf.check_hook_interpreter(env)
    assert got.status == pf.FAIL and "py -3 을 쓰세요" in got.detail


def test_hook_interpreter_requires_launcher_and_handles_bad_json(tmp_path):
    env = make_env(tmp_path, run=lambda cmd: (127, "") if cmd[:2] == ["py", "-3"] else (0, ""))
    assert pf.check_hook_interpreter(env).status == pf.FAIL
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text("{깨짐", encoding="utf-8")
    assert pf.check_hook_interpreter(env).status == pf.FAIL
    settings.unlink()
    assert pf.check_hook_interpreter(env).status == pf.WARN


def test_node_git_hooks_and_env_warnings(tmp_path):
    assert pf.check_node(make_env(tmp_path, which=lambda _n: None)).status == pf.WARN
    env = make_env(tmp_path)
    (tmp_path / "admin-web" / "node_modules").rmdir()
    assert pf.check_node(env).status == pf.WARN
    assert pf.check_git_hooks(make_env(tmp_path, run=lambda _c: (1, ""))).status == pf.WARN
    assert pf.check_env_file(make_env(tmp_path)).status == pf.WARN  # .env 없음


def test_one_crashing_check_does_not_stop_the_rest(tmp_path, monkeypatch):
    def boom(_env):
        raise RuntimeError("점검 자체 오류")

    boom.__name__ = "check_boom"
    monkeypatch.setattr(pf, "CHECKS", (pf.check_python, boom, pf.check_packages))
    results = pf.run_checks(make_env(tmp_path))
    assert [r.status for r in results] == [pf.PASS, pf.FAIL, pf.PASS]
    assert "점검 자체 오류" in results[1].detail


def test_exit_code_and_json_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pf, "Env", lambda: make_env(tmp_path, python_version=(3, 9, 0)))
    assert pf.main(["--json"]) == 1  # FAIL 이 있으면 1
    data = json.loads(capsys.readouterr().out)
    assert any(item["status"] == "FAIL" for item in data)
    monkeypatch.setattr(pf, "Env", lambda: make_env(tmp_path))
    assert pf.main([]) == 0
    assert "결과: PASS" in capsys.readouterr().out


def test_ruff_check_warns_when_commit_hook_interpreter_lacks_ruff(tmp_path):
    missing = make_env(tmp_path, run=lambda cmd: (1, "No module named ruff") if "ruff" in cmd else (0, ""))
    got = pf.check_ruff(missing)
    assert got.status == pf.WARN and "조용히 생략" in got.detail and "pip install ruff" in got.detail
    present = make_env(tmp_path, run=lambda cmd: (0, "ruff 0.16.10") if "ruff" in cmd else (0, ""))
    assert pf.check_ruff(present).status == pf.PASS
    no_launcher = make_env(tmp_path, which=lambda _n: None, run=lambda cmd: (0, "ruff 0.16.10") if cmd[0] != "py" else (127, ""))
    assert pf.check_ruff(no_launcher).status == pf.PASS  # py 런처가 없으면 현재 파이썬으로 확인


def test_claude_cli_check_warns_when_push_review_would_be_skipped(tmp_path):
    missing = pf.check_claude_cli(make_env(tmp_path, which=lambda name: None if name == "claude" else "/bin/x"))
    assert missing.status == pf.WARN and "검수 없이 건너뛰어집니다" in missing.detail
    assert pf.check_claude_cli(make_env(tmp_path, which=lambda _name: "/bin/claude")).status == pf.PASS
