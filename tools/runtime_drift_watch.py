"""Periodic runtime drift watcher.

This is a read-only wrapper around verify_runtime_drift. It writes a redacted
latest JSON file and JSONL history so a systemd timer or cron job can monitor
runtime drift without printing secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
sys.path.insert(0, str(ROOT))

from tools.runtime import verify_runtime_drift  # noqa: E402

DEFAULT_LATEST = ROOT / "data" / "runtime" / "runtime_drift_latest.json"
DEFAULT_HISTORY = ROOT / "data" / "runtime" / "runtime_drift_history.jsonl"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    paths = tuple(args.path) if args.path else verify_runtime_drift.DEFAULT_RUNTIME_PATHS
    if args.self_check:
        local = verify_runtime_drift.local_snapshot(ROOT, remote=args.remote, branch=args.branch, paths=paths)
        server = verify_runtime_drift.self_snapshot(
            ROOT,
            remote=args.remote,
            branch=args.branch,
            container=args.container,
            container_root=args.container_root,
            paths=paths,
        )
    else:
        local = verify_runtime_drift.local_snapshot(ROOT, remote=args.remote, branch=args.branch, paths=paths)
        server = verify_runtime_drift.remote_snapshot(
            server=args.server,
            remote_path=args.remote_path,
            container=args.container,
            remote=args.remote,
            branch=args.branch,
            container_root=args.container_root,
            paths=paths,
        )
    verdict = verify_runtime_drift.evaluate(local, server)
    return {
        "schema_version": 1,
        "created_at": now(),
        "workflow": "runtime_drift_watch",
        "mode": "self" if args.self_check else "remote",
        "ok": verdict["ok"],
        "status": verdict["status"],
        "failed_check_ids": [item["id"] for item in verdict["failed"]],
        "local_head": local.get("head", ""),
        "local_origin": local.get("origin", ""),
        "server_head": server.get("head", ""),
        "server_origin": server.get("origin", ""),
        "container": server.get("container", {}),
        "fingerprints": {
            "local": local.get("fingerprint", {}),
            "server": server.get("fingerprint", {}),
            "container": server.get("container_fingerprint", {}),
        },
        "checks": verdict["checks"],
        "secret_values_output": False,
    }


def write_payload(payload: dict[str, Any], *, latest: Path, history: Path) -> None:
    latest.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with history.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write runtime drift watch status artifacts.")
    parser.add_argument("--self", dest="self_check", action="store_true", help="Run on the server itself.")
    parser.add_argument("--server", default=verify_runtime_drift.DEFAULT_SERVER)
    parser.add_argument("--remote-path", default=verify_runtime_drift.DEFAULT_REMOTE_PATH)
    parser.add_argument("--container", default=verify_runtime_drift.DEFAULT_CONTAINER)
    parser.add_argument("--remote", default=verify_runtime_drift.DEFAULT_REMOTE)
    parser.add_argument("--branch", default=verify_runtime_drift.DEFAULT_BRANCH)
    parser.add_argument("--container-root", default=verify_runtime_drift.DEFAULT_CONTAINER_ROOT)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0 after writing status.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
    except Exception as exc:  # noqa: BLE001 - 런타임 드리프트 감시 — payload 생성 실패 시 ok=False 인 실패 payload로 대체하는 fail-closed 경로.
        payload = {
            "schema_version": 1,
            "created_at": now(),
            "workflow": "runtime_drift_watch",
            "mode": "self" if args.self_check else "remote",
            "ok": False,
            "status": "watch_failed",
            "failed_check_ids": ["watch_execution_failed"],
            "error_type": type(exc).__name__,
            "error_summary": str(exc)[:300],
            "secret_values_output": False,
        }
    write_payload(payload, latest=Path(args.latest), history=Path(args.history))
    print(f"runtime_drift_watch status={payload['status']} ok={payload['ok']}")
    if args.exit_zero:
        return 0
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
