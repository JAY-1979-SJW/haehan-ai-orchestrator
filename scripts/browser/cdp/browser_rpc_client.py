"""browser_rpc_server.py 클라이언트 — 매번 새 Playwright 연결 없이 명령만 보낸다.

사용:
    from scripts.browser.cdp.browser_rpc_client import rpc

    rpc("goto", url="https://blog.naver.com/skyjwsin")
    print(rpc("text")["result"][:200])
    rpc("click", selector="text=삭제")
"""

from __future__ import annotations

import json
import socket

RPC_HOST = "127.0.0.1"
RPC_PORT = 8899


def rpc(cmd: str, timeout: float = 30.0, **kwargs) -> dict:
    """서버에 명령 전송. 서버가 안 떠 있으면 RuntimeError."""
    req = {"cmd": cmd, **kwargs}
    try:
        with socket.create_connection((RPC_HOST, RPC_PORT), timeout=timeout) as s:
            s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            s.settimeout(timeout)
            chunks = b""
            while not chunks.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                chunks += chunk
            return json.loads(chunks.decode("utf-8"))
    except ConnectionRefusedError as e:
        raise RuntimeError(
            "browser_rpc_server가 안 떠 있습니다. python scripts/browser/browser_rpc_server.py start 로 먼저 시작하세요."
        ) from e
