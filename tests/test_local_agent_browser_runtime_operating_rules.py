from pathlib import Path

import pytest

from core.agent_runtime.browser.cdp_attach import (
    CDPAttachValidationError,
    normalize_cdp_endpoint,
    summarize_cdp_tabs,
)
from scripts.archive.misc import chrome_ui_monitor

ROOT = Path(__file__).resolve().parents[1]
POLICY_DOC = ROOT / "docs" / "architecture" / "local_agent_browser_runtime_operating_rules_20260523.md"


def test_browser_runtime_operating_rules_doc_is_locked():
    text = POLICY_DOC.read_text(encoding="utf-8")

    required = [
        "Status: LOCKED",
        "CDP attach is local-only",
        "CDP discovery is read-only",
        "CDP output is redacted",
        "Automated browser execution uses a dedicated profile",
        "Runtime state must not be written under `scripts/archive`",
        "SSO_DIRECT_OAUTH_ENTRY_BLOCKED",
        "OAUTH_CLIENT_REDIRECT_SCOPE_MISMATCH",
        "Desktop app OAuth client JSON",
        "prefill non-secret browser form fields",
        "Final external create/save/submit/approve actions remain user-direct",
        "scripts/archive/data/chrome_ui_monitor_state.json",
        "data/runtime/",
    ]
    for phrase in required:
        assert phrase in text


def test_cdp_attach_operating_rule_rejects_non_loopback_hosts():
    with pytest.raises(CDPAttachValidationError):
        normalize_cdp_endpoint("192.168.0.2", 9222)
    with pytest.raises(CDPAttachValidationError):
        normalize_cdp_endpoint("haehan-ai.kr", 9222)


def test_cdp_tab_summary_operating_rule_redacts_debug_and_secret_url_parts():
    summary = summarize_cdp_tabs(
        [
            {
                "type": "page",
                "title": "Sensitive",
                "url": "https://user:pass@example.com/path?token=value#frag",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/abc",
            }
        ]
    )
    rendered = str(summary)

    assert summary["tabs"][0]["url"]["origin"] == "https://example.com"
    assert summary["tabs"][0]["url"]["has_query"] is True
    assert summary["tabs"][0]["url"]["has_fragment"] is True
    assert summary["tabs"][0]["url"]["has_credentials"] is True
    assert "token=value" not in rendered
    assert "user:pass" not in rendered
    assert "webSocketDebuggerUrl" not in rendered
    assert "ws://" not in rendered


def test_chrome_ui_monitor_operating_rule_uses_runtime_state_path():
    rel = chrome_ui_monitor.STATE_FILE.relative_to(chrome_ui_monitor.REPO_ROOT).as_posix()

    assert rel == "data/runtime/chrome_ui_monitor_state.json"
    assert "scripts/archive/data" not in rel


def test_dry_run_gate_locks_runtime_state_path_check():
    text = (ROOT / "tools" / "verify" / "dry_run_local_agent_cdp_attach.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "chrome_ui_monitor_runtime_path" in text
    assert '"data" / "runtime" / "chrome_ui_monitor_state.json"' in text
    assert "archive/data state path remains active" in text
