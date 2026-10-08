"""런타임 데이터 위치(storage_dir/data_dir)와 예전 위치 1회 복사 이행 — DESKTOP_RUNTIME_AUDIT D1.

핵심 보증:
  ① 환경변수가 없으면 값 불변 — 교체한 모듈 상수가 예전 계산식(`Path(__file__)…/"storage"`·`ROOT/"data"`)과 같다.
  ② HAEHAN_DATA_ROOT 가 있으면 전부 그 아래로 간다(번들 폴더에 쓰지 않는다).
  ③ 이행은 복사(원본 유지)·덮어쓰기 금지·1회 표시·실패해도 시작을 막지 않는다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_orchestrator.paths import migrate, runtime

REPO = Path(__file__).resolve().parents[2]
PKG = REPO / "ai_orchestrator"

# (모듈, 상수, 기대값 — 예전 계산식 결과). 교체 전과 같은 값이어야 한다.
STORAGE = "storage"
DATA = "data"
CONSTANTS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("ai_orchestrator.auth.user_db", "_DB_PATH", STORAGE, ("users.db",)),
    ("ai_orchestrator.auth.auth_audit", "_AUDIT_PATH", STORAGE, ("auth_audit.jsonl",)),
    ("ai_orchestrator.agent_dispatch.agent_dispatch_store", "_DB_PATH", STORAGE, ("agent_dispatch.db",)),
    ("ai_orchestrator.connectors.hanafax.authorization_store", "_DB_PATH", STORAGE, ("fax_authorizations.db",)),
    ("ai_orchestrator.gongmu.gongmu_store", "_DB_PATH", STORAGE, ("gongmu.db",)),
    ("ai_orchestrator.connectors.naver_mail.bulk_store", "_DB_PATH", STORAGE, ("mail_bulk.db",)),
    ("ai_orchestrator.connectors.naver_mail.draft_store", "_DB_PATH", STORAGE, ("naver_mail_drafts.db",)),
    ("ai_orchestrator.scheduler.scheduled_job_store", "_DB_PATH", STORAGE, ("scheduled_jobs.db",)),
    ("ai_orchestrator.site_work.work_record_store", "_DB_PATH", STORAGE, ("work_records.db",)),
    ("ai_orchestrator.connectors.instagram.instagram_dm_db", "_DB_PATH", STORAGE, ("instagram_dm.db",)),
    ("ai_orchestrator.dev_reg.dev_reg_runner", "_SCREENSHOT_DIR", STORAGE, ("screenshots", "dev_reg")),
    ("ai_orchestrator.connectors.hanafax.attachments", "_UPLOAD_DIR", STORAGE, ("fax_attachments",)),
    ("ai_orchestrator.connectors.hanafax.authorization_service", "_CACHE_DIR", STORAGE, ("fax_address_cache",)),
    ("ai_orchestrator.core.config", "LOG_DIR", STORAGE, ()),
    ("ai_orchestrator.core.config", "AUDIT_LOG_PATH", STORAGE, ("audit_logs.jsonl",)),
    ("ai_orchestrator.core.config", "_DEFAULT_DATA_DIR", DATA, ()),
    ("ai_orchestrator.tasks.chat_sessions", "_STORE_PATH", DATA, ("chat_sessions.json",)),
    ("ai_orchestrator.connectors.eum.router", "_TARGETS_LATEST", DATA, ("eum_sales_mail_targets_latest.json",)),
    ("ai_orchestrator.connectors.grant_radar_router", "DATA_DIR", DATA, ("grant_radar",)),
    ("ai_orchestrator.connectors.kakao.setup_router", "STATE_PATH", DATA, ("kakao_setup_state.json",)),
    ("ai_orchestrator.marketing.marketing_ops_router", "_RESEARCH_FILE", DATA, ("blog_topic_research_latest.json",)),
    ("ai_orchestrator.marketing.marketing_ops_router", "_CACHE_FILE", DATA, ("blog_topic_cache.json",)),
    ("ai_orchestrator.marketing.marketing_ops_router", "_REPORTS_DIR", DATA, ("reports",)),
    ("ai_orchestrator.marketing.marketing_ops_router", "_PACKAGES_DIR", DATA, ("marketing_packages",)),
    ("ai_orchestrator.connectors.naver_blog.naver_blog_router", "DRAFTS_DIR", DATA, ("blog_drafts",)),
    ("ai_orchestrator.connectors.naver_cafe.naver_cafe_router", "_CAFE_DIR", DATA, ("cafe",)),
    ("ai_orchestrator.connectors.public_media_router", "MEDIA_DIR", DATA, ("public_media",)),
    ("ai_orchestrator.connectors.session_status_router", "DATA_PATH", DATA, ("login_session_monitor_latest.json",)),
    ("ai_orchestrator.connectors.smartstore._helpers", "_SS_DATA_DIR", DATA, ("smartstore",)),
    ("ai_orchestrator.connectors.naver_cafe.membership_store", "_DIR", DATA, ("cafe",)),
    ("ai_orchestrator.site_work.site_registry_store", "_FILE", DATA, ("site_registry", "sites.json")),
    ("ai_orchestrator.site_work.site_task_map_store", "_DIR", DATA, ("site_task_map",)),
    ("ai_orchestrator.site_work.site_task_map_request_store", "_DIR", DATA, ("site_task_map_requests",)),
    ("ai_orchestrator.routers.deploy_router", "STATUS_FILE", DATA, ("runtime", "server_deploy_latest.json")),
    ("ai_orchestrator.routers.server_router", "_DEPLOY_STATUS_FILE", DATA, ("runtime", "server_deploy_latest.json")),
    ("ai_orchestrator.connectors.naver_auth.login_pipeline", "SESSION_STATUS_FILE", DATA, ("naver_session_state.json",)),
    ("ai_orchestrator.connectors.naver_auth.session_guard", "ATTEMPTS_FILE", DATA, ("naver_login_attempts.json",)),
    ("scripts.common.cdp_audit", "AUDIT_ROOT", DATA, ("audit",)),
    ("scripts.browser.agent.cdp_session_manager", "PROFILE_ROOT", DATA, ("cdp_profile",)),
    ("scripts.browser.agent.action_gate", "_POLICY_PATH", DATA, ("gate_policy.json",)),
    ("ai_orchestrator.agent_hub.registry.common", "_REGISTRY_STATE_PATH", DATA, ("local_agent_registry_state.json",)),
]

_CLEAN_KEYS = ("HAEHAN_DATA_ROOT", "HAEHAN_DATA_DIR", "HAEHAN_STORAGE_DIR", "LOG_DIR", "LOCAL_DATA_DIR")


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _CLEAN_KEYS and k.upper() != "PYTHONPATH"}
    env["PYTHONUTF8"] = "1"
    env.update(extra)
    return env


def _resolve(env: dict[str, str]) -> dict[str, str]:
    """새 프로세스에서 모듈을 import 해 상수를 읽는다(import 시점 계산이라 격리가 필요)."""
    spec = json.dumps([(m, a) for m, a, *_ in CONSTANTS])
    code = (
        "import importlib, json, sys\n"
        f"items = json.loads({spec!r})\n"
        "out = {}\n"
        "for m, a in items:\n"
        "    try:\n"
        "        out[m + ':' + a] = str(getattr(importlib.import_module(m), a))\n"
        "    except Exception as e:\n"
        "        out[m + ':' + a] = 'ERR ' + type(e).__name__ + ': ' + str(e)[:120]\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=240,
    )
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_constants_unchanged_without_env():
    got = _resolve(_clean_env())
    bad = []
    for mod, attr, kind, tail in CONSTANTS:
        base = PKG / "storage" if kind == STORAGE else REPO / "data"
        want = str(base.joinpath(*tail))
        if got[f"{mod}:{attr}"] != want:
            bad.append((mod, attr, got[f"{mod}:{attr}"], want))
    assert not bad, bad


def test_constants_follow_data_root(tmp_path):
    root = tmp_path / "userdata"
    got = _resolve(_clean_env(HAEHAN_DATA_ROOT=str(root)))
    bad = []
    for mod, attr, kind, tail in CONSTANTS:
        want = str((root / ("storage" if kind == STORAGE else "data")).joinpath(*tail))
        if got[f"{mod}:{attr}"] != want:
            bad.append((mod, attr, got[f"{mod}:{attr}"], want))
    assert not bad, bad


def test_log_dir_env_still_wins_for_audit_logs(tmp_path):
    got = _resolve(_clean_env(HAEHAN_DATA_ROOT=str(tmp_path / "r"), LOG_DIR=str(tmp_path / "logs")))
    assert got["ai_orchestrator.core.config:LOG_DIR"] == str(tmp_path / "logs")
    assert got["ai_orchestrator.core.config:AUDIT_LOG_PATH"] == str(tmp_path / "logs" / "audit_logs.jsonl")


# ── 해석 순서 ─────────────────────────────────────────────────────────────


def test_resolution_order(monkeypatch, tmp_path):
    for k in _CLEAN_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert runtime.data_dir() == REPO / "data" and runtime.storage_dir() == PKG / "storage"
    monkeypatch.setenv("HAEHAN_DATA_ROOT", str(tmp_path / "root"))
    assert runtime.data_dir() == tmp_path / "root" / "data"
    assert runtime.storage_dir() == tmp_path / "root" / "storage"
    monkeypatch.setenv("HAEHAN_DATA_DIR", str(tmp_path / "legacy"))  # 옛 이름이 데이터 폴더를 직접 지정
    assert runtime.data_dir() == tmp_path / "legacy"
    assert runtime.storage_dir() == tmp_path / "root" / "storage"
    monkeypatch.setenv("HAEHAN_STORAGE_DIR", str(tmp_path / "st"))
    assert runtime.storage_dir() == tmp_path / "st"
    monkeypatch.setenv("HAEHAN_DATA_ROOT", "   ")  # 공백은 없는 것으로
    monkeypatch.delenv("HAEHAN_DATA_DIR")
    monkeypatch.delenv("HAEHAN_STORAGE_DIR")
    assert runtime.data_dir() == REPO / "data"


def test_data_root_is_the_same_env_as_app_paths():
    from scripts.common import app_paths

    assert runtime.ENV_DATA_ROOT == app_paths.ENV_DATA_ROOT  # 정본이 갈라지지 않게 환경변수 하나로 묶는다


def test_ensure_runtime_dirs_only_with_override(monkeypatch, tmp_path):
    for k in _CLEAN_KEYS:
        monkeypatch.delenv(k, raising=False)
    runtime.ensure_runtime_dirs()  # 환경변수 없음 → 아무것도 만들지 않는다
    monkeypatch.setenv("HAEHAN_DATA_ROOT", str(tmp_path / "new"))
    runtime.ensure_runtime_dirs()
    assert (tmp_path / "new" / "storage").is_dir() and (tmp_path / "new" / "data").is_dir()


# ── 이행 ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def legacy(tmp_path, monkeypatch):
    """번들 안 예전 위치(tmp)에 데이터를 두고, 새 위치는 HAEHAN_DATA_ROOT 로 지정."""
    old_storage, old_data = tmp_path / "bundle" / "storage", tmp_path / "bundle" / "data"
    (old_storage / "secrets").mkdir(parents=True)
    (old_data / "cafe").mkdir(parents=True)
    (old_storage / "users.db").write_bytes(b"OLD-USERS")
    (old_storage / "users.db-wal").write_bytes(b"OLD-WAL")
    (old_storage / "audit_logs.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (old_storage / "secrets" / "tok.json").write_text("{}", encoding="utf-8")
    (old_data / "cafe" / "x.json").write_text("{}", encoding="utf-8")
    (old_storage / "__pycache__").mkdir()
    (old_storage / "__pycache__" / "m.pyc").write_bytes(b"x")
    (old_storage / ".gitkeep").write_text("", encoding="utf-8")
    new_root = tmp_path / "userData"
    for k in _CLEAN_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HAEHAN_DATA_ROOT", str(new_root))
    monkeypatch.setenv("HAEHAN_MIGRATE_LEGACY", "1")
    monkeypatch.setattr(migrate, "default_storage_dir", lambda: old_storage)
    monkeypatch.setattr(migrate, "default_data_dir", lambda: old_data)
    return old_storage, old_data, new_root


def test_migration_copies_not_moves_and_marks_done(legacy):
    old_storage, _old_data, new_root = legacy
    r = migrate.migrate_legacy_data()
    assert r["status"] == "complete"
    assert (new_root / "storage" / "users.db").read_bytes() == b"OLD-USERS"
    assert (new_root / "storage" / "users.db-wal").read_bytes() == b"OLD-WAL"  # WAL 도 함께
    assert (new_root / "storage" / "secrets" / "tok.json").is_file()
    assert (new_root / "data" / "cafe" / "x.json").is_file()
    assert not (new_root / "storage" / "__pycache__").exists() and not (new_root / "storage" / ".gitkeep").exists()
    assert (old_storage / "users.db").read_bytes() == b"OLD-USERS"  # 원본 유지(이동 아님)
    marker = json.loads((new_root / migrate.MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["complete"] is True and marker["summary"]["storage"]["copied"] == 4


def test_migration_runs_once(legacy):
    _, _, new_root = legacy
    assert migrate.migrate_legacy_data()["status"] == "complete"
    (new_root / "storage" / "users.db").write_bytes(b"NEW-AFTER")  # 이후 새 위치에서 바뀐 데이터
    again = migrate.migrate_legacy_data()
    assert again["status"] == "already_done"
    assert (new_root / "storage" / "users.db").read_bytes() == b"NEW-AFTER"  # 다시 복사하지 않는다


def test_migration_never_overwrites_existing_new_files(legacy):
    _, _, new_root = legacy
    (new_root / "storage").mkdir(parents=True)
    (new_root / "storage" / "users.db").write_bytes(b"ALREADY-NEW")
    r = migrate.migrate_legacy_data()
    assert (new_root / "storage" / "users.db").read_bytes() == b"ALREADY-NEW"
    assert r["summary"]["storage"]["skipped_existing"] == 1


def test_partial_failure_does_not_raise_and_retries_only_the_rest(legacy, monkeypatch):
    _old_storage, _, new_root = legacy
    real_copy = migrate.shutil.copy2

    def flaky(src, dst, *a, **k):
        if str(src).endswith("audit_logs.jsonl"):
            raise PermissionError("잠김")
        return real_copy(src, dst, *a, **k)

    monkeypatch.setattr(migrate.shutil, "copy2", flaky)
    r = migrate.migrate_legacy_data()  # 예외 없이 끝나야 한다
    assert r["status"] == "partial" and r["errors"]
    marker = json.loads((new_root / migrate.MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["complete"] is False and marker["attempts"] == 1
    assert (new_root / "storage" / "users.db").is_file() and not (new_root / "storage" / "audit_logs.jsonl").exists()
    monkeypatch.setattr(migrate.shutil, "copy2", real_copy)  # 문제 해소 → 남은 것만 복사
    r2 = migrate.migrate_legacy_data()
    assert r2["status"] == "complete" and (new_root / "storage" / "audit_logs.jsonl").is_file()


def test_gives_up_after_max_attempts(legacy, monkeypatch):
    monkeypatch.setattr(migrate.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("디스크 오류")))
    for _ in range(migrate.MAX_ATTEMPTS):
        assert migrate.migrate_legacy_data()["status"] == "partial"
    assert migrate.migrate_legacy_data()["status"] == "gave_up"


def test_unexpected_error_is_swallowed(legacy, monkeypatch):
    monkeypatch.setattr(migrate, "_migrate", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert migrate.migrate_legacy_data()["status"] == "error"  # 시작을 막지 않는다


def test_skipped_without_override_or_when_not_bundled(legacy, monkeypatch):
    monkeypatch.delenv("HAEHAN_MIGRATE_LEGACY")
    assert migrate.migrate_legacy_data()["status"] == "skipped"  # 번들(frozen) 실행이 아니면 자동 이행 안 함
    monkeypatch.setenv("HAEHAN_MIGRATE_LEGACY", "1")
    monkeypatch.delenv("HAEHAN_DATA_ROOT")
    assert migrate.migrate_legacy_data()["status"] == "skipped"  # 저장소 실행 — 기존 위치 그대로


def test_frozen_bundle_migrates_without_flag(legacy, monkeypatch):
    monkeypatch.delenv("HAEHAN_MIGRATE_LEGACY")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert migrate.migrate_legacy_data()["status"] == "complete"


def test_same_location_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("HAEHAN_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("HAEHAN_MIGRATE_LEGACY", "1")
    monkeypatch.setattr(migrate, "default_storage_dir", lambda: tmp_path / "storage")
    monkeypatch.setattr(migrate, "default_data_dir", lambda: tmp_path / "data")
    assert migrate.migrate_legacy_data()["status"] == "skipped"
