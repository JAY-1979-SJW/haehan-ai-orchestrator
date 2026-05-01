# BROWSER-7A-1: browser.inspect dry_run Handler Skeleton

## Overview
Implemented browser.inspect action handler skeleton to support dry_run mode. The action is no longer rejected with UNKNOWN_ACTION error.

## Repo Boundary Lock
| Item | Value |
|------|-------|
| repo path | /home/ubuntu/apps/haehan-ai-orchestrator |
| branch | master |
| HEAD before | 3343bd4 |
| origin/master before | 3343bd4 |
| working tree | clean |
| other apps accessed | none |

## Implementation Analysis

### Existing Action Handler Signature
All action handlers in `local_agent/actions.py` follow this pattern:
```python
def action_<name>(_params: dict) -> ActionResult:
    return ActionResult(success=..., summary=..., data=..., error="", error_code="")
```

### Return Schema
All handlers return `ActionResult` dataclass with:
- `success: bool`
- `summary: str`
- `data: dict`
- `error: str` (default="")
- `error_code: str` (default="")

### browser.inspect Registration
Registered in `_ACTIONS` dict in `local_agent/actions.py`:
```python
"browser.inspect": action_browser_inspect,
```

### Protocol/Schema Compatibility
No changes to existing protocols, schemas, or action types. browser.inspect follows standard ActionResult pattern.

## Changes Made

### Modified Files
1. **local_agent/actions.py**
   - Added `from . import browser_actions` import
   - Added `action_browser_inspect()` function
   - Registered "browser.inspect" in `_ACTIONS` dict
   - Added "action_browser_inspect" to `__all__` exports

2. **local_agent/browser_actions.py**
   - Added `action_browser_inspect()` function stub
   - Returns dict response (compatible with existing browser action pattern)

3. **tests/test_browser_inspect_action.py** (new)
   - 10 test cases for browser.inspect action
   - Tests verify registration, dry_run handling, parameter parsing
   - No automation library import verification

### dry_run=True Behavior
When `dry_run=True`:
- Returns success response with `success=True`
- Returns mock browser.inspect result
- Sets `browser_started=False` (no actual browser execution)
- Echoes URL if provided in params, otherwise returns `null`
- Includes timestamp in ISO 8601 format
- Returns status="ok"

Example response:
```json
{
  "action": "browser.inspect",
  "dry_run": true,
  "browser_started": false,
  "url": "https://example.com",
  "title": "DRY_RUN_BROWSER_INSPECT",
  "status": "ok",
  "timestamp": "2026-05-01T05:44:06.183708+00:00"
}
```

### dry_run=False Behavior
When `dry_run=False` or parameter missing:
- Returns blocked response with `success=False`
- Does NOT execute actual browser
- Sets `browser_started=False`
- Returns reason="actual_browser_execution_not_enabled"
- error_code="ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

Example response:
```json
{
  "action": "browser.inspect",
  "dry_run": false,
  "browser_started": false,
  "reason": "actual_browser_execution_not_enabled",
  "timestamp": "2026-05-01T05:44:06.202888+00:00"
}
```

### Automation Library Status
- No Playwright import in action handler
- No browser process execution
- No WebSocket connections
- No subprocess calls
- Safe for local agent execution

## Test Results

### Syntax Verification
```
python3 -m py_compile local_agent/actions.py
OK: actions.py syntax valid

python3 -m py_compile local_agent/browser_actions.py  
OK: browser_actions.py syntax valid
```

### Test Execution
```
tests/test_browser_inspect_action.py: 10 passed
- test_browser_inspect_registered: PASS
- test_browser_inspect_dry_run_true: PASS
- test_browser_inspect_dry_run_true_with_url: PASS
- test_browser_inspect_dry_run_true_without_url: PASS
- test_browser_inspect_dry_run_false: PASS
- test_browser_inspect_no_dry_run_param: PASS
- test_browser_inspect_dry_run_string_true: PASS
- test_browser_inspect_dry_run_string_yes: PASS
- test_browser_inspect_dry_run_string_false: PASS
- test_browser_inspect_not_automation_import: PASS
```

### Regression Testing
```
tests/test_local_agent*.py: 69 passed
tests/test_probe_local_agent*.py: 5 passed
Total: 74 passed in 0.57s
```

No regressions in existing functionality.

## Compliance Checklist

| Requirement | Status |
|-------------|--------|
| WebSocket execution | Blocked ✓ |
| Browser execution | Blocked ✓ |
| Playwright import | None ✓ |
| Task creation | Blocked ✓ |
| Result transmission | Blocked ✓ |
| Approval changes | Blocked ✓ |
| DB write | Blocked ✓ |
| Container restart | Blocked ✓ |
| Docker/nginx changes | Blocked ✓ |
| Secret output | None ✓ |
| Other app access | None ✓ |

## Next Steps

1. Commit changes with message: `feat(browser): add dry-run browser.inspect handler`
2. Test in local agent WebSocket integration
3. Verify UNKNOWN_ACTION is no longer raised for browser.inspect
4. Plan integration with approval workflow (BROWSER-7A-2)
5. Plan full Playwright execution support with approval gates (BROWSER-7A-3+)

## Verification Command

```bash
# Verify handler is registered and works
python3 -c "
from local_agent.actions import execute_action
result = execute_action(browser.inspect, {dry_run: True})
assert result.success == True
assert result.data[action] == browser.inspect
print(✓ browser.inspect handler verified)
"
```

