from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTABLE_FILES = [
    "install.bat",
    "start.bat",
    "diagnostics.bat",
    "uninstall.bat",
]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


def _readme() -> str:
    matches = sorted(ROOT.glob("README_*.txt"))
    assert matches, "README_*.txt is required for portable ZIP instructions"
    return matches[0].read_text(encoding="utf-8", errors="replace")


def test_task_receiver_has_no_hardcoded_admin_bearer() -> None:
    src = (ROOT / "desktop" / "task_receiver.py").read_text(encoding="utf-8", errors="replace")
    forbidden = [
        "Bearer admin-token",
        "Authorization\": \"Bearer admin-token",
        "Authorization': 'Bearer admin-token",
    ]
    for token in forbidden:
        assert token not in src
    assert "HAEHAN_DESKTOP_OPS_BASIC_USER" in src
    assert "HAEHAN_DESKTOP_OPS_BASIC_PASSWORD" in src


def test_portable_files_exist() -> None:
    for name in PORTABLE_FILES:
        assert (ROOT / name).is_file(), f"{name} missing"
    assert sorted(ROOT.glob("README_*.txt")), "portable README missing"
    assert (ROOT / "verify_portable_zip_install.py").is_file()


def test_install_bat_is_user_local_and_testable() -> None:
    src = _read("install.bat")
    required = [
        'pushd "%~dp0"',
        'if not exist "logs" mkdir "logs"',
        'if not exist "config" mkdir "config"',
        "HAEHAN_PORTABLE_DESKTOP_DIR",
        "HAEHAN_PORTABLE_SHORTCUT_NAME",
        "$shell.CreateShortcut($lnk)",
        "$shortcut.TargetPath=Join-Path $root 'start.bat'",
        "$shortcut.WorkingDirectory=$root",
    ]
    for item in required:
        assert item in src


def test_start_bat_is_portable_and_points_to_diagnostics_on_failure() -> None:
    src = _read("start.bat")
    required = [
        'pushd "%~dp0"',
        'set "APP_EXE="',
        "HaehanAI-Desktop.exe",
        'start "" "%APP_EXE%"',
        "Run diagnostics.bat",
    ]
    for item in required:
        assert item in src


def test_diagnostics_bat_masks_secret_values_and_writes_required_sections() -> None:
    src = _read("diagnostics.bat")
    required = [
        'set "REPORT=logs\\diagnostics_%TS%.txt"',
        "install_bat=present",
        "start_bat=present",
        "diagnostics_bat=present",
        "uninstall_bat=present",
        "readme=present",
        "desktop_exe=present",
        "Get-NetTCPConnection -LocalPort 8765",
        "secret_values_printed=false",
        "_present={1}",
    ]
    for item in required:
        assert item in src

    forbidden_value_patterns = [
        r"%OPENAI_API_KEY%",
        r"%ANTHROPIC_API_KEY%",
        r"%HAEHAN_DESKTOP_OPS_BASIC_PASSWORD%",
        r"Bearer\s+admin-token",
    ]
    for pattern in forbidden_value_patterns:
        assert re.search(pattern, src, flags=re.IGNORECASE) is None


def test_uninstall_bat_removes_only_shortcut_and_fails_closed() -> None:
    src = _read("uninstall.bat")
    required = [
        "HAEHAN_PORTABLE_DESKTOP_DIR",
        "HAEHAN_PORTABLE_SHORTCUT_NAME",
        "Remove-Item -LiteralPath $lnk -Force -ErrorAction Stop",
        "catch { Write-Error $_; exit 1 }",
        "App files, logs, and config were not deleted",
    ]
    for item in required:
        assert item in src

    destructive_patterns = [
        r"Remove-Item[^\n]*(logs|config|HaehanAI-Desktop\.exe)",
        r"\brmdir\b",
        r"\brd\s+/s\b",
        r"\bdel\s+/",
    ]
    for pattern in destructive_patterns:
        assert re.search(pattern, src, flags=re.IGNORECASE) is None


