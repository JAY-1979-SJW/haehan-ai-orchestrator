"""AGENT_GUI_DESIGN_IMPLEMENTATION_01 audit — 4탭 구현 검증."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_PAGES = ("PAGE_DASHBOARD", "PAGE_REGISTRATION",
                  "PAGE_LOGS", "PAGE_SETTINGS")
SHORTCUT_PATTERNS = (r"Control-Key-1", r"Control-Key-2",
                     r"Control-Key-3", r"Control-Key-4",
                     r"Control-r", r"F1", r"Escape")


@dataclass
class ImplVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_impl(*, cli_regression_ok: bool = True) -> ImplVerdict:
    metrics = {}

    # FAIL_PAGE_ENUM_MISSING
    for p in REQUIRED_PAGES:
        if _resolve("local_agent.gui_app", p) is None:
            return ImplVerdict(False, "FAIL_GUI_PAGE_MISSING",
                               reasons=[f"missing page enum: {p}"],
                               metrics=metrics)

    # FAIL_GUI_PAGE_BUILDER_MISSING
    from local_agent.gui_app import HaehanAgentGuiApp
    for builder in ("_build_page_dashboard", "_build_page_registration",
                    "_build_page_logs", "_build_page_settings",
                    "show_page", "_bind_shortcuts"):
        if not hasattr(HaehanAgentGuiApp, builder):
            return ImplVerdict(False, "FAIL_GUI_PAGE_MISSING",
                               reasons=[f"missing method: {builder}"],
                               metrics=metrics)

    # FAIL_LOG_BUFFER_MISSING
    lb = _resolve("local_agent.gui_log_buffer", "LogBuffer")
    if lb is None or _resolve("local_agent.gui_log_buffer", "redact") is None:
        return ImplVerdict(False, "FAIL_LOG_BUFFER_MISSING",
                           reasons=["LogBuffer / redact missing"],
                           metrics=metrics)

    # FAIL_LOG_REDACT_BROKEN
    from local_agent.gui_log_buffer import redact, LogBuffer
    text = ('device_token=ABCDEF12345678 registration_code=XYZ987 '
             '"device_token": "RAW_VALUE_TEST_long" '
             'Authorization: Bearer abc123def456')
    r = redact(text)
    if "ABCDEF12345678" in r or "XYZ987" in r or "RAW_VALUE_TEST_long" in r:
        return ImplVerdict(False, "FAIL_LOG_REDACT_BROKEN",
                           reasons=["secret value survived redact"],
                           metrics=metrics)
    # buffer instance leak test
    buf = LogBuffer()
    buf.info("device_token=SECRETABCD1234")
    tail = buf.tail()
    if any("SECRETABCD1234" in e.msg for e in tail):
        return ImplVerdict(False, "FAIL_LOG_REDACT_BROKEN",
                           reasons=["LogBuffer stored raw secret"],
                           metrics=metrics)

    # FAIL_SHORTCUTS_MISSING — gui_app 소스에 키바인딩 패턴
    src = Path("local_agent/gui_app.py").read_text(encoding="utf-8")
    for pat in SHORTCUT_PATTERNS:
        if not re.search(pat, src):
            return ImplVerdict(False, "FAIL_SHORTCUTS_MISSING",
                               reasons=[f"shortcut binding missing: {pat}"],
                               metrics=metrics)

    # FAIL_TRAY_NOT_SYNCED
    # 신 구조 (한글 항목) 또는 구 구조 (영문 항목) 둘 중 하나는 모두 있어야 함
    tray_src = Path("local_agent/gui_tray.py").read_text(encoding="utf-8")
    old_set = ("Dashboard", "Registration", "Logs", "Settings")
    new_set = ("열기", "Chat 열기", "상태 보기", "진단 보기", "AI 설정")
    has_old = all(k in tray_src for k in old_set)
    has_new = all(k in tray_src for k in new_set)
    if not (has_old or has_new):
        return ImplVerdict(False, "FAIL_TRAY_NOT_SYNCED",
                           reasons=["tray menu neither old(EN) nor new(KR) set"],
                           metrics=metrics)

    # FAIL_STATE_SOURCE_NOT_UNIFIED — gui_app 에 별도 state 변수가 있으면 의심
    # 기준: GuiController 외부 model 정의 없음
    if "class GuiModel" in src or "_state =" in src and "_state = " in src:
        # gui_app 에서 GuiModel 정의 금지 (gui_state 가 단일 source)
        if "class GuiModel" in src:
            return ImplVerdict(False, "FAIL_STATE_SOURCE_DUPLICATED",
                               reasons=["GuiModel re-defined in gui_app"],
                               metrics=metrics)

    # FAIL_CLI_REGRESSION
    if not cli_regression_ok:
        return ImplVerdict(False, "FAIL_CLI_REGRESSION",
                           reasons=["external signal"],
                           metrics=metrics)

    # FAIL_PII_LEAK — 소스 자체에 토큰 원문 패턴
    for src_file in ("local_agent/gui_app.py",
                      "local_agent/gui_log_buffer.py",
                      "local_agent/gui_icons.py"):
        t = Path(src_file).read_text(encoding="utf-8")
        if re.search(r'"device_token"\s*:\s*"[A-Za-z0-9]{20,}"', t):
            return ImplVerdict(False, "FAIL_PII_LEAK",
                               reasons=[f"hardcoded token in {src_file}"],
                               metrics=metrics)

    metrics["pages"] = REQUIRED_PAGES
    metrics["shortcuts_count"] = len(SHORTCUT_PATTERNS)

    return ImplVerdict(True, "PASS_AGENT_GUI_DESIGN_IMPLEMENTATION",
                       reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli-regression-ok", type=int, default=1)
    args = ap.parse_args(argv)
    v = judge_impl(cli_regression_ok=bool(args.cli_regression_ok))
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
