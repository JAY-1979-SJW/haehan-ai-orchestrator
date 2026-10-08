"""Shared CLI utilities for the Hiworks router."""
from __future__ import annotations


def option_value(args: list[str], prefix: str) -> str | None:
    """Return the value portion of the first arg that starts with *prefix*."""
    for arg in args:
        text = str(arg)
        if text.startswith(prefix):
            return text.split("=", 1)[1]
    return None


HELP_TEXT = """Hiworks usage:
  python scripts/entry/cdp_cli.py hiworks dashboard
  python scripts/entry/cdp_cli.py hiworks apps
  python scripts/entry/cdp_cli.py hiworks mail
  python scripts/entry/cdp_cli.py hiworks compose
  python scripts/entry/cdp_cli.py hiworks service [mail|approval|scheduler|boards|address-book|booking|hr-work|team-mail|files|tasks|admins|bills|sms|notes|groups|ai-chat|plus|all]
  python scripts/entry/cdp_cli.py hiworks actions [mail|approval|scheduler|boards|address-book|booking|hr-work|team-mail|files|tasks|admins|bills|sms|notes|groups|ai-chat|plus|all]
  python scripts/entry/cdp_cli.py hiworks prepare-section [service|all] [--dry-run] [--values=values.json]
  python scripts/entry/cdp_cli.py hiworks submit-section <service> <control_id> --approved --confirm=HIWORKS_APPROVED_SUBMIT [--dry-run] [--approved-by=name]
  python scripts/entry/cdp_cli.py hiworks queue [limit]
  python scripts/entry/cdp_cli.py hiworks prepare-sales-mail [index]
  python scripts/entry/cdp_cli.py hiworks send-batch [limit] --dry-run --delay-min=15 --delay-max=45
"""
