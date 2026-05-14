"""Hiworks risk gate helpers."""
from __future__ import annotations

from scripts.gate import check as gate_check


def check_read() -> None:
    gate_check("scan_page")


def check_prepare() -> None:
    gate_check("type_into")


def check_send(*, force: bool = False, **metadata) -> None:
    gate_check("mail_send", force=force, context="Hiworks state-changing action", **metadata)