def test_portable_files_do_not_use_global_mutation_or_build_commands() -> None:
    combined = "\n".join(_read(name) for name in PORTABLE_FILES)
    forbidden_patterns = [
        r"\breg\s+add\b",
        r"\breg\.exe\b",
        r"\bsetx\s+PATH\b",
        r"\$env:PATH",
        r"SetEnvironmentVariable\([^)]*PATH",
        r"\bProgram Files\b",
        r"\bxcopy\b",
        r"\brobocopy\b",
        r"\bpyinstaller\b",
        r"\belectron-builder\b",
        r"\bdocker\b",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, combined, flags=re.IGNORECASE) is None


def test_portable_files_do_not_contain_secret_values() -> None:
    combined = "\n".join([_read(name) for name in PORTABLE_FILES] + [_readme()])
    secret_patterns = [
        r"Bearer\s+admin-token",
        r"Authorization.*admin-token",
        r"sk-proj-[A-Za-z0-9_-]{8,}",
        r"sk-ant-[A-Za-z0-9_-]{8,}",
        r"(password|token|secret|api[_-]?key)\s*=\s*[\"']?[A-Za-z0-9_-]{8,}",
    ]
    for pattern in secret_patterns:
        assert re.search(pattern, combined, flags=re.IGNORECASE) is None


def test_readme_documents_portable_flow_and_installer_hold() -> None:
    text = _readme()
    required = [
        "Portable ZIP + install.bat",
        "installer exe",
        "보류",
        "install.bat",
        "start.bat",
        "diagnostics.bat",
        "uninstall.bat",
        "Program Files",
        "registry",
        "PATH",
        "secret, token, password, API key",
        "오류 발생 시 복구",
        "uninstall.bat을 실행한 뒤 install.bat을 다시 실행합니다",
        "ZIP 파일을 새 폴더에 다시 압축 해제합니다",
        "python verify_portable_zip_install.py --static-only",
    ]
    for item in required:
        assert item in text


def test_verify_script_full_mode_passes_with_recovery_flow() -> None:
    result = subprocess.run(
        ["python", "verify_portable_zip_install.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "sandbox recovery: shortcut recreated" in result.stdout
    assert "RESULT=PASS" in result.stdout


def test_verify_script_static_mode_passes() -> None:
    result = subprocess.run(
        ["python", "verify_portable_zip_install.py", "--static-only"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT=PASS" in result.stdout


def test_diagnostics_bat_runtime_smoke_writes_complete_masked_log() -> None:
    before = set((ROOT / "logs").glob("diagnostics_*.txt"))
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "sk-proj-VERIFY-SHOULD-NOT-LEAK-1234567890"
    env["HAEHAN_DESKTOP_OPS_BASIC_PASSWORD"] = "verify-password-should-not-leak"

    result = subprocess.run(
        ["cmd", "/c", "diagnostics.bat"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    after = set((ROOT / "logs").glob("diagnostics_*.txt"))
    created = sorted(after - before, key=lambda p: p.stat().st_mtime)
    assert created, "diagnostics.bat did not create a new diagnostics log"
    text = created[-1].read_text(encoding="utf-8", errors="replace")

    required = [
        "HAEHAN_DESKTOP_PORTABLE_DIAGNOSTICS",
        "install_bat=present",
        "start_bat=present",
        "diagnostics_bat=present",
        "uninstall_bat=present",
        "readme=present",
        "port_8765=",
        "secret_values_printed=false",
        "OPENAI_API_KEY_present=True",
        "HAEHAN_DESKTOP_OPS_BASIC_PASSWORD_present=True",
    ]
    for item in required:
        assert item in text

    forbidden_values = [
        "sk-proj-VERIFY-SHOULD-NOT-LEAK-1234567890",
        "verify-password-should-not-leak",
    ]
    for value in forbidden_values:
        assert value not in text
