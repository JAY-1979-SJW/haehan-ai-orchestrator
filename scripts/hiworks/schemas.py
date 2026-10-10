"""Hiworks constants and workflow catalog."""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SALES_QUEUE = DATA_DIR / "eum_sales_mail_queue_latest.jsonl"

HIWORKS_DASHBOARD_URL = "https://dashboard.office.hiworks.com/"
HIWORKS_MAIL_URL = "https://mails.office.hiworks.com/"
HIWORKS_DOMAIN_HINT = "office.hiworks.com"

SERVICE_TARGETS: dict[str, dict[str, str]] = {
    "mail": {
        "label": "메일",
        "url": "https://mails.office.hiworks.com/",
    },
    "approval": {
        "label": "전자결재",
        "url": "https://approval.office.hiworks.com/haehan-ai.kr/approval/document",
    },
    "scheduler": {
        "label": "일정",
        "url": "https://scheduler.office.hiworks.com/calendar/checked",
    },
    "boards": {
        "label": "게시판",
        "url": "https://boards.office.hiworks.com/board/postlist/recent",
    },
    "address-book": {
        "label": "주소록",
        "url": "https://address-book.office.hiworks.com/",
    },
    "booking": {
        "label": "예약",
        "url": "https://booking.office.hiworks.com/haehan-ai.kr/booking/bookingMain",
    },
    "hr-work": {
        "label": "근무/경비처리",
        "url": "https://hr-work.office.hiworks.com/",
    },
    "team-mail": {
        "label": "공용메일",
        "url": "https://team-mail.office.hiworks.com/",
    },
    "files": {
        "label": "드라이브",
        "url": "https://files.office.hiworks.com/",
    },
    "tasks": {
        "label": "업무관리",
        "url": "https://tasks.office.hiworks.com/",
    },
    "admins": {
        "label": "하이웍스 관리",
        "url": "https://admins.office.hiworks.com/",
    },
    "bills": {
        "label": "세금계산서",
        "url": "https://bills.office.hiworks.com/",
    },
    "sms": {
        "label": "메시징",
        "url": "https://sms.office.hiworks.com/haehan-ai.kr/sms/sms_main",
    },
    "notes": {
        "label": "쪽지",
        "url": "https://notes.office.hiworks.com/",
    },
    "groups": {
        "label": "그룹",
        "url": "https://groups.office.hiworks.com/group/main",
    },
    "ai-chat": {
        "label": "AI채팅",
        "url": "https://ai-chat.office.hiworks.com/",
    },
    "plus": {
        "label": "플러스앱",
        "url": "https://plus.office.hiworks.com/",
    },
}

WORKFLOWS: list[dict[str, Any]] = [
    {
        "key": "dashboard",
        "aliases": ["dashboard", "home"],
        "title": "Hiworks dashboard read-only view",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks dashboard",
        "auto_execute": True,
    },
    {
        "key": "apps",
        "aliases": ["apps", "scan"],
        "title": "Hiworks app catalog scan",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks apps",
        "auto_execute": True,
    },
    {
        "key": "mail",
        "aliases": ["mail"],
        "title": "Hiworks mail read-only open",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks mail",
        "auto_execute": True,
    },
    {
        "key": "compose",
        "aliases": ["compose"],
        "title": "Hiworks compose page inspection",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks compose",
        "auto_execute": True,
    },
    {
        "key": "prepare_sales_mail",
        "aliases": ["prepare-sales-mail"],
        "title": "Fill one Hiworks sales-mail draft without sending",
        "risk": "prepare",
        "command": "python scripts/entry/cdp_cli.py hiworks prepare-sales-mail <index>",
        "auto_execute": True,
    },
    {
        "key": "send_batch_plan",
        "aliases": ["send-batch"],
        "title": "Build one-recipient-at-a-time send dry-run plan",
        "risk": "prepare",
        "command": "python scripts/entry/cdp_cli.py hiworks send-batch <limit> --dry-run",
        "auto_execute": True,
    },
    {
        "key": "service_scan",
        "aliases": ["service", "services", "explore-services"],
        "title": "Read-only scan of Hiworks business service surfaces",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks service <name|all>",
        "auto_execute": True,
    },
    {
        "key": "action_catalog",
        "aliases": ["actions", "action-catalog"],
        "title": "Build input/button catalog for all Hiworks service sections",
        "risk": "read",
        "command": "python scripts/entry/cdp_cli.py hiworks actions <name|all>",
        "auto_execute": True,
    },
    {
        "key": "prepare_section",
        "aliases": ["prepare-section", "section-prepare"],
        "title": "Prepare explicit values for a Hiworks section without submit",
        "risk": "prepare",
        "command": "python scripts/entry/cdp_cli.py hiworks prepare-section <name|all> [--values=path]",
        "auto_execute": True,
    },
    {
        "key": "submit_section",
        "aliases": ["submit-section", "section-submit"],
        "title": "Approval-gated Hiworks section submit execution",
        "risk": "send",
        "command": "python scripts/entry/cdp_cli.py hiworks submit-section <name> <control_id> --approved --confirm=HIWORKS_APPROVED_SUBMIT",
        "auto_execute": False,
    },
]


def workflow_for_alias(alias: str) -> dict[str, Any] | None:
    normalized = alias.strip().lower()
    for workflow in WORKFLOWS:
        values = [workflow["key"], *(workflow.get("aliases") or [])]
        if normalized in {str(value).lower() for value in values}:
            return dict(workflow)
    return None
