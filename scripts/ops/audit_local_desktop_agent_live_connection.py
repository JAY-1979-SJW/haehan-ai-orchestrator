"""LOCAL-DESKTOP-AGENT-LIVE-INSTALL-CONNECTION-SMOKE-01 audit."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LiveVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def judge_live(
    *,
    e2e_results: dict | None = None,
    token_leak_detected: bool = False,
    nginx_ok: bool = True,
    uses_orchestrator_prefix: bool = True,
    has_ip_allowlist: bool = False,
    server_matches_local: bool = True,
    url_normalize_all_ok: bool = True,
    installer_packaged: bool = True,
    task_delivery_ok: bool | None = None,
) -> LiveVerdict:
    e2e = dict(e2e_results or {})
    metrics = {
        "e2e": e2e, "token_leak_detected": token_leak_detected,
        "nginx_ok": nginx_ok,
        "uses_orchestrator_prefix": uses_orchestrator_prefix,
        "has_ip_allowlist": has_ip_allowlist,
        "server_matches_local": server_matches_local,
        "url_normalize_all_ok": url_normalize_all_ok,
        "installer_packaged": installer_packaged,
        "task_delivery_ok": task_delivery_ok,
    }

    if token_leak_detected:
        return LiveVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                           reasons=["secret in diagnostics output"],
                           metrics=metrics)

    if not url_normalize_all_ok:
        return LiveVerdict(False, "FAIL_WSS_URL_BROKEN",
                           reasons=["ws URL normalize round-trip mismatch"],
                           metrics=metrics)

    if nginx_ok is False:
        return LiveVerdict(False, "FAIL_WS_PROXY_BROKEN",
                           reasons=["nginx Upgrade/Connection missing"],
                           metrics=metrics)

    if e2e.get("register_ok") is False:
        return LiveVerdict(False, "FAIL_REGISTRATION_LIVE_BROKEN",
                           reasons=["register_with_code failed"],
                           metrics=metrics)
    if e2e.get("auth_ok") is False:
        return LiveVerdict(False, "FAIL_REGISTRATION_LIVE_BROKEN",
                           reasons=["authenticate_agent failed"],
                           metrics=metrics)
    if e2e.get("heartbeat_ok") is False:
        return LiveVerdict(False, "FAIL_HEARTBEAT_LIVE_BROKEN",
                           reasons=["heartbeat path broken"],
                           metrics=metrics)
    if task_delivery_ok is False:
        return LiveVerdict(False, "FAIL_TASK_DELIVERY_BROKEN",
                           reasons=["server→agent delivery broken"],
                           metrics=metrics)

    if e2e.get("token_not_stored_raw") is False:
        return LiveVerdict(False, "FAIL_DESKTOP_TOKEN_STORE_BROKEN",
                           reasons=["device_token stored in raw form"],
                           metrics=metrics)

    if not server_matches_local:
        return LiveVerdict(False, "WARN_SERVER_NOT_UPDATED",
                           reasons=["deployed HEAD != local HEAD"],
                           metrics=metrics)
    if not nginx_ok:
        return LiveVerdict(False, "WARN_PROXY_CONFIG_UNVERIFIED",
                           reasons=["nginx config not inspected"],
                           metrics=metrics)
    if not installer_packaged:
        return LiveVerdict(False, "WARN_INSTALLER_NOT_PACKAGED",
                           reasons=["desktop installer not packaged"],
                           metrics=metrics)

    return LiveVerdict(True, "PASS_LOCAL_DESKTOP_AGENT_LIVE_CONNECTION",
                       reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("smoke_report_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.smoke_report_json.read_text(encoding="utf-8"))
    ai = d.get("audit_input", {})
    v = judge_live(
        e2e_results=ai.get("e2e_results"),
        token_leak_detected=ai.get("token_leak_detected", False),
        nginx_ok=ai.get("nginx_ok", True),
        uses_orchestrator_prefix=ai.get("uses_orchestrator_prefix", True),
        has_ip_allowlist=ai.get("has_ip_allowlist", False),
        server_matches_local=ai.get("server_matches_local", True),
        url_normalize_all_ok=ai.get("url_normalize_all_ok", True),
        installer_packaged=ai.get("installer_packaged", True),
        task_delivery_ok=ai.get("task_delivery_ok"),
    )
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
