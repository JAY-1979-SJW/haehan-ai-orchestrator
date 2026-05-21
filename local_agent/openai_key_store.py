"""OpenAI 개발/테스트 API key 저장소.

policy:
  - Windows Credential Manager (keyring) 우선
  - 평문 fallback 기본 OFF (사용자 opt-in 시에만)
  - API key 원문은 어떤 로그/예외/repr 에도 노출 0
  - fingerprint = "sk-****abcd" 마스킹만 (diagnostics 표시용)

service / account:
  service = "haehan-openai-dev"
  account = "dev-api-key"   (모드 분기 시 account 가 mode 별로 분리될 수 있음)

이번 공정에서는 저장/조회/삭제/검증/fingerprint 만. 실제 OpenAI API 호출 0.
"""
from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("haehan_openai_key_store")

SERVICE_NAME = "haehan-openai-dev"
ACCOUNT_DEFAULT = "dev-api-key"

MIN_KEY_LENGTH = 20            # 너무 짧은 값 거부 (placeholder/오타)
MAX_KEY_LENGTH = 2048

# obvious placeholder 거부 (소문자 비교)
_PLACEHOLDER_VALUES = {
    "sk-...", "your_api_key", "your-api-key", "yourapikey",
    "test", "dummy", "placeholder", "xxxxx", "...",
    "sk-test", "sk-dummy",
}


# ── 결과 / 예외 ────────────────────────────────────────────────


@dataclass
class KeyStoreResult:
    ok: bool
    backend: str = ""             # "keyring" | "plaintext" | ""
    fingerprint: str = ""         # sk-****abcd (저장 성공 시)
    error_code: str = ""          # INVALID_FORMAT / PLACEHOLDER /
                                   # KEYRING_UNAVAILABLE / SAVE_FAILED


class KeyStoreError(RuntimeError):
    """key store 작업 실패."""


# ── keyring optional ───────────────────────────────────────────


def _try_keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def keyring_backend_name() -> str:
    kr = _try_keyring()
    if kr is None:
        return ""
    try:
        return type(kr.get_keyring()).__name__
    except Exception:
        return ""


def keyring_available() -> bool:
    name = keyring_backend_name()
    if not name:
        return False
    bad = ("null", "fail")
    return not any(b in name.lower() for b in bad)


# ── 평문 fallback (opt-in 전용) ───────────────────────────────


def _plaintext_path(*, base_dir: Path | None = None,
                     account: str = ACCOUNT_DEFAULT) -> Path:
    base = base_dir or Path(
        os.getenv("HAEHAN_OPENAI_KEY_DIR",
                   str(Path.home() / ".haehan_agent" / "openai")),
    )
    safe = account.replace("/", "_").replace(":", "_")
    return base / f"{safe}.key"


def _save_plaintext(api_key: str, *, account: str,
                     base_dir: Path | None = None) -> None:
    p = _plaintext_path(base_dir=base_dir, account=account)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(api_key, encoding="utf-8")
    try:
        if not os.name == "nt":
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except Exception:
        pass
    tmp.replace(p)


def _load_plaintext(*, account: str,
                     base_dir: Path | None = None) -> str | None:
    p = _plaintext_path(base_dir=base_dir, account=account)
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _delete_plaintext(*, account: str,
                       base_dir: Path | None = None) -> None:
    p = _plaintext_path(base_dir=base_dir, account=account)
    try:
        p.unlink(missing_ok=True)
    except Exception:
        pass


# ── 검증 + 마스킹 ─────────────────────────────────────────────


def validate_key_format(api_key: str) -> tuple[bool, str]:
    """key 형식 검증. (ok, error_code)."""
    if api_key is None:
        return (False, "INVALID_FORMAT")
    raw = api_key.strip()
    if not raw:
        return (False, "INVALID_FORMAT")
    if len(raw) < MIN_KEY_LENGTH:
        return (False, "INVALID_FORMAT")
    if len(raw) > MAX_KEY_LENGTH:
        return (False, "INVALID_FORMAT")
    if raw.lower() in _PLACEHOLDER_VALUES:
        return (False, "PLACEHOLDER")
    # 공백 포함 거부
    if any(c.isspace() for c in raw):
        return (False, "INVALID_FORMAT")
    return (True, "")


def redact_key(api_key: str) -> str:
    """원문 노출 0 — fingerprint 만. 너무 짧으면 ****."""
    if not api_key:
        return ""
    raw = api_key.strip()
    if len(raw) < 8:
        return "****"
    # sk- 같은 prefix 가 있으면 prefix + ****+ last4
    if "-" in raw[:5]:
        prefix = raw.split("-", 1)[0] + "-"
    else:
        prefix = "key-"
    return f"{prefix}****{raw[-4:]}"


