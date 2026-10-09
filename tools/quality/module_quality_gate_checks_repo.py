"""Repository-guard check functions for module_quality_gate."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys

try:
    from tools.quality.module_quality_gate_common import (
        PY,
        ROOT,
        _run_check_command,
        all_steps,
        command_is_forbidden,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
    )
except ModuleNotFoundError:
    from module_quality_gate_common import (  # type: ignore[no-redef, import-not-found]
        PY,
        ROOT,
        _run_check_command,
        all_steps,
        command_is_forbidden,
        find_staged_out_of_scope,
        git_staged_paths,
        normalize_path,
    )

sys.dont_write_bytecode = True


def imports_local_agent(text: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s*(?:from\s+local_agent(?:\.|\s+import\b)|import\s+local_agent(?:\.|\s|$))",
            text,
        )
    )


def check_out_of_scope_not_staged() -> tuple[bool, str]:
    staged = find_staged_out_of_scope(git_staged_paths())
    if staged:
        return False, "OUT_OF_SCOPE staged: " + ", ".join(staged)
    return True, "OUT_OF_SCOPE files are not staged"


def check_forbidden_command_matrix() -> tuple[bool, str]:
    offenders = [step.name for step in all_steps() if step.command and command_is_forbidden(step.command)]
    if offenders:
        return False, "forbidden commands in module gate matrix: " + ", ".join(offenders)
    return True, "module gate matrix contains no build/deploy/push commands"


def check_local_agent_browser_runtime_rules() -> tuple[bool, str]:
    doc = ROOT / "docs" / "architecture" / "local_agent_browser_runtime_operating_rules_20260523.md"
    dry_run = ROOT / "tools" / "verify" / "dry_run_local_agent_cdp_attach.py"
    tests = ROOT / "tests" / "test_local_agent_browser_runtime_operating_rules.py"
    monitor = ROOT / "scripts" / "archive" / "misc" / "chrome_ui_monitor.py"
    cdp_client = ROOT / "scripts" / "browser" / "cdp_client.py"

    required_files = (doc, dry_run, tests, monitor, cdp_client)
    missing = [normalize_path(str(path.relative_to(ROOT))) for path in required_files if not path.exists()]
    if missing:
        return False, "missing browser runtime gate file(s): " + ", ".join(missing)

    doc_text = doc.read_text(encoding="utf-8", errors="replace")
    required_doc_phrases = (
        "Status: LOCKED",
        "CDP attach is local-only",
        "CDP discovery is read-only",
        "CDP output is redacted",
        "Automated browser execution uses a dedicated profile",
        "Runtime state must not be written under `scripts/archive`",
    )
    missing_phrases = [phrase for phrase in required_doc_phrases if phrase not in doc_text]
    if missing_phrases:
        return False, "browser runtime policy doc missing phrase(s): " + ", ".join(missing_phrases)

    runtime_state_literal = '"data" / "runtime" / "chrome_ui_monitor_state.json"'
    archive_state_literal = '"data" / "chrome_ui_monitor_state.json"'
    for path in (monitor, cdp_client):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = normalize_path(str(path.relative_to(ROOT)))
        if runtime_state_literal not in text:
            return False, f"{rel} does not use data/runtime chrome UI monitor state"
        if archive_state_literal in text:
            return False, f"{rel} still references archive/data chrome UI monitor state"

    dry_run_text = dry_run.read_text(encoding="utf-8", errors="replace")
    if "chrome_ui_monitor_runtime_path" not in dry_run_text:
        return False, "CDP attach dry-run does not enforce chrome UI monitor runtime path"

    ok, message = _run_check_command(
        [
            PY,
            "-m",
            "pytest",
            "tests/test_local_agent_browser_runtime_operating_rules.py",
            "tests/test_local_agent_cdp_attach.py",
            "tests/test_dry_run_local_agent_cdp_attach.py",
            "-p",
            "no:cacheprovider",
            "-q",
        ],
        timeout=180,
    )
    if not ok:
        return False, "browser runtime operating rule pytest failed: " + message
    return True, "browser runtime operating rules are locked by policy, dry-run, and pytest"


# 서버 CI 는 사용자 지시(2026-09-29)로 GitHub Actions 의 ci.yml 하나만 허용한다. 그 외 워크플로 파일은 계속 금지.
# 2026-10-07 대표님 승인(데스크톱 앱 릴리스 빌드, 저녁 계획 18:10)으로 desktop-release.yml 1개를 추가 허용한다(configs/module_boundaries.json 의 allowed_exceptions 와 같은 목록).
_ALLOWED_WORKFLOW_FILES = frozenset({"ci.yml", "desktop-release.yml"})


# 훅 파일별로 존재해야 하는 현행 게이트 호출 문자열(없으면 FAIL).
_REQUIRED_HOOK_NEEDLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pre-commit", ("commit_checklist", "pre-commit.orig")),
    (
        "pre-commit.orig",
        (
            "ruff_new_only_gate",
            "skeleton_gate",
            "audit_kit_gate",
            '"--staged"',
            "quality_gate",
            # 2026-10-08 PR #162 사고: 설치기가 정본을 덮어써 아래 게이트 연결 96줄이 사라진 채 커밋됐다 — 다시 빠지면 막는다
            "move_preflight",
            "tool_home_gate",
            "flat_root_gate",
            "bundle_path_gate",
            "folder_gate",
            "root_calc_gate",
            "audit_r1_api_contract_gate",
            "dup_gate",
        ),
    ),
    ("pre-push", ("ai_code_review_gate",)),
)


def _local_gate_file_failure(required_gate, pre_commit, pre_commit_orig, pre_push) -> tuple[bool, str] | None:
    workflows_dir = ROOT / ".github" / "workflows"
    workflow_files = []
    if workflows_dir.exists():
        workflow_files = [
            normalize_path(str(path.relative_to(ROOT)))
            for path in workflows_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".yml", ".yaml"} and path.name not in _ALLOWED_WORKFLOW_FILES
        ]
    if workflow_files:
        return False, "GitHub Actions workflow files are forbidden: " + ", ".join(sorted(workflow_files))

    required_files = (required_gate, pre_commit, pre_commit_orig, pre_push)
    missing = [normalize_path(str(path.relative_to(ROOT))) for path in required_files if not path.exists()]
    if missing:
        return False, "missing required local gate file(s): " + ", ".join(missing)

    # 현행 훅 구조(f6a169ae 2026-05-31 재작성 이후, 설치기 tools/hooks/install_git_hooks.py):
    #   pre-commit(래퍼) -> pre-commit.orig 위임, pre-commit.orig 가 핵심 게이트들을 호출,
    #   pre-push -> ai_code_review_gate.py. required_quality_gate.py 는 더 이상 훅에서
    #   호출되지 않는다(그 미연결 자체는 의도 미확인 — 훅 변경은 이 검사기의 범위 밖).
    for hook_name, needles in _REQUIRED_HOOK_NEEDLES:
        hook = ROOT / ".githooks" / hook_name
        if not hook.exists():
            return False, f"missing required local gate file(s): .githooks/{hook_name}"
        text = hook.read_text(encoding="utf-8", errors="replace")
        missing_calls = [needle for needle in needles if needle not in text]
        if missing_calls:
            return False, f".githooks/{hook_name} is missing gate call(s): " + ", ".join(missing_calls)
    return None


def check_required_local_gate_wiring() -> tuple[bool, str]:
    required_gate = ROOT / "tools" / "quality" / "required_quality_gate.py"
    pre_commit = ROOT / ".githooks" / "pre-commit"
    pre_commit_orig = ROOT / ".githooks" / "pre-commit.orig"
    pre_push = ROOT / ".githooks" / "pre-push"
    failure = _local_gate_file_failure(required_gate, pre_commit, pre_commit_orig, pre_push)
    if failure is not None:
        return failure

    spec = importlib.util.spec_from_file_location("required_quality_gate", required_gate)
    if spec is None or spec.loader is None:
        return False, "required_quality_gate import spec failed"
    required_gate_mod = importlib.util.module_from_spec(spec)
    try:
        sys.modules[spec.name] = required_gate_mod
        spec.loader.exec_module(required_gate_mod)
    except Exception as exc:  # noqa: BLE001 - 저장소 품질게이트 점검 함수(check_required_local_gate_wiring) - required_quality_gate 모듈 동적 import 실패 시 (False, 사유) 튜플을 반환해 해당 점검이 FAIL 처리됨(=커밋/게이트 차단 방향), 이전에 실제 버그였던 execution_policy_service.py의 fail-open(허용 방향 폴백)과 반대로 이 함수는 실패를 차단 방향으로 전파하는 fail-closed 구조임을 확인
        return False, f"required_quality_gate import failed: {type(exc).__name__}"

    offenders = [
        required_gate_mod.command_text(command)
        for command in required_gate_mod.COMMANDS
        if required_gate_mod.command_is_forbidden(command)
    ]
    if offenders:
        return False, "required gate contains forbidden command(s): " + "; ".join(offenders)

    required_rendered = "\n".join(required_gate_mod.command_text(command) for command in required_gate_mod.COMMANDS)
    required_needles = (
        "tools/verify/dry_run_local_agent_cdp_attach.py",
        "tests/test_local_agent_browser_runtime_operating_rules.py",
        "tests/test_local_agent_cdp_attach.py",
        "tests/test_dry_run_local_agent_cdp_attach.py",
        "tests/test_common_tool_runtime.py",
        "tests/app_contracts/test_common_tool_runtime_baseline_contract.py",
        "tests/app_contracts/test_common_engine_commercialization_baseline.py",
        "tests/test_local_agent_connection_recovery_baseline.py",
        "tests/desktop/test_desktop_auth_runtime_baseline_contract.py",
        "tests/test_local_agent_e2e_flow_contract.py",
        "tests/app_contracts/test_app_baseline_contract.py",
        "tests/app_contracts/test_standard_workflow_contract.py",
        "tests/app_contracts/test_module_baseline_contract.py",
        "tests/app_contracts/test_backend_core_baseline_contract.py",
        "tests/test_local_agent_e2e_baseline_contract.py",
        "tools/audits/agent/audit_common_tool_runtime.py",
        "tools/audits/agent/audit_common_tool_runtime_baseline_contract.py",
        "tools/audits/app/audit_common_engine_commercialization_baseline.py",
        "tools/audits/agent/audit_local_agent_connection_recovery_baseline.py",
        "tools/audits/agent/audit_desktop_auth_runtime_baseline_contract.py",
        "tools/audits/agent/audit_local_agent_e2e_flow_contract.py",
        "tools/audits/app/audit_app_baseline_contract.py",
        "tools/audits/app/audit_standard_workflow_contract.py",
        "tools/audits/app/audit_module_baseline_contract.py",
        "tools/audits/backend/audit_backend_core_baseline_contract.py",
        "tools/audits/agent/audit_local_agent_e2e_baseline_contract.py",
        "tools/audits/app/audit_approval_flow_baseline_contract.py",
        "tools/audits/agent/audit_playwright_ai_baseline_contract.py",
        "tools/repo_gates/audit_root_legacy_scripts.py",
        "tests/approval/test_approval_flow_baseline_contract.py",
        "tests/app_contracts/test_playwright_ai_baseline_contract.py",
        "tests/quality_gates/test_required_quality_gate.py",
        "tests/quality_gates/test_root_legacy_scripts_audit.py",
        "tools/quality/module_quality_gate.py --module repo_guard",
    )
    missing_needles = [needle for needle in required_needles if needle not in required_rendered]
    if missing_needles:
        return False, "required gate missing command target(s): " + ", ".join(missing_needles)

    config = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    hooks_path = normalize_path(config.stdout.strip()) if config.returncode == 0 else ""
    # 설치기가 절대경로(<저장소>/.githooks)로 설정하는 환경도 현행 구조로 인정한다.
    if hooks_path != ".githooks" and not hooks_path.endswith("/.githooks"):
        return False, "core.hooksPath must be .githooks; run python tools/hooks/install_git_hooks.py"

    return True, "required local gate is wired through pre-commit/pre-push and Actions are disabled"


def check_module_boundary_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "tools/audits/app/audit_module_boundaries.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "module boundary map and audit pass"


def check_root_legacy_script_contract() -> tuple[bool, str]:
    ok, message = _run_check_command(
        [PY, "tools/repo_gates/audit_root_legacy_scripts.py"],
        timeout=120,
    )
    if not ok:
        return False, message
    return True, "root legacy script inventory is classified and locked"
