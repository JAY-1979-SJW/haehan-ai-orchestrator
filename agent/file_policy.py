"""파일 기반 action 경로 정책.

규칙:
- 입력 파일은 ``AGENT_WORK_DIR`` 하위만 허용.
- 출력 파일은 ``AGENT_OUTPUT_DIR`` 하위만 허용.
- 상대경로/경로탈출(``..``) 차단 — 허용 디렉터리 밖으로 벗어나면 거부.
- 원본 overwrite 금지 (입력 파일과 같은 경로에 쓰기 금지, 기존 출력 파일 overwrite 금지).

이 모듈은 ``agent.config.AGENT_WORK_DIR`` / ``AGENT_OUTPUT_DIR`` 을
런타임에 참조해 환경변수나 monkeypatch 가 반영되도록 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import config as _cfg
from . import errors as _err


def _resolve_under(base: Path, candidate: str) -> Optional[Path]:
    """``candidate`` 를 절대 경로로 풀어 ``base`` 하위이면 반환, 아니면 None.

    - 상대경로는 거부 (절대 경로만 허용).
    - ``..`` 경로탈출로 base 밖으로 벗어나면 거부.
    """
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    try:
        p = Path(candidate).expanduser()
    except (OSError, ValueError):
        return None
    if not p.is_absolute():
        return None
    try:
        resolved = p.resolve(strict=False)
        base_resolved = Path(base).resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return resolved


def resolve_input_path(file_path: str) -> tuple[Optional[Path], Optional[str]]:
    """입력 파일 경로 검증.

    반환: (resolved_path, error_code). 성공 시 error_code=None.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        return None, _err.FILE_PATH_REQUIRED

    resolved = _resolve_under(_cfg.AGENT_WORK_DIR, file_path)
    if resolved is None:
        return None, _err.FILE_NOT_ALLOWED
    if not resolved.exists() or not resolved.is_file():
        return None, _err.FILE_NOT_FOUND
    return resolved, None


def resolve_output_path(
    output_path: str,
    *,
    source_path: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[str]]:
    """출력 파일 경로 검증.

    - ``AGENT_OUTPUT_DIR`` 하위여야 함.
    - 이미 존재하는 파일이면 거부 (overwrite 금지).
    - ``source_path`` 와 같은 경로면 원본 overwrite 이므로 거부.
    """
    if not isinstance(output_path, str) or not output_path.strip():
        return None, _err.OUTPUT_PATH_REQUIRED

    resolved = _resolve_under(_cfg.AGENT_OUTPUT_DIR, output_path)
    if resolved is None:
        return None, _err.OUTPUT_PATH_NOT_ALLOWED

    if source_path is not None:
        try:
            if resolved == Path(source_path).resolve(strict=False):
                return None, _err.OUTPUT_PATH_NOT_ALLOWED
        except (OSError, RuntimeError):
            return None, _err.OUTPUT_PATH_NOT_ALLOWED

    if resolved.exists():
        return None, _err.OUTPUT_FILE_EXISTS

    return resolved, None


__all__ = [
    "resolve_input_path",
    "resolve_output_path",
]
