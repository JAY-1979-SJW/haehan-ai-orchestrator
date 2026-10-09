"""scripts/common/audit_cli.py — 감사 스크립트 공용 출력·CLI 틀(N2 중복 통합) 시험."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.common import audit_cli


def test_report_findings(capsys: pytest.CaptureFixture[str]) -> None:
    assert audit_cli.report_findings(True, ["a", "b"], "X_CONTRACT") == 0
    assert capsys.readouterr().out.splitlines() == ["[PASS] a", "[PASS] b", "RESULT=PASS_X_CONTRACT"]
    assert audit_cli.report_findings(False, ["c"], "X_CONTRACT") == 1
    assert capsys.readouterr().out.splitlines() == ["[FAIL] c", "RESULT=FAIL_X_CONTRACT"]


def _phrase_audit(base: Path, mod: Path) -> tuple[bool, list[str]]:
    return audit_cli.audit_baseline_with_module_ref(
        audit_cli.BaselineRefSpec(
            baseline=base,
            baseline_missing="base missing",
            baseline_phrases=("Status: LOCKED", "alpha"),
            baseline_fail_prefix="base missing phrase(s): ",
            module_baseline=mod,
            module_missing="module missing",
            module_phrases=("### x",),
            module_fail_prefix="module missing ref(s): ",
            success=["ok1", "ok2"],
        ),
        lambda text, phrases: [p for p in phrases if p not in text],
    )


def test_audit_baseline_with_module_ref(tmp_path: Path) -> None:
    base, mod = tmp_path / "base.md", tmp_path / "mod.md"
    assert _phrase_audit(base, mod) == (False, ["base missing"])
    base.write_text("Status: LOCKED", encoding="utf-8")
    assert _phrase_audit(base, mod) == (False, ["module missing"])
    mod.write_text("nothing", encoding="utf-8")
    assert _phrase_audit(base, mod) == (False, ["base missing phrase(s): alpha", "module missing ref(s): ### x"])
    base.write_text("Status: LOCKED alpha", encoding="utf-8")
    mod.write_text("### x", encoding="utf-8")
    assert _phrase_audit(base, mod) == (True, ["ok1", "ok2"])


def test_run_json_or_report_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    printed: list[dict] = []
    monkeypatch.setattr(sys, "argv", ["x"])
    with pytest.raises(SystemExit) as exc:
        audit_cli.run_json_or_report_cli("d", lambda: {"success": False}, printed.append, "success")
    assert exc.value.code == 1
    assert printed == [{"success": False}]
    monkeypatch.setattr(sys, "argv", ["x", "--json"])
    with pytest.raises(SystemExit) as exc:
        audit_cli.run_json_or_report_cli("d", lambda: {"all_ok": True}, printed.append, "all_ok")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out) == {"all_ok": True}


_CHECKLIST_RESULT = {
    "verdict": "PASS_WITH_KNOWN_WARN",
    "summary": {"pass": 1, "warn": 1, "fail": 0},
    "checklist": [
        {"id": "a-1", "title": "t1", "status": "PASS", "evidence": "e" * 100},
        {"id": "a-2", "title": "t2", "status": "WARN", "evidence": "w"},
    ],
}


def test_run_checklist_cli_text_and_backend_premium_main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.audits.backend import audit_backend_premium_policy_layer as premium

    monkeypatch.setattr(sys, "argv", ["x"])
    monkeypatch.setattr(premium, "run_audit", lambda: _CHECKLIST_RESULT)
    assert premium.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        f"[{premium.AUDIT_NAME}] verdict=PASS_WITH_KNOWN_WARN pass=1 warn=1 fail=0",
        f"  ✓ [a-1] t1 — {'e' * 80}",
        "  △ [a-2] t2 — w",
    ]
    monkeypatch.setattr(premium, "run_audit", lambda: {**_CHECKLIST_RESULT, "verdict": "FAIL"})
    monkeypatch.setattr(sys, "argv", ["x", "--json"])
    assert premium.main() == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


def test_print_check_report(capsys: pytest.CaptureFixture[str]) -> None:
    checks = [("c1", True, ""), ("c2", False, "why")]
    assert audit_cli.print_check_report("T AUDIT", checks, ("R", "W", "B"), 1) == "W"
    out = capsys.readouterr().out
    assert "  [PASS] c1\n  [FAIL] c2 — why\n" in out
    assert "  총 2개 검사: PASS=1, FAIL=1" in out
    assert out.endswith(f"  최종 판정: W\n{'=' * 64}\n\n")
    assert audit_cli.print_check_report("T", checks, ("R", "W", "B"), 0, "개") == "B"
    assert "  총 2개: PASS=1, FAIL=1" in capsys.readouterr().out
    assert audit_cli.print_check_report("T", checks[:1], ("R", "W", "B"), 0) == "R"
