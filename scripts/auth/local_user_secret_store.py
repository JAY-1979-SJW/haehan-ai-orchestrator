"""Local per-user secret store.

Secrets are stored through the operating-system keyring when available. The
module intentionally has no plaintext fallback: callers receive status and
references only, never raw values in command output or reports.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

STORE_PREFIX = "haehan-ai-orchestrator"
REF_PREFIX = "local-secret://"


@dataclass(frozen=True)
class SecretRef:
    kind: str
    name: str

    @property
    def ref(self) -> str:
        return f"{REF_PREFIX}{self.kind}/{self.name}"

    @property
    def service(self) -> str:
        return f"{STORE_PREFIX}:{self.kind}"


def _try_keyring():
    try:
        import keyring  # type: ignore
    except Exception:  # noqa: BLE001 - keyring 라이브러리 부재시 None 반환(호출부에서 blocked 처리)·keyring 삭제 실패시 상태를 missing으로 기록 — 값 자체는 항상 redacted 처리되어 평문 노출 없음
        return None
    return keyring


def parse_ref(ref: str) -> SecretRef:
    if not ref.startswith(REF_PREFIX):
        raise ValueError("secret reference must start with local-secret://")
    body = ref[len(REF_PREFIX) :].strip("/")
    if "/" not in body:
        raise ValueError("secret reference must be local-secret://<kind>/<name>")
    kind, name = body.split("/", 1)
    kind = kind.strip()
    name = name.strip()
    if not kind or not name:
        raise ValueError("secret reference kind and name are required")
    if any(part in {".", ".."} for part in (kind, name)):
        raise ValueError("secret reference cannot use path traversal names")
    return SecretRef(kind=kind, name=name)


def make_ref(kind: str, name: str) -> str:
    return SecretRef(kind=kind.strip(), name=name.strip()).ref


def store_secret(ref: str, value: str) -> dict:
    parsed = parse_ref(ref)
    if not value:
        return {"ok": False, "status": "blocked", "reason": "empty_secret_value", "ref": parsed.ref}
    kr = _try_keyring()
    if kr is None:
        return {"ok": False, "status": "blocked", "reason": "keyring_unavailable", "ref": parsed.ref}
    kr.set_password(parsed.service, parsed.name, value)
    return {
        "ok": True,
        "status": "stored",
        "ref": parsed.ref,
        "backend": "keyring",
        "secret_output": "redacted",
    }


def load_secret(ref: str) -> str:
    parsed = parse_ref(ref)
    kr = _try_keyring()
    if kr is None:
        return ""
    return kr.get_password(parsed.service, parsed.name) or ""


def secret_status(ref: str) -> dict:
    parsed = parse_ref(ref)
    kr = _try_keyring()
    if kr is None:
        return {"ok": False, "status": "blocked", "reason": "keyring_unavailable", "ref": parsed.ref}
    return {
        "ok": True,
        "status": "present" if bool(kr.get_password(parsed.service, parsed.name)) else "missing",
        "ref": parsed.ref,
        "backend": "keyring",
        "secret_output": "redacted",
    }


def delete_secret(ref: str) -> dict:
    parsed = parse_ref(ref)
    kr = _try_keyring()
    if kr is None:
        return {"ok": False, "status": "blocked", "reason": "keyring_unavailable", "ref": parsed.ref}
    try:
        kr.delete_password(parsed.service, parsed.name)
        status = "deleted"
    except Exception:  # noqa: BLE001 - keyring 라이브러리 부재시 None 반환(호출부에서 blocked 처리)·keyring 삭제 실패시 상태를 missing으로 기록 — 값 자체는 항상 redacted 처리되어 평문 노출 없음
        status = "missing"
    return {"ok": True, "status": status, "ref": parsed.ref, "secret_output": "redacted"}


def _print_status(result: dict) -> None:
    for key in ("ok", "status", "reason", "ref", "backend", "secret_output"):
        if key in result:
            print(f"{key}: {result[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store per-user local secrets without printing values.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    put = sub.add_parser("put", help="store secret from stdin")
    put.add_argument("kind")
    put.add_argument("name")

    put_file = sub.add_parser("put-file", help="store secret from a local file")
    put_file.add_argument("kind")
    put_file.add_argument("name")
    put_file.add_argument("path")

    status = sub.add_parser("status", help="check whether a secret exists")
    status.add_argument("kind")
    status.add_argument("name")

    delete = sub.add_parser("delete", help="delete a stored secret")
    delete.add_argument("kind")
    delete.add_argument("name")

    args = parser.parse_args(argv)
    ref = make_ref(args.kind, args.name)
    if args.cmd == "put":
        result = store_secret(ref, sys.stdin.read())
    elif args.cmd == "put-file":
        result = store_secret(ref, Path(args.path).read_text(encoding="utf-8"))
    elif args.cmd == "status":
        result = secret_status(ref)
    elif args.cmd == "delete":
        result = delete_secret(ref)
    else:  # pragma: no cover - argparse enforces choices
        raise AssertionError(args.cmd)
    _print_status(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
