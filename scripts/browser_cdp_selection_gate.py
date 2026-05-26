"""CDP discovery and domain ownership selection gate.

The gate does not launch or close browsers. It only inspects running CDP
endpoints, selects a session for a task domain, and blocks mixed ownership.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS = tuple(range(9222, 9231))

CODE_OK = "ok"
CODE_NO_CDP = "no_cdp_sessions"
CODE_NO_DOMAIN_SESSION = "no_domain_session"
CODE_MIXED_DOMAIN_SESSION = "mixed_domain_session"
CODE_AMBIGUOUS_DOMAIN_SESSION = "ambiguous_domain_session"
CODE_UNKNOWN_TASK = "unknown_task"

TASK_DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "naver": ("naver.com", "pstatic.net"),
    "youtube": ("youtube.com", "youtu.be", "googlevideo.com"),
    "google": ("google.com", "google.co.kr", "gstatic.com", "googleapis.com"),
}

CONFLICT_DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "naver": ("youtube", "google"),
    "youtube": ("naver",),
    "google": ("naver",),
}


@dataclass
class CdpPage:
    url: str
    title: str = ""

    @property
    def host(self) -> str:
        try:
            return (urllib.parse.urlparse(self.url).hostname or "").lower()
        except Exception:
            return ""


@dataclass
class CdpSession:
    host: str
    port: int
    pages: list[CdpPage] = field(default_factory=list)

    @property
    def endpoint(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def urls(self) -> list[str]:
        return [page.url for page in self.pages]


@dataclass
class SelectionReport:
    ok: bool
    code: str
    task: str
    selected_port: int | None = None
    selected_endpoint: str = ""
    messages: list[str] = field(default_factory=list)
    sessions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "task": self.task,
            "selected_port": self.selected_port,
            "selected_endpoint": self.selected_endpoint,
            "messages": self.messages,
            "sessions": self.sessions,
        }


def _host_matches(host: str, suffixes: Iterable[str]) -> bool:
    clean = host.lower().strip(".")
    return any(clean == suffix or clean.endswith("." + suffix) for suffix in suffixes)


def session_domain_groups(session: CdpSession) -> set[str]:
    groups: set[str] = set()
    for page in session.pages:
        host = page.host
        if not host:
            continue
        for group, suffixes in TASK_DOMAIN_GROUPS.items():
            if _host_matches(host, suffixes):
                groups.add(group)
    return groups


def _session_summary(session: CdpSession) -> dict[str, Any]:
    return {
        "endpoint": session.endpoint,
        "port": session.port,
        "domain_groups": sorted(session_domain_groups(session)),
        "pages": [{"url": page.url, "title": page.title} for page in session.pages],
    }


def evaluate_sessions(task: str, sessions: Iterable[CdpSession]) -> SelectionReport:
    task_key = task.strip().lower()
    all_sessions = list(sessions)
    summaries = [_session_summary(session) for session in all_sessions]
    if task_key not in TASK_DOMAIN_GROUPS:
        return SelectionReport(
            ok=False,
            code=CODE_UNKNOWN_TASK,
            task=task_key,
            messages=[f"Unknown CDP task domain: {task_key}"],
            sessions=summaries,
        )
    if not all_sessions:
        return SelectionReport(
            ok=False,
            code=CODE_NO_CDP,
            task=task_key,
            messages=["No running CDP sessions were discovered."],
            sessions=[],
        )

    conflict_groups = set(CONFLICT_DOMAIN_GROUPS.get(task_key, ()))
    candidates: list[CdpSession] = []
    mixed: list[CdpSession] = []
    for session in all_sessions:
        groups = session_domain_groups(session)
        if task_key not in groups:
            continue
        if groups & conflict_groups:
            mixed.append(session)
        else:
            candidates.append(session)

    if mixed:
        return SelectionReport(
            ok=False,
            code=CODE_MIXED_DOMAIN_SESSION,
            task=task_key,
            messages=[f"{task_key} tabs are mixed with conflicting task domains in the same CDP session."],
            sessions=summaries,
        )
    if len(candidates) > 1:
        return SelectionReport(
            ok=False,
            code=CODE_AMBIGUOUS_DOMAIN_SESSION,
            task=task_key,
            messages=[f"Multiple {task_key} CDP sessions found; choose one explicitly."],
            sessions=summaries,
        )
    if len(candidates) == 1:
        selected = candidates[0]
        return SelectionReport(
            ok=True,
            code=CODE_OK,
            task=task_key,
            selected_port=selected.port,
            selected_endpoint=selected.endpoint,
            messages=[f"Selected {task_key} CDP session by open tab domain."],
            sessions=summaries,
        )

    return SelectionReport(
        ok=False,
        code=CODE_NO_DOMAIN_SESSION,
        task=task_key,
        messages=[f"No CDP session with {task_key} tabs was found."],
        sessions=summaries,
    )


def _read_cdp_pages(host: str, port: int, timeout: float) -> list[CdpPage]:
    with urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8") or "[]")
    if not isinstance(payload, list):
        return []
    pages: list[CdpPage] = []
    for row in payload:
        if not isinstance(row, dict) or row.get("type") != "page":
            continue
        pages.append(CdpPage(url=str(row.get("url") or ""), title=str(row.get("title") or "")))
    return pages


def discover_sessions(
    *,
    host: str = DEFAULT_HOST,
    ports: Iterable[int] = DEFAULT_PORTS,
    timeout: float = 0.7,
) -> list[CdpSession]:
    sessions: list[CdpSession] = []
    for port in ports:
        try:
            pages = _read_cdp_pages(host, int(port), timeout)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
            continue
        sessions.append(CdpSession(host=host, port=int(port), pages=pages))
    return sessions


def _parse_ports(raw: str) -> list[int]:
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            out.extend(range(int(start), int(end) + 1))
        else:
            out.append(int(part))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select a running CDP session by task domain.")
    parser.add_argument("--task", required=True, choices=sorted(TASK_DOMAIN_GROUPS))
    parser.add_argument("--host", default=os.environ.get("CDP_DISCOVERY_HOST", DEFAULT_HOST))
    parser.add_argument("--ports", default=os.environ.get("CDP_DISCOVERY_PORTS", "9222-9230"))
    parser.add_argument("--timeout", type=float, default=0.7)
    args = parser.parse_args(argv)

    report = evaluate_sessions(
        args.task,
        discover_sessions(host=args.host, ports=_parse_ports(args.ports), timeout=args.timeout),
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
