import asyncio
import json
import sys
from unittest import mock

sys.path.insert(0, ".")


class MockWS:
    def __init__(self, msgs):
        self.msgs = msgs
        self.sent = []
        self.idx = 0

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if self.idx >= len(self.msgs):
            raise TimeoutError()
        msg = self.msgs[self.idx]
        self.idx += 1
        return json.dumps(msg)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def test_auth_sent():
    from scripts.probe_local_agent_ws_readonly import run_probe

    async def run():
        ws = MockWS([{"type": "auth_ok"}])
        with mock.patch("websockets.connect") as m:
            m.return_value.__aenter__.return_value = ws
            exit_code = await run_probe("ws://host/api/v1/local-agents/ws", "agent", "token", 1.0)  # noqa: F841

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "auth"

    asyncio.run(run())


def test_task_exit4():
    from scripts.probe_local_agent_ws_readonly import run_probe

    async def run():
        ws = MockWS([{"type": "task"}])
        with mock.patch("websockets.connect") as m:
            m.return_value.__aenter__.return_value = ws
            exit_code = await run_probe("ws://host/api/v1/local-agents/ws", "agent", "token", 5.0)

        assert exit_code == 4

    asyncio.run(run())


def test_missing_token_exit2():
    from scripts.probe_local_agent_ws_readonly import main

    exit_code = main(["--agent-id", "a", "--device-token", ""])
    assert exit_code == 2


def test_timeout_exit0():
    from scripts.probe_local_agent_ws_readonly import run_probe

    async def run():
        ws = MockWS([])
        with mock.patch("websockets.connect") as m:
            m.return_value.__aenter__.return_value = ws
            exit_code = await run_probe("ws://host/api/v1/local-agents/ws", "agent", "token", 0.1)

        assert exit_code == 0

    asyncio.run(run())


def test_read_only_no_result():
    from pathlib import Path

    probe_script = Path("scripts/probe_local_agent_ws_readonly.py")
    code = probe_script.read_text()
    assert '"type": "result"' not in code
    assert '"type": "auth"' in code
