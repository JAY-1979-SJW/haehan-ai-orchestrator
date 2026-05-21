"""AGENT_DESKTOP_UI_OPENAI_KEY_UX_SPEC_01 audit."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


SPEC = Path("docs/design/local_agent_desktop_ui_openai_key_ux_spec_20260521.md")
NEXT_PROCESSES = ("AGENT_OPENAI_BYOK_KEY_STORE_01",
                  "AGENT_OPENAI_CHAT_CLIENT_01",
                  "AGENT_GUI_CHAT_IMPLEMENTATION_01")


@dataclass
class SpecVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def judge_spec(*,
               spec_path: Path | None = None,
               desktop_ui_unchanged: bool = True,
               proxy_mode_implemented: bool = False,
               ) -> SpecVerdict:
    p = spec_path or SPEC
    metrics = {
        "spec_exists": p.exists(),
        "desktop_ui_unchanged": desktop_ui_unchanged,
        "proxy_mode_implemented": proxy_mode_implemented,
    }
    text = _read(p)
    if not text:
        return SpecVerdict(False, "FAIL_OPENAI_KEY_UX_MISSING",
                           reasons=[f"spec not found: {p}"],
                           metrics=metrics)

    # FAIL_DESKTOP_UI_SCOPE_VIOLATION
    if not desktop_ui_unchanged:
        return SpecVerdict(False, "FAIL_DESKTOP_UI_SCOPE_VIOLATION",
                           reasons=["desktop/ui touched"],
                           metrics=metrics)

    # FAIL_OPENAI_KEY_UX_MISSING — BYOK / modal / fingerprint / 테스트 / 삭제
    required = ("BYOK", "AI Settings modal", "Credential Manager",
                "sk-****", "연결 테스트", "[삭제]",
                "key 원문", "재표시", "API key",
                "Chat 탭", "Status 탭", "Diagnostics 탭")
    missing = [k for k in required if k not in text]
    if missing:
        return SpecVerdict(False, "FAIL_OPENAI_KEY_UX_MISSING",
                           reasons=[f"missing: {missing[:5]}"],
                           metrics=metrics)

    # FAIL_SECURITY_POLICY_MISSING
    sec_required = ("device_token", "registration_code",
                    "마스킹", "redact",
                    "서버로 전송되지 않", "Credential Manager",
                    "평문 fallback")
    missing_sec = [k for k in sec_required if k not in text]
    if missing_sec:
        return SpecVerdict(False, "FAIL_SECURITY_POLICY_MISSING",
                           reasons=[f"missing security: {missing_sec[:3]}"],
                           metrics=metrics)

    # FAIL_CHATGPT_WEB_AUTOMATION_ALLOWED — 명시적 금지가 있어야 함
    if "ChatGPT 웹 자동화" not in text:
        return SpecVerdict(False, "FAIL_CHATGPT_WEB_AUTOMATION_ALLOWED",
                           reasons=["ChatGPT 웹 자동화 금지 명시 없음"],
                           metrics=metrics)
    # 금지 라인이 "하지 않" / "❌" / "금지" 와 함께 있어야 함
    # 간단 정규식: "ChatGPT 웹 자동화" 이후 100자 안에 금지 표현
    m = re.search(r"ChatGPT 웹 자동화.{0,80}(❌|금지|하지 않)", text,
                  re.DOTALL)
    if not m:
        return SpecVerdict(False, "FAIL_CHATGPT_WEB_AUTOMATION_ALLOWED",
                           reasons=["ChatGPT 웹 자동화 금지 표현 부정확"],
                           metrics=metrics)

    # FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING
    for proc in NEXT_PROCESSES:
        if proc not in text:
            return SpecVerdict(False, "FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING",
                               reasons=[f"next process missing: {proc}"],
                               metrics=metrics)

    # MVP / Later / 하지 않 섹션
    for section in ("MVP", "Later", "하지 않"):
        if section not in text:
            return SpecVerdict(False, "FAIL_NEXT_IMPLEMENTATION_PLAN_MISSING",
                               reasons=[f"section missing: {section}"],
                               metrics=metrics)

    # FAIL — raw API key in doc
    # 진짜 OpenAI key 형태 (sk-XXXXX...20자+) 가 들어가면 leak
    key_matches = re.findall(r"\bsk-[A-Za-z0-9]{20,}\b", text)
    # 단, 정규식 패턴 자체 (e.g. "\\bsk-[A-Za-z0-9_-]{20,}\\b") 는 OK
    # 실제 raw 값처럼 보이는 게 있는지
    real = [k for k in key_matches if "[A-Za-z" not in k]
    if real:
        return SpecVerdict(False, "FAIL_SECURITY_POLICY_MISSING",
                           reasons=[f"raw API key leak in doc: {real[:2]}"],
                           metrics=metrics)

    metrics["spec_length"] = len(text)
    metrics["next_processes"] = list(NEXT_PROCESSES)

    # WARN — Proxy 모드 미구현 (의도된 OUT_OF_SCOPE)
    if not proxy_mode_implemented:
        return SpecVerdict(False, "WARN_PROXY_MODE_DEFERRED",
                           reasons=["Company Proxy 모드는 Later 별도 공정"],
                           metrics=metrics)

    return SpecVerdict(True, "PASS_DESKTOP_UI_OPENAI_KEY_UX_SPEC",
                       reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, default=SPEC)
    ap.add_argument("--desktop-ui-unchanged", type=int, default=1)
    ap.add_argument("--proxy-impl", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_spec(spec_path=args.spec,
                    desktop_ui_unchanged=bool(args.desktop_ui_unchanged),
                    proxy_mode_implemented=bool(args.proxy_impl))
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
