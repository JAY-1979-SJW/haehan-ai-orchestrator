from __future__ import annotations

from scripts.google import router as google_router


def test_google_router_delegates_workspace_tasks(monkeypatch) -> None:
    calls: list[tuple[str, str, list[str]]] = []
    gate_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        google_router,
        "gate_check",
        lambda action, risk="auto": gate_calls.append((action, risk)),
    )
    monkeypatch.setattr(
        google_router.workspace_router,
        "run_workspace",
        lambda service, task, args: calls.append((service, task, args)),
    )

    google_router.run_google("google", "mail", "list", ["inbox"])
    google_router.run_google("google", "drive", "list", [])
    google_router.run_google("google", "calendar", "today", [])
    google_router.run_google("google", "docs", "recent", [])
    google_router.run_google("google", "sheets", "recent", [])

    assert calls == [
        ("gmail", "list", ["inbox"]),
        ("drive", "list", []),
        ("calendar", "today", []),
        ("docs", "recent", []),
        ("sheets", "recent", []),
    ]
    assert gate_calls == [
        ("goto", "auto"),
        ("goto", "auto"),
        ("goto", "auto"),
        ("goto", "auto"),
        ("goto", "auto"),
    ]


def test_google_router_preserves_gmail_alias_and_send_gate(monkeypatch) -> None:
    calls: list[tuple[str, str, list[str]]] = []
    gate_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        google_router,
        "gate_check",
        lambda action, risk="auto": gate_calls.append((action, risk)),
    )
    monkeypatch.setattr(
        google_router.workspace_router,
        "run_workspace",
        lambda service, task, args: calls.append((service, task, args)),
    )

    google_router.run_google("gmail", "", "compose", ["to@example.com", "subject", "body"])

    assert calls == [("gmail", "compose", ["to@example.com", "subject", "body"])]
    assert gate_calls == [("gmail_send", "approve")]
