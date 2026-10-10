from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 루트 패키지(local_agent 등) 해석용
from core.agent_runtime.connection.network_bypass import urlopen_for_server, websocket_connect_kwargs

DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


def _mask_agent_id(agent_id: str) -> str:
    if not agent_id:
        return "-"
    if len(agent_id) <= 10:
        return agent_id[:3] + "***"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def pass_(self, name: str, detail: str = "") -> None:
        self.rows.append(("PASS", name, detail))

    def warn(self, name: str, detail: str = "") -> None:
        self.rows.append(("WARN", name, detail))

    def fail(self, name: str, detail: str = "") -> None:
        self.rows.append(("FAIL", name, detail))

    def result(self) -> str:
        if any(level == "FAIL" for level, _, _ in self.rows):
            return "FAIL_LIVE_AGENT_SMOKE"
        if any(level == "WARN" for level, _, _ in self.rows):
            return "WARN_LIVE_AGENT_SMOKE"
        return "PASS_LIVE_AGENT_SMOKE"

    def print(self) -> None:
        for level, name, detail in self.rows:
            suffix = f" - {detail}" if detail else ""
            print(f"[{level}] {name}{suffix}")
        print(f"RESULT={self.result()}")


def _load_credentials(server_url: str) -> tuple[str, str]:
    from core.agent_runtime.common import desktop_config
    from core.agent_runtime.connection import token_store

    cfg = desktop_config.load_config()
    effective_server = (server_url or cfg.server_url or DEFAULT_SERVER_URL).rstrip("/")
    agent_id = cfg.agent_id.strip()
    token = token_store.load_device_token(effective_server, agent_id) if agent_id else None
    return agent_id, token or ""


def check_server_health(report: Report, server_url: str) -> None:
    try:
        with socket.create_connection(("haehan-ai.kr", 443), timeout=5):
            report.pass_("server tcp 443", "reachable")
    except OSError as exc:
        report.fail("server tcp 443", type(exc).__name__)
        return

    try:
        req = urllib.request.Request(server_url.rstrip("/") + "/api/v1/health", method="GET")
        with urlopen_for_server(server_url, req, timeout=10) as resp:
            if resp.status == 200:
                report.pass_("server health", "status=200")
            else:
                report.fail("server health", f"status={resp.status}")
    except urllib.error.HTTPError as exc:
        report.fail("server health", f"status={exc.code}")
    except urllib.error.URLError as exc:
        report.fail("server health", type(exc.reason).__name__)
    except OSError as exc:
        report.fail("server health", type(exc).__name__)


def _websocket_close_code(exc: object) -> int | None:
    for attr in ("rcvd", "rcvd_close"):
        close = getattr(exc, attr, None)
        code = getattr(close, "code", None)
        if isinstance(code, int):
            return code
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


async def _await_heartbeat_ack(ws, report, agent_id, timeout):
    await ws.send(json.dumps({"type": "heartbeat", "agent_id": agent_id}))
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        raw = await asyncio.wait_for(
            ws.recv(),
            timeout=max(0.5, deadline - asyncio.get_running_loop().time()),
        )
        msg = json.loads(raw)
        mtype = str(msg.get("type") or "")
        if mtype == "heartbeat_ack":
            report.pass_("websocket heartbeat", "heartbeat_ack")
            return
        if mtype == "task":
            report.warn("websocket queued task observed", "not executed by smoke probe")
    report.fail("websocket heartbeat", "timeout")


async def check_ws_heartbeat(report: Report, server_url: str, agent_id: str, token: str, timeout: float) -> None:
    from core.agent_runtime.connection import (
        connection_diagnostics,  # 서브모듈 이름을 함께 가져와 코드맵이 최상위 local_agent 패키지로 해석하게 한다
    )
    from local_agent import (
        __version__,  # 서브모듈 이름을 함께 가져와 코드맵이 최상위 local_agent 패키지로 해석하게 한다
    )

    normalize_ws_url = connection_diagnostics.normalize_ws_url

    try:
        import websockets  # type: ignore
    except ImportError:
        report.fail("websocket dependency", "websockets missing")
        return

    ws_url = normalize_ws_url(server_url)
    try:
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            close_timeout=3,
            open_timeout=timeout,
            **websocket_connect_kwargs(server_url),
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "agent_id": agent_id,
                        "device_token": token,
                        "version": __version__,
                    }
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            first = json.loads(raw)
            if first.get("type") != "auth_ok":
                report.fail("websocket auth", str(first.get("type") or "AUTH_REJECTED"))
                return
            report.pass_("websocket auth", "AUTH_OK")

            await _await_heartbeat_ack(ws, report, agent_id, timeout)
    except TimeoutError:
        report.fail("websocket", "timeout")
    except getattr(websockets.exceptions, "ConnectionClosed", Exception) as exc:
        code = _websocket_close_code(exc)
        if code == 4401:
            report.fail("websocket auth", "AUTH_FAILED_4401")
        else:
            report.fail("websocket", f"closed code={code or 'unknown'}")
    except (TypeError, json.JSONDecodeError):
        report.fail("websocket", "invalid json")
    except OSError as exc:
        report.fail("websocket", type(exc).__name__)
    finally:
        token = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    report = Report()
    server_url = args.server.rstrip("/")
    agent_id, token = _load_credentials(server_url)
    report.pass_("agent config", f"agent_id={_mask_agent_id(agent_id)} token_present={bool(token)}")
    check_server_health(report, server_url)
    asyncio.run(check_ws_heartbeat(report, server_url, agent_id, token, args.timeout))
    if any(level == "FAIL" and "AUTH_FAILED_4401" in detail for level, _, detail in report.rows):
        from core.agent_runtime.connection import connection_diagnostics as cd

        plan = cd.build_recovery_plan(
            state=cd.STATE_AUTH_FAILED,
            last_error_code="AUTH_FAILED_4401",
            token_present=bool(token),
        )
        report.warn("recovery", plan.next_action)
    report.warn("task dispatch", "skipped; admin/owner credentials not present")
    token = ""
    report.print()
    return 1 if report.result().startswith("FAIL") else 0


if __name__ == "__main__":
    raise SystemExit(main())
