# -*- coding: utf-8 -*-
"""CAD-DESKTOP-HUB-CAD-BRIDGE-LIFECYCLE-01 — CadBridgeRunner + lifecycle routes.

FakePopen 기반 — 실제 subprocess spawn 없이 검증. AI agent command
실행 / AutoCAD COM / DB write 일체 없음.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop import cad_bridge_registry as reg
from desktop import cad_bridge_runner as runner_mod
from desktop import local_server as local_server_mod
from desktop.cad_bridge_runner import CadBridgeRunner
from desktop.local_server import app

RUNNER_FILE = ROOT / "desktop" / "cad_bridge_runner.py"
LOCAL_SERVER_FILE = ROOT / "desktop" / "local_server.py"


# ──────────────────────────────────────────────
# FakePopen — 실제 process spawn 없이 검증
# ──────────────────────────────────────────────

class FakePopen:
    """subprocess.Popen 흉내 — poll 결과 시퀀스 제어 가능."""

    def __init__(
        self,
        cmd, cwd=None, stdout=None, stderr=None, stdin=None,
        *,
        poll_sequence: Optional[List] = None,
        pid: int = 123456,
    ):
        self.cmd = cmd
        self.cwd = cwd
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.pid = pid
        self._poll_seq = list(poll_sequence or [None, None, None])
        self._idx = 0
        self.terminated = False
        self.killed = False
        self._returncode_override = None

    def poll(self):
        if self._returncode_override is not None:
            return self._returncode_override
        if self._idx < len(self._poll_seq):
            v = self._poll_seq[self._idx]
            self._idx += 1
            return v
        return self._poll_seq[-1] if self._poll_seq else None

    def terminate(self):
        self.terminated = True
        # terminate 후 즉시 종료된 것처럼 표현
        self._returncode_override = 0

    def kill(self):
        self.killed = True
        self._returncode_override = -9

    def wait(self, timeout=None):
        return self._returncode_override or 0


@pytest.fixture
def fake_popen_factory(monkeypatch):
    """FakePopen 인스턴스를 capture 하는 factory. monkeypatch subprocess.Popen.

    poll_sequence 기본값은 None, None, None (계속 살아있는 상태).
    poll_sequence_override 인자로 변경 가능.
    """
    created: List[FakePopen] = []
    config = {"poll_sequence": [None, None, None], "raises": None}

    def factory(cmd, cwd=None, stdout=None, stderr=None, stdin=None):
        if config["raises"]:
            raise config["raises"]
        p = FakePopen(
            cmd, cwd=cwd, stdout=stdout, stderr=stderr, stdin=stdin,
            poll_sequence=list(config["poll_sequence"]),
        )
        created.append(p)
        return p

    monkeypatch.setattr(runner_mod.subprocess, "Popen", factory)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda _t: None)  # 즉시 진행
    return {"created": created, "config": config}


def _ok_config(tmp_path: Path) -> reg.CadBridgeConfig:
    """존재하는 cad_repo_path 를 흉내내는 임시 디렉토리 설정."""
    (tmp_path / "local_bridge").mkdir(parents=True, exist_ok=True)
    (tmp_path / "local_bridge" / "server.py").write_text("# fake", "utf-8")
    return reg.CadBridgeConfig(
        host="127.0.0.1", port=8766, cad_repo_path=str(tmp_path),
    )


# ──────────────────────────────────────────────
# 1. build_command — uvicorn 명령 구성
# ──────────────────────────────────────────────

def test_build_command_uses_uvicorn_local_bridge():
    r = CadBridgeRunner(config=reg.CadBridgeConfig(port=8766))
    cmd = r.build_command()
    assert "-m" in cmd
    assert "uvicorn" in cmd
    assert "local_bridge.server:app" in cmd
    assert "--host" in cmd
    assert "127.0.0.1" in cmd
    assert "--port" in cmd
    assert "8766" in cmd


def test_build_command_respects_config_port_override():
    r = CadBridgeRunner(config=reg.CadBridgeConfig(port=8767))
    cmd = r.build_command()
    assert "8767" in cmd
    assert "8765" not in cmd
    assert "8001" not in cmd


# ──────────────────────────────────────────────
# 2. cwd 필수 / cad_repo_path 검증
# ──────────────────────────────────────────────

def test_start_fails_when_cad_repo_path_missing(fake_popen_factory):
    r = CadBridgeRunner(config=reg.CadBridgeConfig(cad_repo_path=None))
    assert r.start() is False
    assert r.get_status() == runner_mod.STATE_ERROR
    assert "cad_repo_path required" in (r.get_last_error() or "")
    assert fake_popen_factory["created"] == []  # Popen 호출 0건


def test_start_fails_when_cad_repo_path_does_not_exist(fake_popen_factory):
    r = CadBridgeRunner(config=reg.CadBridgeConfig(
        cad_repo_path="C:/this/path/does/not/exist/xyz",
    ))
    assert r.start() is False
    assert "does not exist" in (r.get_last_error() or "")
    assert fake_popen_factory["created"] == []


def test_start_fails_when_path_is_not_cad_repo(tmp_path, fake_popen_factory):
    # local_bridge/server.py 없는 디렉토리
    r = CadBridgeRunner(config=reg.CadBridgeConfig(cad_repo_path=str(tmp_path)))
    assert r.start() is False
    assert "does not look like CAD repo" in (r.get_last_error() or "")
    assert fake_popen_factory["created"] == []


def test_start_blocks_forbidden_port(fake_popen_factory, tmp_path):
    config = _ok_config(tmp_path)
    bad = reg.CadBridgeConfig(
        host=config.host, port=8001, cad_repo_path=config.cad_repo_path,
    )
    r = CadBridgeRunner(config=bad)
    assert r.start() is False
    assert "forbidden port" in (r.get_last_error() or "")
    assert fake_popen_factory["created"] == []


def test_start_blocks_desktop_hub_port_collision(fake_popen_factory, tmp_path):
    config = _ok_config(tmp_path)
    bad = reg.CadBridgeConfig(
        host=config.host, port=reg.DESKTOP_HUB_PORT,
        cad_repo_path=config.cad_repo_path,
    )
    r = CadBridgeRunner(config=bad)
    assert r.start() is False
    assert "desktop hub port" in (r.get_last_error() or "")
    assert fake_popen_factory["created"] == []


# ──────────────────────────────────────────────
# 3. start / stop / restart / is_running / get_pid
# ──────────────────────────────────────────────

def test_start_spawns_with_correct_cwd_and_command(
    fake_popen_factory, tmp_path,
):
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is True
    assert r.get_status() == runner_mod.STATE_RUNNING
    assert r.is_running() is True
    assert r.get_pid() == 123456
    created = fake_popen_factory["created"]
    assert len(created) == 1
    assert created[0].cwd == str(tmp_path)
    assert "local_bridge.server:app" in created[0].cmd


def test_start_fails_when_process_dies_immediately(
    fake_popen_factory, tmp_path,
):
    fake_popen_factory["config"]["poll_sequence"] = [1, 1, 1]  # 즉사 (rc=1)
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is False
    assert r.get_status() == runner_mod.STATE_ERROR
    assert "exited immediately" in (r.get_last_error() or "")


def test_start_fails_when_popen_raises(fake_popen_factory, tmp_path):
    fake_popen_factory["config"]["raises"] = OSError("boom")
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is False
    assert "spawn failed" in (r.get_last_error() or "")


def test_stop_terminates_only_runner_owned_process(
    fake_popen_factory, tmp_path,
):
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is True
    fake_proc = fake_popen_factory["created"][0]
    assert r.stop() is True
    assert fake_proc.terminated is True
    # kill 은 terminate 가 즉시 응답하므로 호출 안 됨
    assert fake_proc.killed is False
    assert r.get_status() == runner_mod.STATE_STOPPED
    assert r.get_pid() is None


def test_stop_falls_back_to_kill_on_timeout(monkeypatch, tmp_path):
    """terminate 후 wait 가 timeout → kill 진행."""
    created: List[FakePopen] = []

    class StubbornPopen(FakePopen):
        def terminate(self):
            self.terminated = True
            # rc 미설정 — terminate 후에도 alive
        def wait(self, timeout=None):
            if not self.killed and not self._returncode_override:
                raise subprocess.TimeoutExpired(cmd=self.cmd, timeout=timeout or 0)
            return 0

    def factory(cmd, cwd=None, stdout=None, stderr=None, stdin=None):
        p = StubbornPopen(cmd, cwd=cwd, stdout=stdout, stderr=stderr,
                          stdin=stdin)
        created.append(p)
        return p

    monkeypatch.setattr(runner_mod.subprocess, "Popen", factory)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda _t: None)

    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is True
    assert r.stop() is True
    assert created[0].terminated is True
    assert created[0].killed is True  # fallback 발동


def test_restart_calls_stop_then_start(fake_popen_factory, tmp_path):
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is True
    assert r.restart() is True
    # restart 후 새 Popen 호출 발생 (총 2개 생성)
    assert len(fake_popen_factory["created"]) == 2


def test_start_idempotent_when_already_running(fake_popen_factory, tmp_path):
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    assert r.start() is True
    assert r.start() is True  # 두 번째 호출은 noop + True
    # Popen 은 1번만 호출
    assert len(fake_popen_factory["created"]) == 1


def test_get_last_error_cleared_on_successful_start(
    fake_popen_factory, tmp_path,
):
    r = CadBridgeRunner(config=reg.CadBridgeConfig(cad_repo_path=None))
    r.start()  # fail
    assert r.get_last_error() is not None
    r.set_config(_ok_config(tmp_path))
    assert r.start() is True
    assert r.get_last_error() is None


# ──────────────────────────────────────────────
# 4. snapshot
# ──────────────────────────────────────────────

def test_snapshot_returns_full_state(fake_popen_factory, tmp_path):
    r = CadBridgeRunner(config=_ok_config(tmp_path))
    r.start()
    s = r.snapshot()
    assert s["state"] == runner_mod.STATE_RUNNING
    assert s["pid"] == 123456
    assert s["port"] == 8766
    assert s["host"] == "127.0.0.1"
    assert s["cadRepoPath"] == str(tmp_path)


# ──────────────────────────────────────────────
# 5. 안전 정책 — 외부 PID 사용 0건 / 8765·8001 사용 0건
# ──────────────────────────────────────────────

def test_runner_does_not_call_os_kill_or_taskkill():
    src = RUNNER_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "os.kill(", "taskkill /F", "taskkill -F", "Stop-Process",
    ):
        assert forbidden not in src


def test_runner_does_not_accept_external_pid_argument():
    """build_command / start / stop 모두 외부 PID 인자 없음."""
    src = RUNNER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "start", "stop", "restart", "build_command",
        ):
            for arg in node.args.args:
                assert arg.arg not in ("pid", "process_id", "target_pid")


def test_runner_does_not_import_cad_repo_modules():
    src = RUNNER_FILE.read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = ("local_bridge", "app.backend", "app.frontend", "mcp_server")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fp in forbidden:
                assert not node.module.startswith(fp), (
                    f"forbidden import: {node.module}"
                )
        elif isinstance(node, ast.Import):
            for a in node.names:
                for fp in forbidden:
                    assert not a.name.startswith(fp)


def test_runner_does_not_import_autocad_or_com():
    src = RUNNER_FILE.read_text(encoding="utf-8")
    for forbidden in (
        "win32com", "pythoncom", "AutoCAD.Application",
        "GetActiveObject", "from sqlalchemy", "import sqlalchemy",
    ):
        assert forbidden not in src


def test_runner_does_not_use_8001_or_8765():
    src = RUNNER_FILE.read_text(encoding="utf-8")
    forbidden_live = (
        "= 8001", ":8001", "port=8001",
    )
    for tok in forbidden_live:
        assert tok not in src, f"{tok!r} appears as live port"
    # 8765 는 FORBIDDEN config 검사용으로 reference (DESKTOP_HUB_PORT) 만 허용
    # — 즉 == DESKTOP_HUB_PORT 비교만 있고 직접 8765 사용 없음
    assert "= 8765" not in src
    assert "port=8765" not in src


# ──────────────────────────────────────────────
# 6. Lifecycle route 테스트 (TestClient)
# ──────────────────────────────────────────────

class FakeRunner:
    """singleton 교체용 fake runner. process spawn 0건."""

    def __init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self.restart_calls = 0
        self.state = "stopped"
        self.pid = None
        self.last_error = None

    def start(self):
        self.start_calls += 1
        self.state = "running"
        self.pid = 999
        return True

    def stop(self):
        self.stop_calls += 1
        self.state = "stopped"
        self.pid = None
        return True

    def restart(self):
        self.restart_calls += 1
        self.state = "running"
        self.pid = 999
        return True

    def snapshot(self):
        return {
            "state": self.state, "pid": self.pid, "port": 8766,
            "host": "127.0.0.1", "cadRepoPath": None,
            "lastError": self.last_error,
        }


@pytest.fixture
def client_with_fake_runner(monkeypatch):
    fake = FakeRunner()
    monkeypatch.setattr(local_server_mod, "_cad_bridge_runner", fake)
    return TestClient(app), fake


def test_post_start_returns_200_with_snapshot(client_with_fake_runner):
    client, fake = client_with_fake_runner
    res = client.post("/cad/bridge/start")
    assert res.status_code == 200
    data = res.json()
    assert data["started"] is True
    assert data["snapshot"]["state"] == "running"
    assert fake.start_calls == 1


def test_post_stop_returns_200_with_snapshot(client_with_fake_runner):
    client, fake = client_with_fake_runner
    res = client.post("/cad/bridge/stop")
    assert res.status_code == 200
    data = res.json()
    assert data["stopped"] is True
    assert fake.stop_calls == 1


def test_post_restart_returns_200_with_snapshot(client_with_fake_runner):
    client, fake = client_with_fake_runner
    res = client.post("/cad/bridge/restart")
    assert res.status_code == 200
    data = res.json()
    assert data["restarted"] is True
    assert fake.restart_calls == 1


def test_lifecycle_routes_do_not_accept_body_pid(client_with_fake_runner):
    """body 가 있더라도 외부 PID 등 위험 입력은 무시 (route 가 body 인자 없음)."""
    client, fake = client_with_fake_runner
    res = client.post("/cad/bridge/start",
                      json={"pid": 41280, "force": True})
    assert res.status_code == 200
    # FakeRunner 의 start_calls 1 — body 무시되고 정상 start
    assert fake.start_calls == 1


def test_status_route_includes_runner_state_additively(
    client_with_fake_runner, monkeypatch,
):
    """GET /cad/bridge/status 응답에 runnerState 필드 추가."""
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    client, fake = client_with_fake_runner
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    data = res.json()
    # 기존 envelope 유지
    for k in ("status", "host", "port", "detail", "signaturePathsPresent"):
        assert k in data
    # additive 필드
    assert "runnerState" in data
    rs = data["runnerState"]
    assert rs["state"] == "stopped"
    assert rs["port"] == 8766


def test_status_route_runner_failure_does_not_crash_desktop(
    client_with_fake_runner, monkeypatch,
):
    """runner.snapshot 이 예외 던져도 desktop 서버 200 유지."""

    class BoomRunner:
        def snapshot(self):
            raise RuntimeError("simulated runner failure")

    monkeypatch.setattr(local_server_mod, "_cad_bridge_runner", BoomRunner())
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    client = TestClient(app)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    data = res.json()
    assert "runnerState" in data
    # safe snapshot fallback
    assert data["runnerState"].get("state") == "error"


def test_start_route_runner_failure_does_not_crash_desktop(monkeypatch):
    """runner.start 가 예외 던져도 desktop 서버 200 유지."""

    class BoomRunner:
        def start(self):
            raise RuntimeError("simulated start failure")
        def snapshot(self):
            return {"state": "error", "lastError": "boom"}

    monkeypatch.setattr(local_server_mod, "_cad_bridge_runner", BoomRunner())
    client = TestClient(app)
    res = client.post("/cad/bridge/start")
    assert res.status_code == 200
    assert res.json()["started"] is False


# ──────────────────────────────────────────────
# 7. 정책 boundary — proxy / WS action 미등록
# ──────────────────────────────────────────────

def test_proxy_route_still_not_registered():
    """proxy 라우트는 본 트랙 범위 밖 — 미등록 유지."""
    client = TestClient(app)
    res = client.get("/cad/bridge/proxy/openapi.json")
    # 404 (미등록) 또는 405 (다른 메서드만 매칭) — 절대 200 으로 응답 안 함
    assert res.status_code in (404, 405)


def test_ws_action_for_cad_bridge_not_registered():
    """WS dispatcher 에 cad_bridge_* action 등록 0건."""
    src = LOCAL_SERVER_FILE.read_text(encoding="utf-8")
    for forbidden in (
        'action == "cad_bridge_start"',
        'action == "cad_bridge_stop"',
        'action == "cad_bridge_restart"',
        "'cad_bridge_start'",
        "'cad_bridge_stop'",
        "'cad_bridge_restart'",
    ):
        assert forbidden not in src


def test_subprocess_popen_only_inside_cad_bridge_runner():
    """local_server.py 본문에는 subprocess.Popen 호출 0건 (runner 위임)."""
    src = LOCAL_SERVER_FILE.read_text(encoding="utf-8")
    assert "subprocess.Popen" not in src
    # 또한 직접 process kill 호출도 없음
    for forbidden in ("os.kill(", "taskkill /F", "Stop-Process"):
        assert forbidden not in src


# ──────────────────────────────────────────────
# 8. 기존 registry/status 회귀 — 본 트랙이 깨지 않음
# ──────────────────────────────────────────────

def test_registry_status_route_still_works_when_runner_absent(monkeypatch):
    """runner singleton 이 lazy init — status route 가 runner 인스턴스화 자체로
    실패하지 않아야 함."""
    monkeypatch.setattr(local_server_mod, "_cad_bridge_runner", None)
    monkeypatch.setattr(reg, "_safe_fetch_openapi", lambda *a, **kw: None)
    client = TestClient(app)
    res = client.get("/cad/bridge/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == reg.STATUS_STOPPED
    assert "runnerState" in data
