"""F-4E — scripts/local_secret_store.py CLI 단위 테스트.

검증:
  A) MockSecretBackend store / resolve / delete / exists / list_secret_ids
  B) trusted_secrets 의 store_secret / delete_secret / secret_exists 위임
  C) CLI add — getpass 입력값을 stdout/stderr 에 출력하지 않음
  D) CLI check — 존재 여부만 표시, 비밀값/value 출력 금지
  E) CLI delete — secret_id 만 표시, 비밀값 출력 금지
  F) CLI list — mock backend 는 secret_id 목록, keyring backend 는
                "not supported"
  G) invalid secret_id / raw-secret keyword 거절
  H) 비밀값 누출 회귀: 어떤 명령에서도 stdout/stderr/exception 에 평문
                       비밀값이 들어가지 않음
  I) trusted_secrets 가 keyring 미설치 환경에서도 import 됨
  J) page.fill / page.type / click / submit 같은 자동화 코드가 본
     모듈에 없음 (의도치 않은 추가 방지)

본 테스트는 실제 OS 키 저장소 (Windows Credential Manager) 를 절대
건드리지 않는다. WindowsKeyringSecretBackend 자체에 대한 테스트는
F-4D 에 있다 (test_trusted_secret_backend.py).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

import pytest


# ─── 모듈 로딩 (scripts/ 는 패키지가 아니므로 importlib 로 직접) ────────

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from local_agent import trusted_secrets as ts  # noqa: E402


def _load_cli_module():
    """``scripts/local_secret_store.py`` 를 모듈로 로드한다.

    scripts/ 디렉토리는 패키지가 아니라 일반 폴더이므로 importlib 의
    file-spec 방식으로 직접 로드한다.
    """
    cli_path = os.path.join(_REPO_ROOT, "scripts", "local_secret_store.py")
    spec = importlib.util.spec_from_file_location(
        "haehan_test_local_secret_store_cli", cli_path
    )
    assert spec and spec.loader, "spec failed for scripts/local_secret_store.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cli():
    return _load_cli_module()


# ─── 헬퍼 ────────────────────────────────────────────────────────────────

def _make_prompt(values):
    """미리 정해둔 응답 시퀀스를 흘려주는 가짜 getpass.getpass.

    호출 횟수가 values 길이를 넘으면 AssertionError 로 떨어뜨려서
    테스트가 무한 루프가 되지 않게 한다.
    """
    queue = list(values)

    def _prompt(_message: str) -> str:
        assert queue, "prompt called more times than expected"
        return queue.pop(0)

    return _prompt


# ─── A/B) backend store/delete/exists/list + 위임 ───────────────────────

def test_mock_backend_store_resolve_delete_exists_list_roundtrip():
    backend = ts.MockSecretBackend()
    assert backend.exists("hometax_user_id") is False

    backend.store("hometax_user_id", "u-12345")
    backend.store("hometax_cert_password", "p-do-not-leak")

    assert backend.exists("hometax_user_id") is True
    assert backend.resolve("hometax_user_id") == "u-12345"
    assert sorted(backend.list_secret_ids()) == [
        "hometax_cert_password",
        "hometax_user_id",
    ]

    backend.delete("hometax_user_id")
    assert backend.exists("hometax_user_id") is False
    with pytest.raises(ts.SecretNotFoundError):
        backend.resolve("hometax_user_id")


def test_mock_backend_store_overwrites_existing_value():
    backend = ts.MockSecretBackend({"hometax_user_id": "old"})
    backend.store("hometax_user_id", "new")
    assert backend.resolve("hometax_user_id") == "new"


def test_mock_backend_delete_missing_raises_not_found():
    backend = ts.MockSecretBackend()
    with pytest.raises(ts.SecretNotFoundError):
        backend.delete("missing_id")


def test_mock_backend_exists_invalid_id_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.exists("bad id with space")


def test_mock_backend_store_invalid_id_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.store("bad id", "value")


def test_mock_backend_store_empty_value_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        backend.store("hometax_user_id", "")


def test_store_secret_top_level_delegates_to_backend():
    backend = ts.MockSecretBackend()
    ts.store_secret("hometax_user_id", "u-12345", backend=backend)
    assert backend.resolve("hometax_user_id") == "u-12345"


def test_store_secret_without_backend_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        ts.store_secret("hometax_user_id", "v")


def test_store_secret_invalid_id_raises_value_error_before_backend():
    class FailingBackend:
        name = "failing"

        def resolve(self, secret_id):  # pragma: no cover
            raise AssertionError("resolve must not be called")

        def store(self, secret_id, value):  # pragma: no cover
            raise AssertionError("store must not be called for invalid id")

        def delete(self, secret_id):  # pragma: no cover
            raise AssertionError("delete must not be called")

        def exists(self, secret_id):  # pragma: no cover
            raise AssertionError("exists must not be called")

    with pytest.raises(ValueError):
        ts.store_secret("bad id", "v", backend=FailingBackend())  # type: ignore[arg-type]


def test_store_secret_empty_value_raises_value_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(ValueError):
        ts.store_secret("hometax_user_id", "", backend=backend)


def test_store_secret_non_string_value_raises_type_error():
    backend = ts.MockSecretBackend()
    with pytest.raises(TypeError):
        ts.store_secret(
            "hometax_user_id", 12345, backend=backend  # type: ignore[arg-type]
        )


def test_delete_secret_top_level_delegates_to_backend():
    backend = ts.MockSecretBackend({"hometax_user_id": "v"})
    ts.delete_secret("hometax_user_id", backend=backend)
    assert backend.exists("hometax_user_id") is False


def test_delete_secret_without_backend_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        ts.delete_secret("hometax_user_id")


def test_secret_exists_top_level_delegates_to_backend():
    backend = ts.MockSecretBackend({"hometax_user_id": "v"})
    assert ts.secret_exists("hometax_user_id", backend=backend) is True
    assert ts.secret_exists("missing_id", backend=backend) is False


def test_secret_exists_without_backend_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        ts.secret_exists("hometax_user_id")


# ─── C) CLI add — 입력값 stdout/stderr 미노출 ───────────────────────────

LEAK_CANARY_PASSWORD = "p-do-not-leak-pw-canary-7777"


def test_cli_add_stores_value_via_injected_prompt(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "add", "hometax_cert_password"],
        backend=backend,
        prompt_secret=_make_prompt([LEAK_CANARY_PASSWORD, LEAK_CANARY_PASSWORD]),
    )
    assert rc == cli.EXIT_OK
    assert backend.exists("hometax_cert_password") is True
    assert backend.resolve("hometax_cert_password") == LEAK_CANARY_PASSWORD

    captured = capsys.readouterr()
    # stdout 에는 secret_id 만 노출. 비밀값 평문은 절대 들어가면 안 된다.
    assert "hometax_cert_password" in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.err


def test_cli_add_aborts_on_mismatched_confirmation(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "add", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt(
            [LEAK_CANARY_PASSWORD, "different-value-typo"]
        ),
    )
    assert rc == cli.EXIT_USAGE_ERROR
    assert backend.exists("hometax_user_id") is False

    captured = capsys.readouterr()
    assert LEAK_CANARY_PASSWORD not in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.err
    # 입력 두 번째도 stdout/stderr 에 노출되면 안 된다.
    assert "different-value-typo" not in captured.out
    assert "different-value-typo" not in captured.err


def test_cli_add_aborts_on_empty_first_input(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "add", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt([""]),
    )
    assert rc == cli.EXIT_USAGE_ERROR
    assert backend.exists("hometax_user_id") is False


def test_cli_add_invalid_secret_id_format_rejected(cli, capsys):
    backend = ts.MockSecretBackend()

    def _must_not_call(_msg):  # pragma: no cover - safety
        raise AssertionError("prompt must not run for invalid secret_id")

    rc = cli.main(
        ["--backend", "mock", "add", "bad id with space"],
        backend=backend,
        prompt_secret=_must_not_call,
    )
    assert rc == cli.EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert "invalid secret_id format" in captured.err


def test_cli_add_rejects_raw_secret_keyword_as_secret_id(cli, capsys):
    backend = ts.MockSecretBackend()

    def _must_not_call(_msg):  # pragma: no cover
        raise AssertionError("prompt must not run for blocked secret_id")

    rc = cli.main(
        ["--backend", "mock", "add", "password"],
        backend=backend,
        prompt_secret=_must_not_call,
    )
    assert rc == cli.EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert "raw-secret keyword" in captured.err
    assert backend.exists("password") is False


@pytest.mark.parametrize(
    "blocked",
    [
        "password", "PASSWORD", "passwd",
        "cookie", "session", "storage_state",
        "access_token", "refresh_token", "token",
    ],
)
def test_cli_add_rejects_each_raw_keyword(cli, blocked):
    backend = ts.MockSecretBackend()

    def _must_not_call(_msg):  # pragma: no cover
        raise AssertionError("prompt must not run for blocked id")

    rc = cli.main(
        ["--backend", "mock", "add", blocked],
        backend=backend,
        prompt_secret=_must_not_call,
    )
    assert rc == cli.EXIT_USAGE_ERROR


# ─── D) CLI check — 존재 여부만 ──────────────────────────────────────────

def test_cli_check_present(cli, capsys):
    backend = ts.MockSecretBackend({"hometax_user_id": LEAK_CANARY_PASSWORD})
    rc = cli.main(
        ["--backend", "mock", "check", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_OK
    captured = capsys.readouterr()
    assert "present" in captured.out
    assert "hometax_user_id" in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.err


def test_cli_check_absent(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "check", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_NOT_FOUND
    captured = capsys.readouterr()
    assert "absent" in captured.out


def test_cli_check_invalid_id(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "check", "bad id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_USAGE_ERROR


# ─── E) CLI delete — secret_id 만 ────────────────────────────────────────

def test_cli_delete_existing(cli, capsys):
    backend = ts.MockSecretBackend({"hometax_user_id": LEAK_CANARY_PASSWORD})
    rc = cli.main(
        ["--backend", "mock", "delete", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_OK
    assert backend.exists("hometax_user_id") is False

    captured = capsys.readouterr()
    assert "deleted" in captured.out
    assert "hometax_user_id" in captured.out
    # 비밀값 평문은 어떤 출력 채널에도 들어가지 않는다.
    assert LEAK_CANARY_PASSWORD not in captured.out
    assert LEAK_CANARY_PASSWORD not in captured.err


def test_cli_delete_missing_returns_not_found(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "delete", "hometax_user_id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_NOT_FOUND
    captured = capsys.readouterr()
    assert "not found" in captured.err
    assert "hometax_user_id" in captured.err


def test_cli_delete_invalid_id(cli, capsys):
    backend = ts.MockSecretBackend()
    rc = cli.main(
        ["--backend", "mock", "delete", "bad id"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_USAGE_ERROR


# ─── F) CLI list ────────────────────────────────────────────────────────

def test_cli_list_mock_backend_returns_ids_sorted(cli, capsys):
    backend = ts.MockSecretBackend({
        "hometax_user_id": "u",
        "hometax_cert_password": "p",
    })
    rc = cli.main(
        ["--backend", "mock", "list"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_OK
    captured = capsys.readouterr()
    out_lines = [l for l in captured.out.splitlines() if l.strip()]
    assert out_lines == ["hometax_cert_password", "hometax_user_id"]
    # 비밀값 평문은 list 결과에 절대 들어가지 않는다.
    assert "p" not in (s for s in out_lines)
    assert "u" not in (s for s in out_lines)


def test_cli_list_keyring_like_backend_reports_not_supported(cli, capsys):
    """list_secret_ids 가 NotImplementedError 를 던지면 'not supported' 출력."""

    class _ReadOnlyBackend:
        name = "fake_keyring"

        def resolve(self, sid):  # pragma: no cover
            raise ts.SecretNotFoundError("not used in list test")

        def store(self, sid, v):  # pragma: no cover
            raise NotImplementedError

        def delete(self, sid):  # pragma: no cover
            raise NotImplementedError

        def exists(self, sid):  # pragma: no cover
            return False

        def list_secret_ids(self):
            raise NotImplementedError("listing not supported")

    rc = cli.main(
        ["list"],
        backend=_ReadOnlyBackend(),
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_NOT_FOUND
    captured = capsys.readouterr()
    assert "not supported" in captured.err


def test_cli_list_backend_without_list_method_reports_not_supported(cli, capsys):
    class _MinimalBackend:
        name = "minimal"

        def resolve(self, sid):  # pragma: no cover
            raise ts.SecretNotFoundError("nope")

        def store(self, sid, v):  # pragma: no cover
            pass

        def delete(self, sid):  # pragma: no cover
            pass

        def exists(self, sid):  # pragma: no cover
            return False

    rc = cli.main(
        ["list"],
        backend=_MinimalBackend(),
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_NOT_FOUND
    captured = capsys.readouterr()
    assert "not supported" in captured.err


# ─── G) usage 에러 — argparse 레벨 ──────────────────────────────────────

def test_cli_no_subcommand_returns_usage_error(cli, capsys):
    rc = cli.main(
        [],
        backend=ts.MockSecretBackend(),
        prompt_secret=_make_prompt([]),
    )
    assert rc == cli.EXIT_USAGE_ERROR


# ─── H) 비밀값 누출 회귀 — 종합 ─────────────────────────────────────────

def test_secret_value_never_appears_in_repr_after_full_lifecycle(cli, capsys):
    backend = ts.MockSecretBackend()
    canary = "p-canary-do-not-leak-9999"

    # 전체 lifecycle: add → check → delete.
    cli.main(
        ["--backend", "mock", "add", "hometax_cert_password"],
        backend=backend,
        prompt_secret=_make_prompt([canary, canary]),
    )
    cli.main(
        ["--backend", "mock", "check", "hometax_cert_password"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )
    cli.main(
        ["--backend", "mock", "delete", "hometax_cert_password"],
        backend=backend,
        prompt_secret=_make_prompt([]),
    )

    captured = capsys.readouterr()
    assert canary not in captured.out
    assert canary not in captured.err
    # backend 의 repr 도 평문을 흘리지 않는다 (F-4D 회귀).
    assert canary not in repr(backend)


def test_store_then_repr_does_not_leak_value():
    backend = ts.MockSecretBackend()
    canary = "p-canary-store-leak-test-aaaa"
    ts.store_secret("hometax_user_id", canary, backend=backend)
    assert canary not in repr(backend)
    assert canary not in str(backend)


def test_delete_secret_exception_does_not_leak_value():
    backend = ts.MockSecretBackend({"hometax_user_id": "v"})
    canary = "p-canary-stored-bbbb"
    backend.store("hometax_cert_password", canary)
    # 다른 secret_id 삭제 시도 → 본 케이스는 성공이지만 canary 는
    # repr/str 에 안 보여야 한다는 회귀.
    ts.delete_secret("hometax_user_id", backend=backend)
    assert canary not in repr(backend)
    # 미존재 삭제 시도의 예외 메시지에도 canary 노출 없음.
    with pytest.raises(ts.SecretNotFoundError) as exc_info:
        ts.delete_secret("missing_id", backend=backend)
    assert canary not in str(exc_info.value)
    assert canary not in repr(exc_info.value)


# ─── I) keyring 미설치 환경에서도 import OK ─────────────────────────────

def test_trusted_secrets_module_importable_without_keyring():
    # 본 테스트가 실행되고 있다는 사실 자체가 import 가 깨지지 않았다는
    # 증거. 명시적으로 핵심 심볼들이 있는지만 확인한다.
    assert hasattr(ts, "store_secret")
    assert hasattr(ts, "delete_secret")
    assert hasattr(ts, "secret_exists")
    assert hasattr(ts, "MockSecretBackend")
    assert hasattr(ts, "WindowsKeyringSecretBackend")


def test_cli_module_importable_without_keyring(cli):
    assert hasattr(cli, "main")
    assert hasattr(cli, "cmd_add")
    assert hasattr(cli, "cmd_check")
    assert hasattr(cli, "cmd_delete")
    assert hasattr(cli, "cmd_list")


# ─── J) CLI / module 에 자동화 코드 없음을 회귀로 고정 ─────────────────

def test_cli_module_does_not_contain_browser_automation_calls():
    """본 단계는 등록 CLI 만 — page.fill / click / submit / goto /
    Playwright 호출이 모듈에 없는지 회귀로 고정한다."""
    cli_path = os.path.join(_REPO_ROOT, "scripts", "local_secret_store.py")
    with open(cli_path, "r", encoding="utf-8") as f:
        source = f.read()
    forbidden_substrings = [
        "page.fill",
        "page.type",
        "page.click",
        "page.goto",
        "playwright",
        ".submit(",
        "browser_login_probe",
    ]
    for needle in forbidden_substrings:
        assert needle not in source, (
            f"local_secret_store.py must not contain {needle!r}"
        )


def test_trusted_secrets_module_does_not_contain_browser_automation_calls():
    ts_path = os.path.join(_REPO_ROOT, "local_agent", "trusted_secrets.py")
    with open(ts_path, "r", encoding="utf-8") as f:
        source = f.read()
    forbidden_substrings = [
        "page.fill",
        "page.type",
        "page.click",
        "page.goto",
        "playwright",
    ]
    for needle in forbidden_substrings:
        assert needle not in source, (
            f"trusted_secrets.py must not contain {needle!r}"
        )
