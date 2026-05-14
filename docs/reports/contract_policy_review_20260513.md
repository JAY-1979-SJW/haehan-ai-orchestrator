# Contract And Policy Review - 2026-05-13

## Scope

Reviewed `contract_or_policy` changes after the worktree cleanup pass.

Primary files:

- `.gitignore`
- `configs/common_operations_index.json`
- `configs/site_automation_status_index.json`
- `configs/quality_gate.json`
- `configs/codebase_layer_audit.json`
- `ai_orchestrator/local_agent_models.py`
- `security_utils.py`
- `scripts/security.py`
- `logging_utils.py`
- `scripts/credentials.py`
- `scripts/gate.py`
- `scripts/schemas.py`
- `scripts/validate_site_policy_config.py`

## Findings

### Runtime Artifact Policy

`.gitignore` now keeps generated `data/` artifacts local by default. This
reduces accidental commits of site automation output, downloaded evidence,
screenshots, JSONL queues, and generated HTML. Curated evidence must be
promoted to `docs/reports/` or `tests/fixtures/`, or explicitly added with
`git add -f`.

### Common Indexes

G2B is now present in both common and site status indexes. Google completion
links now point to the surface exploration completion report.

### Local Agent Contract

`ai_orchestrator/local_agent_models.py` no longer imports individual registry
functions directly inside `to_safe()`. It uses `importlib.import_module()` for
the registry module lookup. The codebase layer audit now reports:

- circular import cycles: `0`
- tracked open residuals: `0`
- consistency: `ok`

The previous circular import residual has been moved out of
`tracked_residuals` and recorded under `resolved_residuals`.

### Security And Credentials

`security_utils.py` is the shared redaction helper. `scripts/security.py` and
`logging_utils.py` are compatibility facades over the same redaction behavior.
`scripts/credentials.py` stores passwords encrypted with Fernet and masks IDs
in CLI output.

CLI check:

```text
저장된 사이트 (3개):
  eum              id=sm***r7                          [✓]
  naver            id=sk***in                          [✓]
  google           id=sk***@gmail.com                  [✓]
```

### Site Policy Validator

`scripts/validate_site_policy_config.py` remains as a compatibility entrypoint
and delegates to `scripts/archive/one_off/validate_site_policy_config.py`.
The CLI path was fixed so direct execution works from the repository root.

## Verification

```powershell
python -m pytest tests\test_validate_site_policy_config_20260509.py tests\test_codebase_layer_audit.py tests\test_credentials_cli_security.py tests\test_security.py tests\test_naver_auth_redaction.py -q --basetemp=C:\tmp\pytest_contract_policy_final
python -m py_compile scripts\validate_site_policy_config.py scripts\archive\one_off\validate_site_policy_config.py security_utils.py scripts\security.py logging_utils.py scripts\credentials.py scripts\gate.py scripts\schemas.py ai_orchestrator\local_agent_models.py
python scripts\validate_site_policy_config.py configs\site_policies
python scripts\quality_gate.py --allow-existing-code-change
python scripts\ops\worktree_change_index.py
```

Results:

- Focused contract/security/policy tests: `26 passed`
- `py_compile`: passed
- Site policy config CLI: G2B, Hometax, MSS all passed
- Quality gate with intentional existing-code approval: `errors: 0`,
  `warnings: 0`
- Worktree index regenerated

`python scripts\ops\codebase_layer_audit.py` still exits `1` because the
repository has 809 pre-existing structural warnings, mostly root-level scripts.
For this scope, config consistency is OK and circular import cycles are 0.

## Next Scope

Proceed owner by owner. The next practical scope is `eum` because it has the
largest completed baseline and matching reports/tests, followed by `google`,
`naver`, and `smartstore`.

