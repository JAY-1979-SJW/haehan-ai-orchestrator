"""JWT_SECRET 영속화(결함 2026-10-10) — env 없을 때 매 import 마다 새 비밀을 만들어
서버 재시작 때마다 기존 토큰이 전부 무효화되던 문제. storage_dir()/jwt_secret.key 에
한 번 만든 값을 저장해 재사용한다(config._load_or_create_persisted_jwt_secret)."""

from __future__ import annotations

from ai_orchestrator.core import config


def test_creates_and_reuses_secret_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "storage_dir", lambda: tmp_path)

    first = config._load_or_create_persisted_jwt_secret()
    path = tmp_path / config._JWT_SECRET_FILE_NAME
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip() == first

    second = config._load_or_create_persisted_jwt_secret()
    assert second == first  # 재시작(재호출) 해도 같은 값


def test_env_takes_priority_over_file(tmp_path):
    """importlib.reload 는 쓰지 않는다 — 다른 모듈이 config 를 import 시점에 들고
    있는 참조를 오염시키는 결함 패턴(2026-10-10, DEFECTS_FLAKY.md)과 같은 위험이라,
    env 우선순위는 별도 프로세스로 확인한다."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo_root = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
    (tmp_path / config._JWT_SECRET_FILE_NAME).write_text("file-secret", encoding="utf-8")
    code = (
        "import os, json; os.environ['HAEHAN_STORAGE_DIR']=r'" + str(tmp_path) + "'; "
        "os.environ['JWT_SECRET']='env-secret'; "
        "from ai_orchestrator.core import config; "
        "print(json.dumps({'secret': config.JWT_SECRET, 'configured': config.JWT_SECRET_CONFIGURED}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["secret"] == "env-secret"
    assert out["configured"] is True
