"""Shared constants, dataclasses, and utility helpers for module_quality_gate."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

_BOOT = Path(__file__).resolve().parents[2]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

_ROOT_BOOT = str(repo_root())  # 직접 실행(python .../quality/x.py)에서도 scripts 패키지를 찾게 한다
if _ROOT_BOOT not in sys.path:
    sys.path.insert(0, _ROOT_BOOT)
from scripts.common.runtime_temp import usable_temp_base  # noqa: E402 - sys.path 부트스트랩 뒤 import

sys.dont_write_bytecode = True

ROOT = repo_root()
MODULE_GATE_PYCACHE = Path(
    os.environ.get(
        "HAEHAN_MODULE_GATE_PYCACHE", str(usable_temp_base("module_gate_pycache", "HAEHAN_MODULE_GATE_PYCACHE"))
    )
)
os.environ.setdefault("PYTHONPYCACHEPREFIX", str(MODULE_GATE_PYCACHE))
sys.pycache_prefix = str(MODULE_GATE_PYCACHE)

OUT_OF_SCOPE = {
    "scripts/archive/data/chrome_ui_monitor_state.json",
    "scripts/ops/check_naver_mail.py",
    "scripts/ops/check_remote_browser.py",
    "scripts/ops/naver_login_and_mail.py",
    "scripts/ops/verify_remote_browser.py",
}

FORBIDDEN_TOKENS = {
    "docker",
    "docker-compose",
    "electron-builder",
    "git add",
    "git commit",
    "git push",
    "npm run build",
    "next build",
    "pyinstaller",
}


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...] = ()
    live: bool = False
    check: str | None = None


@dataclass(frozen=True)
class GateModule:
    name: str
    description: str
    steps: tuple[GateStep, ...]


PY = sys.executable


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"')


def redact(text: str) -> str:
    rules = (
        (re.compile(r"(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\s'\"`;,]+"), r"\1<redacted>"),
        (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
        (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-<redacted>"),
        (
            re.compile(
                r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|device[_-]?token|secret|password)\s*[:=]\s*)[^\s'\"`;,]+"
            ),
            r"\1<redacted>",
        ),
    )
    redacted = text
    for pattern, replacement in rules:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def command_text(command: Iterable[str]) -> str:
    return " ".join(str(part) for part in command)


def command_is_forbidden(command: Iterable[str]) -> bool:
    lowered = command_text(command).lower()
    return any(token in lowered for token in FORBIDDEN_TOKENS)


def command_is_pytest(command: Iterable[str]) -> bool:
    parts = tuple(str(part) for part in command)
    return "-m" in parts and "pytest" in parts


def workspace_temp_root(env: dict[str, str], step_name: str) -> Path:
    base = usable_temp_base("module_gate_temp", "HAEHAN_MODULE_GATE_TEMP")
    safe_step = re.sub(r"[^A-Za-z0-9_.-]+", "_", step_name).strip("_") or "step"
    target = base / f"{safe_step}_{uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def find_staged_out_of_scope(staged_paths: Iterable[str]) -> list[str]:
    normalized = {normalize_path(path) for path in staged_paths}
    return sorted(path for path in OUT_OF_SCOPE if path in normalized)


def git_staged_paths() -> list[str]:
    result = subprocess.run(  # noqa: UP022
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(redact(result.stderr.strip()) or "git diff --cached failed")
    return [normalize_path(line) for line in result.stdout.splitlines() if line.strip()]


def _run_check_command(command: list[str], *, cwd: Path = ROOT, timeout: int = 120) -> tuple[bool, str]:
    executable = command[0]
    if executable == "npm":
        executable = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    try:
        result = subprocess.run(
            [executable, *command[1:]],
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return False, f"{command[0]} not found"
    output = redact(result.stdout or "").strip()
    tail = output[-500:].replace("\n", " | ") if output else ""
    if result.returncode == 0:
        return True, tail or "ok"
    return False, tail or f"exit_code={result.returncode}"


def _source_contains(path: str, needles: Iterable[str]) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    return [needle for needle in needles if needle in text]


def all_steps() -> list[GateStep]:
    # Imported lazily to avoid circular import with modules leaf
    try:
        from tools.quality.module_quality_gate_modules import MODULES as _MODULES
    except ModuleNotFoundError:
        from module_quality_gate_modules import MODULES as _MODULES  # type: ignore[no-redef, import-not-found]
    return [step for module in _MODULES for step in module.steps]
