"""Desktop agent device_token 저장소 (Windows Credential Manager / keyring 우선).

기본 동작:
  - keyring 라이브러리를 통해 OS 자격증명 저장소에 device_token 저장.
  - keyring이 없거나 backend가 사용 불가능하면 기본은 fail-closed.
  - 명시적으로 ``allow_plaintext_fallback=True`` 인 경우에만 평문 파일에
    fallback 저장(MVP/CI 한정). 평문 fallback 사용 시 audit warning 남김.

저장 키:
  service = "haehan-agent"
  username = f"{server_url}::{agent_id}"  (서버/에이전트 단위 분리)

device_token 원문은 어떤 로그/예외/CLI 출력에도 노출되지 않는다.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAME = "haehan-agent"


class TokenStoreError(RuntimeError):
    """keyring 미설치/backend 불가 등으로 저장이 불가능할 때."""


def _key(server_url: str, agent_id: str) -> str:
    return f"{server_url.rstrip('/')}::{agent_id}"


def _try_import_keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:  # pragma: no cover - 환경 의존  # noqa: BLE001 - OS keyring 기반 토큰 저장/조회/삭제 - 실패 시 예외 타입명만 로그(토큰 값 노출 없음)하고 평문 폴백 허용여부에 따라 처리
        return None


def keyring_backend_name() -> str:
    """현재 사용 가능한 keyring backend 이름. 없으면 ''."""
    kr = _try_import_keyring()
    if kr is None:
        return ""
    try:
        return type(kr.get_keyring()).__name__
    except Exception:  # pragma: no cover  # noqa: BLE001 - OS keyring 기반 토큰 저장/조회/삭제 - 실패 시 예외 타입명만 로그(토큰 값 노출 없음)하고 평문 폴백 허용여부에 따라 처리
        return ""


def keyring_available() -> bool:
    name = keyring_backend_name()
    if not name:
        return False
    # Null/Fail backends는 사용 불가로 간주 (저장은 성공한 척하지 않음).
    bad = ("null", "fail")
    return not any(b in name.lower() for b in bad)


# ── 평문 fallback (옵트인 전용) ───────────────────────────────────────────


def _plaintext_path(server_url: str, agent_id: str, base_dir: Path | None = None) -> Path:
    base = (
        Path(base_dir)
        if base_dir
        else Path(os.getenv("HAEHAN_AGENT_TOKEN_DIR", str(Path.home() / ".haehan_agent" / "tokens")))
    )
    safe = _key(server_url, agent_id).replace("/", "_").replace(":", "_")
    return base / f"{safe}.token"


def _save_plaintext(server_url: str, agent_id: str, token: str, base_dir: Path | None = None) -> None:
    p = _plaintext_path(server_url, agent_id, base_dir=base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"v": 1, "token": token}), encoding="utf-8")
    tmp.replace(p)
    with contextlib.suppress(OSError):
        p.chmod(0o600)


def _load_plaintext(server_url: str, agent_id: str, base_dir: Path | None = None) -> str | None:
    p = _plaintext_path(server_url, agent_id, base_dir=base_dir)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    tok = str(data.get("token", "")).strip()
    return tok or None


def _delete_plaintext(server_url: str, agent_id: str, base_dir: Path | None = None) -> bool:
    p = _plaintext_path(server_url, agent_id, base_dir=base_dir)
    if p.exists():
        try:
            p.unlink()
            return True
        except OSError:
            return False
    return False


# ── public API ────────────────────────────────────────────────────────────


def save_device_token(
    server_url: str,
    agent_id: str,
    token: str,
    *,
    allow_plaintext_fallback: bool = False,
    plaintext_base_dir: Path | None = None,
) -> str:
    """저장 후 사용된 backend 이름을 반환. 실패 시 TokenStoreError."""
    if not server_url or not agent_id or not token:
        raise TokenStoreError("server_url/agent_id/token이 비어있습니다.")
    kr = _try_import_keyring()
    if kr is not None and keyring_available():
        try:
            kr.set_password(SERVICE_NAME, _key(server_url, agent_id), token)
            return keyring_backend_name()
        except Exception as e:  # pragma: no cover - backend 실패 분기  # noqa: BLE001 - OS keyring 기반 토큰 저장/조회/삭제 - 실패 시 예외 타입명만 로그(토큰 값 노출 없음)하고 평문 폴백 허용여부에 따라 처리
            logger.warning("keyring set_password 실패: %s", type(e).__name__)
    if not allow_plaintext_fallback:
        raise TokenStoreError("keyring 사용 불가. 평문 fallback이 비활성화되어 저장을 거부합니다.")
    _save_plaintext(server_url, agent_id, token, base_dir=plaintext_base_dir)
    logger.warning("device_token: keyring 사용 불가 — 평문 fallback에 저장됨 (운영 비권장)")
    return "plaintext-fallback"


def load_device_token(
    server_url: str, agent_id: str, *, allow_plaintext_fallback: bool = False, plaintext_base_dir: Path | None = None
) -> str | None:
    if not server_url or not agent_id:
        return None
    kr = _try_import_keyring()
    if kr is not None and keyring_available():
        try:
            val = kr.get_password(SERVICE_NAME, _key(server_url, agent_id))
            if val:
                return val
        except Exception:  # pragma: no cover  # noqa: S110, BLE001 - keyring 미가용/실패 시 조용히 폴백 경로로 진행, 토큰 값은 노출하지 않음
            pass
    if allow_plaintext_fallback:
        return _load_plaintext(server_url, agent_id, base_dir=plaintext_base_dir)
    return None


def delete_device_token(
    server_url: str, agent_id: str, *, allow_plaintext_fallback: bool = False, plaintext_base_dir: Path | None = None
) -> bool:
    deleted = False
    kr = _try_import_keyring()
    if kr is not None and keyring_available():
        try:
            kr.delete_password(SERVICE_NAME, _key(server_url, agent_id))
            deleted = True
        except Exception:  # pragma: no cover  # noqa: S110, BLE001 - keyring 미가용/실패 시 조용히 폴백 경로로 진행, 토큰 값은 노출하지 않음
            pass
    if allow_plaintext_fallback and _delete_plaintext(server_url, agent_id, base_dir=plaintext_base_dir):
        deleted = True
    return deleted


def has_device_token(
    server_url: str, agent_id: str, *, allow_plaintext_fallback: bool = False, plaintext_base_dir: Path | None = None
) -> bool:
    return (
        load_device_token(
            server_url,
            agent_id,
            allow_plaintext_fallback=allow_plaintext_fallback,
            plaintext_base_dir=plaintext_base_dir,
        )
        is not None
    )


def describe_backend() -> tuple[bool, str]:
    """(usable, backend_name) — CLI/status 용. token 원문은 절대 반환하지 않음."""
    return keyring_available(), keyring_backend_name()


__all__ = [
    "SERVICE_NAME",
    "TokenStoreError",
    "delete_device_token",
    "describe_backend",
    "has_device_token",
    "keyring_available",
    "keyring_backend_name",
    "load_device_token",
    "save_device_token",
]
