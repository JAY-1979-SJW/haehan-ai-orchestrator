"""127.0.0.1 전용 로컬 서버 — samples/web_recording_demo 정적 파일 제공.

사용 예:
  python scripts/serve_web_recording_demo.py
  python scripts/serve_web_recording_demo.py --port 8765 --directory samples/web_recording_demo

외부 네트워크 바인딩 금지: host 는 항상 127.0.0.1
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_DIRECTORY = str(_REPO_ROOT / "samples" / "web_recording_demo")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="127.0.0.1 정적 파일 서버")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"listen host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"listen port (default: {DEFAULT_PORT})")
    parser.add_argument("--directory", default=DEFAULT_DIRECTORY, help="serve 디렉토리")
    return parser.parse_args(argv)


def make_server(host: str, port: int, directory: str) -> http.server.HTTPServer:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=directory,
    )
    handler.log_message = lambda *args: None  # suppress access logs
    return http.server.HTTPServer((host, port), handler)


def main(argv=None) -> int:
    args = parse_args(argv)
    host = DEFAULT_HOST  # 외부 네트워크 바인딩 금지 — 항상 127.0.0.1
    port = args.port
    directory = os.path.abspath(args.directory)

    if not os.path.isdir(directory):
        print(f"ERROR: directory not found: {directory}", file=sys.stderr)
        return 1

    server = make_server(host, port, directory)
    print(f"Serving {directory}")
    print(f"  http://{host}:{port}/")
    print("  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
