"""감사 로그 정본(ai_orchestrator/audit/audit_logger.py) — 폴더로 옮긴 뒤에도 기록 경로·마스킹이 이전과 같다(W17).

경로는 core.config 가 정한다: LOG_DIR(.env 가 load_dotenv 로 먼저 들어온 뒤) > storage_dir()(HAEHAN_STORAGE_DIR > HAEHAN_DATA_ROOT/storage > 패키지 안 ai_orchestrator/storage).
새 프로세스에서 환경변수를 바꿔 값이 같은지 본다(모듈 import 시점에 정해지므로).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_orchestrator.audit import audit_logger
from ai_orchestrator.core import config

ROOT = Path(__file__).resolve().parents[1]
_PROBE = "from ai_orchestrator.audit import audit_logger as a; print(a._LOG_PATH)"


def _resolve(env_extra: dict[str, str], tmp_path: Path) -> Path:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"LOG_DIR", "HAEHAN_DATA_ROOT", "HAEHAN_STORAGE_DIR", "HAEHAN_DATA_DIR"}
    }
    env.update(env_extra, HAEHAN_NO_BROWSER_LAUNCH="1", PYTHONIOENCODING="utf-8")
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=tmp_path,
        env={**env, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    return Path(out.stdout.strip().splitlines()[-1])


def test_audit_log_path_is_the_config_path():
    assert audit_logger._LOG_PATH == config.AUDIT_LOG_PATH
    assert audit_logger._LOG_PATH.name == "audit_logs.jsonl"


def test_desktop_data_root_decides_the_location(tmp_path):
    assert (
        _resolve({"HAEHAN_DATA_ROOT": str(tmp_path / "userdata")}, tmp_path)
        == tmp_path / "userdata" / "storage" / "audit_logs.jsonl"
    )


def test_log_dir_env_wins_over_data_root(tmp_path):
    got = _resolve({"LOG_DIR": str(tmp_path / "logs"), "HAEHAN_DATA_ROOT": str(tmp_path / "userdata")}, tmp_path)
    assert got == tmp_path / "logs" / "audit_logs.jsonl"


def test_server_default_is_the_package_storage_folder(tmp_path):
    assert (
        _resolve({}, tmp_path) == ROOT / "ai_orchestrator" / "storage" / "audit_logs.jsonl"
    )  # 이동 전과 같은 값(패키지 안 storage)


def test_log_event_still_masks_the_note_and_keeps_identifying_fields(tmp_path, monkeypatch):
    target = tmp_path / "audit_logs.jsonl"
    monkeypatch.setattr(audit_logger, "_LOG_PATH", target)
    fake_key = "sk" + "-" + "abcdefghij" * 4  # 비밀정보 검사에 걸리지 않게 조립한 가짜 키
    audit_logger.log_event("TASK_RECEIVED", "task-1", actor="kim", role="admin", note=f"token={fake_key}")
    entry = json.loads(target.read_text(encoding="utf-8").splitlines()[-1])
    assert fake_key not in entry["note"]  # 민감정보는 가려진다(9a48754b)
    assert entry["task_id"] == "task-1" and entry["actor"] == "kim" and entry["role"] == "admin"  # 식별 필드는 그대로


def test_old_import_path_is_gone():
    with pytest.raises(ImportError):
        import ai_orchestrator.audit_logger  # noqa: F401 - 원래 결과를 버리는 호출문(부수효과만 보려던 import)
