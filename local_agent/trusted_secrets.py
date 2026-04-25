"""F-4C/F-4D — Trusted automation secret reference 인터페이스.

본 모듈은 대표님 PC 에서만 동작하는 trusted browser automation 트랙의
**비밀값 처리 인터페이스** 를 정의한다.

핵심 원칙 (docs/design/trusted_browser_automation_policy.md):
  - AI/GPT/서버는 비밀값을 알지 않는다.
  - 오케스트레이터→로컬 에이전트 파라미터는 ``secret_id`` 만 전달한다.
  - 로컬 에이전트만 ``secret_id`` 를 OS 키 저장소에서 resolve 해 잠시
    메모리에 보유한다.
  - 평문 비밀값이 ActionResult / audit log / exception trace 에 절대
    노출되지 않게 한다.

F-4C 단계에서 **구현된** 것 (유지):
  - ``SecretRef`` (TypedDict) — secret_id 기반 reference 타입
  - ``validate_secret_ref(ref)``                     — 형식 검증
  - ``reject_raw_secret_params(params)``             — raw 비밀 키워드 차단
  - ``redact_for_log(payload)``                       — 로그/결과용 마스킹

F-4D 단계에서 **추가** (본 모듈):
  - ``SecretBackend`` Protocol                        — 추상 인터페이스
  - ``MockSecretBackend``                             — 테스트 전용 dict 주입
  - ``WindowsKeyringSecretBackend``                   — keyring 기반 (선택적)
  - ``get_secret_backend(name=None)``                 — backend factory
  - ``resolve_secret(secret_id, *, backend=...)``     — backend 위임
  - ``SecretResolutionError`` / ``SecretNotFoundError`` /
    ``SecretBackendUnavailableError``                — 비밀값 미노출 예외

F-4E 단계에서 **추가** (본 모듈):
  - backend 의 ``store`` / ``delete`` / ``exists`` 메서드
  - ``store_secret(secret_id, value, *, backend=...)``    — backend 위임
  - ``delete_secret(secret_id, *, backend=...)``          — backend 위임
  - ``secret_exists(secret_id, *, backend=...)``          — backend 위임

본 단계에서도 **구현하지 않는** 것:
  - 실제 홈택스 자동 로그인 클릭/입력 (F-4F 이후)
  - DPAPI / pywin32 직접 연동
  - 운영자 secret_id 목록의 enumeration (keyring 미지원).
"""
from __future__ import annotations

from typing import (
    Any,
    Iterable,
    Mapping,
    Optional,
    Protocol,
    TypedDict,
    runtime_checkable,
)


# ─── 정책 상수 ────────────────────────────────────────────────────────────

# raw 비밀값이 들어오면 거절해야 하는 파라미터 키 (lower-case 비교).
# 값이 빈 문자열/None 이면 무해로 보고, 값이 있으면 차단한다.
_RAW_SECRET_PARAM_KEYS: tuple[str, ...] = (
    "password",
    "passwd",
    "cert_password",
    "certificate_password",
    "otp",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "session",
    "storage_state",
    "localstorage",
    "sessionstorage",
)

# secret_id 자체에 들어오면 안 되는 문자 — 보안 저장소에 매핑되는 식별자
# 만 허용한다. 공백/제어/슬래시/콜론 등은 거절.
_SECRET_ID_ALLOWED_CHARS_HINT = (
    "letters/digits/underscore/hyphen/dot only"
)

# secret_id 길이 제한.
_SECRET_ID_MIN_LEN = 3
_SECRET_ID_MAX_LEN = 128

# 로그 마스킹 시 노출할 secret_id 의 prefix 글자수.
_SECRET_ID_PREFIX_LEN = 4


# ─── 타입 ────────────────────────────────────────────────────────────────

class SecretRef(TypedDict, total=False):
    """secret_id 기반 reference. raw 값은 절대 보유하지 않는다.

    필드:
      site_key:           "hometax" 등 사이트 키 (lowercase, ASCII)
      login_method:       "certificate" / "id_password" 등
      user_id_secret_id:  사용자 ID 가 보안 저장소에 저장된 식별자
      password_secret_id: 비밀번호 식별자 (평문 값 아님)
    """
    site_key: str
    login_method: str
    user_id_secret_id: str
    password_secret_id: str


