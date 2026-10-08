"""AGENT_GUI_UX_DESIGN_SPEC_01 audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SPEC = Path("docs/design/local_agent_gui_ux_design_spec_20260521.md")
NEXT_IMPL = "AGENT_GUI_SIMPLIFY_IMPLEMENTATION_01"


@dataclass
class SpecVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _check_flows(text, metrics):
    flow_keywords = (
        "첫 실행",
        "등록코드",
        "wss 자동 연결",
        "재실행",
        "재등록",
        "인증 실패",
        "서버 접속 실패",
        "진단",
        "종료",
    )
    missing = [k for k in flow_keywords if k not in text]
    if missing:
        return SpecVerdict(
            False, "FAIL_USER_FLOW_MISSING", reasons=[f"missing flow keywords: {missing[:5]}"], metrics=metrics
        )

    # FAIL_GUI_OPTION_COMPARISON_MISSING — 4개 안 A/B/C/D 비교
    for opt in ("A. 현재 4탭", "B. 트레이 중심", "C. 단일 창 2탭", "D. 첫 등록 wizard"):
        if opt not in text:
            return SpecVerdict(
                False,
                "FAIL_GUI_OPTION_COMPARISON_MISSING",
                reasons=[f"missing comparison option: {opt}"],
                metrics=metrics,
            )

    # 최종 권장안 명시
    if "권장안" not in text or "권장 =" not in text:
        return SpecVerdict(
            False, "FAIL_GUI_OPTION_COMPARISON_MISSING", reasons=["최종 권장안 명시 없음"], metrics=metrics
        )
    return None


def _check_security_next(text, metrics):
    # FAIL_SECURITY_UX_MISSING
    security_keywords = ("device_token", "registration_code", "agent_id", "마스킹", "redact", "show='●'")
    missing_sec = [k for k in security_keywords if k not in text]
    if missing_sec:
        return SpecVerdict(
            False, "FAIL_SECURITY_UX_MISSING", reasons=[f"missing security UX: {missing_sec[:3]}"], metrics=metrics
        )

    # FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING
    if NEXT_IMPL not in text:
        return SpecVerdict(
            False,
            "FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING",
            reasons=[f"next impl name missing: {NEXT_IMPL}"],
            metrics=metrics,
        )
    return None


def _check_sections_decision(text, metrics):
    # MVP / Later / 하지 않음 필수
    for section in ("MVP", "Later", "하지 않음"):
        if section not in text:
            return SpecVerdict(
                False, "FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING", reasons=[f"section missing: {section}"], metrics=metrics
            )

    # WARN — 권장안에 "(d) 보류" 가 명시되면 결정 미확정
    if "보류 — 추가 검토 필요" in text and "결정 / 승인 요청" in text:
        # 단순 옵션 나열이면 OK. "권장 = " 가 명확하면 진행.
        if "권장 = " in text:
            pass
        else:
            return SpecVerdict(False, "WARN_DECISION_NOT_FINAL", reasons=["결정 미확정"], metrics=metrics)
    return None


def judge_spec(
    *,
    spec_path: Path | None = None,
    desktop_ui_unchanged: bool = True,
) -> SpecVerdict:
    p = spec_path or SPEC
    metrics: dict[str, object] = {
        "spec_exists": p.exists(),
        "desktop_ui_unchanged": desktop_ui_unchanged,
    }
    text = _read(p)
    if not text:
        return SpecVerdict(False, "FAIL_USER_FLOW_MISSING", reasons=[f"spec not found: {p}"], metrics=metrics)

    # FAIL_DESKTOP_UI_SCOPE_VIOLATION
    if not desktop_ui_unchanged:
        return SpecVerdict(False, "FAIL_DESKTOP_UI_SCOPE_VIOLATION", reasons=["desktop/ui touched"], metrics=metrics)

    # FAIL_USER_FLOW_MISSING — 사용자 흐름 8종+
    _early = _check_flows(text, metrics)
    if _early is not None:
        return _early

    _early = _check_security_next(text, metrics)
    if _early is not None:
        return _early

    _early = _check_sections_decision(text, metrics)
    if _early is not None:
        return _early

    metrics["next_implementation"] = NEXT_IMPL
    metrics["spec_length"] = len(text)
    return SpecVerdict(True, "PASS_AGENT_GUI_UX_DESIGN_SPEC", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--desktop-ui-unchanged", type=int, default=1)
    args = ap.parse_args(argv)
    v = judge_spec(spec_path=args.spec, desktop_ui_unchanged=bool(args.desktop_ui_unchanged))
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
