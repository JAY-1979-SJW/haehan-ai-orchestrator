"""Realtime app health checker.

The checker is read-only. It polls the local app/API, CDP browser, audit log,
and latest dry-run evidence, then writes both a dedicated JSONL heartbeat and a
realtime audit event.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common.realtime_audit import emit_event  # noqa: E402 - sys.path 부트스트랩 뒤 import

LOG_DIR = ROOT / "data" / "logs"
LATEST_PATH = LOG_DIR / "app_realtime_check_latest.json"
JSONL_PATH = LOG_DIR / "app_realtime_check.jsonl"
PID_PATH = LOG_DIR / "app_realtime_check.pid"

DEFAULT_APP_URL = "http://127.0.0.1:8400/api/v1/health"
DEFAULT_CDP_VERSION_URL = "http://127.0.0.1:9222/json/version"
DEFAULT_CDP_TABS_URL = "http://127.0.0.1:9222/json/list"
AUDIT_JSONL = LOG_DIR / "realtime_audit.jsonl"
DRY_RUN_LATEST = LOG_DIR / "pre_change_dry_run_latest.json"
WORKTREE_INDEX = ROOT / "data" / "worktree_change_index_latest.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _http_json(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(100_000).decode("utf-8", errors="replace")
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            try:
                payload: Any = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {"raw": body[:500]}
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "elapsed_ms": elapsed_ms,
                "payload": payload,
            }
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": False,
            "status": 0,
            "elapsed_ms": elapsed_ms,
            "error": str(exc)[:300],
        }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    return round(time.time() - path.stat().st_mtime, 1)


def check_app(url: str, timeout: float) -> dict[str, Any]:
    result = _http_json(url, timeout)
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    return {
        "name": "api_health",
        "ok": bool(result.get("ok")),
        "url": url,
        "http_status": result.get("status", 0),
        "elapsed_ms": result.get("elapsed_ms", 0),
        "service_status": payload.get("status") or payload.get("ok") or "",
        "error": result.get("error", ""),
    }


def check_cdp(version_url: str, tabs_url: str, timeout: float) -> dict[str, Any]:
    version = _http_json(version_url, timeout)
    tabs = _http_json(tabs_url, timeout)
    tab_payload = tabs.get("payload") if isinstance(tabs.get("payload"), list) else []
    page_tabs = [row for row in tab_payload if isinstance(row, dict) and row.get("type") == "page"]
    return {
        "name": "cdp_browser",
        "ok": bool(version.get("ok") and tabs.get("ok")),
        "version_status": version.get("status", 0),
        "tabs_status": tabs.get("status", 0),
        "browser": (version.get("payload") or {}).get("Browser", "")
        if isinstance(version.get("payload"), dict)
        else "",
        "tab_count": len(page_tabs),
        "about_blank_count": sum(1 for row in page_tabs if row.get("url") == "about:blank"),
        "error": version.get("error") or tabs.get("error") or "",
    }


def check_audit_log(max_age_seconds: int) -> dict[str, Any]:
    age = _file_age_seconds(AUDIT_JSONL)
    ok = age is not None and age <= max_age_seconds
    return {
        "name": "audit_log_freshness",
        "ok": ok,
        "path": str(AUDIT_JSONL),
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
    }


def check_latest_dry_run() -> dict[str, Any]:
    record = _load_json(DRY_RUN_LATEST)
    return {
        "name": "latest_dry_run",
        "ok": bool(record and record.get("status") == "ok" and record.get("exit_code") == 0),
        "path": str(DRY_RUN_LATEST),
        "status": record.get("status", ""),
        "scope": record.get("scope", ""),
        "generated_at": record.get("generated_at", ""),
        "exit_code": record.get("exit_code", None),
    }


def check_worktree_index(max_age_seconds: int) -> dict[str, Any]:
    age = _file_age_seconds(WORKTREE_INDEX)
    index = _load_json(WORKTREE_INDEX)
    summary = index.get("summary") if isinstance(index.get("summary"), dict) else {}
    ok = age is not None and age <= max_age_seconds and bool(summary)
    return {
        "name": "worktree_index",
        "ok": ok,
        "path": str(WORKTREE_INDEX),
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "changed_count": summary.get("changed_count", None),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    checks = [
        check_app(args.app_url, args.timeout),
        check_cdp(args.cdp_version_url, args.cdp_tabs_url, args.timeout),
        check_audit_log(args.audit_max_age_seconds),
        check_latest_dry_run(),
        check_worktree_index(args.index_max_age_seconds),
    ]
    failed = [check for check in checks if not check.get("ok")]
    status = "ok" if not failed else "degraded"
    return {
        "schema_version": 1,
        "timestamp": _now(),
        "status": status,
        "pid": os.getpid(),
        "failed_checks": [check["name"] for check in failed],
        "checks": checks,
    }


def save_report(report: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, default=str)
    LATEST_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(payload + "\n")
        f.flush()


def emit_report(report: dict[str, Any]) -> None:
    emit_event(
        "APP_REALTIME_CHECK",
        site="app",
        workflow="realtime_check",
        status=report["status"],
        risk="ops",
        message=f"app realtime check {report['status']}",
        artifact_path=str(LATEST_PATH),
        metadata={
            "failed_checks": report.get("failed_checks", []),
            "checks": {
                check["name"]: {
                    "ok": check.get("ok"),
                    "status": check.get("http_status") or check.get("status") or check.get("version_status") or "",
                    "age_seconds": check.get("age_seconds"),
                    "tab_count": check.get("tab_count"),
                }
                for check in report.get("checks", [])
            },
        },
    )


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    report = build_report(args)
    save_report(report)
    emit_report(report)
    return report


def print_report(report: dict[str, Any]) -> None:
    print(f"APP_REALTIME_CHECK status={report['status']} failed={report.get('failed_checks', [])}")
    for check in report.get("checks", []):
        marker = "OK" if check.get("ok") else "FAIL"
        detail = ""
        if "http_status" in check:
            detail = f" http={check.get('http_status')} elapsed={check.get('elapsed_ms')}ms"
        elif check["name"] == "cdp_browser":
            detail = f" tabs={check.get('tab_count')} browser={check.get('browser')}"
        elif "age_seconds" in check:
            detail = f" age={check.get('age_seconds')}s"
        elif check["name"] == "latest_dry_run":
            detail = f" status={check.get('status')} scope={check.get('scope')}"
        print(f"- {marker} {check['name']}{detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run realtime app health checks.")
    parser.add_argument("--app-url", default=DEFAULT_APP_URL)
    parser.add_argument("--cdp-version-url", default=DEFAULT_CDP_VERSION_URL)
    parser.add_argument("--cdp-tabs-url", default=DEFAULT_CDP_TABS_URL)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--audit-max-age-seconds", type=int, default=300)
    parser.add_argument("--index-max-age-seconds", type=int, default=900)
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--max-runs", type=int, default=1, help="0 means run forever.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    count = 0
    while True:
        report = run_once(args)
        if not args.quiet:
            print_report(report)
        count += 1
        if args.max_runs and count >= args.max_runs:
            return 0 if report["status"] == "ok" else 1
        time.sleep(max(args.interval_seconds, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
