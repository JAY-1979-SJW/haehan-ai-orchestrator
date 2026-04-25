"""TAX-API-1 — scripts/check_business_registration.py CLI 테스트.

검증:
  - dry-run (--live 없이) 정상 종료, mock_or_disabled
  - --live + 키 없음 → WARN 종료 (rc=0), 메시지에 키 이름만
  - 입력 없음 → rc=2
  - --json 출력 형식
  - 출력에 service_key 원문 미노출
"""
from __future__ import annotations

import json
import os
import runpy
import sys
import tempfile
from contextlib import contextmanager
from io import StringIO

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator.connectors import (  # noqa: E402
    nts_business_api_config as _cfg_mod,
)


@contextmanager
def _isolate_env(**overrides: str):
    saved = {}
    for k in (
        _cfg_mod.ENV_SERVICE_KEY_PRIMARY,
        _cfg_mod.ENV_SERVICE_KEY_FALLBACK,
        _cfg_mod.ENV_BASE_URL,
        _cfg_mod.ENV_TIMEOUT_SECONDS,
    ):
        saved[k] = os.environ.pop(k, None)
    for k, v in overrides.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k in overrides:
            if k not in saved:
                os.environ.pop(k, None)


@contextmanager
def _capture_stdio():
    out, err = StringIO(), StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        yield out, err
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def _import_main():
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts",
    )))
    import importlib

    if "check_business_registration" in sys.modules:
        return importlib.reload(
            sys.modules["check_business_registration"]
        ).main
    mod = importlib.import_module("check_business_registration")
    return mod.main


def test_cli_no_input_returns_2():
    main = _import_main()
    with _isolate_env(), _capture_stdio() as (out, err):
        rc = main([])
    assert rc == 2
    assert "입력이 없습니다" in err.getvalue() or "입력이 없습니다" in out.getvalue()


def test_cli_dry_run_status_returns_warn_verdict():
    main = _import_main()
    with _isolate_env(), _capture_stdio() as (out, err):
        rc = main(["--status", "1234567890", "--json"])
    assert rc == 0
    payload = json.loads(out.getvalue())
    assert payload["verdict"] in ("WARN",)
    assert payload["config"]["service_key_present"] is False
    assert len(payload["results"]) == 1
    r = payload["results"][0]
    assert r["mode"] == "mock_or_disabled"
    assert r["kind"] == "status"


def test_cli_live_without_key_returns_warn_not_fail():
    main = _import_main()
    with _isolate_env(), _capture_stdio() as (out, err):
        rc = main(["--status", "1234567890", "--live", "--json"])
    assert rc == 0  # WARN, not FAIL
    text = out.getvalue()
    payload = json.loads(text)
    # 단일 WARN payload 형태.
    assert payload["mode"] == "mock_or_disabled"
    assert "live_requested_but_service_key_missing" in payload["warnings"]
    # 메시지에 키 원문 노출 금지 (애초에 없음).
    assert "service_key_present" in json.dumps(payload["config"])


def test_cli_status_file_input(tmp_path):
    main = _import_main()
    p = tmp_path / "list.txt"
    p.write_text(
        "# 주석\n"
        "1234567890\n"
        " 0987654321 \n"
        "\n"
        "bad\n",
        encoding="utf-8",
    )
    with _isolate_env(), _capture_stdio() as (out, err):
        rc = main(["--status-file", str(p), "--json"])
    assert rc == 0
    payload = json.loads(out.getvalue())
    r = payload["results"][0]
    assert r["mode"] == "mock_or_disabled"
    # 정규화 후 유효 2건 (bad 는 invalid_input warning 으로).
    assert r["count"] == 2
    assert any(w.startswith("invalid_input:") for w in r["warnings"])


def test_cli_validate_json_input(tmp_path):
    main = _import_main()
    items = [
        {"b_no": "123-45-67890", "start_dt": "2020-01-01", "p_nm": "홍길동"},
        {"b_no": "bad"},
    ]
    p = tmp_path / "v.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    with _isolate_env(), _capture_stdio() as (out, err):
        rc = main(["--validate-json", str(p), "--json"])
    assert rc == 0
    payload = json.loads(out.getvalue())
    r = payload["results"][0]
    assert r["kind"] == "validate"
    assert r["count"] == 1
    assert any(w.startswith("invalid_input:") for w in r["warnings"])


def test_cli_does_not_print_service_key_value():
    """--live 가 아닌 dry-run 에서도 환경변수 키가 있으면 출력에 키 원문이
    절대 들어가지 않아야 한다."""
    main = _import_main()
    secret = "DO_NOT_LEAK_KEY_VALUE_PLEASE"
    with _isolate_env(NTS_BUSINESS_API_SERVICE_KEY=secret), \
            _capture_stdio() as (out, err):
        rc = main(["--status", "1234567890", "--json"])
    assert rc == 0
    full = out.getvalue() + err.getvalue()
    assert secret not in full
    payload = json.loads(out.getvalue())
    assert payload["config"]["service_key_present"] is True
    assert payload["config"]["service_key_length"] == len(secret)
