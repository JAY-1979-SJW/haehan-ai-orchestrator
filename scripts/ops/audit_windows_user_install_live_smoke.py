"""WINDOWS_USER_INSTALL_LIVE_SMOKE_01 audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DIST_DIR = Path("dist/HaehanAI-Agent")
DIST_ZIP = Path("dist/HaehanAI-Agent.zip")
EXE = DIST_DIR / "HaehanAI-Agent.exe"
USER_DOC = Path("docs/ops/local_agent_user_install_smoke.md")


@dataclass
class UserInstallVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_TOKEN_PATTERNS = (
    re.compile(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
)


def _has_token_leak(text: str) -> list[str]:
    return [p.pattern for p in _TOKEN_PATTERNS if p.search(text or "")]


def judge_user_install(
    *, smoke_results: dict | None = None, same_machine_test: bool = True, gui_available: bool = False
) -> UserInstallVerdict:
    smoke = dict(smoke_results or {})
    metrics = {
        "dist_dir_exists": DIST_DIR.exists(),
        "dist_zip_exists": DIST_ZIP.exists(),
        "exe_exists": EXE.exists(),
        "user_doc_exists": USER_DOC.exists(),
        "same_machine_test": same_machine_test,
        "gui_available": gui_available,
        "smoke": smoke,
    }

    # FAIL_USER_DOC_MISSING
    if not USER_DOC.exists():
        return UserInstallVerdict(False, "FAIL_USER_DOC_MISSING", reasons=[f"missing: {USER_DOC}"], metrics=metrics)

    # 문서 필수 항목
    doc_text = USER_DOC.read_text(encoding="utf-8")
    for keyword in ("설치", "등록", "재실행", "진단", "오류", "SmartScreen", "재등록", "AUTH_FAILED_4401"):
        if keyword not in doc_text:
            return UserInstallVerdict(
                False, "FAIL_USER_DOC_MISSING", reasons=[f"missing keyword: {keyword}"], metrics=metrics
            )

    # FAIL_ZIP_PACKAGE_MISSING
    if not DIST_ZIP.exists():
        return UserInstallVerdict(
            False, "FAIL_ZIP_PACKAGE_MISSING", reasons=["dist/HaehanAI-Agent.zip not found"], metrics=metrics
        )
    metrics["zip_size_bytes"] = DIST_ZIP.stat().st_size

    # FAIL_EXE_NOT_STANDALONE
    if not EXE.exists():
        return UserInstallVerdict(False, "FAIL_EXE_NOT_STANDALONE", reasons=["exe missing in dist"], metrics=metrics)

    # FAIL_REGISTER_FAILED
    if smoke.get("register_ok") is False:
        return UserInstallVerdict(
            False, "FAIL_REGISTER_FAILED", reasons=[f"register: {smoke.get('register_error', '')}"], metrics=metrics
        )

    # FAIL_TOKEN_STORE_FAILED
    if smoke.get("token_store_ok") is False:
        return UserInstallVerdict(False, "FAIL_TOKEN_STORE_FAILED", reasons=["token store failed"], metrics=metrics)

    # FAIL_WSS_AUTH_FAILED
    if smoke.get("wss_auth_ok") is False:
        return UserInstallVerdict(False, "FAIL_WSS_AUTH_FAILED", reasons=["wss auth failed"], metrics=metrics)

    # FAIL_HEARTBEAT_FAILED
    if smoke.get("heartbeat_ok") is False:
        return UserInstallVerdict(False, "FAIL_HEARTBEAT_FAILED", reasons=["heartbeat failed"], metrics=metrics)

    # FAIL_TOKEN_LEAK — smoke output / 문서 안에 raw token
    for src_name, src_text in (("user_doc", doc_text), ("smoke_output", json.dumps(smoke, ensure_ascii=False))):
        leaks = _has_token_leak(src_text)
        if leaks:
            return UserInstallVerdict(False, "FAIL_TOKEN_LEAK", reasons=[f"{src_name}:{leaks[:2]}"], metrics=metrics)

    # WARN
    if not gui_available:
        # GUI 없음 — 본 공정 OUT_OF_SCOPE 이라 정상 WARN
        pass
    if same_machine_test:
        return UserInstallVerdict(
            False,
            "WARN_SAME_MACHINE_TEST_ONLY",
            reasons=["test executed on same machine as build — not true clean PC"],
            metrics=metrics,
        )

    # 코드 서명 — OUT_OF_SCOPE → WARN
    return UserInstallVerdict(
        False, "WARN_UNSIGNED_BINARY", reasons=["dist built but unsigned (code signing OUT_OF_SCOPE)"], metrics=metrics
    )


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke-json", type=Path)
    ap.add_argument("--clean-machine", action="store_true")
    args = ap.parse_args(argv)
    smoke = {}
    if args.smoke_json and args.smoke_json.exists():
        smoke = json.loads(args.smoke_json.read_text(encoding="utf-8"))
    v = judge_user_install(smoke_results=smoke, same_machine_test=not args.clean_machine)
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
