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

## 3. Baseline Contract Answers

- Input/output contract:
- Authorization boundary:
- State changes:
- Regression gate:

## 4. Function-Level Explanation

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

## 5. Verification

- Syntax checks:
- Unit tests:
- Contract audits:
- Module gates:
- Required gate:
- Live checks:
- Skipped checks and reason:

## 6. Findings

- PASS:
- WARN:
- FAIL:
- Remaining risk:

## 7. Prohibited Actions Check

- Secret value output:
- OUT_OF_SCOPE modification/staging:
- Docker/server deploy:
- Build/installer/portable package:
- Push:

## 8. Final Verdict

Use one explicit verdict:

```text
PASS_<TASK_NAME>
WARN_<TASK_NAME>_<REASON>
FAIL_<TASK_NAME>_<REASON>
```

## 9. Next Work

- Recommended next task:
- Required approval before next task:

