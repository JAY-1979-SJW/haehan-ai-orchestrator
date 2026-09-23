"""AGENT_GUI_CHAT_UI_IMPLEMENTATION_01 audit."""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GuiVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


GUI_APP_PATH = Path("local_agent/gui_app.py")
GUI_TRAY_PATH = Path("local_agent/gui_tray.py")
ADAPTER_PATH = Path("local_agent/ai_chat_adapter.py")


_FORBIDDEN_EXTERNAL = (
    # 실제 SDK import / 호출 패턴만.
    # 단순 단어 "OpenAI" 는 UI 라벨, "from . import openai_*" 는 로컬 모듈 — 허용.
    "openai.chat",
    "openai.api",
    "openai.completions",
    "anthropic.messages",
    "anthropic.completions",
    "https://api.openai.com",
    "https://api.anthropic.com",
    "requests.post",
    "httpx.post",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_gui_chat_ui(*, cli_regression_ok: bool = True, desktop_ui_unchanged: bool = True) -> GuiVerdict:
    metrics: dict = {}

    if not desktop_ui_unchanged:
        return GuiVerdict(False, "FAIL_DESKTOP_UI_TOUCHED", reasons=["desktop/ui touched"], metrics=metrics)

    # FAIL_CHAT_TAB_MISSING / FAIL_STATUS_TAB_MISSING / FAIL_DIAGNOSTICS_TAB_MISSING
    app_text = _read(GUI_APP_PATH)
    if 'PAGE_CHAT = "chat"' not in app_text:
        return GuiVerdict(False, "FAIL_CHAT_TAB_MISSING", reasons=["PAGE_CHAT enum missing"], metrics=metrics)
    if 'PAGE_STATUS = "status"' not in app_text:
        return GuiVerdict(False, "FAIL_STATUS_TAB_MISSING", reasons=["PAGE_STATUS enum missing"], metrics=metrics)
    if 'PAGE_DIAGNOSTICS = "diagnostics"' not in app_text:
        return GuiVerdict(
            False, "FAIL_DIAGNOSTICS_TAB_MISSING", reasons=["PAGE_DIAGNOSTICS enum missing"], metrics=metrics
        )

    # builder 함수 존재
    from local_agent.gui_app import HaehanAgentGuiApp

    for fn in (
        "_build_chat_tab",
        "_build_status_tab",
        "_build_diagnostics_tab",
        "open_wizard",
        "open_ai_settings",
        "on_send_chat",
        "on_minimize_to_tray",
        "show_page",
        "_bind_shortcuts",
    ):
        if not hasattr(HaehanAgentGuiApp, fn):
            return GuiVerdict(
                False,
                "FAIL_AI_SETTINGS_MODAL_MISSING" if fn == "open_ai_settings" else "FAIL_CHAT_TAB_MISSING",
                reasons=[f"missing method: {fn}"],
                metrics=metrics,
            )

    # FAIL_EXTERNAL_AI_CALLED — adapter / gui_app 소스 정적 검사
    for f in (GUI_APP_PATH, ADAPTER_PATH):
        t = _read(f).lower()
        for pat in _FORBIDDEN_EXTERNAL:
            if pat in t:
                return GuiVerdict(
                    False, "FAIL_EXTERNAL_AI_CALLED", reasons=[f"forbidden '{pat}' in {f}"], metrics=metrics
                )

    # FAIL_API_KEY_STORED — adapter 가 api_key 를 disk 에 저장하는 호출 없음
    adp_text = _read(ADAPTER_PATH)
    for pat in (".write_text", "open(", "json.dump", "set_password", "save_device_token"):
        if pat == "open(":
            # __init__/Path open 같은 건 OK — 단순 키워드 발생만 보면 위양성
            # 대신 "open(" with mode 'w' 검사
            if re.search(r"open\s*\([^)]*['\"][wa]", adp_text):
                return GuiVerdict(
                    False, "FAIL_API_KEY_STORED", reasons=["adapter opens file for write"], metrics=metrics
                )
            continue
        if pat in adp_text:
            return GuiVerdict(
                False, "FAIL_API_KEY_STORED", reasons=[f"adapter persists data: '{pat}'"], metrics=metrics
            )

    # external_call_count = 0 검증
    from local_agent.ai_chat_adapter import (
        make_default_adapter,
    )

    a = make_default_adapter()
    assert a.is_configured() is False
    r = a.send_message(text_raw="hi")
    if r.external_call_count != 0:
        return GuiVerdict(
            False, "FAIL_EXTERNAL_AI_CALLED", reasons=["adapter external_call_count != 0"], metrics=metrics
        )
    # 신 ServerProxyChatAdapter 는 placeholder text 대신 error_code 반환 — 둘 다 허용
    has_placeholder_text = "설정되지 않" in (r.text_redacted or "")
    has_not_configured_err = r.error_code in (
        "DEVICE_TOKEN_MISSING",
        "AGENT_ID_MISSING",
        "API_KEY_NOT_SET",
    )
    if not (has_placeholder_text or has_not_configured_err):
        return GuiVerdict(
            False, "FAIL_AI_SETTINGS_MODAL_MISSING", reasons=["not configured response missing"], metrics=metrics
        )

    # FAIL_TOKEN_LEAK — gui_app 에 raw token 패턴 부재
    if re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', app_text):
        return GuiVerdict(False, "FAIL_TOKEN_LEAK", reasons=["raw device_token in gui_app"], metrics=metrics)
    if re.search(r"\bsk-[A-Za-z0-9]{20,}\b", app_text):
        return GuiVerdict(False, "FAIL_TOKEN_LEAK", reasons=["raw API key in gui_app"], metrics=metrics)

    # tray 메뉴 갱신
    tray_text = _read(GUI_TRAY_PATH)
    for item in ("열기", "Chat 열기", "상태 보기", "진단 보기", "AI 설정", "재등록", "종료"):
        if item not in tray_text:
            return GuiVerdict(
                False, "FAIL_AI_SETTINGS_MODAL_MISSING", reasons=[f"tray missing: {item}"], metrics=metrics
            )

    # FAIL_CLI_REGRESSION (외부 신호)
    if not cli_regression_ok:
        return GuiVerdict(False, "FAIL_CLI_REGRESSION", reasons=["external signal: cli regression"], metrics=metrics)

    metrics["pages"] = ["chat", "status", "diagnostics"]
    metrics["adapter_external_calls"] = 0
    metrics["mode_options"] = 3

    return GuiVerdict(
        False,
        "WARN_AI_API_NOT_CONNECTED",
        reasons=["adapter is PlaceholderAdapter — 실제 AI 호출 다음 공정"],
        metrics=metrics,
    )


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cli-regression-ok", type=int, default=1)
    args = ap.parse_args(argv)
    v = judge_gui_chat_ui(cli_regression_ok=bool(args.cli_regression_ok))
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
