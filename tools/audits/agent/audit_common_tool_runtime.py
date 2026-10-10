"""Read-only audit for the common tool runtime contract."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_orchestrator.contracts.local_task_protocol import (  # noqa: E402
    build_task,
    validate_task,
)
from core.agent_runtime.runtime.common_tool_runtime import (  # noqa: E402
    EXECUTION_LOCAL_AGENT,
    PHASE_BLOCKED,
    RISK_READ,
    RISK_WRITE,
    TOOL_BROWSER,
    build_common_tool_task,
    dry_run_common_tool_flow,
    validate_common_tool_task,
)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    print("RESULT=FAIL_COMMON_TOOL_RUNTIME_AUDIT")
    return 1


def main() -> int:
    readonly = build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="browser.open_url.readonly",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        params={"target_url_host": "example.com"},
    )
    readonly_result = dry_run_common_tool_flow(readonly)
    if not readonly_result["ok"]:
        return _fail("readonly common browser task did not pass dry-run")

    write_without_approval = dict(readonly)
    write_without_approval.update(
        {
            "task_id": "write-without-approval",
            "action": "browser.submit_with_user_approval",
            "risk_level": RISK_WRITE,
            "requires_approval": True,
            "approval_id": None,
        }
    )
    blocked = dry_run_common_tool_flow(write_without_approval)
    if blocked["ok"] or blocked["phase"] != PHASE_BLOCKED:
        return _fail("approval-required task without approval was not blocked")

    sensitive_task = dict(readonly)
    sensitive_task["params"] = {"authorization": "Bearer <redacted>"}
    violations = validate_common_tool_task(sensitive_task)
    if not violations:
        return _fail("sensitive common tool field was not rejected")

    legacy_task = build_task(
        action="open_url",
        target_url="https://example.com",
        metadata={"purpose": "common-tool-runtime-audit"},
    )
    legacy_task["Authorization"] = "Bearer <redacted>"
    if not validate_task(legacy_task):
        return _fail("legacy task protocol did not reject forbidden auth field")

    print("[PASS] readonly common browser task dry-run")
    print("[PASS] approval-required task blocks without approval")
    print("[PASS] sensitive common tool fields rejected")
    print("[PASS] legacy task protocol still rejects auth headers")
    print("RESULT=PASS_COMMON_TOOL_RUNTIME_AUDIT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
