"""F-4D — local_agent.trusted_secrets backend 단위 테스트.

검증:
  A) MockSecretBackend resolve 성공 / 실패
  B) MockSecretBackend repr/str 에 평문 비밀값 미노출
  C) Mock backend 의 모든 예외 메시지에 평문 비밀값 미노출
  D) resolve_secret(backend=...) 위임 + backend 미지정 시 NotImplementedError
  E) get_secret_backend factory 동작 + 알 수 없는 이름 거절
  F) WindowsKeyringSecretBackend 인스턴스화는 keyring 미설치 시
     SecretBackendUnavailableError (test 환경에서 import error 가
     안 되어야 함)
  G) raw 비밀 키워드 차단 (F-4C 회귀)
  H) redact_for_log 가 backend 객체 노출에도 안전 (F-4D 추가 회귀)
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import trusted_secrets as ts  # noqa: E402


# ─── A) MockSecretBackend resolve ────────────────────────────────────────

def test_mock_backend_resolve_returns_registered_value():
    backend = ts.MockSecretBackend({
        "hometax_user_id": "u-12345",
        "hometax_cert_password": "p-do-not-leak",
    })
    assert backend.resolve("hometax_user_id") == "u-12345"
    assert backend.resolve("hometax_cert_password") == "p-do-not-leak"


def test_mock_backend_register_after_init():
    backend = ts.MockSecretBackend()
    backend.register_secret("hometax_user_id", "u-12345")
    assert backend.resolve("hometax_user_id") == "u-12345"


def test_mock_backend_missing_secret_id_raises_not_found():
    backend = ts.MockSecretBackend({"hometax_user_id": "u-12345"})
    with pytest.raises(ts.SecretNotFoundError):
        backend.resolve("missing_secret_id_xyz")


def test_mock_backend_invalid_secret_id_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.resolve("bad id with space")


def test_mock_backend_register_invalid_secret_id_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.register_secret("bad id with space", "value")


def test_mock_backend_register_rejects_non_string_value():
    backend = ts.MockSecretBackend()
    with pytest.raises(TypeError):
        backend.register_secret("hometax_user_id", 12345)  # type: ignore[arg-type]


def test_mock_backend_register_rejects_empty_value():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.register_secret("hometax_user_id", "")


def test_mock_backend_init_with_invalid_secret_id_raises():
    with pytest.raises(ValueError):
        ts.MockSecretBackend({"bad id": "value"})


# ─── B) MockSecretBackend repr/str — 평문 미노출 ────────────────────────

def test_mock_backend_repr_does_not_leak_secret_value():
    leak_canary = "p-canary-do-not-leak-7777"
    backend = ts.MockSecretBackend({"hometax_cert_password": leak_canary})
    assert leak_canary not in repr(backend)
    assert leak_canary not in str(backend)


def test_mock_backend_repr_does_not_leak_secret_id():
    # secret_id 자체는 비밀값은 아니지만, repr 정책상 (count 만 노출)
    # 키 이름도 가린다.
    backend = ts.MockSecretBackend({"hometax_cert_password": "v"})
    assert "hometax_cert_password" not in repr(backend)


# ─── C) 예외 메시지 — 평문 미노출 ────────────────────────────────────────

def test_mock_backend_not_found_exception_does_not_leak_value():
    leak_canary = "p-canary-do-not-leak-9999"
    backend = ts.MockSecretBackend({"hometax_cert_password": leak_canary})
    with pytest.raises(ts.SecretNotFoundError) as exc_info:
        backend.resolve("missing_id")
    assert leak_canary not in str(exc_info.value)
    assert leak_canary not in repr(exc_info.value)


def test_mock_backend_invalid_id_exception_does_not_leak_value():
    leak_canary = "p-canary-do-not-leak-aaaa"
    backend = ts.MockSecretBackend({"hometax_cert_password": leak_canary})
    with pytest.raises(ValueError) as exc_info:
        backend.resolve("bad id")
    assert leak_canary not in str(exc_info.value)
    assert leak_canary not in repr(exc_info.value)


# ─── D) resolve_secret 위임 ──────────────────────────────────────────────

def test_resolve_secret_delegates_to_backend():
    backend = ts.MockSecretBackend({"hometax_user_id": "u-12345"})
    assert ts.resolve_secret("hometax_user_id", backend=backend) == "u-12345"


def test_resolve_secret_without_backend_raises_not_implemented():
    # F-4C 회귀 — 명시적 backend 가 없으면 NotImplementedError.
    with pytest.raises(NotImplementedError):
        ts.resolve_secret("hometax_cert_password")


def test_resolve_secret_invalid_id_raises_value_error_before_backend():
    # backend 가 호출되지 않음을 검증.
    class FailingBackend:
        name = "failing"

        def resolve(self, secret_id):  # pragma: no cover - should not reach
            raise AssertionError("backend must not be called for invalid id")

    with pytest.raises(ValueError):
        ts.resolve_secret("bad id", backend=FailingBackend())  # type: ignore[arg-type]


def test_resolve_secret_propagates_not_found():
    backend = ts.MockSecretBackend({"hometax_user_id": "u-12345"})
    with pytest.raises(ts.SecretNotFoundError):
        ts.resolve_secret("missing_id", backend=backend)


# ─── E) get_secret_backend factory ───────────────────────────────────────

def test_get_secret_backend_mock():
    b = ts.get_secret_backend("mock")
    assert isinstance(b, ts.MockSecretBackend)
    # 빈 backend.
    with pytest.raises(ts.SecretNotFoundError):
        b.resolve("hometax_user_id")


def test_get_secret_backend_unknown_name_raises_value_error():
    with pytest.raises(ValueError):
        ts.get_secret_backend("nonexistent_backend_xyz")


# ─── F) WindowsKeyringSecretBackend — 선택적 ────────────────────────────

def _keyring_available() -> bool:
    try:
        importlib.import_module("keyring")
        return True
    except ImportError:
        return False


def test_module_imports_without_keyring():
    """본 모듈 import 자체는 keyring 의존성이 없다.

    이 테스트가 실행되고 있다는 사실 자체가 import 가 깨지지 않았다는
    증거이지만, 명시적으로 attribute 접근까지 확인.
    """
    assert hasattr(ts, "WindowsKeyringSecretBackend")
    assert hasattr(ts, "SecretBackendUnavailableError")


@pytest.mark.skipif(_keyring_available(), reason="keyring is installed")
def test_windows_backend_raises_unavailable_when_keyring_missing():
    with pytest.raises(ts.SecretBackendUnavailableError):
        ts.WindowsKeyringSecretBackend()


@pytest.mark.skipif(_keyring_available(), reason="keyring is installed")
def test_get_secret_backend_default_unavailable_when_keyring_missing():
    with pytest.raises(ts.SecretBackendUnavailableError):
        ts.get_secret_backend()


@pytest.mark.skipif(
    not _keyring_available(), reason="keyring not installed (optional)"
)
def test_windows_backend_constructs_when_keyring_available():
    b = ts.WindowsKeyringSecretBackend()
    assert b.name == "windows_keyring"
    # repr 에 service 이름은 노출되지만 비밀값은 없다.
    r = repr(b)
    assert "WindowsKeyringSecretBackend" in r


@pytest.mark.skipif(
    not os.environ.get("HAEHAN_F4D_REAL_KEYRING_TEST"),
    reason="real OS keyring access disabled by default; set HAEHAN_F4D_REAL_KEYRING_TEST=1 to opt-in",
)
def test_windows_backend_real_resolve_opt_in():  # pragma: no cover - opt-in
    """opt-in 만 — 실제 OS 키 저장소를 건드린다.

    기본 실행에서는 skip. 운영자 PC 에서 명시적으로 opt-in 환경변수를
    켜고 secret 을 사전에 등록한 상태에서만 의미가 있다.
    """
    b = ts.WindowsKeyringSecretBackend()
    secret_id = os.environ.get("HAEHAN_F4D_REAL_KEYRING_SECRET_ID", "")
    assert secret_id, "HAEHAN_F4D_REAL_KEYRING_SECRET_ID required when opt-in"
    value = b.resolve(secret_id)
    assert isinstance(value, str)
    # 본 테스트에서도 평문은 절대 출력하지 않는다.


# ─── G) raw 비밀 키워드 차단 회귀 (F-4C) ────────────────────────────────

@pytest.mark.parametrize("key", [
    "password", "cookie", "session", "storage_state", "access_token",
])
def test_raw_secret_param_blocked_after_f4d(key):
    """F-4D 변경 후에도 F-4C 의 raw param 차단이 그대로 유지된다."""
    out = ts.reject_raw_secret_params({key: "secret-value-do-not-leak"})
    assert out["ok"] is False
    assert out["error_code"] == "RAW_SECRET_PARAM_REJECTED"
    assert "secret-value-do-not-leak" not in repr(out)


# ─── H) redact_for_log 회귀 ─────────────────────────────────────────────

def test_redact_for_log_does_not_leak_through_backend_repr():
    """backend 객체가 어떤 dict 필드 안에 들어가더라도, dict 의
    sanitizer 가 그것을 traverse 할 때 평문이 새지 않는다.

    backend 자체는 dict 가 아니므로 redact_for_log 는 그대로 두지만,
    backend 의 __repr__ 가 평문을 흘리지 않으므로 안전하다.
    """
    leak_canary = "p-canary-do-not-leak-bbbb"
    backend = ts.MockSecretBackend({"hometax_cert_password": leak_canary})
    payload = {"site_key": "hometax", "_backend_obj": backend}
    out = ts.redact_for_log(payload)
    assert leak_canary not in repr(out)
