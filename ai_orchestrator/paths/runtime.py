"""런타임 데이터 위치 — 저장(storage)·데이터(data) 폴더의 단일 정본.

왜 필요한가: 데스크톱(PyInstaller 번들 + 포터블 exe)에서는 코드 옆(`ai_orchestrator/storage`, `<저장소>/data`)이
설치/압축해제 폴더 안이라 갱신·재실행 때 계정(users.db)·감사/승인 기록이 사라질 수 있다(DESKTOP_RUNTIME_AUDIT D1).
모든 런타임 쓰기 경로는 `Path(__file__)` 기준으로 직접 계산하지 말고 아래 함수를 쓴다.

해석 순서(저장소/서버 실행에서 환경변수가 없으면 지금 위치 그대로 — 동작 불변):
    data_dir()    : ① HAEHAN_DATA_DIR(옛 이름 — 데이터 폴더를 직접 지정, 기존 호출자 호환)
                    ② HAEHAN_DATA_ROOT/data
                    ③ <저장소>/data
    storage_dir() : ① HAEHAN_STORAGE_DIR(저장 폴더를 직접 지정)
                    ② HAEHAN_DATA_ROOT/storage
                    ③ <저장소>/ai_orchestrator/storage

HAEHAN_DATA_ROOT 는 `scripts.common.app_paths.data_root()` 가 쓰는 같은 환경변수다 — 데스크톱은 Electron 이 이 값을 사용자
프로필 아래 한 곳(userData)으로 정해 서버·스크립트가 같은 루트를 보게 한다. 환경변수가 없을 때 `app_paths` 는
Windows 표준(%LOCALAPPDATA%\\HaehanAI\\Orchestrator)을 쓰지만, 이 모듈은 저장소 실행의 기존 위치를 유지한다
(소스 체크아웃·Docker 의 기존 데이터가 그대로 읽히도록). 두 정본이 갈라지지 않게 환경변수 하나로 묶는다.

표준 라이브러리만 사용하는 잎 모듈 — 어느 층에서 import 해도 순환이 생기지 않는다.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import repo_root

ENV_DATA_ROOT = "HAEHAN_DATA_ROOT"
ENV_DATA_DIR = "HAEHAN_DATA_DIR"  # 옛 이름(Electron 이 userData\data 를 넘기던 값) — 계속 인정
ENV_STORAGE_DIR = "HAEHAN_STORAGE_DIR"

_PKG_DIR = Path(__file__).resolve().parents[1]  # ai_orchestrator/
_REPO_ROOT = repo_root()


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else None


def default_storage_dir() -> Path:
    """환경변수 없이 쓰던 기존 저장 위치(번들이면 번들 안) — 이행의 원본 위치."""
    return _PKG_DIR / "storage"


def default_data_dir() -> Path:
    """환경변수 없이 쓰던 기존 데이터 위치(번들이면 번들 안) — 이행의 원본 위치."""
    return _REPO_ROOT / "data"


def data_root_override() -> Path | None:
    """HAEHAN_DATA_ROOT 가 설정돼 있으면 그 경로(데스크톱), 아니면 None(저장소 실행)."""
    return _env_path(ENV_DATA_ROOT)


def _resolve_dir(env_name: str, root_subdir: str, default: Path) -> Path:
    """폴더 위치 규칙 한 곳: 개별 환경변수 > HAEHAN_DATA_ROOT/<하위> > 예전 기본 위치. data_dir·storage_dir 가 함께 쓴다."""
    explicit = _env_path(env_name)
    if explicit is not None:
        return explicit
    root = data_root_override()
    if root is not None:
        return root / root_subdir
    return default


def data_dir() -> Path:
    """업무 데이터(JSON·보고서·세션 상태·감사 폴더 등) 루트. 디렉터리를 만들지는 않는다."""
    return _resolve_dir(ENV_DATA_DIR, "data", default_data_dir())


def storage_dir() -> Path:
    """DB(SQLite)·감사/승인 JSONL·비밀·업로드 첨부 루트. 디렉터리를 만들지는 않는다."""
    return _resolve_dir(ENV_STORAGE_DIR, "storage", default_storage_dir())


def ensure_runtime_dirs() -> None:
    """HAEHAN_DATA_ROOT 로 새 위치를 지정한 실행(데스크톱)에서 저장·데이터 폴더를 미리 만든다.

    저장소 실행(환경변수 없음)은 기존 폴더 그대로라 아무것도 하지 않는다. 실패해도 예외를 던지지 않는다 —
    실제로 쓰는 쪽이 자기 오류를 내므로 여기서 시작을 막지 않는다.
    """
    if data_root_override() is None:
        return
    for target in (storage_dir(), data_dir()):
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """상태 파일을 tmp 에 쓴 뒤 rename — 쓰는 도중 앱이 종료돼도 반쪽 파일이 남지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))
