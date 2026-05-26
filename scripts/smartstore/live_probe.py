"""Attach-only SmartStore login/access probe.

This module never launches, restarts, or closes a browser. It discovers an
already-running CDP endpoint, creates an isolated Naver tab, and reads page
signals from SmartStore Center.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import websocket  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser_cdp_selection_gate import (  # noqa: E402
    CODE_MIXED_DOMAIN_SESSION,
    CdpSession,
    SelectionReport,
    create_isolated_target,
    discover_sessions,
    evaluate_sessions,
)
from scripts.naver.mail_read import cdp  # noqa: E402

DASHBOARD_URL = "https://sell.smartstore.naver.com/#/home/dashboard"
SMARTSTORE_SESSION_HOST = "sell.smartstore.naver.com"
LATEST_PROBE_PATH = ROOT / "data" / "smartstore_live_probe_latest.json"
SESSIONS_DIR = ROOT / "data" / "sessions"


@dataclass
class SmartStoreProbeReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    host: str = ""
    title: str = ""
    logged_in: bool = False
    smartstore_accessible: bool = False
    login_required: bool = False
    challenge_detected: bool = False
    blank_dashboard: bool = False
    body_length: int = 0
    markers: dict[str, bool] = field(default_factory=dict)
    body_sample: str = ""
    session_saved: bool = False
    session_file: str = ""
    session_cookie_count: int = 0
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)
    isolation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SmartStoreLoginWatchReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    elapsed_s: int = 0
    checks: int = 0
    logged_in: bool = False
    session_saved: bool = False
    session_file: str = ""
    session_cookie_count: int = 0
    last_verdict: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pick_naver_session_when_readonly_mixed(
    selection: SelectionReport,
    sessions: Iterable[CdpSession],
) -> CdpSession | None:
    if selection.code != CODE_MIXED_DOMAIN_SESSION:
        return None
    for session in sessions:
        if any("naver.com" in page.host for page in session.pages):
            return session
    return None


def select_smartstore_session(
    *,
    sessions: Iterable[CdpSession] | None = None,
    allow_mixed_readonly: bool = False,
) -> tuple[CdpSession | None, SelectionReport]:
    discovered = list(sessions) if sessions is not None else discover_sessions()
    selection = evaluate_sessions("smartstore", discovered)
    if selection.ok and selection.selected_port is not None:
        for session in discovered:
            if session.port == selection.selected_port:
                return session, selection
    if allow_mixed_readonly:
        mixed_session = _pick_smartstore_session_when_readonly_mixed(selection, discovered)
        if mixed_session is not None:
            return mixed_session, selection
    return None, selection


def _pick_smartstore_session_when_readonly_mixed(
    selection: SelectionReport,
    sessions: Iterable[CdpSession],
) -> CdpSession | None:
    if selection.code != CODE_MIXED_DOMAIN_SESSION:
        return None
    for session in sessions:
        if any(page.host in {SMARTSTORE_SESSION_HOST, "smartstore.naver.com"} for page in session.pages):
            return session
    return None


PAGE_SIGNAL_EXPR = r"""JSON.stringify((() => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const body = clean(document.body ? document.body.innerText : '');
  const href = String(location.href || '');
  const host = String(location.host || '').toLowerCase();
  const title = String(document.title || '');
  const combined = `${href} ${title} ${body}`;
  const markers = {
    naverLogin: /nid\.naver\.com|로그인|아이디|비밀번호|sign in/i.test(combined),
    logout: /로그아웃|logout|sign out/i.test(combined),
    accountUser: /[A-Za-z0-9_.-]{2,}\s*님|내정보|마이비즈/i.test(combined),
    storeNavigation: /상품관리|판매관리|정산관리|문의\/리뷰관리|스토어관리/i.test(combined),
    smartstore: /스마트스토어|스마트스토어센터|상품관리|판매관리|정산관리|문의\/리뷰관리|스토어/i.test(combined),
    sellerCenter: /sell\.smartstore\.naver\.com|판매자|센터/i.test(combined),
    challenge: /보안|captcha|자동입력|로봇|인증번호|비정상|차단/i.test(combined),
    permission: /권한|접근할 수|가입|판매자 가입|사업자/i.test(combined)
  };
  return {
    href,
    host,
    title,
    readyState: document.readyState,
    markers,
    bodyLength: body.length,
    hasVisibleBody: body.length > 20,
    bodySample: body.slice(0, 2000)
  };
})())"""


def classify_probe(raw: dict[str, Any]) -> dict[str, Any]:
    href = str(raw.get("href") or "")
    host = str(raw.get("host") or "").lower()
    title = str(raw.get("title") or "")
    markers = raw.get("markers") if isinstance(raw.get("markers"), dict) else {}
    body_sample = str(raw.get("bodySample") or "")
    body_length = int(raw.get("bodyLength") or len(body_sample))

    on_login_host = "nid.naver.com" in host or "nid.naver.com" in href
    smartstore_host = "sell.smartstore.naver.com" in host or "sell.smartstore.naver.com" in href
    visible_smartstore_evidence = bool(markers.get("smartstore") and body_length > 20)
    logged_in_evidence = bool(markers.get("logout") or markers.get("accountUser") or markers.get("storeNavigation"))
    smartstore_accessible = bool(smartstore_host and visible_smartstore_evidence)
    public_landing = "/home/about" in href or "/#/home/about" in href
    blank_dashboard = bool(smartstore_host and "/home/dashboard" in href and body_length <= 20)
    login_required = bool(on_login_host or public_landing or (markers.get("naverLogin") and not logged_in_evidence))
    challenge_detected = bool(markers.get("challenge"))
    logged_in = bool(smartstore_accessible and logged_in_evidence and not login_required and not challenge_detected)

    if challenge_detected:
        code = "challenge_detected"
    elif login_required:
        code = "login_required"
    elif blank_dashboard:
        code = "login_unverified_blank_dashboard"
    elif smartstore_accessible:
        code = "smartstore_accessible"
    elif smartstore_host:
        code = "smartstore_loaded_unknown"
    else:
        code = "unexpected_page"

    return {
        "code": code,
        "url": href,
        "host": host,
        "title": title,
        "logged_in": logged_in,
        "smartstore_accessible": smartstore_accessible,
        "login_required": login_required,
        "challenge_detected": challenge_detected,
        "markers": {str(key): bool(value) for key, value in markers.items()},
        "body_length": body_length,
        "blank_dashboard": blank_dashboard,
        "logged_in_evidence": logged_in_evidence,
        "body_sample": body_sample,
    }


def probe_dashboard(
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 6.0,
) -> SmartStoreProbeReport:
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStoreProbeReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    existing_target_id, existing_raw = find_rendered_smartstore_target(port=session.port)
    if existing_target_id and existing_raw:
        verdict = classify_probe(existing_raw)
        session_saved = False
        session_file = ""
        session_cookie_count = 0
        if verdict["logged_in"]:
            saved = save_target_session(existing_target_id, port=session.port)
            session_saved = bool(saved.get("ok"))
            session_file = str(saved.get("path") or "")
            session_cookie_count = int(saved.get("cookie_count") or 0)
        return SmartStoreProbeReport(
            ok=verdict["code"] in {"smartstore_accessible", "login_required", "challenge_detected", "smartstore_loaded_unknown"},
            code=str(verdict["code"]),
            port=session.port,
            target_id=existing_target_id,
            url=str(verdict["url"]),
            host=str(verdict["host"]),
            title=str(verdict["title"]),
            logged_in=bool(verdict["logged_in"]),
            smartstore_accessible=bool(verdict["smartstore_accessible"]),
            login_required=bool(verdict["login_required"]),
            challenge_detected=bool(verdict["challenge_detected"]),
            blank_dashboard=bool(verdict["blank_dashboard"]),
            body_length=int(verdict["body_length"]),
            markers=dict(verdict["markers"]),
            body_sample=str(verdict["body_sample"]),
            session_saved=session_saved,
            session_file=session_file,
            session_cookie_count=session_cookie_count,
            messages=[
                "Reused an existing rendered SmartStore CDP tab; no browser launch, restart, close, submit, or write action.",
            ],
            selection=selection.to_dict(),
        )

    isolation = create_isolated_target(
        task="smartstore",
        work="smartstore:dashboard_probe",
        port=session.port,
        start_url=DASHBOARD_URL,
    )
    if not isolation.ok or not isolation.target_id:
        return SmartStoreProbeReport(
            ok=False,
            code=isolation.code,
            port=session.port,
            messages=list(isolation.messages),
            selection=selection.to_dict(),
            isolation=isolation.to_dict(),
        )

    cdp.navigate(isolation.target_id, DASHBOARD_URL, port=session.port)
    deadline = time.time() + max(1.0, wait_seconds)
    raw: dict[str, Any] = {}
    while time.time() < deadline:
        value = cdp.evaluate(isolation.target_id, PAGE_SIGNAL_EXPR, timeout=5.0, port=session.port)
        if isinstance(value, dict):
            raw = value
            if raw.get("readyState") == "complete" and raw.get("href") != "about:blank":
                break
        time.sleep(0.5)
    if not raw:
        raw = cdp.evaluate(isolation.target_id, PAGE_SIGNAL_EXPR, timeout=5.0, port=session.port) or {}
    if not isinstance(raw, dict):
        raw = {}

    verdict = classify_probe(raw)
    session_saved = False
    session_file = ""
    session_cookie_count = 0
    if verdict["logged_in"]:
        saved = save_target_session(isolation.target_id, port=session.port)
        session_saved = bool(saved.get("ok"))
        session_file = str(saved.get("path") or "")
        session_cookie_count = int(saved.get("cookie_count") or 0)

    return SmartStoreProbeReport(
        ok=verdict["code"] in {"smartstore_accessible", "login_required", "challenge_detected", "smartstore_loaded_unknown"},
        code=str(verdict["code"]),
        port=session.port,
        target_id=isolation.target_id,
        url=str(verdict["url"]),
        host=str(verdict["host"]),
        title=str(verdict["title"]),
        logged_in=bool(verdict["logged_in"]),
        smartstore_accessible=bool(verdict["smartstore_accessible"]),
        login_required=bool(verdict["login_required"]),
        challenge_detected=bool(verdict["challenge_detected"]),
        blank_dashboard=bool(verdict["blank_dashboard"]),
        body_length=int(verdict["body_length"]),
        markers=dict(verdict["markers"]),
        body_sample=str(verdict["body_sample"]),
        session_saved=session_saved,
        session_file=session_file,
        session_cookie_count=session_cookie_count,
        messages=[
            "Created an isolated SmartStore tab in the existing CDP session; no browser launch, restart, close, submit, or write action.",
        ],
        selection=selection.to_dict(),
        isolation=isolation.to_dict(),
    )


def save_probe_report(report: SmartStoreProbeReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_PROBE_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def watch_login_and_save(
    *,
    allow_mixed_readonly: bool = False,
    timeout_seconds: int = 300,
    interval_seconds: float = 1.0,
) -> SmartStoreLoginWatchReport:
    """Watch an existing SmartStore browser tab and save session on login.

    This never receives credentials and never types into the page. The user logs
    in directly in the browser; the agent only observes completion signals and
    saves the SmartStore-scoped session file.
    """
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStoreLoginWatchReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    start = time.time()
    checks = 0
    last_target = ""
    last_verdict: dict[str, Any] = {}
    while time.time() - start <= max(1, timeout_seconds):
        checks += 1
        target_id, raw = find_rendered_smartstore_target(port=session.port)
        if target_id and raw:
            last_target = target_id
            last_verdict = classify_probe(raw)
            if last_verdict.get("logged_in"):
                saved = save_target_session(target_id, port=session.port)
                return SmartStoreLoginWatchReport(
                    ok=bool(saved.get("ok")),
                    code="login_detected_session_saved" if saved.get("ok") else "login_detected_session_save_failed",
                    port=session.port,
                    target_id=target_id,
                    url=str(last_verdict.get("url") or ""),
                    title=str(last_verdict.get("title") or ""),
                    elapsed_s=int(time.time() - start),
                    checks=checks,
                    logged_in=True,
                    session_saved=bool(saved.get("ok")),
                    session_file=str(saved.get("path") or ""),
                    session_cookie_count=int(saved.get("cookie_count") or 0),
                    last_verdict=last_verdict,
                    messages=[
                        "Detected SmartStore login from an existing CDP tab and saved the domain-scoped session.",
                    ],
                    selection=selection.to_dict(),
                )
        time.sleep(max(0.2, interval_seconds))

    return SmartStoreLoginWatchReport(
        ok=False,
        code="login_watch_timeout",
        port=session.port,
        target_id=last_target,
        url=str(last_verdict.get("url") or ""),
        title=str(last_verdict.get("title") or ""),
        elapsed_s=int(time.time() - start),
        checks=checks,
        logged_in=False,
        last_verdict=last_verdict,
        messages=["Timed out waiting for SmartStore login completion."],
        selection=selection.to_dict(),
    )


def find_rendered_smartstore_target(*, port: int) -> tuple[str, dict[str, Any]]:
    """Find an already-open SmartStore tab with usable rendered page evidence."""
    best_target = ""
    best_raw: dict[str, Any] = {}
    best_score = -1
    for page in cdp.list_pages(port=port):
        target_id = str(page.get("id") or "")
        url = str(page.get("url") or "")
        if not target_id or "sell.smartstore.naver.com" not in url:
            continue
        raw = cdp.evaluate(target_id, PAGE_SIGNAL_EXPR, timeout=5.0, port=port)
        if not isinstance(raw, dict):
            continue
        verdict = classify_probe(raw)
        score = int(verdict.get("body_length") or 0)
        if verdict.get("logged_in"):
            score += 100000
        if verdict.get("code") == "login_required":
            score += 1000
        if score > best_score:
            best_score = score
            best_target = target_id
            best_raw = raw
    return best_target, best_raw


def _target_ws_url(target_id: str, *, port: int) -> str:
    for page in cdp.list_pages(port=port):
        if str(page.get("id") or "") == target_id:
            return str(page.get("webSocketDebuggerUrl") or "")
    return ""


def _send_target_cdp(target_id: str, method: str, params: dict[str, Any] | None = None, *, port: int, timeout: float = 8.0) -> dict[str, Any]:
    ws_url = _target_ws_url(target_id, port=port)
    if not ws_url:
        raise RuntimeError("target_websocket_url_missing")
    ws = websocket.create_connection(ws_url, timeout=timeout)
    try:
        return cdp._send(ws, 9001, method, params or {}, timeout=timeout)
    finally:
        ws.close()


def _cookie_applies_to_host(cookie: dict[str, Any], host: str) -> bool:
    domain = str(cookie.get("domain") or "").lstrip(".").lower()
    clean_host = host.lower()
    if not domain:
        return False
    return clean_host == domain or clean_host.endswith("." + domain)


def _capture_storage_from_target(target_id: str, *, port: int) -> dict[str, Any]:
    expr = r"""JSON.stringify((() => {
      const out = {local: {}, session: {}, url: location.href, title: document.title || ''};
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          out.local[k] = localStorage.getItem(k);
        }
      } catch (e) {}
      try {
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          out.session[k] = sessionStorage.getItem(k);
        }
      } catch (e) {}
      return out;
    })())"""
    value = cdp.evaluate(target_id, expr, timeout=8.0, port=port)
    return value if isinstance(value, dict) else {"local": {}, "session": {}, "url": "", "title": ""}


def save_target_session(
    target_id: str,
    *,
    port: int,
    host: str = SMARTSTORE_SESSION_HOST,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Save SmartStore cookies/storage into a SmartStore-specific session file."""
    storage = _capture_storage_from_target(target_id, port=port)
    cookie_event = _send_target_cdp(target_id, "Network.getAllCookies", {}, port=port)
    all_cookies = ((cookie_event.get("result") or {}).get("cookies") or [])
    cookies = [cookie for cookie in all_cookies if isinstance(cookie, dict) and _cookie_applies_to_host(cookie, host)]

    from scripts.auth_session import _encrypt

    bundle = {
        "host": host,
        "site": "smartstore",
        "saved_at": datetime.now().isoformat(),
        "url": storage.get("url") or DASHBOARD_URL,
        "title": str(storage.get("title") or "")[:200],
        "cookies": cookies,
        "localStorage": storage.get("local", {}),
        "sessionStorage": storage.get("session", {}),
    }
    payload = _encrypt(json.dumps(bundle, ensure_ascii=False))

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(output) if output else SESSIONS_DIR / f"{host}.json"
    path.write_text(
        json.dumps(
            {
                "host": host,
                "site": "smartstore",
                "saved_at": bundle["saved_at"],
                "url_host": urlparse(str(bundle["url"])).hostname or "",
                "cookie_count": len(cookies),
                "local_keys": len(bundle["localStorage"]),
                "session_keys": len(bundle["sessionStorage"]),
                "encrypted_bundle": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return {
        "ok": True,
        "path": str(path),
        "host": host,
        "cookie_count": len(cookies),
        "local_keys": len(bundle["localStorage"]),
        "session_keys": len(bundle["sessionStorage"]),
    }


def restore_target_session(
    target_id: str,
    *,
    port: int,
    host: str = SMARTSTORE_SESSION_HOST,
) -> dict[str, Any]:
    """Restore the SmartStore-specific session file into an existing CDP target."""
    from scripts.auth_session import _load_bundle

    bundle = _load_bundle(host)
    if not bundle:
        return {"ok": False, "reason": "no_smartstore_session_saved", "host": host}

    cookies = bundle.get("cookies") or []
    if cookies:
        event = _send_target_cdp(target_id, "Network.setCookies", {"cookies": cookies}, port=port)
        if event.get("error"):
            return {"ok": False, "reason": f"cookie_restore_failed:{event.get('error')}", "host": host}

    cdp.navigate(target_id, DASHBOARD_URL, port=port)
    cdp.wait_dom(target_id, "location.host === 'sell.smartstore.naver.com'", timeout=12.0, port=port)
    storage_expr = json.dumps(
        {
            "local": bundle.get("localStorage") or {},
            "session": bundle.get("sessionStorage") or {},
        },
        ensure_ascii=False,
    )
    cdp.evaluate(
        target_id,
        f"""(() => {{
          const payload = {storage_expr};
          try {{
            for (const [k, v] of Object.entries(payload.local || {{}})) localStorage.setItem(k, v);
            for (const [k, v] of Object.entries(payload.session || {{}})) sessionStorage.setItem(k, v);
          }} catch (e) {{}}
          return true;
        }})()""",
        timeout=8.0,
        port=port,
    )
    cdp.navigate(target_id, DASHBOARD_URL, port=port)
    return {
        "ok": True,
        "host": host,
        "restored_cookies": len(cookies),
        "restored_local": len(bundle.get("localStorage") or {}),
        "restored_session": len(bundle.get("sessionStorage") or {}),
        "saved_at": bundle.get("saved_at"),
    }
