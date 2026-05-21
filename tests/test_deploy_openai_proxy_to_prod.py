"""DEPLOY_OPENAI_PROXY_TO_PROD_01 audit + report 검증 (offline)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPORT = Path("data/inspection/deploy_openai_proxy_to_prod/deploy_report.json")
AUDIT_MOD = "scripts.ops.audit_deploy_openai_proxy_to_prod"


# ── 1) 보고서 존재 / 스키마 ─────────────────────────────


def test_report_exists():
    assert REPORT.exists()


def test_report_is_json():
    json.loads(REPORT.read_text(encoding="utf-8"))


def test_report_required_keys():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    for k in ("server_head_matches_local", "container_rebuilt",
              "health_status", "agent_ai_routes_present",
              "openai_key_in_env", "agent_ai_health_ok",
              "bad_token_rejected", "live_chat_ok",
              "live_chat_external_call_count",
              "api_key_leak", "device_token_leak",
              "raw_chat_history_saved"):
        assert k in d, f"missing: {k}"


# ── 2) leak 검사 — 보고서 자체 ───────────────────────


def test_report_no_raw_api_key():
    text = REPORT.read_text(encoding="utf-8")
    matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", text)
    real = [m for m in matches if "A-Za-z" not in m]
    assert real == []


def test_report_no_raw_device_token():
    text = REPORT.read_text(encoding="utf-8")
    assert not re.search(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"', text)


def test_report_key_value_not_in_response():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    storage = d.get("openai_key_storage", {})
    assert storage.get("value_in_response") is False


def test_report_agent_id_masked():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    aid = d.get("agent_id_masked_used", "")
    # 마스킹 형식 (la-xxx***yyyy) 만 허용
    assert "***" in aid


# ── 3) 라이브 결과 ─────────────────────────────────


def test_live_chat_external_call_count_at_least_one():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["live_chat_external_call_count"] >= 1


def test_live_chat_ok():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["live_chat_ok"] is True
    assert d["live_chat_response_length"] > 0


def test_bad_token_returns_401():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["bad_token_rejected"] is True
    assert d["bad_token_status"] == 401


def test_health_200():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["health_status"] == 200


def test_routes_present():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["agent_ai_routes_present"] is True
    assert "/agent-ai/chat" in d["agent_ai_routes"]
    assert "/agent-ai/health" in d["agent_ai_routes"]


# ── 4) 응답 전문 미저장 (preview cap) ─────────────


def test_response_preview_under_80():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    preview = d.get("live_chat_response_preview", "")
    assert len(preview) <= 80


def test_raw_chat_history_saved_false():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert d["raw_chat_history_saved"] is False


# ── 5) key 저장 정책 ──────────────────────────────


def test_key_storage_uses_locked_file():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    s = d["openai_key_storage"]
    assert s["method"] == "locked_file_env_file"
    assert s["permissions"] == "0400"
    assert "haehan-secrets" in s["path"]


def test_compose_override_gitignored():
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    assert "gitignored" in d["openai_key_storage"]["compose_override"].lower()


# ── 6) audit verdict ─────────────────────────────


def test_audit_pass_with_report_metrics():
    """보고서의 metrics 를 audit 에 입력해 PASS 확인."""
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    v = a.judge_deploy(
        server_head_matches_local=d["server_head_matches_local"],
        container_rebuilt=d["container_rebuilt"],
        health_status=d["health_status"],
        agent_ai_routes_present=d["agent_ai_routes_present"],
        openai_key_in_env=d["openai_key_in_env"],
        agent_ai_health_ok=d["agent_ai_health_ok"],
        bad_token_rejected=d["bad_token_rejected"],
        live_chat_ok=d["live_chat_ok"],
        external_call_count=d["live_chat_external_call_count"],
        api_key_leak=d["api_key_leak"],
        device_token_leak=d["device_token_leak"],
        raw_chat_history_saved=d["raw_chat_history_saved"],
    )
    assert v.code == "PASS_DEPLOY_OPENAI_PROXY_TO_PROD", v.reasons


def test_audit_fail_api_key_leak():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(api_key_leak=True)
    assert v.code == "FAIL_OPENAI_KEY_LEAK"


def test_audit_fail_device_token_leak():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(device_token_leak=True)
    assert v.code == "FAIL_DEVICE_TOKEN_LEAK"


def test_audit_fail_raw_chat_history():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(raw_chat_history_saved=True)
    assert v.code == "FAIL_RAW_CHAT_HISTORY_SAVED"


def test_audit_fail_openai_key_missing():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(openai_key_in_env=False)
    assert v.code == "FAIL_OPENAI_API_KEY_MISSING"


def test_audit_fail_server_not_updated():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(server_head_matches_local=False)
    assert v.code == "FAIL_SERVER_NOT_UPDATED"


def test_audit_fail_route_missing():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(agent_ai_routes_present=False)
    assert v.code == "FAIL_AGENT_AI_ROUTE_MISSING"


def test_audit_fail_bad_token_not_rejected():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(bad_token_rejected=False)
    assert v.code == "FAIL_AGENT_AUTH_BROKEN"


def test_audit_fail_live_chat_failed():
    import importlib
    a = importlib.import_module(AUDIT_MOD)
    v = a.judge_deploy(live_chat_ok=False)
    assert v.code == "FAIL_OPENAI_PROXY_LIVE_CALL_FAILED"


# ── 7) 회귀 가드 ─────────────────────────────


def test_regression_proxy_router_intact():
    from ai_orchestrator import agent_ai_proxy_router as r
    assert hasattr(r, "agent_ai_proxy_router")
    assert hasattr(r, "ChatResponse")


def test_regression_caller_intact():
    from ai_orchestrator import openai_proxy_caller as c
    assert hasattr(c, "call_openai_chat")
    assert hasattr(c, "has_server_openai_key")


def test_regression_desktop_client_intact():
    from local_agent import server_proxy_chat_client as s
    assert hasattr(s, "ServerProxyChatClient")
