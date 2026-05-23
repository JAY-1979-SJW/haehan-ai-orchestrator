from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BAT_FILES = ["install.bat", "start.bat", "diagnostics.bat", "uninstall.bat"]
OUT_OF_SCOPE = [
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
]


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=90,
    )


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_repo(name: str) -> str:
    return read(ROOT / name)


def find_readme(base: Path = ROOT) -> Path | None:
    matches = sorted(base.glob("README_*.txt"))
    return matches[0] if matches else None


def has_all(text: str, needles: list[str]) -> tuple[bool, str]:
    missing = [needle for needle in needles if needle not in text]
    return not missing, ", ".join(missing)


def no_regex(text: str, patterns: list[str]) -> tuple[bool, str]:
    hits = [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]
    return not hits, ", ".join(hits)


def latest_diagnostics_log(base: Path) -> Path | None:
    logs_dir = base / "logs"
    logs = sorted(logs_dir.glob("diagnostics_*.txt"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def check_git_status() -> list[Check]:
    checks: list[Check] = []
    staged = run(["git", "diff", "--cached", "--name-only"])
    staged_names = {line.strip().replace("\\", "/") for line in staged.stdout.splitlines() if line.strip()}
    staged_oos = sorted(set(OUT_OF_SCOPE) & staged_names)
    checks.append(Check("git: OUT_OF_SCOPE not staged", not staged_oos, ", ".join(staged_oos)))

    status = run(["git", "status", "--short"])
    checks.append(Check("git: status available", status.returncode == 0, status.stdout.strip()))
    return checks


def check_required_files() -> list[Check]:
    checks = [Check(f"file exists: {name}", (ROOT / name).is_file()) for name in BAT_FILES]
    checks.append(Check("file exists: README_*.txt", find_readme() is not None))
    return checks


def check_install_bat() -> list[Check]:
    text = read_repo("install.bat")
    checks: list[Check] = []
    ok, detail = has_all(text, [
        'pushd "%~dp0"',
        'if not exist "logs" mkdir "logs"',
        'if not exist "config" mkdir "config"',
        "HAEHAN_PORTABLE_DESKTOP_DIR",
        "HAEHAN_PORTABLE_SHORTCUT_NAME",
        "$shell.CreateShortcut($lnk)",
        "$shortcut.TargetPath=Join-Path $root 'start.bat'",
        "$shortcut.WorkingDirectory=$root",
    ])
    checks.append(Check("install.bat: portable install flow", ok, detail))

    ok, detail = no_regex(text, [
        r"\bProgram Files\b",
        r"\breg\s+add\b",
        r"\breg\.exe\b",
        r"\bsetx\s+PATH\b",
        r"\$env:PATH",
        r"SetEnvironmentVariable\([^)]*PATH",
        r"\bcopy\b.*Program Files",
        r"\bxcopy\b",
        r"\brobocopy\b",
        r"\brunas\b",
        r"\bnet session\b",
    ])
    checks.append(Check("install.bat: no admin/global install mutation", ok, detail))
    return checks


def check_start_bat() -> list[Check]:
    text = read_repo("start.bat")
    ok, detail = has_all(text, [
        'pushd "%~dp0"',
        'set "APP_EXE="',
        "HaehanAI-Desktop.exe",
        'start "" "%APP_EXE%"',
        "Run diagnostics.bat",
    ])
    return [Check("start.bat: portable launch flow", ok, detail)]


def check_diagnostics_bat() -> list[Check]:
    text = read_repo("diagnostics.bat")
    checks: list[Check] = []
    ok, detail = has_all(text, [
        'set "REPORT=logs\\diagnostics_%TS%.txt"',
        "install_bat=present",
        "desktop_exe=present",
        "Get-NetTCPConnection -LocalPort 8765",
        "secret_values_printed=false",
        "_present={1}",
    ])
    checks.append(Check("diagnostics.bat: required checks present", ok, detail))

    ok, detail = no_regex(text, [
        r"%OPENAI_API_KEY%",
        r"%ANTHROPIC_API_KEY%",
        r"%HAEHAN_DESKTOP_OPS_BASIC_PASSWORD%",
        r"Write-Host\s+\$.*token",
    ])
    checks.append(Check("diagnostics.bat: no secret value output pattern", ok, detail))
    return checks


def check_uninstall_bat() -> list[Check]:
    text = read_repo("uninstall.bat")
    checks: list[Check] = []
    ok, detail = has_all(text, [
        "HAEHAN_PORTABLE_DESKTOP_DIR",
        "HAEHAN_PORTABLE_SHORTCUT_NAME",
        "Remove-Item -LiteralPath $lnk",
        "App files, logs, and config were not deleted",
    ])
    checks.append(Check("uninstall.bat: shortcut-only uninstall", ok, detail))

    ok, detail = no_regex(text, [
        r"Remove-Item[^\n]*(logs|config|HaehanAI-Desktop\.exe)",
        r"\brmdir\b",
        r"\brd\s+/s\b",
        r"\bdel\s+/",
    ])
    checks.append(Check("uninstall.bat: does not delete app/logs/config", ok, detail))
    return checks


def check_readme() -> list[Check]:
    readme = find_readme()
    if readme is None:
        return [Check("README: required guidance", False, "README_*.txt missing")]
    text = read(readme)
    ok, detail = has_all(text, [
        "Portable ZIP + install.bat",
        "installer exe",
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
    ])
    return [Check("README: required guidance", ok, detail)]


def check_no_hardcoded_secret_values() -> list[Check]:
    readme = find_readme()
    files = [ROOT / name for name in BAT_FILES]
    if readme is not None:
        files.append(readme)

    patterns = [
        r"Bearer\s+admin-token",
        r"Authorization.*admin-token",
        r"sk-proj-[A-Za-z0-9_-]{8,}",
        r"sk-ant-[A-Za-z0-9_-]{8,}",
        r"(password|token|secret|api[_-]?key)\s*=\s*[\"']?[A-Za-z0-9_-]{8,}",
    ]
    hits: list[str] = []
    for path in files:
        text = read(path)
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits.append(f"{path.name}:{pattern}")
    return [Check("portable files: no hardcoded secret values", not hits, "; ".join(hits))]


def make_sandbox() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path(os.environ.get("HAEHAN_PORTABLE_VERIFY_ROOT", str(Path(os.environ["TEMP"]) / "haehan_portable_verify")))
    sandbox = base / f"portable_verify_{stamp}"
    sandbox.mkdir(parents=True, exist_ok=False)
    return sandbox


def copy_portable_files(sandbox: Path) -> None:
    for name in BAT_FILES:
        shutil.copy2(ROOT / name, sandbox / name)
    readme = find_readme()
    if readme is not None:
        shutil.copy2(readme, sandbox / readme.name)

    exe = sandbox / "dist" / "HaehanAI-Desktop" / "HaehanAI-Desktop.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ portable verification placeholder\r\n")
    (exe.parent / "_internal").mkdir(parents=True, exist_ok=True)


def run_full_sandbox_check() -> list[Check]:
    checks: list[Check] = []
    sandbox = make_sandbox()
    copy_portable_files(sandbox)

    desktop_dir = sandbox / "Desktop"
    shortcut_name = "HaehanAI Desktop Verify"
    shortcut = desktop_dir / f"{shortcut_name}.lnk"
    env = os.environ.copy()
    env["HAEHAN_PORTABLE_DESKTOP_DIR"] = str(desktop_dir)
    env["HAEHAN_PORTABLE_SHORTCUT_NAME"] = shortcut_name

    install = run(["cmd", "/c", "install.bat"], cwd=sandbox, env=env)
    checks.append(Check("sandbox install.bat: executes", install.returncode == 0, install.stderr.strip() or install.stdout.strip()))
    checks.append(Check("sandbox install.bat: shortcut created", shortcut.exists(), str(shortcut)))
    checks.append(Check("sandbox install.bat: logs folder created", (sandbox / "logs").is_dir()))
    checks.append(Check("sandbox install.bat: config folder created", (sandbox / "config").is_dir()))

    diag_before = latest_diagnostics_log(sandbox)
    diagnostics = run(["cmd", "/c", "diagnostics.bat"], cwd=sandbox, env=env)
    checks.append(Check("sandbox diagnostics.bat: executes", diagnostics.returncode == 0, diagnostics.stderr.strip()))
    diag_after = latest_diagnostics_log(sandbox)
    checks.append(Check("sandbox diagnostics.bat: new log created", diag_after is not None and diag_after != diag_before, str(diag_after or "")))

    if diag_after is not None:
        text = read(diag_after)
        ok, detail = has_all(text, [
            "HAEHAN_DESKTOP_PORTABLE_DIAGNOSTICS",
            "install_bat=present",
            "start_bat=present",
            "diagnostics_bat=present",
            "uninstall_bat=present",
            "readme=present",
            "desktop_exe=present",
            "internal_folder_dist=present",
            "logs=present",
            "config=present",
            "port_8765=",
            "secret_values_printed=false",
            "OPENAI_API_KEY_present=",
        ])
        checks.append(Check("sandbox diagnostics.bat: log content complete", ok, detail))
        ok, detail = no_regex(text, [
            r"sk-proj-[A-Za-z0-9_-]{8,}",
            r"sk-ant-[A-Za-z0-9_-]{8,}",
            r"Bearer\s+[A-Za-z0-9._-]{8,}",
            r"(password|token|secret|api[_-]?key)\s*=\s*[A-Za-z0-9._-]{8,}",
        ])
        checks.append(Check("sandbox diagnostics.bat: log has no secret values", ok, detail))

    uninstall = run(["cmd", "/c", "uninstall.bat"], cwd=sandbox, env=env)
    checks.append(Check("sandbox uninstall.bat: executes", uninstall.returncode == 0, uninstall.stderr.strip() or uninstall.stdout.strip()))
    checks.append(Check("sandbox uninstall.bat: shortcut removed", not shortcut.exists(), str(shortcut)))
    checks.append(Check("sandbox uninstall.bat: logs preserved", (sandbox / "logs").is_dir()))
    checks.append(Check("sandbox uninstall.bat: config preserved", (sandbox / "config").is_dir()))
    checks.append(Check("sandbox uninstall.bat: app preserved", (sandbox / "dist" / "HaehanAI-Desktop" / "HaehanAI-Desktop.exe").is_file()))

    reinstall = run(["cmd", "/c", "install.bat"], cwd=sandbox, env=env)
    checks.append(Check("sandbox recovery: reinstall executes", reinstall.returncode == 0, reinstall.stderr.strip() or reinstall.stdout.strip()))
    checks.append(Check("sandbox recovery: shortcut recreated", shortcut.exists(), str(shortcut)))
    recovery_uninstall = run(["cmd", "/c", "uninstall.bat"], cwd=sandbox, env=env)
    checks.append(Check("sandbox recovery: cleanup uninstall executes", recovery_uninstall.returncode == 0, recovery_uninstall.stderr.strip() or recovery_uninstall.stdout.strip()))
    checks.append(Check("sandbox recovery: shortcut removed again", not shortcut.exists(), str(shortcut)))

    return checks


def main() -> int:
    static_only = "--static-only" in sys.argv[1:]

    checks: list[Check] = []
    checks.extend(check_git_status())
    checks.extend(check_required_files())
    checks.extend(check_install_bat())
    checks.extend(check_start_bat())
    checks.extend(check_diagnostics_bat())
    checks.extend(check_uninstall_bat())
    checks.extend(check_readme())
    checks.extend(check_no_hardcoded_secret_values())
    if not static_only:
        checks.extend(run_full_sandbox_check())

    failed = [check for check in checks if not check.ok]
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        suffix = f" - {check.detail}" if check.detail else ""
        print(f"[{status}] {check.name}{suffix}")

    print(f"RESULT={'PASS' if not failed else 'FAIL'} checks={len(checks)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
