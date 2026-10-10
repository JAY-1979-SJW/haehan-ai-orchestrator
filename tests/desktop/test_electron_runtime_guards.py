"""Electron 런타임 가드 시험 — D5(자기 PID 정리)·D6(config.json 보호)·버전 주입(build-info.json).

electron 모듈을 가짜로 바꿔 node 로 직접 실행한다(`tests/electron_guard_harness.js`). node 가 없으면 건너뛴다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).parent.parent / "electron_guard_harness.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node 가 없다")


def run_case(case: str, tmp_path: Path) -> dict:
    user_data = tmp_path / "userData"
    user_data.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [str(NODE), str(HARNESS), case, str(user_data), str(REPO)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── D6: config.json ──────────────────────────────────────────────────────


def test_missing_config_creates_persistent_secret_atomically(tmp_path):
    r = run_case("config-missing", tmp_path)
    assert r == {"same": True, "len": 64, "saved": True, "tmp": False}


def test_adding_secret_keeps_other_settings(tmp_path):
    r = run_case("config-keeps-other-settings", tmp_path)
    assert r == {"jwt": True, "license": "LIC-1", "owner": True, "sites": ["a"]}


def test_corrupt_config_is_preserved_and_core_values_salvaged(tmp_path):
    r = run_case("config-corrupt", tmp_path)
    assert r["keptSecret"] is True  # 비밀이 유지돼 로그인이 안 풀린다
    assert r["salvaged"] == ["tok-1", "LIC-9", True]  # 로그인 토큰·라이선스·소유자 모드
    assert r["preserved"] == 1 and r["preservedHasOriginal"] is True  # 깨진 원본을 .corrupt-<시각> 으로 보존
    assert r["warnings"] >= 1  # 오류로 알림


def test_corrupt_config_without_secret_gets_new_secret_and_keeps_original(tmp_path):
    r = run_case("config-corrupt-no-secret", tmp_path)
    assert r["newSecret"] and r["saved"] and r["preserved"] == 1 and r["warnings"] >= 1


def test_unreadable_config_is_never_overwritten(tmp_path):
    r = run_case("config-unreadable", tmp_path)
    assert r["threw"] and r["threwPatch"]  # 저장 거부
    assert r["unchanged"] is True  # 파일은 그대로
    assert r["ephemeralStable"] and r["ephemeralNotSaved"]  # 이번 실행에만 쓰는 임시 비밀(저장 안 함)
    assert r["warnings"] is True


# ── D5: 자기 PID 정리 ────────────────────────────────────────────────────


def test_previous_own_server_is_killed_via_pid_file(tmp_path):
    r = run_case("pid-kills-own-leftover", tmp_path)
    assert r["killed"] is True and r["alive"] is False and r["pidFileGone"] is True


def test_process_with_other_image_is_not_killed(tmp_path):
    """PID 가 재사용돼 다른 프로그램이 된 경우(이름 불일치) — 건드리지 않고 PID 파일만 정리."""
    r = run_case("pid-image-mismatch-not-killed", tmp_path)
    assert r["killed"] is False and r["reason"] == "not-our-process" and r["alive"] is True and r["pidFileGone"] is True


def test_same_executable_but_different_command_line_is_not_killed(tmp_path):
    """Next 서버는 Electron 실행 파일로 fork 되므로 이름만 같은 다른 프로세스를 명령줄로 구분한다."""
    r = run_case("pid-cmdline-mismatch-not-killed", tmp_path)
    assert r["killed"] is False and r["alive"] is True


def test_never_kills_self_or_dead_pid_or_missing_file(tmp_path):
    r = run_case("pid-never-kills-self-or-dead", tmp_path)
    assert r["self"] == "invalid-pid"
    assert r["dead"] == "not-our-process"
    assert r["none"] == "no-pid-file"


# ── 버전 주입 ────────────────────────────────────────────────────────────


def test_build_info_is_read_validated_and_never_fatal(tmp_path):
    r = run_case("build-info", tmp_path)
    assert r["none"] == {}  # 파일 없음 → 비어 있음(시작을 막지 않는다)
    assert r["ok"] == {"git_sha": "a" * 40, "build_time": "2026-10-07T12:34:56Z", "version": "20261007-aaaaaaa"}
    assert r["bad"] == {}  # 형식 위반 값은 버린다(서버도 한 번 더 검증)
    assert r["broken"] == {}  # JSON 이 깨져도 예외 없음


# ── B안: 시작할 때마다 자동 세션 토큰 갱신 ────────────────────────────────


def test_desktop_session_refresh_stores_new_token_with_desktop_header(tmp_path):
    r = run_case("desktop-session-200", tmp_path)
    assert r["result"] == "refreshed" and r["token"] == "NEW-TOKEN"
    assert r["seen"] == {"method": "POST", "path": "/api/v1/auth/desktop-session", "header": "1"}


def test_desktop_session_needs_setup_clears_stale_token(tmp_path):
    r = run_case("desktop-session-needs-setup", tmp_path)
    assert r["result"] == "needs_setup" and r["token"] == ""


@pytest.mark.parametrize("mode", ["404", "no-owner", "down"])
def test_desktop_session_keeps_existing_token_when_unavailable(tmp_path, mode):
    """서버 모드(404)·활성 owner 없음·서버 접속 실패 — 시작을 막지 않고 기존 토큰을 그대로 둔다."""
    r = run_case(f"desktop-session-{mode}", tmp_path)
    assert r["result"] == "kept" and r["token"] == "OLD-TOKEN"