# ─── 검증 ────────────────────────────────────────────────────────────────

def is_valid_secret_id(value: Any) -> bool:
    """secret_id 식별자 형식 검증.

    - str 이어야 한다.
    - 길이 [3, 128].
    - 영문/숫자/_ - . 만 허용. 공백/슬래시/콜론/한글 등 불허.
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) != len(value):  # 양옆 공백 자체를 허용하지 않음
        return False
    if not (_SECRET_ID_MIN_LEN <= len(s) <= _SECRET_ID_MAX_LEN):
        return False
    for ch in s:
        # ASCII 영숫자 + _-. 만 허용. 한글 등 비-ASCII 는 거절.
        if ch in ("_", "-", "."):
            continue
        if not (("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9")):
            return False
    return True


def validate_secret_ref(ref: Any) -> dict[str, Any]:
    """SecretRef dict 형식 검증.

    반환:
      {"ok": bool, "error_code": str, "warnings": [str, ...]}

    원칙:
      - dict / Mapping 만 허용.
      - 알려진 raw 비밀 키 (``password`` 등) 가 들어와 있으면 즉시 거절.
      - ``site_key`` 는 lowercase ASCII slug.
      - id 는 ``user_id_secret_id`` / ``password_secret_id`` 둘 다
        ``is_valid_secret_id`` 통과해야 한다.
      - 본 단계에서는 ``login_method`` 는 free-form (검증만, 거절 안 함).
    """
    if not isinstance(ref, Mapping):
        return _err("REF_NOT_MAPPING")

    raw_check = reject_raw_secret_params(ref)
    if not raw_check["ok"]:
        return raw_check

    site_key = ref.get("site_key")
    if not isinstance(site_key, str) or not site_key.strip():
        return _err("MISSING_SITE_KEY")
    if site_key != site_key.strip().lower():
        return _err("SITE_KEY_NOT_LOWERCASE")
    if not all(c.isalnum() or c in ("_", "-") for c in site_key):
        return _err("SITE_KEY_INVALID_CHARS")

    user_id = ref.get("user_id_secret_id")
    if not is_valid_secret_id(user_id):
        return _err("INVALID_USER_ID_SECRET_ID")

    password_id = ref.get("password_secret_id")
    if not is_valid_secret_id(password_id):
        return _err("INVALID_PASSWORD_SECRET_ID")

    if user_id == password_id:
        return _err("USER_AND_PASSWORD_SECRET_ID_COLLIDE")

    return {"ok": True, "error_code": "", "warnings": []}


def reject_raw_secret_params(params: Any) -> dict[str, Any]:
    """파라미터 dict 에 raw 비밀값이 들어왔는지 검사.

    - dict 가 아닌 입력은 ok=True 로 통과 (호출자가 별도 검증).
    - dict key 의 lowercase 가 ``_RAW_SECRET_PARAM_KEYS`` 에 포함되고,
      해당 value 가 비어있지 않으면 거절.
    - raw 비밀값을 거절할 때 **value 자체는 결과에 노출하지 않는다**.

    반환:
      {"ok": bool, "error_code": str, "warnings": [str, ...]}
    """
    if not isinstance(params, Mapping):
        return {"ok": True, "error_code": "", "warnings": []}

    bad_keys: list[str] = []
    for key, value in params.items():
        if not isinstance(key, str):
            continue
        if key.lower() not in _RAW_SECRET_PARAM_KEYS:
            continue
        if value is None:
            continue
        # 빈 문자열/빈 컨테이너는 무해.
        if isinstance(value, (str, bytes)) and len(value) == 0:
            continue
        if isinstance(value, (list, tuple, dict)) and len(value) == 0:
            continue
        bad_keys.append(key.lower())

    if bad_keys:
        # 키 이름은 노출 가능 (값은 절대 노출 금지).
        unique = sorted(set(bad_keys))
        return {
            "ok": False,
            "error_code": "RAW_SECRET_PARAM_REJECTED",
            "warnings": [f"raw_secret_param:{k}" for k in unique],
        }
    return {"ok": True, "error_code": "", "warnings": []}


# ─── 마스킹 ──────────────────────────────────────────────────────────────

def redact_for_log(payload: Any) -> Any:
    """로그/audit/ActionResult 용 sanitizer.

    - dict 는 동일 키를 유지하되, 위 raw 비밀 키워드의 값은 ``"***"`` 로
      치환. ``*_secret_id`` 같은 reference 식별자는 prefix 만 노출.
    - list/tuple 은 재귀.
    - 그 외 타입은 그대로.
    """
    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(key, str) and key.lower() in _RAW_SECRET_PARAM_KEYS:
                out[key] = "***"
                continue
            if (
                isinstance(key, str)
                and key.lower().endswith("_secret_id")
                and isinstance(value, str)
            ):
                out[key] = _mask_secret_id(value)
                continue
            out[key] = redact_for_log(value)
        return out
    if isinstance(payload, list):
        return [redact_for_log(v) for v in payload]
    if isinstance(payload, tuple):
        return tuple(redact_for_log(v) for v in payload)
    return payload


def _mask_secret_id(value: str) -> str:
    if not isinstance(value, str) or not value:
        return ""
    head = value[:_SECRET_ID_PREFIX_LEN]
    return f"{head}***"


# ─── 예외 ────────────────────────────────────────────────────────────────
#
# 모든 예외는 메시지에 **평문 비밀값을 포함하지 않는다.** secret_id 와
# 백엔드 식별자는 노출 가능하지만, 그 외 ``__cause__`` 등도 비밀값을
# 흘리지 않게 ``raise ... from None`` 패턴을 사용한다.

class SecretResolutionError(Exception):
    """secret resolve 과정에서 발생한 일반 오류 (base).

    메시지에 비밀값을 절대 포함하지 않는다. 호출자는 except 시
    ``str(exc)`` / ``repr(exc)`` 어디에도 평문이 없음을 가정해도 된다.
    """


class SecretNotFoundError(SecretResolutionError):
    """주어진 secret_id 가 backend 에 없음."""


class SecretBackendUnavailableError(SecretResolutionError):
    """backend 가 사용 불가 (예: keyring 패키지 미설치).

    ``import`` 단계에서 실패하지 않고 본 예외로 전환한다 — 그래야
    keyring 미설치 환경에서도 본 모듈 import 자체는 깨지지 않는다.
    """


# ─── Backend Protocol ───────────────────────────────────────────────────

@runtime_checkable
class SecretBackend(Protocol):
    """secret_id → 평문 비밀값 resolver 인터페이스.

    구현체 계약:
      - ``resolve(secret_id)`` 는 평문 str 반환 또는 예외.
      - ``store(secret_id, value)`` 는 None 반환 또는 예외.
      - ``delete(secret_id)`` 는 None 반환 또는 예외.
      - ``exists(secret_id)`` 는 bool 반환.
      - ``__repr__`` 결과에 평문 비밀값을 절대 포함하지 않는다.
      - ``__str__`` 도 동일.
      - 미존재 시 ``SecretNotFoundError``.
      - backend 자체 사용 불가 시 ``SecretBackendUnavailableError``.
      - 모든 예외 메시지에 평문 비밀값을 포함하지 않는다.
    """

    name: str

    def resolve(self, secret_id: str) -> str:  # pragma: no cover - protocol
        ...

    def store(  # pragma: no cover - protocol
        self, secret_id: str, value: str
    ) -> None:
        ...

    def delete(self, secret_id: str) -> None:  # pragma: no cover - protocol
        ...

    def exists(self, secret_id: str) -> bool:  # pragma: no cover - protocol
        ...


# ─── Mock backend (테스트 전용) ─────────────────────────────────────────

class MockSecretBackend:
    """테스트 전용 in-memory backend.

    실제 OS 키 저장소를 절대 건드리지 않는다. 운영 코드에서 사용 금지.
    """

    name = "mock"

    def __init__(self, secrets: Optional[Mapping[str, str]] = None) -> None:
        self._store: dict[str, str] = {}
        if secrets:
            for sid, value in secrets.items():
                self.register_secret(sid, value)

    def register_secret(self, secret_id: str, value: str) -> None:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        if not isinstance(value, str):
            raise TypeError("secret value must be str")
        # 빈 문자열은 정책상 허용하지 않음 — 비밀값 없음과 구분 위함.
        if value == "":
            raise ValueError("secret value must not be empty")
        self._store[secret_id] = value

    def resolve(self, secret_id: str) -> str:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        try:
            return self._store[secret_id]
        except KeyError:
            raise SecretNotFoundError(
                f"secret_id not found in mock backend: {secret_id!r}"
            ) from None

    def store(self, secret_id: str, value: str) -> None:
        # register_secret 가 secret_id 형식/value 형식을 모두 검증한다.
        # 기존 값이 있어도 덮어쓴다 (rotation 시나리오).
        self.register_secret(secret_id, value)

    def delete(self, secret_id: str) -> None:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        try:
            del self._store[secret_id]
        except KeyError:
            raise SecretNotFoundError(
                f"secret_id not found in mock backend: {secret_id!r}"
            ) from None

    def exists(self, secret_id: str) -> bool:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        return secret_id in self._store

    def list_secret_ids(self) -> list[str]:
        """테스트 전용 — 등록된 secret_id 목록.

        WindowsKeyring backend 는 enumeration 을 지원하지 않으므로
        본 메서드는 Mock 에서만 의미가 있다.
        """
        return sorted(self._store.keys())

    def __repr__(self) -> str:
        # entry 개수만 노출. 키/값 둘 다 가린다.
        return f"MockSecretBackend(<{len(self._store)} entries>)"

    __str__ = __repr__


# ─── Windows / keyring backend (선택적) ─────────────────────────────────

class WindowsKeyringSecretBackend:
    """Windows Credential Manager (또는 OS keyring) 기반 backend.

    ``keyring`` 패키지에 위임한다.
      - service_name 은 기본 ``haehan_local_agent`` 로 고정.
      - username 자리에 secret_id, password 자리에 비밀값.
      - 본 단계에서는 **저장 (store)** 메서드를 노출하지 않는다 —
        등록 CLI 는 후속 F-4E. 본 클래스는 read-only.

    ``keyring`` 미설치 환경에서는 인스턴스화 시점에
    ``SecretBackendUnavailableError`` 로 전환된다 (import error 가
    아닌). 그래야 본 모듈을 import 만 하는 환경 (서버 / CI) 이 깨지지
    않는다.
    """

    name = "windows_keyring"
    DEFAULT_SERVICE_NAME = "haehan_local_agent"

    def __init__(self, service_name: Optional[str] = None) -> None:
        self._service = service_name or self.DEFAULT_SERVICE_NAME
        try:
            import keyring  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SecretBackendUnavailableError(
                "keyring package is not installed; "
                "install it on the operator PC to enable Windows backend",
            ) from None
        self._keyring = keyring

    def resolve(self, secret_id: str) -> str:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        try:
            value = self._keyring.get_password(self._service, secret_id)
        except Exception as exc:
            # keyring 내부 예외 메시지를 그대로 노출하지 않는다.
            raise SecretResolutionError(
                f"keyring backend error: {type(exc).__name__} "
                f"(service={self._service!r}, secret_id={secret_id!r})"
            ) from None
        if value is None:
            raise SecretNotFoundError(
                "secret_id not found in Windows Credential Manager: "
                f"service={self._service!r}, secret_id={secret_id!r}"
            )
        if not isinstance(value, str):  # pragma: no cover - defensive
            raise SecretResolutionError(
                f"keyring returned non-string value type: {type(value).__name__}"
            )
        return value

    def store(self, secret_id: str, value: str) -> None:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        if not isinstance(value, str):
            raise TypeError("secret value must be str")
        if value == "":
            raise ValueError("secret value must not be empty")
        try:
            self._keyring.set_password(self._service, secret_id, value)
        except Exception as exc:
            # 비밀값 자체는 메시지에 절대 노출하지 않는다.
            raise SecretResolutionError(
                f"keyring backend store error: {type(exc).__name__} "
                f"(service={self._service!r}, secret_id={secret_id!r})"
            ) from None

    def delete(self, secret_id: str) -> None:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        # 우선 존재 여부를 확인 — 없으면 SecretNotFoundError 로 통일.
        try:
            existing = self._keyring.get_password(self._service, secret_id)
        except Exception as exc:
            raise SecretResolutionError(
                f"keyring backend lookup error: {type(exc).__name__} "
                f"(service={self._service!r}, secret_id={secret_id!r})"
            ) from None
        if existing is None:
            raise SecretNotFoundError(
                "secret_id not found in Windows Credential Manager: "
                f"service={self._service!r}, secret_id={secret_id!r}"
            )
        try:
            self._keyring.delete_password(self._service, secret_id)
        except Exception as exc:
            raise SecretResolutionError(
                f"keyring backend delete error: {type(exc).__name__} "
                f"(service={self._service!r}, secret_id={secret_id!r})"
            ) from None

    def exists(self, secret_id: str) -> bool:
        if not is_valid_secret_id(secret_id):
            raise ValueError("invalid secret_id format")
        try:
            value = self._keyring.get_password(self._service, secret_id)
        except Exception as exc:
            raise SecretResolutionError(
                f"keyring backend lookup error: {type(exc).__name__} "
                f"(service={self._service!r}, secret_id={secret_id!r})"
            ) from None
        return value is not None

    def list_secret_ids(self) -> list[str]:
        # keyring 은 backend 별로 enumeration 지원이 일관되지 않다.
        # CLI 는 본 메서드의 NotImplementedError 를 보고 "not supported"
        # 메시지를 출력해야 한다.
        raise NotImplementedError(
            "Windows Credential Manager backend does not support listing"
        )

    def __repr__(self) -> str:
        return f"WindowsKeyringSecretBackend(service={self._service!r})"

    __str__ = __repr__


# ─── factory ────────────────────────────────────────────────────────────

_KNOWN_BACKEND_ALIASES: dict[str, str] = {
    "": "windows_keyring",
    "auto": "windows_keyring",
    "windows": "windows_keyring",
    "windows_keyring": "windows_keyring",
    "keyring": "windows_keyring",
    "mock": "mock",
}


def get_secret_backend(name: Optional[str] = None) -> SecretBackend:
    """Backend factory.

    ``name``:
      - ``None`` / ``"auto"`` / ``"windows_keyring"`` / ``"keyring"`` /
        ``"windows"`` → ``WindowsKeyringSecretBackend`` (keyring 미설치 시
        ``SecretBackendUnavailableError``).
      - ``"mock"`` → 빈 ``MockSecretBackend``. **테스트 전용.**
      - 그 외 → ``ValueError``.
    """
    requested = (name or "").strip().lower()
    resolved = _KNOWN_BACKEND_ALIASES.get(requested)
    if resolved is None:
        raise ValueError(f"unknown secret backend: {name!r}")
    if resolved == "mock":
        return MockSecretBackend()
    if resolved == "windows_keyring":
        return WindowsKeyringSecretBackend()
    # pragma: no cover - guarded by alias table above
    raise ValueError(f"unknown secret backend: {name!r}")


# ─── resolve_secret ─────────────────────────────────────────────────────

def resolve_secret(
    secret_id: str,
    *,
    backend: Optional[SecretBackend] = None,
) -> str:
    """secret_id → 평문 비밀값.

    - ``backend`` 가 명시되지 않으면 (``None``) 자동 resolve 를 일부러
      막아서 ``NotImplementedError`` 를 던진다. 호출 측은 항상
      ``backend=...`` 로 책임 있게 backend 를 주입해야 한다.
      이는 서버/오케스트레이터 같은 곳에서 실수로 본 함수가 호출돼도
      OS 키 저장소를 자동으로 열지 않게 하는 안전장치이다.
    - ``secret_id`` 형식이 틀리면 ``ValueError``.
    - ``backend.resolve`` 의 모든 예외는 그대로 전파.

    호출 측 보안 의무:
      - 반환값은 함수 종료 시 폐기한다.
      - 반환값을 절대 ActionResult / audit log / exception 메시지에
        넣지 않는다.
    """
    if not is_valid_secret_id(secret_id):
        raise ValueError("invalid secret_id format")
    if backend is None:
        raise NotImplementedError(
            "trusted_secrets.resolve_secret requires an explicit backend; "
            "pass backend=get_secret_backend() on the operator PC, or "
            "MockSecretBackend(...) in tests",
        )
    return backend.resolve(secret_id)


# ─── store_secret / delete_secret / secret_exists ───────────────────────

def store_secret(
    secret_id: str,
    value: str,
    *,
    backend: Optional[SecretBackend] = None,
) -> None:
    """secret_id 에 평문 비밀값을 보안 저장소에 저장한다.

    원칙:
      - ``backend`` 미지정 시 ``NotImplementedError`` (자동 저장 금지).
      - ``secret_id`` 형식 위반 시 ``ValueError``.
      - ``value`` 가 str 가 아니면 ``TypeError``.
      - ``value`` 가 빈 문자열이면 ``ValueError``.
      - 저장 실패 시 발생하는 ``SecretResolutionError`` 메시지에는
        평문 비밀값이 절대 들어가지 않는다.

    호출 측 보안 의무:
      - 이 함수에 넘기는 ``value`` 변수는 호출 종료 직후 폐기한다.
      - 호출 결과/예외를 그대로 ActionResult / audit log 에 넣지 않는다.
    """
    if not is_valid_secret_id(secret_id):
        raise ValueError("invalid secret_id format")
    if not isinstance(value, str):
        raise TypeError("secret value must be str")
    if value == "":
        raise ValueError("secret value must not be empty")
    if backend is None:
        raise NotImplementedError(
            "trusted_secrets.store_secret requires an explicit backend; "
            "pass backend=get_secret_backend() on the operator PC, or "
            "MockSecretBackend(...) in tests",
        )
    backend.store(secret_id, value)


def delete_secret(
    secret_id: str,
    *,
    backend: Optional[SecretBackend] = None,
) -> None:
    """secret_id 를 보안 저장소에서 삭제한다.

    - ``backend`` 미지정 시 ``NotImplementedError``.
    - ``secret_id`` 형식 위반 시 ``ValueError``.
    - 미존재 시 backend 가 ``SecretNotFoundError`` 를 그대로 전파.
    """
    if not is_valid_secret_id(secret_id):
        raise ValueError("invalid secret_id format")
    if backend is None:
        raise NotImplementedError(
            "trusted_secrets.delete_secret requires an explicit backend; "
            "pass backend=get_secret_backend() on the operator PC, or "
            "MockSecretBackend(...) in tests",
        )
    backend.delete(secret_id)


def secret_exists(
    secret_id: str,
    *,
    backend: Optional[SecretBackend] = None,
) -> bool:
    """secret_id 가 보안 저장소에 존재하는지 여부 (값은 반환하지 않는다).

    - ``backend`` 미지정 시 ``NotImplementedError``.
    - ``secret_id`` 형식 위반 시 ``ValueError``.
    """
    if not is_valid_secret_id(secret_id):
        raise ValueError("invalid secret_id format")
    if backend is None:
        raise NotImplementedError(
            "trusted_secrets.secret_exists requires an explicit backend; "
            "pass backend=get_secret_backend() on the operator PC, or "
            "MockSecretBackend(...) in tests",
        )
    return backend.exists(secret_id)


# ─── helpers ─────────────────────────────────────────────────────────────

def _err(code: str, *warnings: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "warnings": [code.lower(), *warnings],
    }


def raw_secret_param_keys() -> tuple[str, ...]:
    """테스트/문서용 — 차단 대상 키 목록을 노출."""
    return _RAW_SECRET_PARAM_KEYS


__all__ = [
    "SecretRef",
    "SecretBackend",
    "MockSecretBackend",
    "WindowsKeyringSecretBackend",
    "SecretResolutionError",
    "SecretNotFoundError",
    "SecretBackendUnavailableError",
    "is_valid_secret_id",
    "validate_secret_ref",
    "reject_raw_secret_params",
    "redact_for_log",
    "resolve_secret",
    "store_secret",
    "delete_secret",
    "secret_exists",
    "get_secret_backend",
    "raw_secret_param_keys",
]
