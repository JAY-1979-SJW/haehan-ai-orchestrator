"""배포 트리거 데몬 — 호스트에서 실행, 컨테이너의 요청을 받아 deploy 스크립트를 실행한다.

127.0.0.1:8401 에서 청취. 외부 노출 없음.
컨테이너는 host.docker.internal:8401 로 접근한다.

실행:
  python3 scripts/ops/deploy_trigger_daemon.py

systemd 서비스로 등록:
  /etc/systemd/system/ai-orchestrator-deploy-trigger.service
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("deploy_trigger_daemon")

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "ops" / "deploy_api_with_runtime_gates.py"
# 0.0.0.0 으로 바인드해야 컨테이너(host.docker.internal)에서 접근 가능.
# HMAC-SHA256 서명 검증으로 무단 트리거를 차단한다.
HOST = "0.0.0.0"
PORT = 8401

_lock = threading.Lock()
_running = False


def _trigger_secret() -> bytes:
    secret = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("DEPLOY_WEBHOOK_SECRET 환경변수 미설정")
    return secret.encode()


def _verify(body: bytes, sig: str | None) -> bool:
    if not sig or not sig.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(_trigger_secret(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _run_deploy() -> None:
    global _running
    try:
        logger.info("deploy: starting")
        result = subprocess.run(
            [sys.executable, str(DEPLOY_SCRIPT), "--approved"],
            cwd=str(ROOT),
            timeout=900,
            check=False,
        )
        logger.info("deploy: finished exit_code=%d", result.returncode)
    except Exception as exc:
        logger.error("deploy: error: %s", exc)
    finally:
        with _lock:
            _running = False


class TriggerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        logger.info(fmt, *args)

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        global _running
        if self.path != "/trigger":
            self._send(404, {"ok": False})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        sig = self.headers.get("X-Deploy-Signature")

        if not _verify(body, sig):
            logger.warning("deploy trigger: invalid signature from %s", self.client_address)
            self._send(401, {"ok": False, "error": "invalid_signature"})
            return

        with _lock:
            if _running:
                self._send(409, {"ok": False, "error": "deploy_already_running"})
                return
            _running = True

        t = threading.Thread(target=_run_deploy, daemon=True)
        t.start()
        logger.info("deploy trigger: accepted from %s", self.client_address)
        self._send(202, {"ok": True, "secret_values_output": False})

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send(404, {"ok": False})
            return
        self._send(200, {"ok": True, "running": _running})


def main() -> None:
    server = HTTPServer((HOST, PORT), TriggerHandler)
    logger.info("deploy_trigger_daemon listening on %s:%d", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutdown")


if __name__ == "__main__":
    main()
