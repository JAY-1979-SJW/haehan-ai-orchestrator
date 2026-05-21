"""LIVE_PUBLIC_WS_FROM_USER_IP_01 audit."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LiveWsVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN_KEYS = ("token", "secret", "device_token", "registration_code",
                   "authorization", "cookie", "session=", "x-api-key")


def _find_leaks(text: str) -> list[str]:
    low = (text or "").lower()
    return [k for k in _FORBIDDEN_KEYS if k in low]


def judge_live_ws(report: dict,
                  *, external_ip_confirmed: bool = False
                  ) -> LiveWsVerdict:
    steps = (report or {}).get("steps", {})
    metrics = {
        "external_ip_confirmed": external_ip_confirmed,
    }

    # 0) registration_code 로드
    rc = steps.get("00_regcode_loaded", {})
    if not rc.get("ok"):
        return LiveWsVerdict(False, "FAIL_REGISTER_WITH_CODE_BLOCKED",
                             reasons=["registration_code not loaded"],
                             metrics=metrics)

    # 1) register-with-code
    s1 = steps.get("01_register_with_code", {})
    metrics["register_status"] = s1.get("status")
    metrics["register_ok"] = s1.get("ok", False)
    if not s1.get("ok"):
        return LiveWsVerdict(False, "FAIL_REGISTER_WITH_CODE_BLOCKED",
                             reasons=[f"status={s1.get('status')} "
                                      f"err={s1.get('error', '')}"],
                             metrics=metrics)

    # 2) WS auth_ok
    s2 = steps.get("02_ws_auth_ok", {})
    metrics["ws_auth_ok"] = s2.get("ok", False)
    metrics["auth_steps"] = s2.get("steps", [])
    if not s2.get("ok"):
        if "ws_open" not in s2.get("steps", []):
            return LiveWsVerdict(False, "FAIL_WS_PUBLIC_BLOCKED",
                                 reasons=["WS open failed"], metrics=metrics)
        return LiveWsVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=[f"auth flow incomplete: "
                                      f"{s2.get('steps')}"],
                             metrics=metrics)
    if "auth_ok" not in s2.get("steps", []):
        return LiveWsVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=["auth_ok not received"],
                             metrics=metrics)

    # heartbeat check
    hb_steps = [s for s in s2.get("steps", []) if s.startswith("hb_")
                and "heartbeat_ack" in s]
    metrics["heartbeat_ack_count"] = len(hb_steps)
    if not hb_steps:
        return LiveWsVerdict(False, "FAIL_HEARTBEAT_BROKEN",
                             reasons=["no heartbeat_ack"],
                             metrics=metrics)

    # 3) reconnect
    s3 = steps.get("03_reconnect_same_token", {})
    metrics["reconnect_ok"] = s3.get("ok", False)
    if not s3.get("ok"):
        return LiveWsVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=[f"reconnect failed: {s3.get('steps')}"],
                             metrics=metrics)

    # 4) bad token → 4401
    s4 = steps.get("04_bad_token", {})
    bad_err = s4.get("error", "")
    metrics["bad_token_4401_signal"] = "4401" in bad_err
    if "4401" not in bad_err:
        # 일부 클라이언트는 4401 코드 대신 close 만 받음 — 단, auth_ok 받으면 안 됨
        if s4.get("auth_response_type") == "auth_ok":
            return LiveWsVerdict(False, "FAIL_BAD_TOKEN_ACCEPTED",
                                 reasons=["bad token returned auth_ok"],
                                 metrics=metrics)
        # close 없이 그냥 끝났을 가능성 → FAIL
        return LiveWsVerdict(False, "FAIL_WS_AUTH_BROKEN",
                             reasons=[f"bad token close signal missing: "
                                      f"{s4}"],
                             metrics=metrics)

    # 5) admin endpoint 보호 — 이 테스트는 allowed IP 에서 수행되므로
    #    nginx config 검증으로 보장 (deploy audit 단계). 본 단계는 정보용.
    s5 = steps.get("05_admin_endpoints_from_allowed_ip", {})
    metrics["admin_list_status_from_allowed_ip"] = s5.get("list_status")

    # 6) device_token / registration_code leak self-check
    body_text = json.dumps(report, ensure_ascii=False)
    # 정확 매칭으로 hash/mask 가 아닌 원문이 있는지
    if (re.search(r'"device_token"\s*:\s*"[^"]{8,}"', body_text)
            or re.search(r'"registration_code"\s*:\s*"[^"]{8,}"', body_text)):
        return LiveWsVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                             reasons=["device_token/registration_code raw value in report"],
                             metrics=metrics)

    # 7) 사용자 진단 메시지
    s6 = steps.get("06_user_diagnostics", {})
    metrics["has_user_diagnostics"] = bool(s6.get("connected_block")
                                            and s6.get("auth_failed_block"))

    # 환경 제약 — 진짜 외부 IP 가 아니면 WARN
    if not external_ip_confirmed:
        return LiveWsVerdict(False, "WARN_EXTERNAL_TEST_ENV_LIMITED",
                             reasons=["test source IP is in allowlist — "
                                      "could not verify external-IP path explicitly"],
                             metrics=metrics)

    return LiveWsVerdict(True, "PASS_LIVE_PUBLIC_WS_FROM_USER_IP",
                         reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    ap.add_argument("--external-ip-confirmed", type=int, default=0)
    args = ap.parse_args(argv)
    rep = json.loads(args.report_json.read_text(encoding="utf-8"))
    v = judge_live_ws(rep, external_ip_confirmed=bool(args.external_ip_confirmed))
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
