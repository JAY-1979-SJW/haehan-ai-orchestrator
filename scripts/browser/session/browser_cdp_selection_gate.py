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
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import websocket  # type: ignore

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORTS = tuple(range(9222, 9234))

CODE_OK = "ok"
CODE_NO_CDP = "no_cdp_sessions"
CODE_NO_DOMAIN_SESSION = "no_domain_session"
CODE_MIXED_DOMAIN_SESSION = "mixed_domain_session"
CODE_AMBIGUOUS_DOMAIN_SESSION = "ambiguous_domain_session"
CODE_UNKNOWN_TASK = "unknown_task"
CODE_TARGET_CREATE_FAILED = "target_create_failed"
CODE_TARGET_CREATE_BLOCKED = "target_create_blocked"
CODE_TAB_LIMIT_EXCEEDED = "tab_limit_exceeded"
CODE_INFRASTRUCTURE_URL_TAB = "infrastructure_url_tab"

TASK_DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "naver": ("naver.com", "pstatic.net"),
    "smartstore": ("sell.smartstore.naver.com", "smartstore.naver.com", "commerce.naver.com"),
    "youtube": ("youtube.com", "youtu.be", "googlevideo.com"),
    "google": ("google.com", "google.co.kr", "gstatic.com", "googleapis.com"),
}

DEFAULT_TASK_TAB_LIMITS: dict[str, int] = {
    "naver": 1,
    "smartstore": 1,
    "youtube": 1,
    "google": 1,
}
DEFAULT_TOTAL_TAB_LIMIT = 6
INFRASTRUCTURE_URL_PATTERNS = (
    "haehan-ai-orchestrator/data/browser_sessions/",
    "haehan-ai-orchestrator/data/cdp_profile/",
)

CONFLICT_DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "naver": ("youtube", "google"),
    "smartstore": ("youtube", "google"),
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
        except Exception:  # noqa: BLE001 - CDP 세션 선택/탭격리 게이트 — host 파싱 실패나 게이트체크·타겟생성 실패 시 전부 ok=False(차단) 결과로 fail-closed 폴백, 허용 방향으로 새는 기본값 없음
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


@dataclass
class TargetIsolationReport:
    ok: bool
    code: str
    task: str
    work: str
    port: int
    target_id: str = ""
    start_url: str = ""
    page: dict[str, Any] = field(default_factory=dict)
    tab_limit: int | None = None
    existing_task_tabs: int = 0
    existing_total_tabs: int = 0
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "task": self.task,
            "work": self.work,
            "port": self.port,
            "target_id": self.target_id,
            "start_url": self.start_url,
            "page": self.page,
            "tab_limit": self.tab_limit,
            "existing_task_tabs": self.existing_task_tabs,
            "existing_total_tabs": self.existing_total_tabs,
            "messages": self.messages,
        }


def _host_matches(host: str, suffixes: Iterable[str]) -> bool:
    clean = host.lower().strip(".")
    return any(clean == suffix or clean.endswith("." + suffix) for suffix in suffixes)


def is_infrastructure_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return any(pattern in lowered for pattern in INFRASTRUCTURE_URL_PATTERNS)


def infrastructure_urls(session: CdpSession) -> list[str]:
    return [page.url for page in session.pages if is_infrastructure_url(page.url)]


def session_domain_groups(session: CdpSession) -> set[str]:
    groups: set[str] = set()
    for page in session.pages:
        host = page.host
        if not host:
            continue
        if _host_matches(host, TASK_DOMAIN_GROUPS["smartstore"]):
            groups.add("smartstore")
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
        "infrastructure_urls": infrastructure_urls(session),
        "pages": [{"url": page.url, "title": page.title} for page in session.pages],
    }


