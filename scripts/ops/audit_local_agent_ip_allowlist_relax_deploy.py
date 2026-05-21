"""IP_ALLOWLIST_RELAX_DEPLOY_01 audit — nginx 변경 적용 후 검증."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DeployVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


PUBLIC_EXACT_PATHS = (
    "/orchestrator/api/v1/local-agents/register-with-code",
    "/orchestrator/api/v1/local-agents/ws",
)

PROTECTED_PREFIX = "/orchestrator/api/v1/local-agents/"
PROTECTED_ADMIN_PATHS = (
    "/orchestrator/api/v1/local-agents/registration-codes",
    "/orchestrator/admin-web/",
)


def _find_location_block(nginx_text: str, location_signature: str) -> str:
    """nginx config 에서 특정 location 블록 본문 추출."""
    pat = re.compile(
        re.escape(location_signature) + r"\s*\{(.*?)^\s*\}",
        re.DOTALL | re.MULTILINE,
    )
    m = pat.search(nginx_text)
    return m.group(1) if m else ""


def judge_deploy(*,
                 nginx_config_text: str = "",
                 nginx_syntax_ok: bool = True,
                 health_status: int = 200,
                 e2e_results: dict | None = None,
                 backup_path: str = "",
                 token_leak_detected: bool = False,
                 external_smoke_available: bool = False,
                 ) -> DeployVerdict:
    e2e = dict(e2e_results or {})
    metrics = {
        "nginx_syntax_ok": nginx_syntax_ok,
        "health_status": health_status,
        "e2e": e2e,
        "backup_path": backup_path,
        "token_leak_detected": token_leak_detected,
        "external_smoke_available": external_smoke_available,
    }

    # FAIL_DEVICE_TOKEN_LEAK
    if token_leak_detected:
        return DeployVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                             reasons=["token leak in output"],
                             metrics=metrics)

    # FAIL_ROLLBACK_BACKUP_MISSING
    if not backup_path:
        return DeployVerdict(False, "FAIL_ROLLBACK_BACKUP_MISSING",
                             reasons=["backup path empty"], metrics=metrics)

    # FAIL_NGINX_SYNTAX_FAILED
    if not nginx_syntax_ok:
        return DeployVerdict(False, "FAIL_NGINX_SYNTAX_FAILED",
                             reasons=["nginx -t failed"], metrics=metrics)

    if not nginx_config_text:
        return DeployVerdict(False, "FAIL_NGINX_SYNTAX_FAILED",
                             reasons=["nginx config not provided"],
                             metrics=metrics)

    # 공개 endpoint location 존재 확인
    for path in PUBLIC_EXACT_PATHS:
        block = _find_location_block(nginx_config_text, f"location = {path}")
        if not block:
            if "register-with-code" in path:
                return DeployVerdict(False, "FAIL_REGISTER_WITH_CODE_BLOCKED",
                                     reasons=[f"public location missing: {path}"],
                                     metrics=metrics)
            else:
                return DeployVerdict(False, "FAIL_WS_BLOCKED",
                                     reasons=[f"public location missing: {path}"],
                                     metrics=metrics)
        # 공개 location 안에 allow/deny 가 없어야 함 (IP allowlist 제거)
        if re.search(r"^\s*allow\s+\d", block, re.MULTILINE):
            return DeployVerdict(False, "FAIL_ADMIN_ENDPOINT_PUBLIC",
                                 reasons=[f"public location {path} 안에 allow 지시어 잔존"],
                                 metrics=metrics)

    # WebSocket Upgrade 헤더 유지 확인
    ws_block = _find_location_block(
        nginx_config_text,
        "location = /orchestrator/api/v1/local-agents/ws",
    )
    if not ("Upgrade" in ws_block and "$http_upgrade" in ws_block):
        return DeployVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=["WS Upgrade header missing in public ws block"],
                             metrics=metrics)
    if not re.search(r'Connection\s+"upgrade"', ws_block):
        return DeployVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=["Connection \"upgrade\" missing"],
                             metrics=metrics)

    # PROTECTED prefix 가 allow 지시어 유지하는지
    prefix_block = _find_location_block(
        nginx_config_text,
        f"location {PROTECTED_PREFIX}",
    )
    if not prefix_block:
        return DeployVerdict(False, "FAIL_ADMIN_ENDPOINT_PUBLIC",
                             reasons=[f"protected prefix block missing: {PROTECTED_PREFIX}"],
                             metrics=metrics)
    if not re.search(r"^\s*allow\s+\d", prefix_block, re.MULTILINE):
        return DeployVerdict(False, "FAIL_ADMIN_ENDPOINT_PUBLIC",
                             reasons=["protected prefix has no allow directives"],
                             metrics=metrics)
    if not re.search(r"^\s*deny\s+all", prefix_block, re.MULTILINE):
        return DeployVerdict(False, "FAIL_ADMIN_ENDPOINT_PUBLIC",
                             reasons=["protected prefix has no deny all"],
                             metrics=metrics)

    # health
    if health_status != 200:
        return DeployVerdict(False, "FAIL_NGINX_SYNTAX_FAILED",
                             reasons=[f"health={health_status}"],
                             metrics=metrics)

    # E2E
    if e2e.get("auth") is False:
        return DeployVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=["authenticate_agent failed in container"],
                             metrics=metrics)
    if e2e.get("bad4401") is False:
        return DeployVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=["bad token did not return 4401"],
                             metrics=metrics)
    if e2e.get("register") is False:
        return DeployVerdict(False, "FAIL_REGISTER_WITH_CODE_BLOCKED",
                             reasons=["register_agent failed"], metrics=metrics)

    # 모든 FAIL 통과
    if not external_smoke_available:
        return DeployVerdict(False, "WARN_EXTERNAL_IP_SMOKE_NOT_AVAILABLE",
                             reasons=["external IP smoke not performed"],
                             metrics=metrics)

    return DeployVerdict(True, "PASS_IP_ALLOWLIST_RELAX_DEPLOY",
                         reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("nginx_config_text_file", type=Path)
    ap.add_argument("--syntax-ok", type=int, default=1)
    ap.add_argument("--health", type=int, default=200)
    ap.add_argument("--backup", default="")
    ap.add_argument("--external-smoke", type=int, default=0)
    ap.add_argument("--e2e-json", type=Path, default=None)
    args = ap.parse_args(argv)
    cfg = args.nginx_config_text_file.read_text(encoding="utf-8")
    e2e = {}
    if args.e2e_json and args.e2e_json.exists():
        e2e = json.loads(args.e2e_json.read_text(encoding="utf-8"))
    v = judge_deploy(
        nginx_config_text=cfg,
        nginx_syntax_ok=bool(args.syntax_ok),
        health_status=args.health,
        e2e_results=e2e,
        backup_path=args.backup,
        external_smoke_available=bool(args.external_smoke),
    )
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
