"""F-4E — Local secret registration CLI for the operator PC.

본 CLI 는 대표님 PC 에서 trusted browser automation 트랙 (F-4C/F-4D
시리즈) 이 사용할 ``secret_id`` 를 OS 보안 저장소 (Windows Credential
Manager 등) 에 직접 등록/확인/삭제하기 위한 운영자용 도구이다.

원칙 (docs/design/trusted_browser_automation_policy.md 참조):
  - 비밀값은 본 CLI 가 실행되는 PC 의 OS 키 저장소에만 머문다.
  - 입력은 ``getpass.getpass`` 로 받고 echo 하지 않는다.
  - 비밀값을 stdout / stderr / 로그 / 예외 메시지에 절대 출력하지 않는다.
  - secret_id 는 ``letters/digits/_-.`` 만 허용하고, raw-secret keyword
    (``password``, ``cookie``, ``session``, ``storage_state`` 등) 와
    동일한 이름은 거절한다.
  - ``--backend mock`` 은 테스트 전용. 기본은 OS keyring backend.
  - 본 CLI 는 홈택스 자동 로그인이나 브라우저 입력/클릭/제출 동작을
    수행하지 않는다 (F-4F 이후).

사용 예:
    python scripts/local_secret_store.py add hometax_cert_password
    python scripts/local_secret_store.py check hometax_cert_password
    python scripts/local_secret_store.py delete hometax_cert_password
    python scripts/local_secret_store.py list
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Callable, Optional, Sequence

# 프로젝트 루트를 sys.path 에 올려야 ``local_agent`` import 가 동작한다.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from local_agent import trusted_secrets as ts  # noqa: E402


# ─── 종료 코드 ───────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_NOT_FOUND = 1            # check/delete 시 secret_id 가 없음
EXIT_USAGE_ERROR = 2          # 잘못된 secret_id, 빈 값, 확인 입력 불일치 등
EXIT_BACKEND_UNAVAILABLE = 3  # keyring 미설치 등
EXIT_BACKEND_ERROR = 4        # keyring 내부 오류, 기타 SecretResolutionError


# CLI-level 거절 대상: secret_id 이름이 raw-secret keyword 와 같으면
# 의미가 모호해지므로 정책상 거절한다 (예: secret_id="password" 금지).
_BLOCKED_SECRET_IDS = frozenset(ts.raw_secret_param_keys())


# 운영자용 가이드: 홈택스 자동화에 권장되는 secret_id 후보. 실제 비밀값
# 자체는 본 파일/문서에 절대 들어가지 않는다.
_RECOMMENDED_HOMETAX_SECRET_IDS = (
    "hometax_user_id",
    "hometax_cert_password",
    "hometax_simple_auth_hint",
)


PromptFn = Callable[[str], str]


def _eprint(message: str) -> None:
    """stderr 로 사람-friendly 메시지를 출력 (비밀값은 절대 들어가지 않는다)."""
    print(message, file=sys.stderr)


def _validate_cli_secret_id(secret_id: str) -> Optional[str]:
    """CLI 입력 secret_id 검증. 문제 없으면 ``None``, 있으면 사람-readable
    에러 문자열 (비밀값 미포함) 반환."""
    if not ts.is_valid_secret_id(secret_id):
        return (
            "invalid secret_id format "
            "(allowed chars: letters / digits / '_' / '-' / '.', "
            "length 3..128, no leading/trailing whitespace)"
        )
    if secret_id.lower() in _BLOCKED_SECRET_IDS:
        return (
            f"refusing to use raw-secret keyword as secret_id: {secret_id!r} "
            "(use a descriptive name like 'hometax_cert_password' instead)"
        )
    return None


def _prompt_value_twice(
    secret_id: str, prompt_secret: PromptFn
) -> Optional[str]:
    """getpass 로 비밀값을 두 번 받아서 일치 여부 확인.

    일치하면 평문 str 반환, 불일치/빈값이면 ``None``.
    화면에는 입력값을 절대 출력하지 않는다.
    """
    first = prompt_secret(f"Enter value for secret_id {secret_id!r}: ")
    if first == "":
        _eprint("aborted: empty value not allowed")
        return None
    second = prompt_secret("Re-enter to confirm: ")
    if first != second:
        _eprint("aborted: confirmation did not match")
        return None
    return first


def _build_default_backend(name: Optional[str]) -> ts.SecretBackend:
    """``--backend`` 플래그를 받아 backend 인스턴스 생성.

    keyring 미설치 시 ``SecretBackendUnavailableError`` 가 호출자에게
    전파된다. 본 함수는 평문 비밀값을 다루지 않는다.
    """
    return ts.get_secret_backend(name)


# ─── 서브커맨드 ──────────────────────────────────────────────────────────

def cmd_add(
    args: argparse.Namespace,
    backend: ts.SecretBackend,
    prompt_secret: PromptFn,
) -> int:
    err = _validate_cli_secret_id(args.secret_id)
    if err is not None:
        _eprint(err)
        return EXIT_USAGE_ERROR

    value = _prompt_value_twice(args.secret_id, prompt_secret)
    if value is None:
        return EXIT_USAGE_ERROR

    try:
        ts.store_secret(args.secret_id, value, backend=backend)
    except ts.SecretBackendUnavailableError:
        _eprint("backend unavailable (is the keyring package installed?)")
        return EXIT_BACKEND_UNAVAILABLE
    except ts.SecretResolutionError:
        # 평문 비밀값은 메시지에 들어가지 않는다는 trusted_secrets 계약.
        _eprint("backend error while storing secret")
        return EXIT_BACKEND_ERROR
    finally:
        # 즉시 폐기 — 호출 후 지역 변수 ref 만 남아도 GC 까지 짧게.
        value = None  # type: ignore[assignment]

    print(f"stored: {args.secret_id}")
    return EXIT_OK


def cmd_check(
    args: argparse.Namespace,
    backend: ts.SecretBackend,
    prompt_secret: PromptFn,
) -> int:
    err = _validate_cli_secret_id(args.secret_id)
    if err is not None:
        _eprint(err)
        return EXIT_USAGE_ERROR

    try:
        present = ts.secret_exists(args.secret_id, backend=backend)
    except ts.SecretBackendUnavailableError:
        _eprint("backend unavailable (is the keyring package installed?)")
        return EXIT_BACKEND_UNAVAILABLE
    except ts.SecretResolutionError:
        _eprint("backend error while checking secret")
        return EXIT_BACKEND_ERROR

    if present:
        print(f"present: {args.secret_id}")
        return EXIT_OK
    print(f"absent: {args.secret_id}")
    return EXIT_NOT_FOUND


def cmd_delete(
    args: argparse.Namespace,
    backend: ts.SecretBackend,
    prompt_secret: PromptFn,
) -> int:
    err = _validate_cli_secret_id(args.secret_id)
    if err is not None:
        _eprint(err)
        return EXIT_USAGE_ERROR

    try:
        ts.delete_secret(args.secret_id, backend=backend)
    except ts.SecretNotFoundError:
        # secret_id 만 출력 — 비밀값은 어차피 본 함수가 본 적이 없다.
        _eprint(f"not found: {args.secret_id}")
        return EXIT_NOT_FOUND
    except ts.SecretBackendUnavailableError:
        _eprint("backend unavailable (is the keyring package installed?)")
        return EXIT_BACKEND_UNAVAILABLE
    except ts.SecretResolutionError:
        _eprint("backend error while deleting secret")
        return EXIT_BACKEND_ERROR

    print(f"deleted: {args.secret_id}")
    return EXIT_OK


def cmd_list(
    args: argparse.Namespace,
    backend: ts.SecretBackend,
    prompt_secret: PromptFn,
) -> int:
    list_fn = getattr(backend, "list_secret_ids", None)
    if list_fn is None:
        _eprint("not supported by this backend")
        return EXIT_NOT_FOUND
    try:
        ids = list_fn()
    except NotImplementedError:
        _eprint("not supported by this backend")
        return EXIT_NOT_FOUND
    except ts.SecretBackendUnavailableError:
        _eprint("backend unavailable (is the keyring package installed?)")
        return EXIT_BACKEND_UNAVAILABLE
    except ts.SecretResolutionError:
        _eprint("backend error while listing secrets")
        return EXIT_BACKEND_ERROR

    for sid in ids:
        print(sid)
    return EXIT_OK


# ─── 진입점 ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="local_secret_store",
        description=(
            "Register / inspect / delete secret_ids in the operator PC's "
            "OS keyring. Secret values are never echoed or logged."
        ),
        epilog=(
            "Recommended secret_ids for hometax: "
            + ", ".join(_RECOMMENDED_HOMETAX_SECRET_IDS)
        ),
    )
    p.add_argument(
        "--backend",
        default=None,
        choices=("mock", "keyring", "windows", "windows_keyring", "auto"),
        help=(
            "Backend selector. Default = OS keyring (Windows Credential "
            "Manager). 'mock' is for tests only."
        ),
    )
    sub = p.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add", help="Register a secret_id (prompts twice)")
    add_p.add_argument("secret_id")

    check_p = sub.add_parser("check", help="Check whether a secret_id exists")
    check_p.add_argument("secret_id")

    delete_p = sub.add_parser("delete", help="Delete a stored secret_id")
    delete_p.add_argument("secret_id")

    sub.add_parser(
        "list",
        help=(
            "List secret_ids (mock backend only — keyring backend reports "
            "'not supported')"
        ),
    )

    return p


_DISPATCH: dict[str, Callable[
    [argparse.Namespace, ts.SecretBackend, PromptFn], int
]] = {
    "add": cmd_add,
    "check": cmd_check,
    "delete": cmd_delete,
    "list": cmd_list,
}


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    backend: Optional[ts.SecretBackend] = None,
    prompt_secret: Optional[PromptFn] = None,
) -> int:
    """CLI 진입점.

    파라미터:
      argv:           ``sys.argv[1:]`` 같은 인자 시퀀스. ``None`` 이면 기본.
      backend:        주입형 backend (테스트 전용). ``None`` 이면
                       ``--backend`` 플래그 → ``get_secret_backend()``.
      prompt_secret:  주입형 입력 함수 (테스트 전용). ``None`` 이면
                       ``getpass.getpass``.

    반환: 종료 코드 (int).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help(sys.stderr)
        return EXIT_USAGE_ERROR

    if backend is None:
        try:
            backend = _build_default_backend(args.backend)
        except ts.SecretBackendUnavailableError:
            _eprint("backend unavailable (is the keyring package installed?)")
            return EXIT_BACKEND_UNAVAILABLE
        except ValueError as exc:
            _eprint(str(exc))
            return EXIT_USAGE_ERROR

    if prompt_secret is None:
        prompt_secret = getpass.getpass

    handler = _DISPATCH[args.cmd]
    return handler(args, backend, prompt_secret)


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