def _classify_sessions(
    task_key: str, all_sessions: list[CdpSession]
) -> tuple[list[CdpSession], list[CdpSession], list[CdpSession], list[tuple[CdpSession, int, int]]]:
    """세션을 (후보, 혼합 도메인, 내부 URL 탭 포함, 탭 한도 초과)로 분류."""
    conflict_groups = set(CONFLICT_DOMAIN_GROUPS.get(task_key, ()))
    candidates: list[CdpSession] = []
    mixed: list[CdpSession] = []
    invalid_infra: list[CdpSession] = []
    tab_limited: list[tuple[CdpSession, int, int]] = []
    for session in all_sessions:
        groups = session_domain_groups(session)
        if task_key not in groups:
            continue
        if infrastructure_urls(session):
            invalid_infra.append(session)
            continue
        task_tab_count = _task_page_count(task_key, session.pages)
        task_tab_limit = _resolve_task_tab_limit(task_key, None)
        if task_tab_limit is not None and task_tab_count > task_tab_limit:
            tab_limited.append((session, task_tab_count, task_tab_limit))
            continue
        if groups & conflict_groups:
            mixed.append(session)
        else:
            candidates.append(session)
    return candidates, mixed, invalid_infra, tab_limited


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

    candidates, mixed, invalid_infra, tab_limited = _classify_sessions(task_key, all_sessions)

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
    if invalid_infra:
        return SelectionReport(
            ok=False,
            code=CODE_INFRASTRUCTURE_URL_TAB,
            task=task_key,
            messages=[
                f"{task_key} CDP session contains internal profile/data URL tabs. Close those tabs or reuse a clean domain tab before running background work.",
            ],
            sessions=summaries,
        )
    if tab_limited:
        details = ", ".join(f"port {session.port}: {count}/{limit}" for session, count, limit in tab_limited)
        return SelectionReport(
            ok=False,
            code=CODE_TAB_LIMIT_EXCEEDED,
            task=task_key,
            messages=[
                f"{task_key} CDP session has too many task-domain tabs ({details}). Reuse one tab or clean up duplicates before running work.",
            ],
            sessions=summaries,
        )
    if mixed:
        return SelectionReport(
            ok=False,
            code=CODE_MIXED_DOMAIN_SESSION,
            task=task_key,
            messages=[f"{task_key} tabs are mixed with conflicting task domains in the same CDP session."],
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


def _read_cdp_page_dicts(host: str, port: int, timeout: float = 2.0) -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"http://{host}:{port}/json/list", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8") or "[]")
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict) and row.get("type") == "page"]


def _page_dict_to_cdp_page(row: dict[str, Any]) -> CdpPage:
    return CdpPage(url=str(row.get("url") or ""), title=str(row.get("title") or ""))


def _task_page_count(task: str, pages: Iterable[CdpPage]) -> int:
    task_key = task.strip().lower()
    suffixes = TASK_DOMAIN_GROUPS.get(task_key, ())
    count = 0
    for page in pages:
        host = page.host
        if not host:
            continue
        is_smartstore = _host_matches(host, TASK_DOMAIN_GROUPS["smartstore"])
        if task_key == "smartstore":
            count += int(is_smartstore)
            continue
        if is_smartstore:
            continue
        count += int(_host_matches(host, suffixes))
    return count


def _resolve_task_tab_limit(task: str, max_task_tabs: int | None) -> int | None:
    if max_task_tabs is not None:
        return max_task_tabs
    raw = os.environ.get(f"CDP_MAX_{task.strip().upper()}_TABS", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_TASK_TAB_LIMITS.get(task.strip().lower(), 1)


def _resolve_total_tab_limit(max_total_tabs: int | None) -> int | None:
    if max_total_tabs is not None:
        return max_total_tabs
    raw = os.environ.get("CDP_MAX_TOTAL_TABS", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_TOTAL_TAB_LIMIT


def _read_browser_ws_url(host: str, port: int, timeout: float = 2.0) -> str:
    with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8") or "{}")
    return str(payload.get("webSocketDebuggerUrl") or "")


def _send_browser_cdp(
    browser_ws_url: str, method: str, params: dict[str, Any], *, timeout: float = 5.0
) -> dict[str, Any]:
    ws = websocket.create_connection(browser_ws_url, timeout=timeout)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params}))
        ws.settimeout(timeout)
        while True:
            raw = ws.recv()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("id") == 1:
                return event if isinstance(event, dict) else {}
    finally:
        ws.close()


