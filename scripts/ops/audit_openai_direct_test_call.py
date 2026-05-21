"""AGENT_OPENAI_DIRECT_TEST_CALL_01 audit."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CallVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


CLIENT_PATH = Path("local_agent/openai_chat_client.py")
ADAPTER_PATH = Path("local_agent/ai_chat_adapter.py")
GUI_APP_PATH = Path("local_agent/gui_app.py")
SMOKE_REPORT = Path("data/inspection/openai_direct_test_call/live_smoke_report.json")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_call(*, desktop_ui_unchanged: bool = True,
                proxy_implemented: bool = False
                ) -> CallVerdict:
    metrics: dict = {}

    if not desktop_ui_unchanged:
        return CallVerdict(False, "FAIL_DESKTOP_UI_TOUCHED",
                           reasons=["desktop/ui touched"],
                           metrics=metrics)

    # FAIL — client module missing
    if not CLIENT_PATH.exists():
        return CallVerdict(False, "FAIL_EXTERNAL_AI_NOT_CALLED",
                           reasons=[f"missing: {CLIENT_PATH}"],
                           metrics=metrics)
    for sym in ("OpenAiDirectTestClient", "OpenAiChatRequest",
                 "OpenAiChatResponse", "live_smoke",
                 "DEFAULT_MODEL"):
        if _resolve("local_agent.openai_chat_client", sym) is None:
            return CallVerdict(False, "FAIL_EXTERNAL_AI_NOT_CALLED",
                               reasons=[f"missing symbol: {sym}"],
                               metrics=metrics)

    # adapter dev mode 분기
    adp_text = _read(ADAPTER_PATH)
    if "OpenAiDirectTestAdapter" not in adp_text:
        return CallVerdict(False, "FAIL_EXTERNAL_AI_NOT_CALLED",
                           reasons=["adapter missing OpenAiDirectTestAdapter"],
                           metrics=metrics)
    if "MODE_DEV_TEST_KEY" not in adp_text:
        return CallVerdict(False, "FAIL_EXTERNAL_AI_NOT_CALLED",
                           reasons=["adapter no MODE_DEV_TEST_KEY branching"],
                           metrics=metrics)

    # FAIL_API_KEY_LEAK — 소스 / 보고서 안에 real-looking long sk-* 부재.
    # 테스트 파일은 redaction 검증용 dummy (40자 이하) 허용.
    for f, threshold in (
        (CLIENT_PATH, 30),
        (ADAPTER_PATH, 30),
        (GUI_APP_PATH, 30),
        (SMOKE_REPORT, 30),
        (Path("scripts/ops/audit_openai_direct_test_call.py"), 30),
        (Path("tests/test_openai_direct_test_call.py"), 50),
    ):
        t = _read(f)
        if not t:
            continue
        pat = re.compile(rf"\bsk-[A-Za-z0-9_]{{{threshold},}}\b")
        matches = pat.findall(t)
        real = [m for m in matches if "A-Za-z" not in m]
        if real:
            return CallVerdict(False, "FAIL_API_KEY_LEAK",
                               reasons=[f"raw key in {f}: {real[:2]}"],
                               metrics=metrics)

    # FAIL_DEVICE_TOKEN_LEAK — chat client 가 device_token 변수 처리 안 함
    src_client = _read(CLIENT_PATH)
    if re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', src_client):
        return CallVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                           reasons=["raw device_token in client"],
                           metrics=metrics)

    # FAIL_RAW_CHAT_HISTORY_SAVED — client 가 chat history file 저장 안 함
    if re.search(r"open\s*\([^)]*['\"][wa]", src_client):
        return CallVerdict(False, "FAIL_RAW_CHAT_HISTORY_SAVED",
                           reasons=["client opens file for write"],
                           metrics=metrics)
    if ".write_text" in src_client:
        return CallVerdict(False, "FAIL_RAW_CHAT_HISTORY_SAVED",
                           reasons=["client writes file"],
                           metrics=metrics)

    # FAIL_GUI_TEST_BUTTON_BROKEN — GUI modal 의 [연결 테스트] / [저장] / [삭제] 활성
    gui_text = _read(GUI_APP_PATH)
    # state="disabled" 가 modal 의 모든 버튼에 있으면 broken
    # 우리는 dev_mode 분기로 normal/disabled 토글하므로 "state=\"normal\" if dev_mode" 패턴이 있어야 함
    if "state=\"normal\" if dev_mode" not in gui_text \
            and 'btn_modal_save' not in gui_text:
        return CallVerdict(False, "FAIL_GUI_TEST_BUTTON_BROKEN",
                           reasons=["modal buttons not wired"],
                           metrics=metrics)
    for kw in ("_on_save", "_on_test", "_on_delete"):
        if kw not in gui_text:
            return CallVerdict(False, "FAIL_GUI_TEST_BUTTON_BROKEN",
                               reasons=[f"missing handler: {kw}"],
                               metrics=metrics)

    # live smoke report 확인
    if SMOKE_REPORT.exists():
        d = json.loads(_read(SMOKE_REPORT))
        result = d.get("result", {})
        metrics["live_smoke_external_call_count"] = result.get(
            "external_call_count", 0)
        metrics["live_smoke_ok"] = result.get("ok", False)
        if result.get("external_call_count", 0) >= 1 and result.get("ok"):
            metrics["live_smoke_passed"] = True
        else:
            metrics["live_smoke_passed"] = False
    else:
        metrics["live_smoke_passed"] = False

    metrics["proxy_implemented"] = proxy_implemented

    # WARN — production proxy 미구현 (의도)
    if not proxy_implemented:
        return CallVerdict(False, "WARN_PRODUCTION_PROXY_NOT_IMPLEMENTED",
                           reasons=["server proxy mode 별도 공정 — 본 공정 OUT_OF_SCOPE"],
                           metrics=metrics)

    return CallVerdict(True, "PASS_OPENAI_DIRECT_TEST_CALL",
                       reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy-impl", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_call(proxy_implemented=bool(args.proxy_impl))
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
