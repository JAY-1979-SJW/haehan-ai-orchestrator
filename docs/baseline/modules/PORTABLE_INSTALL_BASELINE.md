# HAEHAN Portable Install Baseline

Status: LOCKED
Baseline ID: HAEHAN-PORTABLE-INSTALL-BASELINE-01
Approved by: user approval in current Codex session
Baseline HEAD: aa5a309db47fe3e651792aa9130e47fc63952960
Last updated: 2026-05-24

## 1. Purpose

This document locks the `portable_install` module contract. Portable install is
the first official no-admin user distribution flow. It must support
install/start/diagnostics/uninstall from an extracted folder without modifying
system-wide locations or exposing secrets.

Portable install is not an installer exe build.

## 2. Responsibility

`portable_install` owns:

- `install.bat`
- `start.bat`
- `diagnostics.bat`
- `uninstall.bat`
- `README_실행방법.txt`
- no-admin install flow
- logs/config folder creation
- desktop shortcut creation
- desktop shortcut removal
- secret-masked diagnostics
- portable static verification

## 3. Input Contract

Allowed inputs:

- extracted portable folder
- user runs `install.bat`
- user runs `start.bat`
- user runs `diagnostics.bat`
- user runs `uninstall.bat`
- local runtime config

Rejected inputs:

- installer exe build request
- Program Files install request
- registry modification request
- PATH modification request
- Docker or server deploy request
- request to print secret values
- request to delete app, logs, or config during uninstall

## 4. Output Contract

Allowed outputs:

- desktop shortcut
- logs folder
- config folder
- diagnostics log
- safe start guidance
- shortcut removal only on uninstall
- static verifier PASS/WARN/FAIL summary

Forbidden outputs:

- raw secret, token, cookie, session, password, OTP, or Authorization header
- installer exe
- portable zip artifact unless explicitly approved
- build output
- registry changes
- PATH changes
- deleted app/logs/config data

## 5. Install Boundary

Required rules:

- `install.bat` must run without administrator rights.
- Paths must be based on the current extracted folder.
- Installation may create `logs` and `config` folders.
- Installation may create a desktop shortcut.
- Installation must not copy files into Program Files.
- Installation must not edit registry.
- Installation must not edit PATH.
- Installation must not build installer exe.

## 6. Start Boundary

Required rules:

- `start.bat` must start from the current folder.
- Failure must guide the user to `diagnostics.bat`.
- Start flow must not print raw secrets.
- Start flow must not trigger build, deploy, Docker, or installer actions.

## 7. Diagnostics And Redaction Boundary

Required rules:

- `diagnostics.bat` may check required files, ports, and environment.
- Diagnostics logs must be saved under `logs/`.
- Diagnostics filename should include timestamp.
- Diagnostics must mask secrets.
- Diagnostics must not print raw secret, token, cookie, session, password, OTP,
  or Authorization header.

## 8. Uninstall Boundary

Required rules:

- `uninstall.bat` removes shortcuts only.
- `uninstall.bat` must not delete app files.
- `uninstall.bat` must not delete logs.
- `uninstall.bat` must not delete config.
- Uninstall must not edit registry or PATH.

## 9. Forbidden Portable Behavior

Portable install code must not:

- build installer exe
- create portable zip artifact without explicit approval
- copy to Program Files
- edit registry
- edit PATH
- delete app/logs/config
- print raw secrets
- run Docker
- deploy server
- start unrelated apps

## 10. Allowed Paths

Portable install work may modify portable `.bat` files, README execution guide,
portable install verifier, and focused portable install tests only when the task
explicitly approves those paths.

Baseline and gate work may modify:

```text
docs/baseline/modules/PORTABLE_INSTALL_BASELINE.md
docs/baseline/MODULE_BASELINE.md
scripts/ops/audit_portable_install_baseline_contract.py
tools/quality/module_quality_gate.py
tools/quality/required_quality_gate.py
tests/test_portable_install_baseline_contract.py
tests/test_module_quality_gate.py
tests/test_required_quality_gate.py
```

## 11. Required Verification

Baseline verification:

```text
python scripts/ops/audit_portable_install_baseline_contract.py
python -m pytest tests/test_portable_install_baseline_contract.py -q
```

Runtime/static verification:

```text
python tools/quality/module_quality_gate.py --module portable_install
python tools/quality/module_quality_gate.py --module repo_guard
python tools/quality/required_quality_gate.py
```

Actual portable zip creation is separate and requires explicit approval.

## 12. Known WARN

- Actual ZIP creation is a separate approved stage.
- Actual user PC execution is a separate approved runtime stage.
- Installer exe remains a separate stage.
- Runtime executable presence may be WARN until packaging stage.

## 13. Learning Notes

Portable install differs from an installer because it runs from an extracted
folder and avoids system-wide changes.

Avoiding Program Files, registry, and PATH reduces permission requirements and
prevents hard-to-recover system changes.

Diagnostics need secret masking because diagnostic files are often shared for
support.

Uninstall must preserve logs and config so users do not lose diagnostics or
settings by removing a shortcut.

Static verifier catches unsafe install behavior before any packaging or live
execution stage.

## 14. Baseline Change Rule

Any portable install change that weakens no-admin behavior, secret masking,
uninstall preservation, or build/deploy separation must be handled as:

```text
portable_install baseline proposal
-> user approval
-> baseline update
-> audit/test/gate update
-> verification
-> report
```

