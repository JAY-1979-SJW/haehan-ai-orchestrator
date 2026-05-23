# Release Tooling Inventory

This document fixes the pre-release tool boundaries for the desktop portable
release path. The default release checks must stay static and must not build,
deploy, push, start Docker, or run external browser/service automation.

## Official Static Gates

- `python -m scripts.module_quality_gate --module all`
  - Runs static module checks only unless `--include-live` is explicitly passed.
  - Blocks build/deploy/push/Docker commands from the gate matrix.
- `python -m scripts.module_quality_gate --module release_preflight`
  - Runs admin-web typecheck/lint, production dependency audit, and
    active-source secret scan.
  - Development-only tool audit findings are tracked separately and do not
    block the portable runtime release unless they affect shipped code.
- `python verify_portable_zip_install.py --static-only`
  - Verifies portable install scripts without creating an installer.
- `python verify_local_runtime_dry_run.py`
  - Verifies local runtime readiness. Missing desktop exe is a packaging WARN,
    not a source-code failure.

## Official User Portable Tools

- `install.bat`
  - Creates local folders and desktop shortcut only.
- `start.bat`
  - Starts the app from the current portable folder.
- `diagnostics.bat`
  - Writes masked diagnostics to `logs/diagnostics_*.txt`.
- `uninstall.bat`
  - Removes shortcut only. It must not delete app files, logs, or config.

## Packaging Tools

These commands create `dist/` or build artifacts and are not part of static
preflight.

- `scripts/build_desktop_webview_app_windows.py`
  - Primary desktop executable packaging candidate for `HaehanAI-Desktop`.
- `scripts/build_desktop_agent_windows.py`
  - Agent executable packaging path. Keep separate from desktop portable
    packaging unless explicitly selected.
- `packaging/local-agent.spec`
  - Legacy/agent PyInstaller spec. Do not use as the desktop portable default.

## Live And Server Tools

These tools touch server, WebSocket, Docker, SSH, or live task dispatch. Run only
in an explicit live validation stage.

- `verify_agent_ws_auth.py`
- `verify_live_agent_smoke.py`
- `verify_live_task_dispatch.py`
- `scripts/deploy_dry_run.py`
- `scripts/check_compose_safe.sh`
- `scripts/ops/check_container_restart_counts.sh`
- `scripts/ops/smoke_*live*.py`
- `scripts/ops/live_*.py`

## Manual External Automation

These tools depend on local browser/CDP sessions or third-party web accounts and
must stay out of default release gates.

- `scripts/cdp_*.py`
- `scripts/chrome_ui_*.py`
- `scripts/google/**`
- `scripts/naver/**`
- `scripts/naver_mail/**`
- `scripts/local_agent/naver/**`
- `scripts/ops/audit_naver_*`
- `scripts/ops/verify_naver_*`

## Legacy And Archive

- `scripts/archive/**`
  - Historical/debug/reference material only.
  - Not part of release preflight or packaging.

## Release Rule

Before packaging, run the static gates and confirm `git status --short` is clean.
Only after a PASS should a separate packaging instruction run the PyInstaller or
portable artifact creation step.
