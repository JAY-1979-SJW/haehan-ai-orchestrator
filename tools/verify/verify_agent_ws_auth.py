from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 직접 실행에서도 scripts 패키지를 찾게 한다
from scripts.common.app_paths import repo_root

ROOT = repo_root()
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


def _mask_agent_id(agent_id: str) -> str:
    if not agent_id:
        return ""
    if len(agent_id) <= 10:
        return agent_id[:3] + "***"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


def _websocket_close_code(exc: object) -> int | None:
    for attr in ("rcvd", "rcvd_close"):
        close = getattr(exc, attr, None)
        code = getattr(close, "code", None)
        if isinstance(code, int):
            return code
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) else None


async def _probe(server_url: str, timeout: float) -> tuple[bool, str, str]:
    from core.agent_runtime.common import (
        desktop_config,  # 서브모듈 이름을 함께 가져와 코드맵이 최상위 local_agent 패키지로 해석하게 한다
    )
    from core.agent_runtime.connection import (
        token_store,  # 서브모듈 이름을 함께 가져와 코드맵이 최상위 local_agent 패키지로 해석하게 한다
    )
    from core.agent_runtime.connection.connection_diagnostics import normalize_ws_url
    from core.agent_runtime.connection.network_bypass import websocket_connect_kwargs
    from local_agent import (
        __version__,  # 서브모듈 이름을 함께 가져와 코드맵이 최상위 local_agent 패키지로 해석하게 한다
    )

    try:
        import websockets  # type: ignore
    except ImportError:
        return False, "WEBSOCKETS_MISSING", ""

    cfg = desktop_config.load_config()
    effective_server = (server_url or cfg.server_url or DEFAULT_SERVER_URL).rstrip("/")
    agent_id = cfg.agent_id.strip()
    if not agent_id:
        return False, "AGENT_ID_MISSING", ""

    device_token = token_store.load_device_token(effective_server, agent_id)
    if not device_token:
        return False, "DEVICE_TOKEN_MISSING", _mask_agent_id(agent_id)

    ws_url = normalize_ws_url(effective_server)
    try:
        async with websockets.connect(
            ws_url,
            ping_interval=None,
            close_timeout=3,
            open_timeout=timeout,
            **websocket_connect_kwargs(effective_server),
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "agent_id": agent_id,
                        "device_token": device_token,
                        "version": __version__,
                    }
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            try:
                first = json.loads(raw)
            except json.JSONDecodeError:
                return False, "INVALID_AUTH_RESPONSE", _mask_agent_id(agent_id)
            if first.get("type") == "auth_ok":
                return True, "AUTH_OK", _mask_agent_id(agent_id)
            return False, str(first.get("type") or "AUTH_REJECTED"), _mask_agent_id(agent_id)
    except TimeoutError:
        return False, "AUTH_TIMEOUT", _mask_agent_id(agent_id)
    except getattr(websockets.exceptions, "ConnectionClosed", Exception) as exc:
        code = _websocket_close_code(exc)
        if code == 4401:
            return False, "AUTH_FAILED_4401", _mask_agent_id(agent_id)
        return False, f"WS_CLOSED_{code or 'UNKNOWN'}", _mask_agent_id(agent_id)
    except OSError as exc:
        return False, type(exc).__name__, _mask_agent_id(agent_id)
    finally:
        device_token = ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=DEFAULT_SERVER_URL)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)

    ok, status, masked_agent = asyncio.run(_probe(args.server, args.timeout))
    print(f"agent_id_masked={masked_agent or '-'}")
    print(f"ws_auth_status={status}")
    print(f"RESULT={'PASS_AGENT_WS_AUTH' if ok else 'FAIL_AGENT_WS_AUTH'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
