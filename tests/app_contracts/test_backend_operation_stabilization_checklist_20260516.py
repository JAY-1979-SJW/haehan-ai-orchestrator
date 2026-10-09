"""백엔드 운영 안정화 체크리스트 테스트.

ASSISTANT_BACKEND_OPERATION_MONITORING_AND_INCIDENT_RUNBOOK_NO_FRONTEND_01
프론트엔드 제외 원칙 준수 확인 포함.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "audits" / "backend" / "audit_backend_operation_stabilization.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_op_stab", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_json() -> dict:
    # 스크립트가 한글이 섞인 JSON을 print 한다 — Windows 콘솔 기본 코드페이지(cp949)로는
    # 인코딩 못 하는 문자(em dash 등)가 있어 UnicodeEncodeError 로 죽어 stdout 이 빈다.
    # 자식 프로세스 stdio 를 utf-8 로 강제한다.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        encoding="utf-8",
        env=env,
    )
    return json.loads(result.stdout)


# ── 스크립트 존재 ─────────────────────────────────────────────────────────────


def test_script_exists():
    assert SCRIPT.exists(), f"감사 스크립트 없음: {SCRIPT}"


def test_script_is_python():
    assert SCRIPT.suffix == ".py"


# ── frontend_excluded ─────────────────────────────────────────────────────────


def test_frontend_excluded_true():
    report = _run_json()
    assert report["frontend_excluded"] is True


def test_read_only_true():
    report = _run_json()
    assert report["read_only"] is True


def test_admin_web_not_in_smoke_commands():
    report = _run_json()
    for cmd in report["smoke_commands"]:
        assert "admin-web" not in cmd["path"], f"smoke에 admin-web 포함: {cmd['path']}"
        assert "admin_web" not in cmd["path"]


# ── health / smoke ────────────────────────────────────────────────────────────


def test_health_commands_exist():
    report = _run_json()
    assert len(report["health_commands"]) >= 4


def test_api_health_command_present():
    report = _run_json()
    health_labels = [c["label"] for c in report["health_commands"]]
    assert any("health" in lbl.lower() for lbl in health_labels)


def test_smoke_commands_at_least_8():
    report = _run_json()
    assert len(report["smoke_commands"]) >= 8


def test_smoke_host_header_required():
    report = _run_json()
    base_cmd = report["smoke_base_cmd_template"]
    assert "haehan-ai.kr" in base_cmd, "smoke 명령에 Host: haehan-ai.kr 없음"


def test_smoke_all_get_expected_200():
    report = _run_json()
    for cmd in report["smoke_commands"]:
        assert cmd["expected"] == 200, f"{cmd['path']} expected != 200"


def test_p0_smoke_exists():
    report = _run_json()
    p0 = [c for c in report["smoke_commands"] if c["tier"] == "P0"]
    assert len(p0) >= 2, "P0 smoke 항목 2개 이상 필요"


# ── nginx routing ─────────────────────────────────────────────────────────────


def test_nginx_routing_api_to_8400():
    report = _run_json()
    api_routes = [r for r in report["nginx_routing"] if "/orchestrator/api/" in r["location"]]
    assert any("8400" in r["backend"] for r in api_routes), "/orchestrator/api/ → 8400 기준 없음"


def test_nginx_routing_legacy_5050():
    report = _run_json()
    legacy = [r for r in report["nginx_routing"] if r["location"] == "/orchestrator/"]
    assert len(legacy) == 1
    assert "5050" in legacy[0]["backend"], "/orchestrator/ → 5050 기준 없음"


def test_nginx_host_header_note_exists():
    report = _run_json()
    assert "haehan-ai.kr" in report["host_header_required"]
    assert len(report["host_header_note"]) > 10


def test_5050_not_shutdown_condition():
    mod = _load_module()
    for r in mod.NGINX_ROUTING:
        if r["location"] == "/orchestrator/":
            assert "중단 금지" in r["note"], "5050 중단 금지 조건 없음"
            break
    else:
        pytest.fail("/orchestrator/ routing 기준 없음")


# ── rollback ──────────────────────────────────────────────────────────────────


def test_rollback_conditions_exist():
    report = _run_json()
    assert len(report["rollback_conditions"]) >= 3


def test_rollback_includes_health_failure():
    report = _run_json()
    conds = " ".join(report["rollback_conditions"]).lower()
    assert "health" in conds or "api" in conds


# ── external app hold ────────────────────────────────────────────────────────


def test_external_app_hold_all_no_auto_execute():
    report = _run_json()
    for item in report["external_app_hold"]:
        assert item["auto_execute"] is False, f"{item['app']} auto_execute=True"


def test_external_app_hold_cad_exists():
    report = _run_json()
    apps = [item["app"] for item in report["external_app_hold"]]
    assert "CAD" in apps


def test_external_app_hold_note_exists():
    report = _run_json()
    assert len(report["external_app_hold_note"]) > 10


# ── secret 출력 금지 ──────────────────────────────────────────────────────────


def test_secret_output_forbidden_exists():
    report = _run_json()
    assert report["secret_output_forbidden"] is True
    forbidden = " ".join(report["log_forbidden_output"]).lower()
    assert "secret" in forbidden or "token" in forbidden or "password" in forbidden


# ── verdict ───────────────────────────────────────────────────────────────────


def test_script_returns_pass_verdict():
    report = _run_json()
    assert report["verdict"] == "PASS"


def test_checklist_all_pass():
    report = _run_json()
    failed = [c for c in report["checklist"] if not c["ok"]]
    assert report['checklist'], "report['checklist'] 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert not failed, f"체크리스트 실패 항목: {failed}"


# ── read-only (파일 쓰기 없음) ────────────────────────────────────────────────


def test_script_does_not_write_files(tmp_path, monkeypatch):
    written = []
    original_write = Path.write_text

    def fake_write(self, *args, **kwargs):
        written.append(str(self))
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fake_write)

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        encoding="utf-8",
        env=env,
    )
    assert not written, f"스크립트가 파일을 씀: {written}"