def create_isolated_target(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    *,
    task: str,
    work: str,
    port: int,
    start_url: str,
    host: str = DEFAULT_HOST,
    timeout: float = 5.0,
    max_task_tabs: int | None = None,
    max_total_tabs: int | None = None,
    allow_create: bool | None = None,
) -> TargetIsolationReport:
    """Create a dedicated tab in an existing CDP browser session.

    This is the common tab-isolation gate for parallel browser work. It never
    launches, restarts, or closes a browser. Creating a new CDP target is
    blocked by default so audits/tests cannot open visible tabs by accident.
    Live callers must pass allow_create=True or set
    HAEHAN_CDP_CREATE_TARGET_ALLOWED=1.
    """
    try:
        from scripts.common.gate import check as gate_check

        gate_check("cdp_nav", context="cdp_tab_isolation", task=task, work=work, port=port)
    except Exception as exc:  # noqa: BLE001 - CDP 세션 선택/탭격리 게이트 — host 파싱 실패나 게이트체크·타겟생성 실패 시 전부 ok=False(차단) 결과로 fail-closed 폴백, 허용 방향으로 새는 기본값 없음
        return TargetIsolationReport(
            ok=False,
            code="tab_isolation_gate_blocked",
            task=task,
            work=work,
            port=port,
            start_url=start_url,
            messages=[str(exc)],
        )

    task_key = task.strip().lower()
    tab_limit = _resolve_task_tab_limit(task_key, max_task_tabs)
    total_tab_limit = _resolve_total_tab_limit(max_total_tabs)
    if allow_create is None:
        allow_create = os.environ.get("HAEHAN_CDP_CREATE_TARGET_ALLOWED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
    try:
        current_page_dicts = _read_cdp_page_dicts(host, port, timeout=min(timeout, 2.0))
        current_pages = [_page_dict_to_cdp_page(row) for row in current_page_dicts]
        existing_task_tabs = _task_page_count(task_key, current_pages)
        existing_total_tabs = len(current_page_dicts)
        if tab_limit is not None and existing_task_tabs >= tab_limit:
            return TargetIsolationReport(
                ok=False,
                code=CODE_TAB_LIMIT_EXCEEDED,
                task=task_key,
                work=work,
                port=port,
                start_url=start_url,
                tab_limit=tab_limit,
                existing_task_tabs=existing_task_tabs,
                existing_total_tabs=existing_total_tabs,
                messages=[
                    f"{task_key} already has {existing_task_tabs} tab(s) in this CDP browser; max allowed is {tab_limit}. Reuse the existing tab instead of creating another.",
                ],
            )
        if total_tab_limit is not None and existing_total_tabs >= total_tab_limit:
            return TargetIsolationReport(
                ok=False,
                code=CODE_TAB_LIMIT_EXCEEDED,
                task=task_key,
                work=work,
                port=port,
                start_url=start_url,
                tab_limit=tab_limit,
                existing_task_tabs=existing_task_tabs,
                existing_total_tabs=existing_total_tabs,
                messages=[
                    f"CDP browser already has {existing_total_tabs} page tab(s); max total allowed is {total_tab_limit}. Reuse an existing task tab or clean up surplus tabs before creating another.",
                ],
            )
        if not allow_create:
            return TargetIsolationReport(
                ok=False,
                code=CODE_TARGET_CREATE_BLOCKED,
                task=task_key,
                work=work,
                port=port,
                start_url=start_url,
                tab_limit=tab_limit,
                existing_task_tabs=existing_task_tabs,
                existing_total_tabs=existing_total_tabs,
                messages=[
                    "CDP target creation is blocked by default. Pass allow_create=True only for an approved live task.",
                ],
            )
        browser_ws_url = _read_browser_ws_url(host, port, timeout=min(timeout, 2.0))
        if not browser_ws_url:
            raise RuntimeError("browser_websocket_url_missing")
        event = _send_browser_cdp(
            browser_ws_url,
            "Target.createTarget",
            {"url": start_url},
            timeout=timeout,
        )
        target_id = str((event.get("result") or {}).get("targetId") or "")
        if not target_id:
            raise RuntimeError("target_id_missing")
        page = next((row for row in _read_cdp_page_dicts(host, port, timeout=2.0) if row.get("id") == target_id), {})
        return TargetIsolationReport(
            ok=True,
            code=CODE_OK,
            task=task,
            work=work,
            port=port,
            target_id=target_id,
            start_url=start_url,
            page=page,
            tab_limit=tab_limit,
            existing_task_tabs=existing_task_tabs,
            existing_total_tabs=existing_total_tabs,
            messages=[
                "Created an isolated tab in the existing CDP session; no browser launch, restart, or close action.",
            ],
        )
    except Exception as exc:  # noqa: BLE001 - CDP 세션 선택/탭격리 게이트 — host 파싱 실패나 게이트체크·타겟생성 실패 시 전부 ok=False(차단) 결과로 fail-closed 폴백, 허용 방향으로 새는 기본값 없음
        return TargetIsolationReport(
            ok=False,
            code=CODE_TARGET_CREATE_FAILED,
            task=task,
            work=work,
            port=port,
            start_url=start_url,
            messages=[str(exc)],
        )


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


def _pick_naver_session_when_readonly_mixed(
    selection: SelectionReport,
    sessions: Iterable[CdpSession],
) -> CdpSession | None:
    """읽기 전용이면 네이버 페이지가 섞여 있는 세션도 허용할 때, 네이버 페이지가 있는 세션을 고른다."""
    if selection.code != CODE_MIXED_DOMAIN_SESSION:
        return None
    for session in sessions:
        if any("naver.com" in page.host for page in session.pages):
            return session
    return None


def select_naver_session(
    *,
    sessions: Iterable[CdpSession] | None = None,
    allow_mixed_readonly: bool = False,
) -> tuple[CdpSession | None, SelectionReport]:
    """네이버 작업에 쓸 CDP 세션을 고른다(카페·메일 백그라운드 러너 공용 — 예전엔 두 러너에 복사돼 있었다)."""
    discovered = list(sessions) if sessions is not None else discover_sessions()
    selection = evaluate_sessions("naver", discovered)
    if selection.ok and selection.selected_port is not None:
        for session in discovered:
            if session.port == selection.selected_port:
                return session, selection
    if allow_mixed_readonly:
        mixed_session = _pick_naver_session_when_readonly_mixed(selection, discovered)
        if mixed_session is not None:
            return mixed_session, selection
    return None, selection


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
