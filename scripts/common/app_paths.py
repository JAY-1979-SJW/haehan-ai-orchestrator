"""윈도우 표준 저장소 경로 해석기 — 데이터·설정·설치 위치의 단일 정본 (결함 #17).

설계: docs/specs/2026-10-01_windows_standard_storage.md

우선순위: ① 환경변수 HAEHAN_DATA_ROOT ② 윈도우 표준(%LOCALAPPDATA%\\HaehanAI\\Orchestrator) ③ 비윈도우 폴백.
**저장소(소스 폴더) 상대 경로 폴백은 두지 않는다.** `%LOCALAPPDATA%` 가 없으면 조용히 다른 곳에 쓰지 않고 오류를 낸다.

`%LOCALAPPDATA%\\HaehanAI\\` 는 해한 제품군 공용 상위 폴더(CADQuantity·runtime·inventory 가 이미 있다)이므로 그 바로
아래에는 쓰지 않고 제품 하위 폴더 `Orchestrator` 만 사용한다.

data_root()/config_root() 등 OS 표준 경로 해석 함수는 표준 라이브러리만 쓴다.
repo_root()만 예외로 ai_orchestrator.paths 를 재수출한다(scripts → ai_orchestrator
는 허용된 방향이라 코드맵 폴더 순환이 생기지 않는다. 2026-10-07).
"""

from __future__ import annotations

import ctypes
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from ai_orchestrator.paths import repo_root as repo_root

# 런타임 데이터 위치 정본(ai_orchestrator.paths.runtime) 재노출 — 이 모듈의 data_dir(app, sub)(앱별 하위 폴더)와 이름이 겹쳐 runtime_ 접두를 붙인다.
# ai_orchestrator 를 직접 import 하면 안 되는 scripts 하위 패키지(예: naver/blog/automation 의 분리 경계)가 쓴다.
from ai_orchestrator.paths.runtime import atomic_write_bytes as atomic_write_bytes
from ai_orchestrator.paths.runtime import atomic_write_text as atomic_write_text
from ai_orchestrator.paths.runtime import data_dir as runtime_data_dir  # noqa: F401 - 재노출
from ai_orchestrator.paths.runtime import storage_dir as runtime_storage_dir  # noqa: F401 - 재노출

_SUITE = "HaehanAI"
_PRODUCT = "Orchestrator"
ENV_DATA_ROOT = "HAEHAN_DATA_ROOT"
ENV_CONFIG_ROOT = "HAEHAN_CONFIG_ROOT"

# 데이터 루트 아래의 표준 하위 폴더
_SUBDIRS = ("data", "db", "logs", "cache", "sessions", "browser_profile", "secrets", "migration")


class AppPathsError(RuntimeError):
    """표준 저장소 위치를 정할 수 없을 때(환경이 비정상)."""


def _is_windows() -> bool:
    return sys.platform == "win32"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def _windows_base(env_name: str, what: str) -> Path:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise AppPathsError(
            f"%{env_name}% 가 설정돼 있지 않아 {what} 위치를 정할 수 없습니다. "
            f"환경변수 {ENV_DATA_ROOT} 로 위치를 직접 지정하세요."
        )
    return Path(value)


