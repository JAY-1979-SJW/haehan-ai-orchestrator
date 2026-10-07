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
  python scripts/browser/cdp_client.py hiworks dashboard
  python scripts/browser/cdp_client.py hiworks apps
  python scripts/browser/cdp_client.py hiworks mail
  python scripts/browser/cdp_client.py hiworks compose
  python scripts/browser/cdp_client.py hiworks service [mail|approval|scheduler|boards|address-book|booking|hr-work|team-mail|files|tasks|admins|bills|sms|notes|groups|ai-chat|plus|all]
  python scripts/browser/cdp_client.py hiworks actions [mail|approval|scheduler|boards|address-book|booking|hr-work|team-mail|files|tasks|admins|bills|sms|notes|groups|ai-chat|plus|all]
  python scripts/browser/cdp_client.py hiworks prepare-section [service|all] [--dry-run] [--values=values.json]
  python scripts/browser/cdp_client.py hiworks submit-section <service> <control_id> --approved --confirm=HIWORKS_APPROVED_SUBMIT [--dry-run] [--approved-by=name]
  python scripts/browser/cdp_client.py hiworks queue [limit]
  python scripts/browser/cdp_client.py hiworks prepare-sales-mail [index]
  python scripts/browser/cdp_client.py hiworks send-batch [limit] --dry-run --delay-min=15 --delay-max=45
"""