def get_key_fingerprint(*, account: str = ACCOUNT_DEFAULT,
                         allow_plaintext_fallback: bool = False,
                         base_dir: Path | None = None) -> str:
    """저장된 key 의 fingerprint 만 반환. 원문 노출 0.

    없으면 빈문자열.
    """
    key = load_dev_key(account=account,
                        allow_plaintext_fallback=allow_plaintext_fallback,
                        base_dir=base_dir)
    if not key:
        return ""
    fp = redact_key(key)
    # 즉시 폐기
    key = ""
    return fp


# ── core API ─────────────────────────────────────────────────


def save_dev_key(api_key: str, *,
                  account: str = ACCOUNT_DEFAULT,
                  allow_plaintext_fallback: bool = False,
                  base_dir: Path | None = None) -> KeyStoreResult:
    """key 저장. Credential Manager 우선, fallback 은 opt-in."""
    ok, err = validate_key_format(api_key)
    if not ok:
        return KeyStoreResult(ok=False, error_code=err)

    fp = redact_key(api_key)
    kr = _try_keyring()
    if kr is not None and keyring_available():
        try:
            kr.set_password(SERVICE_NAME, account, api_key)
            return KeyStoreResult(ok=True, backend="keyring",
                                    fingerprint=fp)
        except Exception:
            # keyring 실패 — fallback 검토
            if not allow_plaintext_fallback:
                return KeyStoreResult(ok=False,
                                        error_code="KEYRING_UNAVAILABLE")
    elif not allow_plaintext_fallback:
        return KeyStoreResult(ok=False, error_code="KEYRING_UNAVAILABLE")

    # 평문 fallback (opt-in)
    if not allow_plaintext_fallback:
        return KeyStoreResult(ok=False, error_code="KEYRING_UNAVAILABLE")
    try:
        _save_plaintext(api_key, account=account, base_dir=base_dir)
        # 권한 경고 로그 (값 미포함)
        logger.warning(
            "openai-key: keyring 사용 불가 — 평문 fallback 사용 중 (운영 비권장)"
        )
        return KeyStoreResult(ok=True, backend="plaintext",
                                fingerprint=fp)
    except Exception:
        return KeyStoreResult(ok=False, error_code="SAVE_FAILED")


def load_dev_key(*, account: str = ACCOUNT_DEFAULT,
                  allow_plaintext_fallback: bool = False,
                  base_dir: Path | None = None) -> str | None:
    """저장된 key 반환. 호출자는 사용 후 즉시 변수 폐기 책임."""
    kr = _try_keyring()
    if kr is not None and keyring_available():
        try:
            v = kr.get_password(SERVICE_NAME, account)
            if v:
                return v
        except Exception:
            pass
    if allow_plaintext_fallback:
        return _load_plaintext(account=account, base_dir=base_dir)
    return None


def delete_dev_key(*, account: str = ACCOUNT_DEFAULT,
                    allow_plaintext_fallback: bool = False,
                    base_dir: Path | None = None) -> bool:
    """key 삭제 — 둘 다 시도 (keyring + plaintext)."""
    deleted = False
    kr = _try_keyring()
    if kr is not None and keyring_available():
        try:
            kr.delete_password(SERVICE_NAME, account)
            deleted = True
        except Exception:
            pass
    if allow_plaintext_fallback:
        _delete_plaintext(account=account, base_dir=base_dir)
        deleted = True
    return deleted


def has_dev_key(*, account: str = ACCOUNT_DEFAULT,
                 allow_plaintext_fallback: bool = False,
                 base_dir: Path | None = None) -> bool:
    return bool(load_dev_key(account=account,
                               allow_plaintext_fallback=allow_plaintext_fallback,
                               base_dir=base_dir))


def describe_backend() -> tuple[bool, str]:
    """(available, backend_name) — diagnostics 표시용."""
    return (keyring_available(), keyring_backend_name() or "none")


# ── 공개 API 표면 ───────────────────────────────────────────

__all__ = (
    "SERVICE_NAME", "ACCOUNT_DEFAULT", "MIN_KEY_LENGTH",
    "KeyStoreResult", "KeyStoreError",
    "save_dev_key", "load_dev_key", "delete_dev_key",
    "has_dev_key", "get_key_fingerprint",
    "validate_key_format", "redact_key",
    "keyring_available", "keyring_backend_name", "describe_backend",
)
