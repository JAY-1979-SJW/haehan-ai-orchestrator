"""Google router commands for session, module checks, and work records."""
from __future__ import annotations

import json

from scripts.common.gate import check as gate_check
from scripts.google import module_check, work_records
from scripts.google.common.base import check_session


def run_session_check() -> None:
    print("=" * 60)
    print("Google session check")
    print("=" * 60)
    result = check_session()
    if result["error"]:
        print(f"[fail] daemon connection failed: {result['error']}")
    elif result["logged_in"]:
        print("[ok] logged in")
    else:
        print("[needs-login] run: python scripts/entry/cdp_cli.py google login")
    print("=" * 60)


def run_module_check() -> None:
    payload = module_check.build_google_module_index()
    path = module_check.save_google_module_index(payload)
    module_check.record_google_module_check(payload, path)
    module_check.print_google_module_summary(payload, path)
    if not payload.get("ok"):
        raise SystemExit(1)


def run_work_records(args: list[str] | None = None) -> None:
    limit = 10
    for arg in args or []:
        if arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except ValueError:
                limit = 10
    latest = work_records.load_latest()
    history = work_records.load_history(limit=limit)
    latest_path, history_path = work_records.record_paths()
    print(json.dumps({
        "ok": latest is not None,
        "lane": work_records.LANE,
        "latest_path": str(latest_path),
        "history_path": str(history_path),
        "latest": latest,
        "history": history,
        "secret_values_output": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))


def run_login() -> None:
    """User-present Google login helper."""
    from scripts.google.auth import login_google
    from scripts.browser.cdp.connection import get_page

    gate_check("wait_login", risk="notify")
    print("=" * 60)
    print("Google login")
    print("=" * 60)
    page = get_page()
    result = login_google(page, wait_for_user_s=300)
    if result["ok"]:
        print(f"[ok] login success: {result.get('user')} ({result.get('reason')})")
    else:
        print(f"[fail] login failed: {result.get('reason')}")
        if result.get("hint"):
            print(f"  hint: {result['hint']}")
    print("=" * 60)