def data_root() -> Path:
    """이 앱의 데이터 루트. 디렉터리를 만들지는 않는다(`ensure_layout()` 이 만든다)."""
    override = _env_path(ENV_DATA_ROOT)
    if override is not None:
        return override
    if _is_windows():
        return _windows_base("LOCALAPPDATA", "데이터") / _SUITE / _PRODUCT
    xdg = _env_path("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return xdg / _SUITE.lower() / _PRODUCT.lower()


def config_root() -> Path:
    """로밍 설정 루트(작은 설정 파일용)."""
    override = _env_path(ENV_CONFIG_ROOT)
    if override is not None:
        return override
    # 데이터 루트를 직접 지정한 경우(테스트·격리) 설정도 그 아래로 둬 한 곳에 모은다
    if _env_path(ENV_DATA_ROOT) is not None:
        return data_root() / "config"
    if _is_windows():
        return _windows_base("APPDATA", "설정") / _SUITE / _PRODUCT
    xdg = _env_path("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return xdg / _SUITE.lower() / _PRODUCT.lower()


def install_root() -> Path:
    """사용자별 설치 위치(읽기 전용 실행 파일). 환경변수로 바꿀 수 없다."""
    if _is_windows():
        return _windows_base("LOCALAPPDATA", "설치") / "Programs" / f"{_SUITE} {_PRODUCT}"
    return Path.home() / ".local" / "opt" / f"{_SUITE.lower()}-{_PRODUCT.lower()}"


def _sub(name: str, *parts: str, create: bool) -> Path:
    path = data_root() / name
    for part in parts:
        path = path / part
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir(*parts: str, create: bool = True) -> Path:
    return _sub("data", *parts, create=create)


def app_dir(app: str, sub: str = "", create: bool = True) -> Path:
    """앱(기능)별 데이터 폴더: data/{app}[/{sub}]. 기존 `get_app_dir` 의 대체."""
    return data_dir(app, *([sub] if sub else []), create=create)


def db_path(name: str, create_parent: bool = True) -> Path:
    """sqlite 등 DB 파일 경로: db/{name}. 파일은 만들지 않고 폴더만 만든다."""
    folder = _sub("db", create=create_parent)
    return folder / name


def logs_dir(create: bool = True) -> Path:
    return _sub("logs", create=create)


def cache_dir(create: bool = True) -> Path:
    return _sub("cache", create=create)


def sessions_dir(create: bool = True) -> Path:
    return _sub("sessions", create=create)


def browser_profile_dir(name: str = "ai_chrome", create: bool = True) -> Path:
    return _sub("browser_profile", name, create=create)


def secrets_dir(create: bool = True) -> Path:
    return _sub("secrets", create=create)


def migration_dir(create: bool = True) -> Path:
    return _sub("migration", create=create)


def ensure_layout() -> Path:
    """데이터 루트와 표준 하위 폴더를 모두 만든다(설치·첫 실행 시). 데이터 루트를 반환한다."""
    root = data_root()
    for name in _SUBDIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


# ── Known Folder (사용자 폴더: 다운로드·문서·바탕화면) ─────────────────────────────

_KNOWN_FOLDER_IDS = {
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}
_HOME_FALLBACK = {
    "downloads": "Downloads",
    "documents": "Documents",
    "desktop": "Desktop",
    "pictures": "Pictures",
    "videos": "Videos",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _windows_known_folder(folder_id: str) -> Path | None:
    guid_bytes = uuid.UUID(folder_id).bytes_le
    guid = _GUID.from_buffer_copy(guid_bytes)
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined]  # 윈도우에서만 호출됨
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    result = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
    try:
        if result != 0 or not out.value:
            return None
        return Path(out.value)
    finally:
        ole32.CoTaskMemFree(out)


def known_folder(name: str) -> Path:
    """사용자 폴더(downloads·documents·desktop·pictures·videos). 하드코딩 대신 윈도우 Known Folder API 를 쓴다."""
    key = name.strip().lower()
    if key not in _KNOWN_FOLDER_IDS:
        raise ValueError(f"알 수 없는 사용자 폴더: {name!r} (가능: {', '.join(sorted(_KNOWN_FOLDER_IDS))})")
    if _is_windows():
        found = _windows_known_folder(_KNOWN_FOLDER_IDS[key])
        if found is not None:
            return found
    return Path.home() / _HOME_FALLBACK[key]


# ── 저장소(소스 폴더) 위치 — data_root()/config_root() 와는 다른 질문이다 ─────────────
# data_root()/config_root() 는 "앱 데이터를 어디 쓰나"(OS 표준, 저장소 상대 폴백 없음).
# repo_root() 는 "이 저장소 소스가 어디 있나"(T1-① 정본화). 실제 구현은
# ai_orchestrator/paths.py 에 있다(2026-10-07, 폴더 순환 해소 — ai_orchestrator
# 쪽 호출자가 이 모듈을 import하면 ai_orchestrator↔scripts 양방향 간선이 생겨
# 순환으로 집계되던 문제. scripts → ai_orchestrator 는 원래 허용된 방향이라
# 여기서 재수출하는 건 문제없다). ai_orchestrator 안의 호출자는
# ai_orchestrator.paths.repo_root 를 직접 쓴다.


# ── 이전 PC 경로 대체: 형제 프로젝트·OneDrive·환경변수 우선 해석 ─────────────────────


def sibling_project(name: str) -> Path:
    """저장소와 같은 부모 폴더에 있는 형제 프로젝트 폴더(예: '05. g2b', '30. 해한 AI 홈페이지').

    예전에는 드라이브 루트의 작업 폴더(work 아래 NN. 프로젝트)로 하드코딩했다. 프로젝트 루트가 어디든 저장소 기준으로 찾는다.
    존재 여부는 확인하지 않는다(호출부가 필요할 때 검사).
    """
    return repo_root().parent / name


def onedrive_root() -> Path | None:
    """OneDrive 동기화 루트(%OneDrive% 계열 환경변수). 없으면 None."""
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        value = os.environ.get(var, "").strip()
        if value:
            return Path(value)
    return None


def resolve_external(env_var: str, *default_parts: str, base: Path | None = None) -> Path:
    """외부 자료 경로: 환경변수 → (base 또는 사용자 문서 폴더)/default_parts.

    컴퓨터마다 다른 위치의 이미지·영상·내보내기 폴더처럼 코드에 박을 수 없는 경로용. 환경변수로 바꿀 수 있다.
    """
    override = os.environ.get(env_var, "").strip()
    if override:
        return Path(override)
    root = base if base is not None else known_folder("documents")
    return root.joinpath(*default_parts)
