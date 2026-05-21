"""LOCAL_AGENT_INSTALLER_PACKAGE_01 audit."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


ENTRY_MODULE = "local_agent.desktop_launcher"
BUILD_SCRIPT = Path("scripts/build_desktop_agent_windows.py")
DOC = Path("docs/ops/local_agent_installer_package.md")
DIST_REPORT = Path("data/inspection/local_agent_installer_package/build_report.json")


@dataclass
class PackageVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN_PATTERNS = ("device_token", "registration_code")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve_symbol(modname: str, sym: str):
    try:
        m = importlib.import_module(modname)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_package(*, run_self_test: bool = True) -> PackageVerdict:
    metrics = {
        "entry_module": ENTRY_MODULE,
        "build_script_present": BUILD_SCRIPT.exists(),
        "doc_present": DOC.exists(),
        "build_report_present": DIST_REPORT.exists(),
    }

    # FAIL_ENTRYPOINT_MISSING
    main_fn = _resolve_symbol(ENTRY_MODULE, "main")
    self_test_fn = _resolve_symbol(ENTRY_MODULE, "self_test")
    register_fn = _resolve_symbol(ENTRY_MODULE, "register_flow")
    connect_fn = _resolve_symbol(ENTRY_MODULE, "connect_flow")
    if not (main_fn and self_test_fn and register_fn and connect_fn):
        return PackageVerdict(False, "FAIL_ENTRYPOINT_MISSING",
                              reasons=[f"missing symbols in {ENTRY_MODULE}"],
                              metrics=metrics)

    # FAIL_CONFIG_STORE_BROKEN
    ts_save = _resolve_symbol("local_agent.token_store", "save_device_token")
    ts_load = _resolve_symbol("local_agent.token_store", "load_device_token")
    ts_del = _resolve_symbol("local_agent.token_store", "delete_device_token")
    ts_describe = _resolve_symbol("local_agent.token_store", "describe_backend")
    if not (ts_save and ts_load and ts_del and ts_describe):
        return PackageVerdict(False, "FAIL_CONFIG_STORE_BROKEN",
                              reasons=["token_store symbols missing"],
                              metrics=metrics)

    # FAIL_DIAGNOSTICS_MISSING
    cd_normalize = _resolve_symbol("local_agent.connection_diagnostics",
                                    "normalize_ws_url")
    cd_build = _resolve_symbol("local_agent.connection_diagnostics",
                                "build_diagnostics")
    cd_render = _resolve_symbol("local_agent.connection_diagnostics",
                                 "render_user_block")
    cd_explain = _resolve_symbol("local_agent.connection_diagnostics",
                                  "explain_error")
    if not (cd_normalize and cd_build and cd_render and cd_explain):
        return PackageVerdict(False, "FAIL_DIAGNOSTICS_MISSING",
                              reasons=["connection_diagnostics symbols missing"],
                              metrics=metrics)

    # FAIL_WS_URL_NORMALIZE_BROKEN
    try:
        u = cd_normalize("https://api.example.com/orchestrator")
        if u != "wss://api.example.com/orchestrator/api/v1/local-agents/ws":
            return PackageVerdict(False, "FAIL_WS_URL_NORMALIZE_BROKEN",
                                  reasons=[f"normalize unexpected: {u}"],
                                  metrics=metrics)
    except Exception as exc:
        return PackageVerdict(False, "FAIL_WS_URL_NORMALIZE_BROKEN",
                              reasons=[f"normalize raised: {exc}"],
                              metrics=metrics)

    # FAIL_TOKEN_LEAK — doc / build_report 에 토큰 원문 패턴
    leak_files = [DOC]
    if DIST_REPORT.exists():
        leak_files.append(DIST_REPORT)
    for p in leak_files:
        text = _read(p)
        # "device_token": "..." pattern with non-empty value > 8 chars
        if re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._-]{8,}"', text):
            return PackageVerdict(False, "FAIL_TOKEN_LEAK",
                                  reasons=[f"device_token raw value in {p}"],
                                  metrics=metrics)
        if re.search(r'"registration_code"\s*:\s*"[A-Za-z0-9._-]{8,}"', text):
            return PackageVerdict(False, "FAIL_TOKEN_LEAK",
                                  reasons=[f"registration_code raw value in {p}"],
                                  metrics=metrics)

    # self_test 실행 → 의존성/URL/diagnostics 회귀 검증
    if run_self_test:
        try:
            r = self_test_fn()
            metrics["self_test"] = r
            if not r.get("ok"):
                # diagnostics render 누수면 별도 verdict
                if r["checks"].get("diagnostics_render_leaks"):
                    return PackageVerdict(False, "FAIL_TOKEN_LEAK",
                                          reasons=["diagnostics render leaks tokens"],
                                          metrics=metrics)
                return PackageVerdict(False, "FAIL_DIAGNOSTICS_MISSING",
                                      reasons=[f"self_test failed: {r}"],
                                      metrics=metrics)
        except Exception as exc:
            return PackageVerdict(False, "FAIL_ENTRYPOINT_MISSING",
                                  reasons=[f"self_test raised: {exc}"],
                                  metrics=metrics)

    # FAIL_DIST_MISSING — 옵셔널 (PyInstaller 빌드 안 했어도 OK, WARN)
    # FAIL_BUILD_FAILED — build_report 에 error 가 있으면 FAIL
    if DIST_REPORT.exists():
        try:
            br = json.loads(_read(DIST_REPORT))
            if br.get("error") and "PyInstaller 미설치" not in br.get("error", ""):
                if br.get("ok") is False:
                    return PackageVerdict(False, "FAIL_BUILD_FAILED",
                                          reasons=[f"build error: {br.get('error')[:200]}"],
                                          metrics=metrics)
            metrics["build_ok"] = br.get("ok", False)
            metrics["pyinstaller_version"] = br.get("pyinstaller_version", "")
        except Exception:
            pass

    # 빌드 산출물 부재 → WARN_ONE_FILE_NOT_BUILT 또는 WARN_LIVE_REGISTER_NOT_TESTED
    if not metrics.get("build_ok"):
        return PackageVerdict(False, "WARN_ONE_FILE_NOT_BUILT",
                              reasons=["dist artifact not built (PyInstaller missing or build skipped)"],
                              metrics=metrics)

    # PyInstaller 빌드 됐지만 코드 서명 안 함 → WARN_UNSIGNED_BINARY
    if metrics.get("build_ok"):
        return PackageVerdict(False, "WARN_UNSIGNED_BINARY",
                              reasons=["dist built but unsigned (code signing OUT_OF_SCOPE)"],
                              metrics=metrics)

    return PackageVerdict(True, "PASS_LOCAL_AGENT_INSTALLER_PACKAGE",
                          reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-self-test", action="store_true")
    args = ap.parse_args(argv)
    v = judge_package(run_self_test=not args.skip_self_test)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons,
                      "metrics": {k: v for k, v in v.metrics.items()
                                   if k != "self_test"}},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
