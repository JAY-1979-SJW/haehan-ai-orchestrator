"""local_agent Browser Provider — 사용자 로컬 PC에서 visible 브라우저를 직접
실행한다.

목적:
  - Google / YouTube / Naver Cafe / 홈택스 등 사용자 계정 기반 세션(USER_LOGIN_
    SESSION)을 열어야 할 때, 서버에서 Chromium 을 실행하지 않고 **사용자 PC
    의 msedge / chrome / chromium 를 visible 모드로 직접 기동**한다.
  - 사용자가 Chrome 아이콘을 더블클릭해 여는 것과 최대한 동일한 방식.

지원 브라우저(이번 단계):
  - msedge / chrome / chromium. firefox 는 향후 확장 자리만 남김.

금지 (본 모듈):
  - headless=True / ``--headless`` 플래그
  - ``--remote-debugging-port`` 자동 부여
  - ID/PW 자동 입력 (page.fill / page.type / page.press / keyboard 등)
  - storage_state / cookies / localStorage / sessionStorage 수집·주입
  - 기본 Chrome / Edge 사용자 프로필 (``...Google/Chrome/User Data``,
    ``...Microsoft/Edge/User Data``) 직접 사용
  - ``GOOGLE_PASSWORD`` / ``GOOGLE_LOGIN_PASSWORD`` / ``GOOGLE_COOKIE`` /
    ``GOOGLE_SESSION`` / ``GOOGLE_STORAGE_STATE`` / ``GOOGLE_OTP_SECRET``
    환경변수가 비어있지 않게 설정된 상태에서의 실행
  - 서버(ai_orchestrator) 코드에서 본 모듈을 호출하는 것

반환 dict (성공/실패 동일 스키마):
  {
    "launched":             bool,
    "target_url":           str,
    "browser_provider":     str,           # "msedge" / "chrome" / "chromium" / ""
    "browser_channel":      str | None,    # playwright channel 힌트
    "browser_path_category": str,          # env_override / program_files /
                                           # program_files_x86 / path /
                                           # bundled_chromium / ""
    "profile_dir_category": str,           # haehan_dedicated /
                                           # haehan_dedicated_named / ""
    "pid":                  int | None,
    "warnings":             list[str],
  }

주의:
  - chrome.exe 의 **전체 경로는 반환하지 않는다.** ``browser_path_category``
    로만 위치 분류를 노출.
  - 전용 프로필 경로의 **절대경로도 반환하지 않는다.** ``profile_dir_category``
    로만 분류 노출.
  - 실패는 예외를 던지지 않고 ``launched=False`` + ``warnings=[...]`` 로
    반환한다 (테스트 용이성).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── 정책 상수 ────────────────────────────────────────────────────────────

SUPPORTED_PROVIDERS: Tuple[str, ...] = ("msedge", "chrome", "chromium")

# 향후 firefox 확장 자리. 이번 단계에서는 미지원.
_RESERVED_FUTURE_PROVIDERS: Tuple[str, ...] = ("firefox",)

SITE_POLICY_AUTO = "auto"
SITE_POLICY_GOOGLE = "google"

# F-2: 사이트 분류용 추상 정책 토큰. provider 우선순위 분기에는 직접
# 사용되지 않지만, 호출자/문서/감사 로그에서 일관된 라벨로 쓰기 위해 노출.
SITE_POLICY_GENERIC = "generic"
SITE_POLICY_PUBLIC_FETCH = "public_fetch"
SITE_POLICY_GOOGLE_OPEN_ONLY = "google_open_only"
SITE_POLICY_YOUTUBE_OPEN_ONLY = "youtube_open_only"
SITE_POLICY_LOCAL_PROBE_ALLOWED = "local_probe_allowed"

# Google 자동 로그인 차단 도메인. ``probe_visible_browser`` (Playwright
# launch_persistent_context) 는 이 도메인에 대해 launch 전에 거절하고,
# 사용자는 ``open_local_browser`` (subprocess) 로만 열도록 강제한다.
# 비교는 lowercase host 와의 정확 일치 또는 서브도메인 매칭 (host == d
# or host.endswith("." + d)).
GOOGLE_OPEN_ONLY_DOMAINS: Tuple[str, ...] = (
    "accounts.google.com",
    "google.com",
    "studio.youtube.com",
    "youtube.com",
    "gmail.com",
    "drive.google.com",
)

_PROVIDER_PRIORITY_AUTO: Tuple[str, ...] = ("msedge", "chrome", "chromium")
_PROVIDER_PRIORITY_GOOGLE: Tuple[str, ...] = ("chrome", "msedge", "chromium")

# 존재(+비어있지 않음) 만으로 FAIL 시키는 환경변수들. 값은 절대 읽지 않는다.
_FORBIDDEN_ENV_VARS: Tuple[str, ...] = (
    "GOOGLE_PASSWORD",
    "GOOGLE_LOGIN_PASSWORD",
    "GOOGLE_OTP_SECRET",
)

# 기본 사용자 프로필을 가리키는 문자열 마커(대소문자/슬래시 정규화 후 비교).
_DEFAULT_PROFILE_MARKERS: Tuple[str, ...] = (
    "google/chrome/user data",
    "microsoft/edge/user data",
)


# ─── 테스트 주입 가능한 OS 접근 hook ──────────────────────────────────────

def _candidate_exists(path: str) -> bool:
    """주어진 문자열 경로가 실제 파일인지 검사 (테스트에서 monkeypatch)."""
    try:
        return bool(path) and Path(path).is_file()
    except OSError:
        return False


def _which_command(cmd: str, env: dict) -> Optional[str]:
    """PATH 기반 실행파일 탐색 (테스트에서 monkeypatch)."""
    path_env = env.get("PATH") if isinstance(env, dict) else None
    try:
        return shutil.which(cmd, path=path_env)
    except Exception:  # noqa: BLE001
        return None


def _iter_ms_playwright_chromium(env: dict) -> Sequence[str]:
    """%LOCALAPPDATA%/ms-playwright/chromium-*/chrome-win/chrome.exe 후보 반환."""
    base = env.get("LOCALAPPDATA") if isinstance(env, dict) else None
    if not base:
        home = env.get("USERPROFILE") if isinstance(env, dict) else None
        if home:
            base = str(Path(home) / "AppData" / "Local")
    if not base:
        return ()
    root = Path(base) / "ms-playwright"
    try:
        if not root.is_dir():
            return ()
        subdirs = sorted(
            (d for d in root.iterdir()
             if d.is_dir() and d.name.startswith("chromium-")),
            reverse=True,
        )
    except OSError:
        return ()
    return tuple(str(d / "chrome-win" / "chrome.exe") for d in subdirs)


# ─── 경로 / 프로필 유틸 ───────────────────────────────────────────────────

def _profile_root(env: dict) -> Path:
    override = env.get("HAEHAN_BROWSER_PROFILE_ROOT") if isinstance(env, dict) else None
    if override:
        return Path(override).expanduser()
    base = env.get("LOCALAPPDATA") if isinstance(env, dict) else None
    if not base:
        home = env.get("USERPROFILE") if isinstance(env, dict) else None
        if home:
            base = str(Path(home) / "AppData" / "Local")
    if not base:
        base = str(Path.home() / "AppData" / "Local")
    return Path(base) / "HaehanAI" / "BrowserProfiles"


def _profile_path_for(provider: str, profile_name: str, env: dict) -> Path:
    return _profile_root(env) / provider / profile_name


def _normalize_for_marker_check(p: str) -> str:
    return p.replace("\\", "/").lower()


def _detect_default_profile(path_str: str) -> Optional[str]:
    norm = _normalize_for_marker_check(path_str)
    for marker in _DEFAULT_PROFILE_MARKERS:
        if marker in norm:
            return marker
    return None


def _validate_profile_name(name: str) -> Optional[str]:
    if not isinstance(name, str):
        return "profile_name_not_string"
    if not name:
        return "profile_name_empty"
    if ".." in name:
        return "profile_name_traversal"
    if "/" in name or "\\" in name:
        return "profile_name_has_separator"
    # 절대경로 (드라이브 레터 등) 차단
    if len(name) >= 2 and name[1:2] == ":":
        return "profile_name_absolute"
    if name.startswith("~"):
        return "profile_name_home_expansion"
    return None


# ─── provider 별 실행파일 후보 ────────────────────────────────────────────

def _edge_candidates(env: dict) -> Sequence[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    ov = env.get("HAEHAN_EDGE_EXE") if isinstance(env, dict) else None
    if ov:
        out.append((ov, "env_override"))
    out.append((
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "program_files_x86",
    ))
    out.append((
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "program_files",
    ))
    w = _which_command("msedge", env)
    if w:
        out.append((w, "path"))
    return tuple(out)


def _chrome_candidates(env: dict) -> Sequence[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    ov = env.get("HAEHAN_CHROME_EXE") if isinstance(env, dict) else None
    if ov:
        out.append((ov, "env_override"))
    out.append((
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "program_files",
    ))
    out.append((
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "program_files_x86",
    ))
    w = _which_command("chrome", env)
    if w:
        out.append((w, "path"))
    return tuple(out)


def _chromium_candidates(env: dict) -> Sequence[Tuple[str, str]]:
    out: list[Tuple[str, str]] = []
    ov = env.get("HAEHAN_CHROMIUM_EXE") if isinstance(env, dict) else None
    if ov:
        out.append((ov, "env_override"))
    for p in _iter_ms_playwright_chromium(env):
        out.append((p, "bundled_chromium"))
    w = _which_command("chromium", env)
    if w:
        out.append((w, "path"))
    return tuple(out)


_CANDIDATE_BUILDERS = {
    "msedge": _edge_candidates,
    "chrome": _chrome_candidates,
    "chromium": _chromium_candidates,
}


def _find_executable(provider: str, env: dict) -> Tuple[Optional[str], str]:
    builder = _CANDIDATE_BUILDERS.get(provider)
    if builder is None:
        return None, ""
    for path_str, category in builder(env):
        if _candidate_exists(path_str):
            return path_str, category
    return None, ""


# ─── 실행 인자 구성 & spawn ───────────────────────────────────────────────

def _build_launch_args(exe_path: str, profile_dir: Path, url: str) -> list[str]:
    """사용자가 아이콘으로 브라우저를 연 것과 가장 유사한 최소 인자."""
    return [
        exe_path,
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]


def _default_spawn(args: Sequence[str]):
    # 부모 프로세스가 종료되어도 브라우저는 사용자가 닫을 때까지 유지.
    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(
        list(args),
        creationflags=creationflags,
        close_fds=True,
    )


# ─── 결과 빌더 ────────────────────────────────────────────────────────────

def _fail_result(url: str, warnings: Sequence[str]) -> dict:
    return {
        "launched": False,
        "target_url": url if isinstance(url, str) else "",
        "browser_provider": "",
        "browser_channel": None,
        "browser_path_category": "",
        "profile_dir_category": "",
        "pid": None,
        "warnings": list(warnings),
    }


def _channel_for_provider(provider: str) -> Optional[str]:
    # playwright 의 channel 인자 힌트. chromium 은 channel 없음.
    if provider in ("chrome", "msedge"):
        return provider
    return None


def _profile_category(profile_name: str) -> str:
    return "haehan_dedicated" if profile_name == "default" else "haehan_dedicated_named"


# ─── Public API ───────────────────────────────────────────────────────────

def open_local_browser(
    url: str,
    *,
    profile_name: str = "default",
    site_policy: str = SITE_POLICY_AUTO,
    provider_override: Optional[str] = None,
    spawn: Optional[Callable[[Sequence[str]], "subprocess.Popen"]] = None,
    env: Optional[dict] = None,
) -> dict:
    """사용자 로컬 PC에서 visible 브라우저를 띄워 ``url`` 로 이동한다.

    절대 수행하지 않는 것:
      - 자동 ID/PW 입력
      - cookies / storage_state / localStorage / sessionStorage 수집
      - 기본 Chrome/Edge 프로필 사용
      - headless 실행
    """
    eff_env = dict(os.environ) if env is None else dict(env)

    # 1) URL 기본 유효성
    if not isinstance(url, str) or not url.strip():
        return _fail_result("", ["invalid_target_url"])
    if not (url.startswith("http://") or url.startswith("https://")):
        return _fail_result(url, ["target_url_scheme_forbidden"])

    # 2) 민감 환경변수 차단 (값은 읽지 않고 존재+비어있지 않음만 본다)
    forbidden_hit: list[str] = []
    for key in _FORBIDDEN_ENV_VARS:
        v = eff_env.get(key)
        if v is not None and str(v).strip() != "":
            forbidden_hit.append(f"forbidden_env_present:{key}")
    if forbidden_hit:
        # 값은 절대 노출하지 않는다. 키 이름만 기록.
        return _fail_result(url, forbidden_hit)

    # 3) profile_name 검증
    name_err = _validate_profile_name(profile_name)
    if name_err:
        return _fail_result(url, [name_err])

    # 4) provider 우선순위 결정
    if provider_override is not None:
        if provider_override not in SUPPORTED_PROVIDERS:
            return _fail_result(url, [f"unsupported_provider:{provider_override}"])
        order: Sequence[str] = (provider_override,)
    elif site_policy == SITE_POLICY_GOOGLE:
        order = _PROVIDER_PRIORITY_GOOGLE
    elif site_policy == SITE_POLICY_AUTO:
        order = _PROVIDER_PRIORITY_AUTO
    else:
        return _fail_result(url, [f"unknown_site_policy:{site_policy}"])

    # 5) 실행파일 탐색 (첫 번째 발견)
    chosen_provider: Optional[str] = None
    chosen_path: Optional[str] = None
    chosen_category: str = ""
    for provider in order:
        path_str, category = _find_executable(provider, eff_env)
        if path_str:
            chosen_provider = provider
            chosen_path = path_str
            chosen_category = category
            break
    if chosen_provider is None or chosen_path is None:
        return _fail_result(url, ["no_browser_found"])

    # 6) 전용 프로필 경로 산출 + 기본 프로필/탈출 차단
    profile_root = _profile_root(eff_env)
    profile_dir = _profile_path_for(chosen_provider, profile_name, eff_env)

    try:
        profile_root_res = profile_root.expanduser().resolve(strict=False)
        profile_dir_res = profile_dir.expanduser().resolve(strict=False)
    except OSError:
        return _fail_result(url, ["profile_path_resolve_failed"])

    try:
        profile_dir_res.relative_to(profile_root_res)
    except ValueError:
        return _fail_result(url, ["profile_not_within_root"])

    marker = _detect_default_profile(str(profile_dir_res)) or \
        _detect_default_profile(str(profile_root_res))
    if marker:
        return _fail_result(url, [f"default_profile_blocked:{marker}"])

    # 7) 전용 프로필 디렉터리 자동 생성 (root 내부 검증 통과한 경우에만)
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _fail_result(url, [f"profile_dir_create_failed:{type(e).__name__}"])

    # 8) 실행
    args = _build_launch_args(chosen_path, profile_dir, url)
    # 금지 인자 방어 (내부 버그로도 절대 들어가지 않도록)
    if any(a.startswith("--headless") for a in args):
        return _fail_result(url, ["headless_flag_forbidden"])
    if any(a.startswith("--remote-debugging-port") for a in args):
        return _fail_result(url, ["remote_debugging_port_forbidden"])

    spawn_fn = spawn if spawn is not None else _default_spawn
    try:
        proc = spawn_fn(args)
    except FileNotFoundError:
        return _fail_result(url, ["spawn_executable_missing"])
    except OSError as e:
        return _fail_result(url, [f"spawn_failed:{type(e).__name__}"])

    pid = getattr(proc, "pid", None)

    return {
        "launched": True,
        "target_url": url,
        "browser_provider": chosen_provider,
        "browser_channel": _channel_for_provider(chosen_provider),
        "browser_path_category": chosen_category,
        "profile_dir_category": _profile_category(profile_name),
        "pid": int(pid) if isinstance(pid, int) else pid,
        "warnings": [],
    }


def is_google_open_only_url(url: str) -> bool:
    """URL host 가 ``GOOGLE_OPEN_ONLY_DOMAINS`` 정책 대상인지 판정.

    Google / YouTube 계열은 Playwright 자동화 제어 브라우저 (probe) 가
    Google 로그인 페이지를 ``signin/rejected`` 로 차단당하는 사례가 있어,
    visible probe 대상에서 제외하고 subprocess 기반 ``open_local_browser``
    로만 띄운다. 본 헬퍼는 host 의 lowercase 정확 일치 / 서브도메인
    매칭만 수행하며 query/fragment 는 보지 않는다. http/https 가 아닌
    스킴은 Google 정책 대상이 아니다 (별도 scheme 정책에서 거절).
    """
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    scheme = (parsed.scheme or "").strip().lower()
    if scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().strip(".").lower()
    if not host:
        return False
    for domain in GOOGLE_OPEN_ONLY_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


__all__ = [
    "open_local_browser",
    "SUPPORTED_PROVIDERS",
    "SITE_POLICY_AUTO",
    "SITE_POLICY_GOOGLE",
    "SITE_POLICY_GENERIC",
    "SITE_POLICY_PUBLIC_FETCH",
    "SITE_POLICY_GOOGLE_OPEN_ONLY",
    "SITE_POLICY_YOUTUBE_OPEN_ONLY",
    "SITE_POLICY_LOCAL_PROBE_ALLOWED",
    "GOOGLE_OPEN_ONLY_DOMAINS",
    "is_google_open_only_url",
]
