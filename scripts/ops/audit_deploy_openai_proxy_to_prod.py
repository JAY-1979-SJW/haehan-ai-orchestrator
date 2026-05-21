"""DEPLOY_OPENAI_PROXY_TO_PROD_01 audit — 운영 배포 검증."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class DeployVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def judge_deploy(*, server_head_matches_local: bool = True,
                  container_rebuilt: bool = True,
                  health_status: int = 200,
                  agent_ai_routes_present: bool = True,
                  openai_key_in_env: bool = True,
                  agent_ai_health_ok: bool = True,
                  bad_token_rejected: bool = True,
                  live_chat_ok: bool = True,
                  external_call_count: int = 0,
                  api_key_leak: bool = False,
                  device_token_leak: bool = False,
                  raw_chat_history_saved: bool = False,
                  ) -> DeployVerdict:
    metrics = {
        "server_head_matches_local": server_head_matches_local,
        "container_rebuilt": container_rebuilt,
        "health_status": health_status,
        "agent_ai_routes_present": agent_ai_routes_present,
        "openai_key_in_env": openai_key_in_env,
        "agent_ai_health_ok": agent_ai_health_ok,
        "bad_token_rejected": bad_token_rejected,
        "live_chat_ok": live_chat_ok,
        "external_call_count": external_call_count,
        "api_key_leak": api_key_leak,
        "device_token_leak": device_token_leak,
        "raw_chat_history_saved": raw_chat_history_saved,
    }

    if api_key_leak:
        return DeployVerdict(False, "FAIL_OPENAI_KEY_LEAK",
                              reasons=["API key 원문 leak 감지"],
                              metrics=metrics)
    if device_token_leak:
        return DeployVerdict(False, "FAIL_DEVICE_TOKEN_LEAK",
                              reasons=["device_token 원문 leak 감지"],
                              metrics=metrics)
    if raw_chat_history_saved:
        return DeployVerdict(False, "FAIL_RAW_CHAT_HISTORY_SAVED",
                              reasons=["chat history 디스크 저장 감지"],
                              metrics=metrics)

    if not server_head_matches_local:
        return DeployVerdict(False, "FAIL_SERVER_NOT_UPDATED",
                              reasons=["server HEAD != local HEAD"],
                              metrics=metrics)
    if not container_rebuilt:
        return DeployVerdict(False, "FAIL_CONTAINER_NOT_REBUILT",
                              reasons=["docker compose build 미수행"],
                              metrics=metrics)
    if health_status != 200:
        return DeployVerdict(False, "FAIL_HEALTHCHECK_FAILED",
                              reasons=[f"/api/v1/health = {health_status}"],
                              metrics=metrics)
    if not agent_ai_routes_present:
        return DeployVerdict(False, "FAIL_AGENT_AI_ROUTE_MISSING",
                              reasons=["agent-ai router mount 안 됨"],
                              metrics=metrics)
    if not openai_key_in_env:
        return DeployVerdict(False, "FAIL_OPENAI_API_KEY_MISSING",
                              reasons=["서버 env 에 OPENAI_API_KEY 없음"],
                              metrics=metrics)
    if not bad_token_rejected:
        return DeployVerdict(False, "FAIL_AGENT_AUTH_BROKEN",
                              reasons=["bad token 거부 안 됨"],
                              metrics=metrics)
    if not agent_ai_health_ok:
        return DeployVerdict(False, "FAIL_AGENT_AUTH_BROKEN",
                              reasons=["agent-ai/health 정상 token 거부됨"],
                              metrics=metrics)
    if not live_chat_ok:
        return DeployVerdict(False, "FAIL_OPENAI_PROXY_LIVE_CALL_FAILED",
                              reasons=["live chat smoke 실패"],
                              metrics=metrics)
    if external_call_count < 1:
        return DeployVerdict(False, "FAIL_OPENAI_PROXY_LIVE_CALL_FAILED",
                              reasons=["external_call_count < 1"],
                              metrics=metrics)

    return DeployVerdict(True, "PASS_DEPLOY_OPENAI_PROXY_TO_PROD",
                          reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics-json", type=str, default=None,
                    help="metrics 를 외부 JSON 으로 입력")
    args = ap.parse_args(argv)
    if args.metrics_json:
        with open(args.metrics_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = judge_deploy(**data)
    else:
        v = judge_deploy()
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
