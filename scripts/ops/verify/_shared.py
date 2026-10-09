"""라이브 검증 스크립트들이 함께 쓰는 원격 임시 관리자 계정 조작·워커 코드(verify 패키지 안의 잎 모듈).

원래 tools/smoke/live_approved_browser_instruction_smoke.py 에 있던 것을 옮겼다(동작 변경 없음).
verify 가 ops 를 import 하던 방향을 없애 scripts/verify <-> scripts/ops 순환을 끊는다(ops 가 이 모듈을 import 한다).
"""

from __future__ import annotations

import base64
import json
import subprocess

REMOTE_HOST = "haehan-app"

REMOTE_USER_SCRIPT = r"""
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
path_candidates = [
    Path("/home/ubuntu/apps/haehan-ai-orchestrator/secrets/api/http_users.json"),
    Path("/home/ubuntu/apps/haehan-ai-orchestrator-api/secrets/api/http_users.json"),
]
path = next((candidate for candidate in path_candidates if candidate.exists()), path_candidates[0])
if not path.exists():
    raise SystemExit(f"http_users file not found: {path}")
raw = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(raw, list):
    raise SystemExit("http_users format is not a list")

username = payload["username"]
action = payload["action"]
raw = [rec for rec in raw if not (isinstance(rec, dict) and rec.get("username") == username)]

if action == "add":
    password = payload["password"]
    salt = secrets.token_bytes(16)
    digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
    raw.append({
        "username": username,
        "password_hash": f"sha256${salt.hex()}${digest}",
        "role": "admin",
        "enabled": True,
    })
elif action != "remove":
    raise SystemExit("unknown action")

tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
os.chmod(path, 0o600)
print("OK")
"""


WORKER_CODE = r"""
import os
from local_agent import config
from local_agent import websocket_client

config.SERVER_BASE_URL = os.environ["HAEHAN_LIVE_SERVER_URL"]
config.WEBSOCKET_ENABLED = True
websocket_client.connect(
    os.environ["HAEHAN_LIVE_AGENT_ID"],
    os.environ["HAEHAN_LIVE_DEVICE_TOKEN"],
)
"""


def remote_user(action: str, username: str, password: str = "") -> None:
    payload = {"action": action, "username": username, "password": password}
    encoded = base64.b64encode(REMOTE_USER_SCRIPT.encode("utf-8")).decode("ascii")
    remote_command = f"python3 -c 'import base64; exec(base64.b64decode(\"{encoded}\"))'"
    proc = subprocess.run(
        ["ssh", REMOTE_HOST, remote_command],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        safe_detail = detail[-1][:200] if detail else "no remote detail"
        raise RuntimeError(f"remote user {action} failed: rc={proc.returncode} detail={safe_detail}")
