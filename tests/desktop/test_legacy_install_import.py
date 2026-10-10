"""예전 설치 폴더 데이터 가져오기(paths/legacy_import.py) — 복사만·덮어쓰기 없음·원본 보존·1회 표식·재시도·예전 앱 실행 중 건너뜀."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

from ai_orchestrator.auth import user_db
from ai_orchestrator.paths import legacy_import

_ENV_CLEAN = (
    "HAEHAN_DATA_ROOT",
    "HAEHAN_DATA_DIR",
    "HAEHAN_STORAGE_DIR",
    "LOG_DIR",
    "HAEHAN_LEGACY_INSTALL_DIRS",
    "HAEHAN_PORT",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for k in _ENV_CLEAN:
        monkeypatch.delenv(k, raising=False)
    install = tmp_path / "old" / "Haehan AI"
    old_storage = install / "resources" / "server" / "haehan-server" / "_internal" / "ai_orchestrator" / "storage"
    old_storage.mkdir(parents=True)
    root = tmp_path / "userData"
    monkeypatch.setenv("HAEHAN_DATA_ROOT", str(root))
    monkeypatch.setenv("HAEHAN_MIGRATE_LEGACY", "1")
    monkeypatch.setenv("HAEHAN_LEGACY_INSTALL_DIRS", str(install))
    monkeypatch.setenv("HAEHAN_PORT", str(_free_port()))  # 예전 앱이 떠 있지 않은 상태(포트 비어 있음)
    return {"install": install, "old_storage": old_storage, "root": root, "new_storage": root / "storage"}


def _make_old_owner(monkeypatch, old_storage: Path) -> dict:
    """예전 앱의 users.db 에 활성 owner 한 명을 만든다."""
    monkeypatch.setattr(user_db, "_get_db_path", lambda: old_storage / "users.db")
    user = user_db.create_user("old-owner@example.com", "예전 소유자", "pw-demo-secret-1")
    with user_db._conn() as con:
        con.execute("UPDATE users SET role='owner', enabled=1 WHERE id=?", (user["id"],))
        con.commit()
    return user


def _populate(old_storage: Path) -> None:
    (old_storage / "audit_logs.jsonl").write_text('{"old": 1}\n', encoding="utf-8")
    (old_storage / "secrets").mkdir(exist_ok=True)
    (old_storage / "secrets" / "tok.json").write_text("{}", encoding="utf-8")
    (old_storage / "__pycache__").mkdir(exist_ok=True)
    (old_storage / "__pycache__" / "x.pyc").write_bytes(b"x")


def test_imports_old_data_and_old_owner_becomes_auto_login_target(env, monkeypatch):
    user = _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    r = legacy_import.import_legacy_install()
    assert r["status"] == "complete" and r["source"] == str(env["install"])
    ns = env["new_storage"]
    assert (ns / "users.db").is_file() and (ns / "audit_logs.jsonl").read_text(encoding="utf-8") == '{"old": 1}\n'
    assert (ns / "secrets" / "tok.json").is_file() and not (ns / "__pycache__").exists()
    # 가져온 DB 로 자동 로그인 대상(활성 owner)이 존재한다 — B안 desktop-session 이 설정 화면 없이 이 계정을 쓴다
    monkeypatch.setattr(user_db, "_get_db_path", lambda: ns / "users.db")
    owner = user_db.select_desktop_owner()
    assert owner is not None and owner["id"] == user["id"]
    marker = json.loads((env["root"] / legacy_import.MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["complete"] is True and marker["source"] == str(env["install"])
    assert not list(env["root"].glob("*.tmp"))  # 원자적 표식(tmp+rename) — 임시 파일이 남지 않는다


def test_original_files_are_preserved(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    before = {p.name: p.read_bytes() for p in env["old_storage"].rglob("*") if p.is_file()}
    legacy_import.import_legacy_install()
    after = {p.name: p.read_bytes() for p in env["old_storage"].rglob("*") if p.is_file()}
    assert before == after  # 예전 폴더는 그대로(이동 아님)


def test_not_done_when_new_location_already_has_users_db(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    env["new_storage"].mkdir(parents=True)
    (env["new_storage"] / "users.db").write_bytes(b"NEW-REGISTERED")
    r = legacy_import.import_legacy_install()
    assert r["status"] == "skipped" and "users.db" in r["reason"]
    assert (env["new_storage"] / "users.db").read_bytes() == b"NEW-REGISTERED"
    assert not (env["new_storage"] / "audit_logs.jsonl").exists()  # 아무것도 복사하지 않는다
    assert not (env["root"] / legacy_import.MARKER_NAME).exists()


def test_never_overwrites_existing_files(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    env["new_storage"].mkdir(parents=True)
    (env["new_storage"] / "audit_logs.jsonl").write_text(
        '{"new": 1}\n', encoding="utf-8"
    )  # 새 앱이 이미 쓴 기록(users.db 는 아직 없음)
    r = legacy_import.import_legacy_install()
    assert r["status"] == "complete"
    assert (env["new_storage"] / "audit_logs.jsonl").read_text(encoding="utf-8") == '{"new": 1}\n'  # 덮어쓰지 않음
    assert r["summary"]["storage"]["skipped_existing"] == 1
    assert (env["new_storage"] / "users.db").is_file()


def test_second_run_does_not_copy_again(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    assert legacy_import.import_legacy_install()["status"] == "complete"
    (env["new_storage"] / "audit_logs.jsonl").write_text("CHANGED-AFTER", encoding="utf-8")
    (env["new_storage"] / "secrets" / "tok.json").unlink()  # 사용자가 지운 파일이 되살아나면 안 된다
    (env["old_storage"] / "extra_new_old_file.json").write_text("{}", encoding="utf-8")
    again = legacy_import.import_legacy_install()
    assert again["status"] == "already_done"
    assert (env["new_storage"] / "audit_logs.jsonl").read_text(encoding="utf-8") == "CHANGED-AFTER"
    assert not (env["new_storage"] / "secrets" / "tok.json").exists()
    assert not (env["new_storage"] / "extra_new_old_file.json").exists()


def test_partial_failure_leaves_no_marker_and_retries_next_run(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    real_copy = legacy_import._copy_file.__globals__["shutil"].copy2

    def flaky(src, dst, *a, **k):
        if str(src).endswith("audit_logs.jsonl"):
            raise PermissionError("잠김")
        return real_copy(src, dst, *a, **k)

    monkeypatch.setattr(legacy_import._copy_file.__globals__["shutil"], "copy2", flaky)
    r = legacy_import.import_legacy_install()
    assert r["status"] == "partial" and r["errors"]
    assert not (env["root"] / legacy_import.MARKER_NAME).exists()  # 표식 없음
    assert not (
        env["new_storage"] / "users.db"
    ).exists()  # 계정 DB 는 맨 마지막이라 복사되지 않음 → '새 위치에 users.db 없음' 유지
    assert (
        env["new_storage"] / "secrets" / "tok.json"
    ).is_file()  # 성공한 파일은 남아도 된다(덮어쓰기 없는 재시도라 안전)
    monkeypatch.setattr(legacy_import._copy_file.__globals__["shutil"], "copy2", real_copy)  # 원인 해소
    r2 = legacy_import.import_legacy_install()  # 다음 실행: 재시도
    assert r2["status"] == "complete"
    assert (env["new_storage"] / "users.db").is_file() and (env["new_storage"] / "audit_logs.jsonl").is_file()
    assert (env["root"] / legacy_import.MARKER_NAME).is_file()


def test_skipped_with_guidance_when_legacy_app_is_running(env, monkeypatch, capsys):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    port = int(__import__("os").environ["HAEHAN_PORT"])
    with socket.socket() as srv:  # 예전 앱 서버가 8401(여기선 임의 포트)을 쓰고 있는 상황
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
        r = legacy_import.import_legacy_install()
    assert r["status"] == "skipped" and r["reason"] == "legacy_app_running"
    assert not env["new_storage"].exists() or not any(env["new_storage"].iterdir())  # 아무것도 복사 안 함
    assert not (env["root"] / legacy_import.MARKER_NAME).exists()
    assert "예전 앱이 실행 중" in capsys.readouterr().err  # 안내 로그
    assert legacy_import.import_legacy_install()["status"] == "complete"  # 예전 앱 종료 후 다음 실행에서 가져옴


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 파일 공유 잠금")
def test_skipped_when_a_legacy_file_is_held_open_for_writing(env, monkeypatch, capsys):
    _make_old_owner(monkeypatch, env["old_storage"])
    _populate(env["old_storage"])
    with (env["old_storage"] / "audit_logs.jsonl").open(
        "a", encoding="utf-8"
    ):  # 쓰기로 열어 둔 파일(예전 앱이 기록 중)
        r = legacy_import.import_legacy_install()
    assert r["status"] == "skipped" and r["reason"] == "legacy_files_locked"
    assert not (env["root"] / legacy_import.MARKER_NAME).exists()
    assert "파일을 쓰는 중" in capsys.readouterr().err


def test_no_legacy_install_found_is_a_quiet_skip(env):
    legacy_import.import_legacy_install()  # 폴더는 있지만 비어 있음
    r = legacy_import.import_legacy_install()
    assert r["status"] == "skipped" and "찾지 못함" in r["reason"]
    assert not (env["root"] / legacy_import.MARKER_NAME).exists()


def test_skipped_outside_bundle_and_without_data_root(env, monkeypatch):
    _make_old_owner(monkeypatch, env["old_storage"])
    monkeypatch.delenv("HAEHAN_MIGRATE_LEGACY")
    assert legacy_import.import_legacy_install()["status"] == "skipped"  # 번들 실행이 아님
    monkeypatch.setenv("HAEHAN_MIGRATE_LEGACY", "1")
    monkeypatch.delenv("HAEHAN_DATA_ROOT")
    assert legacy_import.import_legacy_install()["status"] == "skipped"  # 저장소 실행


def test_default_candidates_are_the_known_install_locations(monkeypatch, tmp_path):
    monkeypatch.delenv("HAEHAN_LEGACY_INSTALL_DIRS", raising=False)
    profile = tmp_path / "kim"
    local = profile / "AppData" / "Local"
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert legacy_import.default_candidates() == [profile / "Haehan AI", local / "Programs" / "Haehan AI"]


def test_first_candidate_with_data_wins(env, monkeypatch, tmp_path):
    empty = tmp_path / "old" / "Other"
    empty.mkdir(parents=True)
    monkeypatch.setenv(
        "HAEHAN_LEGACY_INSTALL_DIRS",
        str(empty) + ";" + str(env["install"]) if sys.platform == "win32" else f"{empty}:{env['install']}",
    )
    _make_old_owner(monkeypatch, env["old_storage"])
    r = legacy_import.import_legacy_install()
    assert r["status"] == "complete" and r["source"] == str(env["install"])
