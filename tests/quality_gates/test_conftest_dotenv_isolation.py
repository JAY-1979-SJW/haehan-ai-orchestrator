"""시험 환경의 `.env` 격리 — 상위 폴더의 `.env` 가 시험이 지정한 환경변수를 덮어쓰지 못한다 (conftest._isolate_dotenv_override)."""

from __future__ import annotations

import dotenv


def test_dotenv_cannot_override_test_set_variable(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("HAEHAN_ISO_PROBE=from_dotenv_file\n", encoding="utf-8")
    monkeypatch.setenv("HAEHAN_ISO_PROBE", "from_test")
    dotenv.load_dotenv(env_file, override=True)  # 코드가 override=True 로 불러도
    import os

    assert os.environ["HAEHAN_ISO_PROBE"] == "from_test"


def test_dotenv_still_fills_missing_variable(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("HAEHAN_ISO_ONLY_IN_FILE=filled\n", encoding="utf-8")
    monkeypatch.delenv("HAEHAN_ISO_ONLY_IN_FILE", raising=False)
    dotenv.load_dotenv(env_file, override=True)
    import os

    assert os.environ.get("HAEHAN_ISO_ONLY_IN_FILE") == "filled"  # 없는 값을 .env 로 채우는 동작은 유지
    monkeypatch.delenv("HAEHAN_ISO_ONLY_IN_FILE", raising=False)


def test_wrapper_is_installed_once():
    assert getattr(dotenv.load_dotenv, "_haehan_no_override", False) is True
