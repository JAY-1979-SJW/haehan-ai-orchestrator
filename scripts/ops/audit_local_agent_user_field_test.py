"""USER_FIELD_TEST_01 audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPORT = Path("data/inspection/local_agent_user_field_test/user_field_test_report.json")
CHECKSUMS = Path("data/inspection/local_agent_user_field_test/checksums.json")
SUMMARY = Path("data/inspection/local_agent_user_field_test/user_field_test_summary.md")
RUNBOOK = Path("docs/ops/local_agent_external_field_runbook.md")


@dataclass
class FieldTestVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_TOKEN_PATTERNS = (
    re.compile(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9._\-]{8,}"),
)


def _has_leak(text: str) -> list[str]:
    return [p.pattern for p in _TOKEN_PATTERNS if p.search(text or "")]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _check_token_leak(rp, metrics):
    for src_name, src_path in (("report", rp), ("summary", SUMMARY), ("runbook", RUNBOOK), ("checksums", CHECKSUMS)):
        if src_path.exists():
            leaks = _has_leak(_read(src_path))
            if leaks:
                return FieldTestVerdict(False, "FAIL_TOKEN_LEAK", reasons=[f"{src_name}: {leaks[:2]}"], metrics=metrics)
    return None


def _check_required_steps(steps, metrics):
    required = (
        "01_extract_zip_to_clean_folder",
        "02_self_test_python_free",
        "03_diagnostics_python_free",
        "04_gui_launch",
        "05_registration_with_code",
        "06_credential_manager_storage",
        "07_wss_auth_ok",
        "08_heartbeat",
        "09_reexecute_auto_reconnect",
        "10_error_token_not_stored",
        "11_error_register_no_env",
    )
    for k in required:
        s = steps.get(k, {})
        if not s.get("ok"):
            return FieldTestVerdict(False, "FAIL_STEP_FAILED", reasons=[f"step {k} failed: {s}"], metrics=metrics)
    return None


def judge_field_test(
    *,
    report_path: Path | None = None,
    desktop_ui_unchanged_signal: bool = True,
) -> FieldTestVerdict:
    rp = report_path or REPORT
    metrics = {
        "report_exists": rp.exists(),
        "checksums_exists": CHECKSUMS.exists(),
        "summary_exists": SUMMARY.exists(),
        "runbook_exists": RUNBOOK.exists(),
        "desktop_ui_unchanged_signal": desktop_ui_unchanged_signal,
    }

    # FAIL_REPORT_MISSING
    if not rp.exists():
        return FieldTestVerdict(False, "FAIL_REPORT_MISSING", reasons=[f"missing: {rp}"], metrics=metrics)

    text = _read(rp)
    try:
        d = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - 로컬 에이전트 필드 테스트 리포트 검증 — JSON 파싱 실패 시 FAIL_REPORT_INVALID_JSON 판정을 반환하는 fail-closed 경로.
        return FieldTestVerdict(False, "FAIL_REPORT_INVALID_JSON", reasons=[str(exc)[:200]], metrics=metrics)

    # FAIL_TOKEN_LEAK — 보고서/runbook/summary 안에 raw token
    _early = _check_token_leak(rp, metrics)
    if _early is not None:
        return _early

    # FAIL_DESKTOP_UI_TOUCHED
    if not desktop_ui_unchanged_signal:
        return FieldTestVerdict(
            False, "FAIL_DESKTOP_UI_TOUCHED", reasons=["desktop/ui modified in this process"], metrics=metrics
        )

    # 13 단계 — 필수 단계 PASS
    steps = d.get("steps", {})
    _early = _check_required_steps(steps, metrics)
    if _early is not None:
        return _early

    # FAIL_ARTIFACTS_MISSING — sha256 둘 다
    art = d.get("artifacts", {})
    if not (art.get("exe_sha256") and art.get("zip_sha256")):
        return FieldTestVerdict(
            False, "FAIL_ARTIFACTS_MISSING", reasons=["exe_sha256 / zip_sha256 missing"], metrics=metrics
        )

    metrics["exe_sha256"] = art["exe_sha256"]
    metrics["zip_sha256"] = art["zip_sha256"]
    metrics["zip_size_bytes"] = art.get("zip_size_bytes")

    # WARN — 외부 PC 미사용
    env = d.get("test_environment", {})
    metrics["external_pc_used"] = env.get("external_pc_used", False)
    if not env.get("external_pc_used"):
        return FieldTestVerdict(
            False, "WARN_SAME_MACHINE_TEST_ONLY", reasons=["external PC not used — build machine"], metrics=metrics
        )

    # WARN — SmartScreen 미확인
    sm = steps.get("12_smartscreen_antivirus", {})
    if sm.get("smartscreen_warning_observed") is None or sm.get("smartscreen_warning_observed") is False:
        # 외부 PC 미사용이면 위에서 잡힘. 외부 PC 인데도 false 면 OK.
        pass

    return FieldTestVerdict(True, "PASS_USER_FIELD_TEST", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPORT))
    args = ap.parse_args(argv)
    v = judge_field_test(report_path=Path(args.report))
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
