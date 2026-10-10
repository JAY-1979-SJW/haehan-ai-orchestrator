"""설치·실행 환경 점검(preflight) — 이 PC·다른 PC 어디서든 같은 기준으로 "지금 이 앱이 돌 수 있는가"를 확인한다.

기준서: docs/specs/2026-10-04_portability_standard.md

- 읽기 전용이다: 아무것도 고치거나 설치하거나 브라우저를 켜지 않는다. `.env` 의 값은 읽지도 출력하지도 않는다(키 이름 존재만).
- 결과는 PASS / WARN / FAIL. FAIL 이 하나라도 있으면 종료코드 1.
- 각 검사는 (이름, 상태, 설명) 을 돌려주는 작은 함수이고, 환경(파이썬 버전·경로·실행 함수)은 `Env` 로 주입해 시험에서 가짜로 바꾼다.

사용: python tools/verify/preflight.py [--json]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
MIN_PYTHON = (3, 11)  # configs/ruff.toml target-version = py311
CDP_HOST, CDP_PORT = "127.0.0.1", 9222
CHROME_MIN_MAJOR = 136  # 이 버전부터 기본 프로필에서 원격 디버깅 포트가 조용히 무시된다(비표준 --user-data-dir 필수)
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "playwright", "python-dotenv", "pydantic", "requests", "openpyxl")


@dataclass
class Check:
    name: str
    status: str
    detail: str


@dataclass
class Env:
    """점검이 보는 환경. 시험에서는 필드를 가짜로 바꿔 넣는다."""

    root: Path = ROOT
    python_version: tuple[int, ...] = field(default_factory=lambda: tuple(sys.version_info[:3]))
    environ: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    package_version: Callable[[str], str | None] = field(default=lambda name: _installed_version(name))
    which: Callable[[str], str | None] = shutil.which
    run: Callable[[list[str]], tuple[int, str]] = field(default=lambda cmd: _run(cmd))
    http_get: Callable[[str], tuple[int, str] | None] = field(default=lambda url: _http_get(url))
    port_in_use: Callable[[str, int], bool] = field(default=lambda host, port: _port_in_use(host, port))
    find_chrome: Callable[[], str | None] = field(default=lambda: _find_chrome())


def _installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()


def _http_get(url: str) -> tuple[int, str] | None:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status, resp.read(4000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _find_chrome() -> str | None:
    from scripts.browser.session.browser_paths import find_chrome

    return find_chrome()


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", text)[:4])


# ── 검사 ──────────────────────────────────────────────────────────────────


def check_python(env: Env) -> Check:
    ok = env.python_version >= MIN_PYTHON
    ver = ".".join(map(str, env.python_version))
    need = ".".join(map(str, MIN_PYTHON))
    return Check("파이썬 버전", PASS if ok else FAIL, f"{ver} (필요 {need} 이상)")


def check_packages(env: Env) -> Check:
    missing: list[str] = []
    versions: list[str] = []
    for name in REQUIRED_PACKAGES:
        ver = env.package_version(name)
        (versions if ver else missing).append(f"{name} {ver}" if ver else name)
    if missing:
        return Check(
            "필수 패키지",
            FAIL,
            "없음: " + ", ".join(missing) + "  → pip install -r requirements.txt -c constraints.txt",
        )
    return Check("필수 패키지", PASS, ", ".join(versions))


def check_constraints(env: Env) -> Check:
    """constraints.txt 와 설치된 버전이 같은가(재현성). 파일이 없으면 알린다."""
    path = env.root / "constraints.txt"
    if not path.is_file():
        return Check(
            "버전 고정(constraints.txt)", WARN, "constraints.txt 가 없습니다 — 설치 시점마다 버전이 달라질 수 있음"
        )
    drift = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-\[\]]+)==([^\s;#]+)", line.strip())
        if not match:
            continue
        name, wanted = match.group(1).split("[", 1)[0], match.group(2)
        have = env.package_version(name)
        if have is not None and have != wanted:
            drift.append(f"{name} {have}≠{wanted}")
    if drift:
        return Check("버전 고정(constraints.txt)", WARN, f"검증된 버전과 다름 {len(drift)}건: " + ", ".join(drift[:6]))
    return Check("버전 고정(constraints.txt)", PASS, "설치된 버전이 검증된 집합과 같음")


def check_chrome(env: Env) -> Check:
    chrome = env.find_chrome()
    if not chrome:
        return Check("Chrome 설치", FAIL, "Chrome 을 찾지 못했습니다(Program Files·LOCALAPPDATA 확인)")
    # Windows 의 chrome.exe 는 --version 에 출력하지 않는다 → 실행 파일의 버전 정보를 읽는다(그 밖의 OS 는 --version)
    if sys.platform == "win32":
        quoted = chrome.replace("'", "''")
        code, out = env.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-Item -LiteralPath '{quoted}').VersionInfo.ProductVersion"]
        )
    else:
        code, out = env.run([chrome, "--version"])
    ver = _version_tuple(out) if code == 0 else ()
    if not ver:
        return Check("Chrome 설치", WARN, f"{chrome} (버전 확인 실패)")
    return Check("Chrome 설치", PASS, f"{'.'.join(map(str, ver))}")


def _default_profile_dirs(environ: dict[str, str]) -> list[Path]:
    local = environ.get("LOCALAPPDATA", "")
    home = Path(environ.get("USERPROFILE") or environ.get("HOME") or "~").expanduser()
    return [
        p
        for p in (
            Path(local) / "Google" / "Chrome" / "User Data" if local else None,
            home / ".config" / "google-chrome",
            home / "Library" / "Application Support" / "Google" / "Chrome",
        )
        if p
    ]


def check_cdp_profile(env: Env) -> Check:
    """Chrome 136+ 규칙: 원격 디버깅은 기본 프로필이 아닌 폴더에서만 열린다."""
    chosen = (env.environ.get("HAEHAN_CDP_PROFILE") or "").strip()
    profile = Path(chosen) if chosen else env.root / "data" / "cdp_profile" / "ai_chrome"
    try:
        resolved = profile.resolve()
    except OSError:
        resolved = profile
    for default in _default_profile_dirs(env.environ):
        try:
            if resolved == default.resolve() or default.resolve() in resolved.parents:
                return Check(
                    "CDP 프로필 폴더",
                    FAIL,
                    f"기본 Chrome 프로필({default})입니다 — Chrome {CHROME_MIN_MAJOR}+ 는 이 경우 디버깅 포트를 조용히 무시합니다",
                )
        except OSError:
            continue
    note = "환경변수 HAEHAN_CDP_PROFILE" if chosen else "기본 data/cdp_profile/ai_chrome"
    return Check("CDP 프로필 폴더", PASS, f"비표준 폴더({note})")


def check_cdp_port(env: Env) -> Check:
    answer = env.http_get(f"http://{CDP_HOST}:{CDP_PORT}/json/version")
    if answer and answer[0] == 200:
        return Check("CDP 포트 9222", PASS, "크롬 디버그 포트가 응답함")
    if env.port_in_use(CDP_HOST, CDP_PORT):
        return Check("CDP 포트 9222", FAIL, "포트를 다른 프로그램이 쓰고 있어 크롬 디버그 포트가 응답하지 않습니다")
    return Check(
        "CDP 포트 9222",
        WARN,
        "꺼져 있음 — 필요할 때 python scripts/browser/cdp/cdp_force_start.py start (읽기 전용 점검이라 켜지 않음)",
    )


def check_writable(env: Env) -> Check:
    bad = []
    for sub in ("data", "ai_orchestrator/storage"):
        folder = env.root / sub
        target = folder if folder.exists() else folder.parent
        if not os.access(target, os.W_OK):
            bad.append(sub)
    return Check(
        "쓰기 가능한 폴더",
        FAIL if bad else PASS,
        ("쓸 수 없음: " + ", ".join(bad)) if bad else "data, ai_orchestrator/storage",
    )


def check_hook_interpreter(env: Env) -> Check:
    """`.claude/settings.json` 훅이 부르는 파이썬 실행기가 이 PC 에 있는가(마이너 버전 고정 포함)."""
    settings = env.root / ".claude" / "settings.json"
    if not settings.is_file():
        return Check("훅 인터프리터", WARN, ".claude/settings.json 없음")
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except ValueError:
        return Check("훅 인터프리터", FAIL, ".claude/settings.json 이 올바른 JSON 이 아닙니다")
    wanted = set()
    for entries in (data.get("hooks") or {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                wanted.update(re.findall(r"\bpy -(3(?:\.\d+)?)\b", str(hook.get("command", ""))))
    if not wanted:
        return Check("훅 인터프리터", PASS, "py 실행기를 쓰지 않는 훅")
    pinned = sorted(w for w in wanted if "." in w)
    if pinned:
        return Check(
            "훅 인터프리터",
            FAIL,
            f"마이너 버전이 고정돼 있습니다(py -{pinned[0]}) — 그 버전이 없는 PC 에서는 안전 훅이 전부 실패합니다. py -3 을 쓰세요",
        )
    code, _ = env.run(["py", "-3", "-c", "pass"])
    return Check(
        "훅 인터프리터",
        PASS if code == 0 else FAIL,
        "py -3 사용 가능" if code == 0 else "py -3 실행 실패 — Python Launcher 설치 필요",
    )


def check_ruff(env: Env) -> Check:
    """git pre-commit 의 ruff 단계는 훅이 고른 파이썬(`py -3`)에 ruff 가 있어야 돈다. 없으면 `No module named ruff` 만 출력하고 **조용히 건너뛴다**."""
    code, out = (
        env.run(["py", "-3", "-m", "ruff", "--version"])
        if env.which("py")
        else env.run([sys.executable, "-m", "ruff", "--version"])
    )
    if code == 0:
        return Check("ruff(커밋 훅)", PASS, out.splitlines()[0] if out else "설치됨")
    return Check(
        "ruff(커밋 훅)",
        WARN,
        "훅이 쓰는 파이썬에 ruff 가 없어 커밋 시 ruff 검사가 조용히 생략됩니다 — py -3 -m pip install ruff",
    )


def check_claude_cli(env: Env) -> Check:
    """pre-push AI 코드 검수는 `claude` 명령을 PATH 에서 찾는다. 못 찾으면 **검수 없이 PASS 로 건너뛴다**(2026-10-04 푸시에서 실측)."""
    if env.which("claude"):
        return Check("claude CLI(푸시 AI 검수)", PASS, "PATH 에서 찾음")
    return Check(
        "claude CLI(푸시 AI 검수)",
        WARN,
        "claude 명령을 PATH 에서 찾지 못해 푸시 때 AI 검수가 검수 없이 건너뛰어집니다 — 훅은 자기 PATH 로 실행되므로 설치 경로를 시스템 PATH 에 넣으세요",
    )


def check_node(env: Env) -> Check:
    if not env.which("node") or not env.which("npm"):
        return Check("Node/npm(관리 화면)", WARN, "node 또는 npm 이 없습니다 — admin-web 을 쓰지 않으면 무시")
    if not (env.root / "admin-web" / "node_modules").is_dir():
        return Check("Node/npm(관리 화면)", WARN, "admin-web/node_modules 없음 — cd admin-web && npm ci")
    return Check("Node/npm(관리 화면)", PASS, "node, npm, node_modules 있음")


def check_git_hooks(env: Env) -> Check:
    code, out = env.run(["git", "-C", str(env.root), "config", "--get", "core.hooksPath"])
    if code == 0 and out.strip():
        return Check("git 훅", PASS, f"core.hooksPath={out.strip()}")
    return Check("git 훅", WARN, "core.hooksPath 가 설정되지 않음 — python tools/hooks/install_git_hooks.py")


def check_env_file(env: Env) -> Check:
    path = env.root / ".env"
    if not path.is_file():
        return Check(".env", WARN, ".env 가 없습니다(키 값은 읽지 않음) — 비밀 값이 필요한 기능은 동작하지 않습니다")
    names = [
        ln.split("=", 1)[0].strip()
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    ]
    return Check(".env", PASS, f"키 {len(names)}개(이름만 확인, 값은 읽지 않음)")


def check_optional_tools(env: Env) -> Check:
    found = []
    try:
        from tools.hooks.audit_kit_gate import find_audit_kit

        kit = find_audit_kit(env.root, env.environ)
    except Exception:  # noqa: BLE001 - 선택 도구 탐색 실패는 점검 전체를 막지 않는다
        kit = None
    found.append("audit-kit " + ("있음" if kit else "없음(코드 검사 훅은 생략됨)"))
    return Check("선택 도구", PASS if kit else WARN, ", ".join(found))


CHECKS: tuple[Callable[[Env], Check], ...] = (
    check_python,
    check_packages,
    check_constraints,
    check_chrome,
    check_cdp_profile,
    check_cdp_port,
    check_writable,
    check_hook_interpreter,
    check_ruff,
    check_claude_cli,
    check_node,
    check_git_hooks,
    check_env_file,
    check_optional_tools,
)


def run_checks(env: Env | None = None) -> list[Check]:
    env = env or Env()
    results = []
    for check in CHECKS:
        try:
            results.append(check(env))
        except Exception as exc:  # noqa: BLE001 - 검사 하나의 실패가 점검 전체를 멈추지 않게 FAIL 로 기록한다
            results.append(
                Check(check.__name__.removeprefix("check_"), FAIL, f"점검 중 오류: {type(exc).__name__}: {exc}")
            )
    return results


def render(results: list[Check]) -> str:
    icon = {PASS: "OK  ", WARN: "WARN", FAIL: "FAIL"}
    lines = [f"[{icon[r.status]}] {r.name}: {r.detail}" for r in results]
    counts = {s: sum(r.status == s for r in results) for s in (PASS, WARN, FAIL)}
    lines.append(f"\n결과: PASS {counts[PASS]} / WARN {counts[WARN]} / FAIL {counts[FAIL]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    results = run_checks()
    if "--json" in args:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=1))
    else:
        print(render(results))
    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
