"""AGENT_GUI_TRAY_01 audit."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_MODULES = (
    (
        "local_agent.gui_state",
        (
            "GuiController",
            "GuiModel",
            "transition",
            "ALL_STATES",
            "STATE_NOT_REGISTERED",
            "STATE_CONNECTED",
            "STATE_AUTH_FAILED",
        ),
    ),
    ("local_agent.gui_app", ("HaehanAgentGuiApp", "launch_gui")),
    ("local_agent.gui_tray", ("run_tray_with_app",)),
)

LAUNCHER = Path("local_agent/desktop_launcher.py")
BUILD_SCRIPT = Path("scripts/build_desktop_agent_windows.py")


@dataclass
class GuiVerdict:
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


def _has_pystray() -> bool:
    try:
        import pystray  # noqa

        return True
    except Exception:
        return False


def judge_gui(*, cli_regression_ok: bool = True, gui_build_executed: bool = False) -> GuiVerdict:
    metrics = {
        "pystray_available": _has_pystray(),
        "gui_build_executed": gui_build_executed,
    }

    # FAIL_GUI_ENTRYPOINT_MISSING
    for mod, syms in REQUIRED_MODULES:
        for s in syms:
            if _resolve(mod, s) is None:
                return GuiVerdict(
                    False, "FAIL_GUI_ENTRYPOINT_MISSING", reasons=[f"missing: {mod}.{s}"], metrics=metrics
                )

    # FAIL_REGISTER_UI_MISSING — gui_app 에 on_register 메서드
    gui_app = importlib.import_module("local_agent.gui_app")
    if not hasattr(gui_app.HaehanAgentGuiApp, "on_register"):
        return GuiVerdict(
            False, "FAIL_REGISTER_UI_MISSING", reasons=["HaehanAgentGuiApp.on_register missing"], metrics=metrics
        )

    # FAIL_STATUS_UI_MISSING — 상태 표시 메서드
    if not (hasattr(gui_app.HaehanAgentGuiApp, "_poll_model") and hasattr(gui_app.HaehanAgentGuiApp, "_build_ui")):
        return GuiVerdict(False, "FAIL_STATUS_UI_MISSING", reasons=["status UI builders missing"], metrics=metrics)

    # FAIL_DIAGNOSTICS_UI_MISSING
    if not hasattr(gui_app.HaehanAgentGuiApp, "on_diagnostics"):
        return GuiVerdict(False, "FAIL_DIAGNOSTICS_UI_MISSING", reasons=["on_diagnostics missing"], metrics=metrics)

    # FAIL_TOKEN_LEAK — gui_state.to_dict 결과에 token 키 없음
    gs = importlib.import_module("local_agent.gui_state")
    model = gs.GuiModel(server_url="https://x/y?device_token=SECRET", agent_id="la-abc123def456")
    d = model.to_dict()
    if any("device_token" in k for k in d.keys()):
        return GuiVerdict(False, "FAIL_TOKEN_LEAK", reasons=["device_token in model.to_dict keys"], metrics=metrics)
    js = json.dumps(d, ensure_ascii=False)
    if "SECRET" in js or "abc123def456" in js:
        return GuiVerdict(False, "FAIL_TOKEN_LEAK", reasons=["raw secret/agent_id in to_dict output"], metrics=metrics)

    # FAIL_CLI_REGRESSION
    if not cli_regression_ok:
        return GuiVerdict(False, "FAIL_CLI_REGRESSION", reasons=["CLI tests failed"], metrics=metrics)

    # launcher 에 --gui 옵션 존재 확인
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    if "--gui" not in launcher_text:
        return GuiVerdict(
            False, "FAIL_GUI_ENTRYPOINT_MISSING", reasons=["desktop_launcher --gui flag missing"], metrics=metrics
        )

    # 빌드 스크립트 GUI hidden imports
    build_text = BUILD_SCRIPT.read_text(encoding="utf-8")
    for imp in ("tkinter", "pystray", "PIL"):
        if imp not in build_text:
            return GuiVerdict(
                False,
                "FAIL_GUI_ENTRYPOINT_MISSING",
                reasons=[f"build script missing hidden import: {imp}"],
                metrics=metrics,
            )

    # WARN
    if not metrics["pystray_available"]:
        return GuiVerdict(
            False,
            "WARN_TRAY_LIBRARY_NOT_INSTALLED",
            reasons=["pystray not installed (tkinter fallback works)"],
            metrics=metrics,
        )
    if not gui_build_executed:
        return GuiVerdict(
            False, "WARN_GUI_BUILD_NOT_EXECUTED", reasons=["GUI bundled exe not rebuilt"], metrics=metrics
        )
    return GuiVerdict(
        False, "WARN_UNSIGNED_BINARY", reasons=["dist unsigned (code signing OUT_OF_SCOPE)"], metrics=metrics
    )


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cli-regression-ok", type=int, default=1)
    ap.add_argument("--gui-build-executed", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_gui(cli_regression_ok=bool(args.cli_regression_ok), gui_build_executed=bool(args.gui_build_executed))
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
