"""데스크톱 앱 ↔ 사용자 PC Claude MCP 연동 시험 (M1~M6).

- Node 단위 시험(admin-web/electron/tests/claude_mcp.test.js)을 pytest 에서 실행한다 — 임시 폴더만 사용.
- mcp_server.py 의 앱 주소(env 덮어쓰기)와 '앱이 꺼져 있을 때' 안내를 고정한다.
- 앱 배선(IPC·트레이·preload)이 끊기지 않았는지 정적으로 확인한다. 실제 Claude 연동은 빌드 후 PC 점검 항목이다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import requests

from ai_orchestrator.server import mcp_server

ROOT = Path(__file__).resolve().parents[2]
ELECTRON = ROOT / "admin-web" / "electron"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 필요")
def test_node_unit_tests_pass():
    r = subprocess.run(
        ["node", "--test", str(ELECTRON / "tests" / "claude_mcp.test.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


# ── M3: 앱 주소 ──


def test_api_base_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_FASTAPI_URL", raising=False)
    monkeypatch.delenv("HAEHAN_PORT", raising=False)
    assert mcp_server._resolve_api_base() == "http://127.0.0.1:8401"


def test_api_base_from_url_env_wins(monkeypatch):
    monkeypatch.setenv("HAEHAN_FASTAPI_URL", "http://127.0.0.1:9100/")
    monkeypatch.setenv("HAEHAN_PORT", "9200")
    assert mcp_server._resolve_api_base() == "http://127.0.0.1:9100"


def test_api_base_from_port_env(monkeypatch):
    monkeypatch.delenv("HAEHAN_FASTAPI_URL", raising=False)
    monkeypatch.setenv("HAEHAN_PORT", "9200")
    assert mcp_server._resolve_api_base() == "http://127.0.0.1:9200"


def test_api_base_ignores_garbage_port(monkeypatch):
    monkeypatch.delenv("HAEHAN_FASTAPI_URL", raising=False)
    monkeypatch.setenv("HAEHAN_PORT", "abc")
    assert mcp_server._resolve_api_base() == "http://127.0.0.1:8401"


def test_app_not_running_gives_actionable_message(monkeypatch):
    def refuse(*_a, **_k):
        raise requests.ConnectionError("Connection refused")

    monkeypatch.setattr(mcp_server.requests, "request", refuse)
    res = mcp_server._api_call("naver.session.status")
    assert res["ok"] is False
    assert "Haehan AI 앱을 실행한 뒤 다시 시도하세요" in res["error"]
    assert "Haehan AI 앱을 실행한 뒤 다시 시도하세요" in res["hint"]


def test_other_request_errors_keep_generic_hint(monkeypatch):
    def timeout(*_a, **_k):
        raise requests.Timeout("slow")

    monkeypatch.setattr(mcp_server.requests, "request", timeout)
    res = mcp_server._api_call("naver.session.status")
    assert res["ok"] is False
    assert "실행 중인지" in res["hint"]


# ── 앱 배선 (정적) ──


def test_main_wires_connect_disconnect_status_and_consent():
    main = (ELECTRON / "main.js").read_text(encoding="utf-8")
    for token in (
        'ipcMain.handle("local-config:connect-claude"',
        'ipcMain.handle("local-config:disconnect-claude"',
        'ipcMain.handle("local-config:claude-status"',
        "EVENTS.CLAUDE_CONNECT",
        "EVENTS.CLAUDE_DISCONNECT",
        "syncClaudeOnStart",
        "dialog.showMessageBox",  # 처음 한 번 사용자 동의를 받는다
        "claude_mcp",  # 동의·빌드 기록(config.json)
    ):
        assert token in main, token


def test_preload_and_tray_expose_the_flow():
    pre = (ELECTRON / "webview_preload.js").read_text(encoding="utf-8")
    for name in ("connectClaude", "disconnectClaude", "getClaudeStatus"):
        assert name in pre
    tray = (ELECTRON / "lib" / "tray.js").read_text(encoding="utf-8")
    assert "Claude 연결" in tray
    assert "Claude 연결 해제" in tray


def test_old_resourcespath_registration_is_gone():
    """리소스(포터블 임시 폴더) 경로를 Claude 설정에 직접 쓰던 옛 구현이 남아 있지 않다."""
    cfg = (ELECTRON / "lib" / "config.js").read_text(encoding="utf-8")
    assert "connectClaudeDesktop" not in cfg
    assert 'path.join(process.resourcesPath, "mcp"' not in cfg
    mod = (ELECTRON / "lib" / "claude_mcp.js").read_text(encoding="utf-8")
    assert "writeFileSync(cfgPath" not in mod  # 설정 파일은 writeAtomic(tmp+rename)으로만 쓴다
