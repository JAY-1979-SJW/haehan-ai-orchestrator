# HAEHAN Standard Report Template

## 1. Baseline

- Task ID:
- Start HEAD:
- End HEAD:
- Git status:
- Approved scope:
- Out-of-scope files preserved:

## 2. Work Summary

- Goal:
- Changed files:
- Unchanged protected files:
- Build/deploy/push/installer status:

## 3. Agent Work Record

- User request summary:
- Agent role or execution mode:
- Approval status:
- Ordered work steps performed:
- Files, tools, commands, or runtime targets touched:
- Decisions and reasons:
- User-visible evidence path:
- Remaining risks or blocked work:
- Next approval needed:

## 4. Baseline Contract Answers

- Input/output contract:
- Authorization boundary:
- State changes:
- Regression gate:

## 5. Function-Level Explanation

For each changed function:

```text
Function:
Why it exists:
Input:
Output:
Failure behavior:
Security or state boundary:
How to think when writing it manually:
```

## 6. Verification

- Syntax checks:
- Unit tests:
- Contract audits:
- Module gates:
- Required gate:
- Live checks:
- Skipped checks and reason:

## 7. Findings

- PASS:
- WARN:
- FAIL:
- Remaining risk:

## 8. Prohibited Actions Check

- Secret value output:
- OUT_OF_SCOPE modification/staging:
- Docker/server deploy:
- Build/installer/portable package:
- Push:

## 9. Final Verdict

Use one explicit verdict:

```text
PASS_<TASK_NAME>
WARN_<TASK_NAME>_<REASON>
FAIL_<TASK_NAME>_<REASON>
```

## 10. Next Work

- Recommended next task:
- Required approval before next task:
