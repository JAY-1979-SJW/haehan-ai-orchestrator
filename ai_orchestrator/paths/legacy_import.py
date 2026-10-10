"""예전 설치 폴더(이전 Haehan AI 앱)의 데이터를 새 앱 데이터 위치로 1회 복사 가져오기.

배경: 예전 앱(예: `C:\\Users\\<사용자>\\Haehan AI`)은 계정(users.db)·감사/승인 기록을 **자기 설치 폴더 안**
(`resources\\server\\haehan-server\\_internal\\ai_orchestrator\\storage`)에 저장했다. 새 앱은 데이터를 사용자 프로필
(`%APPDATA%\\Haehan AI` = HAEHAN_DATA_ROOT) 아래에 두므로, 예전 계정으로 이어 쓰려면 이 데이터를 가져와야 한다
(`paths.migrate` 의 이행은 '새 앱 자신의 번들 안쪽'만 보므로 예전 **설치 폴더**는 대상이 아니다).

동작(첫 실행에서만):
  - 새 위치에 `storage\\users.db` 가 아직 없을 때만 한다 — 이미 계정이 있으면(새로 등록했거나 이미 가져왔으면) 하지 않는다.
  - 알려진 예전 설치 경로를 순서대로 탐색한다(아래 default_candidates). 데이터가 있는 첫 후보 하나만 쓴다.
  - **복사만**, 새 위치에 이미 있는 파일은 **덮어쓰지 않고**, 원본은 건드리지 않는다(`paths.migrate._copy_tree` 재사용).
  - users.db 는 **맨 마지막에** 복사한다 — 앞 단계에서 하나라도 실패하면 users.db 를 복사하지 않으므로, 다음 실행에서
    '새 위치에 users.db 없음' 조건이 그대로 유지돼 **재시도**된다(부분 실패 후 계정만 있고 나머지가 빠지는 상태 방지).
  - 모두 성공하면 `<root>\\.legacy-import.json`(tmp+rename 원자적 쓰기) 표식을 남기고, 이후엔 다시 하지 않는다.
    실패하면 표식을 남기지 않고 오류를 로그(서버 로그 fastapi.log)에 남긴 뒤 시작은 계속한다.
  - 예전 앱이 실행 중으로 보이면(서버 포트 사용 중 또는 파일 잠김) 아무것도 복사하지 않고 안내만 남긴다(다음 실행에서 재시도).
번들(frozen) 실행 + HAEHAN_DATA_ROOT 일 때만 자동 동작한다(시험·수동은 HAEHAN_MIGRATE_LEGACY=1).
탐색 경로를 바꾸려면 HAEHAN_LEGACY_INSTALL_DIRS(os.pathsep 로 구분)를 쓴다(시험용).
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

from .migrate import _copy_file, _copy_tree, _same
from .runtime import data_dir, data_root_override, storage_dir

logger = logging.getLogger(__name__)

MARKER_NAME = ".legacy-import.json"
ENV_CANDIDATES = "HAEHAN_LEGACY_INSTALL_DIRS"
_INTERNAL = Path("resources") / "server" / "haehan-server" / "_internal"
_SKIP_DEFER = frozenset({"users.db"})


def _say(message: str, *, warn: bool = False) -> None:
    """서버 로그(fastapi.log)에 보이도록 stderr 로도 남긴다(부트스트랩 시점에는 logging 설정 전이다)."""
    (logger.warning if warn else logger.info)(message)
    print(f"[legacy-import] {message}", file=sys.stderr, flush=True)


def default_candidates() -> list[Path]:
    """알려진 예전 설치 위치. 근거: ① 실제 예전 빌드(9월 9일 unpacked)는 %USERPROFILE%\\Haehan AI 에 있다,
    ② electron-builder nsis(oneClick=false, 사용자 설치 기본)의 기본 위치는 %LOCALAPPDATA%\\Programs\\Haehan AI 다."""
    override = os.environ.get(ENV_CANDIDATES, "").strip()
    if override:
        return [Path(p) for p in override.split(os.pathsep) if p.strip()]
    out: list[Path] = []
    profile = os.environ.get("USERPROFILE", "").strip()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if profile:
        out.append(Path(profile) / "Haehan AI")
    if local:
        out.append(Path(local) / "Programs" / "Haehan AI")
    return out


def _sources(install_dir: Path) -> list[tuple[str, Path, Path]]:
    internal = install_dir / _INTERNAL
    return [
        ("storage", internal / "ai_orchestrator" / "storage", storage_dir()),
        ("data", internal / "data", data_dir()),
    ]


def _has_files(path: Path) -> bool:
    return path.is_dir() and any(p.is_file() for p in path.rglob("*"))


def _legacy_app_running() -> bool:
    """예전 앱 서버가 떠 있으면 같은 포트(기본 8401)가 이미 쓰이고 있다 — 이때 복사하면 쓰는 중인 파일을 복사하게 된다."""
    port = int(os.environ.get("HAEHAN_PORT", "8401") or "8401")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _locked_files(files: list[Path]) -> list[Path]:
    """Windows 에서 다른 프로세스가 쓰기로 열어 둔(공유 거부) 파일. 다른 OS 에서는 항상 빈 목록."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    k32.CreateFileW.restype = wintypes.HANDLE
    invalid = wintypes.HANDLE(-1).value
    locked: list[Path] = []
    for f in files:
        # 읽기 접근 + 다른 쓰기 거부(FILE_SHARE_READ): 누가 쓰기로 열고 있으면 공유 위반으로 실패한다.
        handle = k32.CreateFileW(str(f), 0x80000000, 0x1, None, 3, 0x80, None)
        if handle == invalid or handle is None:
            if ctypes.get_last_error() == 32:  # ERROR_SHARING_VIOLATION
                locked.append(f)
            continue
        k32.CloseHandle(handle)
    return locked


