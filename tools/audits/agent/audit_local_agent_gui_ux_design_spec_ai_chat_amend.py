"""AGENT_GUI_UX_DESIGN_SPEC_AI_CHAT_AMEND_01 audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SPEC = Path("docs/design/local_agent_gui_ux_design_spec_ai_chat_amend_20260521.md")
NEXT_IMPL_API = "AGENT_AI_CHAT_API_CLIENT_01"
NEXT_IMPL_UI = "AGENT_GUI_CHAT_IMPLEMENTATION_01"


@dataclass
class AmendVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _amend_chat_status(text, metrics):
    # FAIL_CHAT_REQUIREMENT_MISSING — Chat 관련 키워드
    chat_keywords = ("AI 채팅", "Chat 탭", "메시지 목록", "사용자 입력창", "작업 위임", "Enter 전송")
    missing_chat = [k for k in chat_keywords if k not in text]
    if missing_chat:
        return AmendVerdict(
            False, "FAIL_CHAT_REQUIREMENT_MISSING", reasons=[f"missing chat UX: {missing_chat[:3]}"], metrics=metrics
        )

    # FAIL_STATUS_DIAGNOSTICS_MISSING — Status / Diagnostics 탭
    for tab in ("Status 탭", "Diagnostics 탭", "agent_id 마스킹", "재연결", "재등록"):
        if tab not in text:
            return AmendVerdict(False, "FAIL_STATUS_DIAGNOSTICS_MISSING", reasons=[f"missing: {tab}"], metrics=metrics)
    return None


def _amend_security_next(text, metrics):
    # FAIL_SECURITY_UX_MISSING
    sec_keywords = ("device_token", "registration_code", "마스킹", "redact", "대화 로그", "민감정보")
    missing_sec = [k for k in sec_keywords if k not in text]
    if missing_sec:
        return AmendVerdict(
            False, "FAIL_SECURITY_UX_MISSING", reasons=[f"missing security UX: {missing_sec[:3]}"], metrics=metrics
        )

    # 다음 공정명 명시
    if NEXT_IMPL_API not in text or NEXT_IMPL_UI not in text:
        return AmendVerdict(
            False,
            "FAIL_CHAT_REQUIREMENT_MISSING",
            reasons=[f"next process names missing: {NEXT_IMPL_API} / {NEXT_IMPL_UI}"],
            metrics=metrics,
        )
    return None


def _amend_options(text, metrics):
    # 4안 비교 명시
    for opt in (
        "A. wizard + tray only",
        "B. wizard + tray + Chat 단일창",
        "C. wizard + tray + 3탭 미니창",
        "D. React desktop/ui",
    ):
        if opt not in text:
            return AmendVerdict(
                False, "FAIL_CHAT_REQUIREMENT_MISSING", reasons=[f"missing option: {opt}"], metrics=metrics
            )

    # 권장 C 명시
    if not ("권장" in text and "C" in text):
        return AmendVerdict(False, "FAIL_CHAT_REQUIREMENT_MISSING", reasons=["권장 C 명시 없음"], metrics=metrics)
    return None


def judge_amend(
    *,
    spec_path: Path | None = None,
    desktop_ui_unchanged: bool = True,
    ai_api_implementation_done: bool = False,
) -> AmendVerdict:
    p = spec_path or SPEC
    metrics: dict[str, Any] = {
        "spec_exists": p.exists(),
        "desktop_ui_unchanged": desktop_ui_unchanged,
        "ai_api_implementation_done": ai_api_implementation_done,
    }
    text = _read(p)
    if not text:
        return AmendVerdict(False, "FAIL_CHAT_REQUIREMENT_MISSING", reasons=[f"spec not found: {p}"], metrics=metrics)

    # FAIL_DESKTOP_UI_SCOPE_VIOLATION
    if not desktop_ui_unchanged:
        return AmendVerdict(False, "FAIL_DESKTOP_UI_SCOPE_VIOLATION", reasons=["desktop/ui touched"], metrics=metrics)

    _early = _amend_chat_status(text, metrics)
    if _early is not None:
        return _early

    _early = _amend_security_next(text, metrics)
    if _early is not None:
        return _early

    _early = _amend_options(text, metrics)
    if _early is not None:
        return _early

    metrics["spec_length"] = len(text)
    metrics["next_processes"] = [NEXT_IMPL_API, NEXT_IMPL_UI]

    # WARN — AI API 실제 구현은 본 공정 OUT_OF_SCOPE
    if not ai_api_implementation_done:
        return AmendVerdict(
            False,
            "WARN_AI_API_IMPLEMENTATION_DEFERRED",
            reasons=[f"AI API client 실제 구현은 별도 공정 {NEXT_IMPL_API}"],
            metrics=metrics,
        )

    return AmendVerdict(True, "PASS_AGENT_GUI_UX_AI_CHAT_AMEND", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--desktop-ui-unchanged", type=int, default=1)
    ap.add_argument("--ai-api-done", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_amend(
        spec_path=args.spec,
        desktop_ui_unchanged=bool(args.desktop_ui_unchanged),
        ai_api_implementation_done=bool(args.ai_api_done),
    )
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
