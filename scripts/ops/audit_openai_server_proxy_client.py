"""AGENT_OPENAI_SERVER_PROXY_CLIENT_01 audit."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProxyVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


SERVER_ROUTER = Path("ai_orchestrator/agent_ai_proxy_router.py")
SERVER_CALLER = Path("ai_orchestrator/openai_proxy_caller.py")
DESKTOP_CLIENT = Path("local_agent/server_proxy_chat_client.py")
ADAPTER_PATH = Path("local_agent/ai_chat_adapter.py")
GUI_APP = Path("local_agent/gui_app.py")
MAIN_ROUTER = Path("ai_orchestrator/router.py")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_proxy(*, desktop_ui_unchanged: bool = True,
                 server_deployed: bool = False) -> ProxyVerdict:
    metrics: dict = {}

    if not desktop_ui_unchanged:
        return ProxyVerdict(False, "FAIL_DESKTOP_UI_TOUCHED",
                            reasons=["desktop/ui touched"],
                            metrics=metrics)

    # FAIL_SERVER_PROXY_ENDPOINT_MISSING
    if not SERVER_ROUTER.exists() or not SERVER_CALLER.exists():
        return ProxyVerdict(False, "FAIL_SERVER_PROXY_ENDPOINT_MISSING",
                            reasons=["router or caller missing"],
                            metrics=metrics)
    for sym in ("agent_ai_proxy_router", "ChatRequest", "ChatResponse",
                 "MAX_MESSAGE_LEN", "RATE_LIMIT_PER_MIN"):
        if _resolve("ai_orchestrator.agent_ai_proxy_router", sym) is None:
            return ProxyVerdict(False, "FAIL_SERVER_PROXY_ENDPOINT_MISSING",
                                reasons=[f"missing: {sym}"],
                                metrics=metrics)
    # router mount 됐는지
    main_text = _read(MAIN_ROUTER)
    if "agent_ai_proxy_router" not in main_text:
        return ProxyVerdict(False, "FAIL_SERVER_PROXY_ENDPOINT_MISSING",
                            reasons=["agent_ai_proxy_router not mounted"],
                            metrics=metrics)

    # FAIL_AGENT_AUTH_BROKEN — router 가 authenticate_agent 호출
    router_text = _read(SERVER_ROUTER)
    if "authenticate_agent" not in router_text:
        return ProxyVerdict(False, "FAIL_AGENT_AUTH_BROKEN",
                            reasons=["authenticate_agent not used"],
                            metrics=metrics)
    if "Bearer" not in router_text and "X-Device-Token" not in router_text:
        return ProxyVerdict(False, "FAIL_AGENT_AUTH_BROKEN",
                            reasons=["device_token header parsing 없음"],
                            metrics=metrics)

    # FAIL_SERVER_OPENAI_NOT_CALLED — caller 가 OpenAI API 호출 패턴 보유
    caller_text = _read(SERVER_CALLER)
    if "api.openai.com" not in caller_text:
        return ProxyVerdict(False, "FAIL_SERVER_OPENAI_NOT_CALLED",
                            reasons=["openai endpoint not present"],
                            metrics=metrics)
    if "OPENAI_API_KEY" not in caller_text:
        return ProxyVerdict(False, "FAIL_SERVER_OPENAI_NOT_CALLED",
                            reasons=["env OPENAI_API_KEY not read"],
                            metrics=metrics)

    # FAIL_OPENAI_KEY_LEAK — 모든 관련 소스 안에 raw long sk- 패턴 부재
    for f, threshold in (
        (SERVER_ROUTER, 30), (SERVER_CALLER, 30),
        (DESKTOP_CLIENT, 30), (ADAPTER_PATH, 30), (GUI_APP, 30),
        (Path("scripts/ops/audit_openai_server_proxy_client.py"), 30),
        (Path("tests/test_openai_server_proxy_client.py"), 50),
    ):
        t = _read(f)
        if not t:
            continue
        pat = re.compile(rf"\bsk-[A-Za-z0-9_]{{{threshold},}}\b")
        matches = [m for m in pat.findall(t) if "A-Za-z" not in m]
        if matches:
            return ProxyVerdict(False, "FAIL_OPENAI_KEY_LEAK",
                                reasons=[f"raw key in {f}: {matches[:2]}"],
                                metrics=metrics)

    # FAIL_DEVICE_TOKEN_LEAK
    for f in (SERVER_ROUTER, DESKTOP_CLIENT):
        t = _read(f)
        if re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', t):
            return ProxyVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                                reasons=[f"raw device_token in {f}"],
                                metrics=metrics)
        # logger 가 token 변수 인자로 받지 않는지
        if re.search(r"log(?:ger)?\.\w+\([^)]*token\b[^)]*\)", t):
            # 'token' 단어가 log 안에 등장하면 의심. 단, "rate_limit_exceeded"
            # 같이 'token' 단어 없는 호출만 허용.
            bad = [ln for ln in t.split("\n")
                    if "log" in ln and ".info" in ln or ".warning" in ln or ".error" in ln]
            # 직접 'token' 변수 인자 전달 패턴만 검사
            if re.search(r"log(?:ger)?\.\w+\([^)]*%[sr][^)]*,\s*token\b", t):
                return ProxyVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                                    reasons=["token value logged"],
                                    metrics=metrics)

    # FAIL_RAW_CHAT_LOG_SAVED — 서버 router 가 raw chat 본문 디스크 저장 안 함
    for f in (SERVER_ROUTER, SERVER_CALLER, DESKTOP_CLIENT):
        t = _read(f)
        if re.search(r"open\s*\([^)]*['\"][wa]", t):
            return ProxyVerdict(False, "FAIL_RAW_CHAT_LOG_SAVED",
                                reasons=[f"file write in {f}"],
                                metrics=metrics)
        if ".write_text" in t:
            return ProxyVerdict(False, "FAIL_RAW_CHAT_LOG_SAVED",
                                reasons=[f".write_text in {f}"],
                                metrics=metrics)

    # adapter SERVER_PROXY 분기
    adp_text = _read(ADAPTER_PATH)
    if "ServerProxyChatAdapter" not in adp_text:
        return ProxyVerdict(False, "FAIL_SERVER_PROXY_ENDPOINT_MISSING",
                            reasons=["ServerProxyChatAdapter missing"],
                            metrics=metrics)
    if "MODE_SERVER_PROXY" not in adp_text:
        return ProxyVerdict(False, "FAIL_SERVER_PROXY_ENDPOINT_MISSING",
                            reasons=["MODE_SERVER_PROXY branching missing"],
                            metrics=metrics)

    metrics["server_router_present"] = True
    metrics["caller_present"] = True
    metrics["desktop_client_present"] = DESKTOP_CLIENT.exists()
    metrics["adapter_branching"] = True

    # WARN_SERVER_DEPLOY_REQUIRED — 서버 코드 추가, 운영 배포 필요
    if not server_deployed:
        return ProxyVerdict(False, "WARN_SERVER_DEPLOY_REQUIRED",
                            reasons=["server changes need deploy (별도 공정)"],
                            metrics=metrics)
    return ProxyVerdict(True, "PASS_OPENAI_SERVER_PROXY_CLIENT",
                        reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-deployed", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_proxy(server_deployed=bool(args.server_deployed))
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