def _write_marker(root: Path, payload: dict) -> None:
    marker = root / MARKER_NAME
    root.mkdir(parents=True, exist_ok=True)
    tmp = marker.with_name(marker.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(marker)  # 원자적 완료 표식


def import_legacy_install() -> dict:
    """필요하면 예전 설치 폴더 데이터를 가져오고 결과 요약을 돌려준다. 절대 예외를 밖으로 던지지 않는다."""
    try:
        return _import()
    except Exception as exc:  # noqa: BLE001 - 가져오기 실패가 서버 시작을 막으면 안 된다(로그만 남김)
        _say(f"예전 설치 폴더 가져오기 중 예기치 못한 오류 — 건너뜀: {type(exc).__name__}: {exc}", warn=True)
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _import() -> dict:  # noqa: C901, PLR0912 - 전제 조건(환경·번들·표식·새 데이터·예전 앱 실행)을 순서대로 점검하는 절차
    root = data_root_override()
    if root is None:
        return {"status": "skipped", "reason": "HAEHAN_DATA_ROOT 없음(저장소 실행)"}
    if not (getattr(sys, "frozen", False) or os.environ.get("HAEHAN_MIGRATE_LEGACY") == "1"):
        return {"status": "skipped", "reason": "번들 실행이 아님(HAEHAN_MIGRATE_LEGACY=1 로 강제 가능)"}
    if (root / MARKER_NAME).is_file():
        return {"status": "already_done"}
    if (storage_dir() / "users.db").is_file():
        return {"status": "skipped", "reason": "새 위치에 이미 계정 DB(users.db)가 있음 — 가져오지 않음"}

    chosen: Path | None = None
    for cand in default_candidates():
        sources = _sources(cand)
        if any(_has_files(src) for _, src, _ in sources):
            if any(_same(src, dst) for _, src, dst in sources):
                continue
            chosen = cand
            break
    if chosen is None:
        return {"status": "skipped", "reason": "알려진 예전 설치 경로에서 데이터를 찾지 못함"}

    sources = [(label, src, dst) for label, src, dst in _sources(chosen) if _has_files(src)]
    if _legacy_app_running():
        _say(
            f"예전 앱이 실행 중으로 보입니다(서버 포트 사용 중) — 가져오기를 건너뜁니다. 예전 앱을 종료한 뒤 이 앱을 다시 실행하세요: {chosen}",
            warn=True,
        )
        return {"status": "skipped", "reason": "legacy_app_running", "source": str(chosen)}
    files = [p for _, src, _ in sources for p in src.rglob("*") if p.is_file()]
    locked = _locked_files(files)
    if locked:
        _say(
            f"예전 앱이 파일을 쓰는 중으로 보입니다({locked[0].name} 등 {len(locked)}개 잠김) — 가져오기를 건너뜁니다. 예전 앱을 종료한 뒤 다시 실행하세요.",
            warn=True,
        )
        return {"status": "skipped", "reason": "legacy_files_locked", "source": str(chosen)}

    errors: list[str] = []
    summary: dict[str, dict[str, int]] = {}
    for label, src, dst in sources:
        copied, skipped = _copy_tree(src, dst, errors, defer=_SKIP_DEFER)
        summary[label] = {"copied": copied, "skipped_existing": skipped}
    # users.db 는 맨 마지막 — 앞 단계가 실패하면 복사하지 않아 '새 위치에 users.db 없음' 이 유지되고 다음 실행에서 재시도된다.
    legacy_users = sources[0][1] / "users.db" if sources and sources[0][0] == "storage" else None
    if legacy_users is not None and legacy_users.is_file() and not errors:
        target = storage_dir() / "users.db"
        if _copy_file(legacy_users, target, errors):
            summary["storage"]["copied"] += 1
    if errors:
        _say(
            f"예전 설치 폴더 가져오기 일부 실패 {len(errors)}건 — 표식을 남기지 않고 다음 실행에서 다시 시도합니다: {errors[0]}",
            warn=True,
        )
        return {"status": "partial", "source": str(chosen), "summary": summary, "errors": errors[:20]}
    total = sum(v["copied"] for v in summary.values())
    payload = {
        "complete": True,
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": str(chosen),
        "summary": summary,
    }
    try:
        _write_marker(root, payload)
    except OSError as exc:
        _say(f"완료 표식 기록 실패(다음 실행에서 다시 확인): {exc}", warn=True)
    _say(f"예전 설치 폴더에서 {total}개 파일을 복사해 가져왔습니다(원본 유지): {chosen}")
    return {"status": "complete", **payload}
