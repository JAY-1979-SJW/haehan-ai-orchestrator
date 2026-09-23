"""AGENT_OPENAI_DEV_KEY_STORE_01 audit."""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class KeyStoreVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


MODULE_PATH = Path("local_agent/openai_key_store.py")
REQUIRED_API = (
    "save_dev_key",
    "load_dev_key",
    "delete_dev_key",
    "has_dev_key",
    "get_key_fingerprint",
    "validate_key_format",
    "redact_key",
    "describe_backend",
    "keyring_available",
    "SERVICE_NAME",
    "ACCOUNT_DEFAULT",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _resolve(mod: str, sym: str):
    try:
        m = importlib.import_module(mod)
        return getattr(m, sym, None)
    except Exception:
        return None


def judge_key_store(*, desktop_ui_unchanged: bool = True, gui_connection_test_done: bool = False) -> KeyStoreVerdict:
    metrics: dict = {}

    if not desktop_ui_unchanged:
        return KeyStoreVerdict(False, "FAIL_DESKTOP_UI_TOUCHED", reasons=["desktop/ui touched"], metrics=metrics)

    # FAIL_KEY_STORE_MISSING
    if not MODULE_PATH.exists():
        return KeyStoreVerdict(False, "FAIL_KEY_STORE_MISSING", reasons=[f"missing: {MODULE_PATH}"], metrics=metrics)
    for sym in REQUIRED_API:
        if _resolve("local_agent.openai_key_store", sym) is None:
            return KeyStoreVerdict(False, "FAIL_KEY_STORE_MISSING", reasons=[f"missing API: {sym}"], metrics=metrics)

    src = _read(MODULE_PATH)

    # FAIL_KEY_FORMAT_VALIDATION_MISSING — validate_key_format 동작 라이브
    from local_agent.openai_key_store import (
        SERVICE_NAME,
        load_dev_key,
        redact_key,
        save_dev_key,
        validate_key_format,
    )

    cases = [
        ("", False),  # empty
        ("short", False),  # too short
        ("sk-...", False),  # placeholder
        ("YOUR_API_KEY", False),  # placeholder
        ("test", False),  # placeholder
        (" " * 50, False),  # whitespace
        ("sk-abcdEFGH12345678ijklMNOP", True),  # 24 chars OK
        ("real_key_value_long_enough_xyz", True),
    ]
    for raw, expected_ok in cases:
        ok, _ = validate_key_format(raw)
        if ok != expected_ok:
            return KeyStoreVerdict(
                False,
                "FAIL_KEY_FORMAT_VALIDATION_MISSING",
                reasons=[f"validate({raw[:10]!r}) expected={expected_ok} got={ok}"],
                metrics=metrics,
            )

    # FAIL_KEY_LEAK — 소스/문서/test 에 raw OpenAI key 패턴 부재
    # (단, 정규식 패턴 자체 [A-Za-z 같은 건 OK)
    for f in (
        MODULE_PATH,
        Path("scripts/ops/audit_openai_dev_key_store.py"),
        Path("tests/test_openai_dev_key_store.py"),
    ):
        t = _read(f)
        if not t:
            continue
        # 진짜 long sk- 토큰 패턴 (20+ alnum)
        matches = re.findall(r"\bsk-[A-Za-z0-9_]{30,}\b", t)
        real = [m for m in matches if "[" not in m and "A-Za-z" not in m]
        if real:
            return KeyStoreVerdict(False, "FAIL_KEY_LEAK", reasons=[f"raw key in {f}: {real[:2]}"], metrics=metrics)

    # FAIL_PLAINTEXT_FALLBACK_ENABLED — 기본값이 OFF 인지
    # save_dev_key 의 allow_plaintext_fallback default 가 False 여야 함
    import inspect

    sig = inspect.signature(save_dev_key)
    p_fb = sig.parameters.get("allow_plaintext_fallback")
    if p_fb is None or p_fb.default is not False:
        return KeyStoreVerdict(
            False,
            "FAIL_PLAINTEXT_FALLBACK_ENABLED",
            reasons=["save_dev_key.allow_plaintext_fallback default != False"],
            metrics=metrics,
        )
    sig2 = inspect.signature(load_dev_key)
    if sig2.parameters["allow_plaintext_fallback"].default is not False:
        return KeyStoreVerdict(
            False,
            "FAIL_PLAINTEXT_FALLBACK_ENABLED",
            reasons=["load_dev_key fallback default != False"],
            metrics=metrics,
        )

    # FAIL_CREDENTIAL_MANAGER_NOT_USED — keyring import 시도가 있어야 함
    if "import keyring" not in src and "_try_keyring" not in src:
        return KeyStoreVerdict(
            False, "FAIL_CREDENTIAL_MANAGER_NOT_USED", reasons=["keyring not referenced"], metrics=metrics
        )
    # SERVICE_NAME 명시
    if "haehan-openai" not in src:
        return KeyStoreVerdict(
            False, "FAIL_CREDENTIAL_MANAGER_NOT_USED", reasons=["service name 'haehan-openai' 미정의"], metrics=metrics
        )

    # fingerprint 동작 검증
    fp = redact_key("sk-abcdEFGH12345678ijklMNOP")
    if "MNOP" not in fp or "sk-****" not in fp:
        return KeyStoreVerdict(
            False, "FAIL_KEY_FORMAT_VALIDATION_MISSING", reasons=[f"redact_key unexpected: {fp}"], metrics=metrics
        )
    # 원문이 fingerprint 에 포함되면 안 됨
    if "abcdEFGH12345678ijkl" in fp:
        return KeyStoreVerdict(False, "FAIL_KEY_LEAK", reasons=["fingerprint leaks key body"], metrics=metrics)

    metrics["service_name"] = SERVICE_NAME
    metrics["keyring_available"] = bool(
        _resolve("local_agent.openai_key_store", "keyring_available")()
        if _resolve("local_agent.openai_key_store", "keyring_available")
        else False
    )

    # WARN — GUI [연결 테스트] 버튼은 다음 공정에서 활성화
    if not gui_connection_test_done:
        return KeyStoreVerdict(
            False,
            "WARN_GUI_CONNECTION_TEST_DEFERRED",
            reasons=["[연결 테스트] 활성은 AGENT_OPENAI_DIRECT_DEV_CALL_01"],
            metrics=metrics,
        )

    return KeyStoreVerdict(True, "PASS_OPENAI_DEV_KEY_STORE", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--gui-connection-done", type=int, default=0)
    args = ap.parse_args(argv)
    v = judge_key_store(gui_connection_test_done=bool(args.gui_connection_done))
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
