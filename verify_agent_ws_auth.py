from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


def _mask_agent_id(agent_id: str) -> str:
    if not agent_id:
        return ""
    if len(agent_id) <= 10:
        return agent_id[:3] + "***"
    return f"{agent_id[:6]}***{agent_id[-4:]}"


async def _probe(server_url: str, timeout: float) -> tuple[bool, str, str]:
    from local_agent import __version__
    from local_agent import desktop_config
    from local_agent import token_store
    from local_agent.connection_diagnostics import normalize_ws_url
    from local_agent.network_bypass import websocket_connect_kwargs

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
            await ws.send(json.dumps({
                "type": "auth",
                "agent_id": agent_id,
                "device_token": device_token,
                "version": __version__,
            }))
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            try:
                first = json.loads(raw)
            except json.JSONDecodeError:
                return False, "INVALID_AUTH_RESPONSE", _mask_agent_id(agent_id)
            if first.get("type") == "auth_ok":
                return True, "AUTH_OK", _mask_agent_id(agent_id)
            return False, str(first.get("type") or "AUTH_REJECTED"), _mask_agent_id(agent_id)
    except asyncio.TimeoutError:
        return False, "AUTH_TIMEOUT", _mask_agent_id(agent_id)
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
