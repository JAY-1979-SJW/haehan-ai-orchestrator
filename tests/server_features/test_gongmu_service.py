"""공무 업무판 저장소·서비스·예약 액션·라우터 인증 — 임시 DB 만 사용(실제 데이터·외부 접속 없음)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_mail import draft_policy as draft_policy
from ai_orchestrator.gongmu import gongmu_service as service
from ai_orchestrator.gongmu import gongmu_store as store
from ai_orchestrator.gongmu.gongmu_router import gongmu_router
from ai_orchestrator.server import mcp_server
from ai_orchestrator.services import scheduled_job_actions as actions
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

TODAY = date(2026, 10, 2)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "gongmu.db")
    monkeypatch.setattr(service, "today_kst", lambda: TODAY)
    monkeypatch.setattr(draft_policy, "allowed_attachment_dirs", lambda *_a, **_k: [tmp_path])
    return tmp_path


def _site(**over):
    base = {"name": "가상 현장 A", "role": "원도급", "contract_amount": "150,000,000", "start_date": "2026-09-01"}
    return {**base, **over}


def test_create_site_generates_tasks_and_is_idempotent(env):
    result = service.create_site(_site(), actor="t")
    site_id = result["site"]["id"]
    codes = sorted(t["catalog_code"] for t in service.list_tasks(site_id))
    assert {"L2", "P1", "L4", "P8", "P5", "P4", "P6", "P9", "L3"} == set(codes)
    again = service.generate_for_site(site_id, actor="t")
    assert again["created"] == 0  # 두 번 불러도 중복 생성 없음
    assert len(service.list_tasks(site_id)) == len(codes)


def test_catalog_seeded_without_g2b_and_user_edit_survives(env):
    codes = {c["code"] for c in service.list_catalog()}
    assert len(codes) == 12 and "P7" not in codes
    with sqlite3.connect(store._DB_PATH) as con:
        con.execute("UPDATE task_catalog SET name='내가 고친 이름' WHERE code='P1'")
    assert {c["code"]: c["name"] for c in service.list_catalog()}["P1"] == "내가 고친 이름"  # 시드가 덮어쓰지 않는다


def test_contract_creates_l1_l2_and_change_regenerates_l2(env):
    site_id = service.create_site(_site(contract_amount=None), actor="t")["site"]["id"]
    out = service.create_contract(
        site_id,
        {"kind": "하도급", "counterparty": "가상 협력사", "amount": "50000000", "contract_date": "2026-09-10"},
        actor="t",
    )
    contract_id = out["contract"]["id"]
    codes = [t["catalog_code"] for t in service.list_tasks(site_id)]
    assert codes.count("L1") == 1 and codes.count("L2") == 1 and codes.count("P3") == 1
    service.add_contract_change(
        contract_id, {"date": "2026-09-25", "amount": "60000000", "memo": "물량 증가"}, actor="t"
    )
    codes = [t["catalog_code"] for t in service.list_tasks(site_id)]
    assert codes.count("L2") == 2 and codes.count("L1") == 1
    assert store.get_contract(contract_id)["amount"] == 60_000_000
    assert len(store.get_contract(contract_id)["changes"]) == 1


def test_contract_change_history_is_append_only(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    cid = service.create_contract(site_id, {"kind": "하도급", "amount": "50000000"}, actor="t")["contract"]["id"]
    service.add_contract_change(cid, {"date": "2026-09-20", "amount": "51000000"}, actor="t")
    service.add_contract_change(cid, {"date": "2026-09-21", "amount": "52000000"}, actor="t")
    changes = store.get_contract(cid)["changes"]
    assert [c["amount"] for c in changes] == [51_000_000, 52_000_000]


def test_validation_rejects_bad_input(env):
    with pytest.raises(ValueError):
        service.create_site(_site(name=""), actor="t")
    with pytest.raises(ValueError):
        service.create_site(_site(role="기타"), actor="t")
    with pytest.raises(ValueError):
        service.create_site(_site(start_date="2026-10-10", end_date="2026-10-01"), actor="t")
    with pytest.raises(ValueError):
        service.create_site(_site(contract_amount="-1"), actor="t")
    with pytest.raises(ValueError):
        service.create_contract("0" * 32, {"kind": "하도급"}, actor="t")
    assert store.list_sites() == []  # 거부된 입력은 아무것도 저장하지 않는다


def test_status_change_and_event_log(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    task = service.list_tasks(site_id)[0]
    done = service.set_status(task["id"], "done", actor="kim")
    assert done["status"] == "done" and done["completed_at"] and done["grade"] == "closed"
    with pytest.raises(ValueError):
        service.set_status(task["id"], "bogus", actor="kim")
    actions_logged = [e["action"] for e in service.list_events()]
    assert "task.status" in actions_logged and "site.create" in actions_logged
    assert any(e["actor"] == "kim" for e in service.list_events())


def test_unknown_due_is_flagged_not_guessed(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    l4 = next(t for t in service.list_tasks(site_id) if t["catalog_code"] == "L4")
    assert l4["due_date"] is None and l4["grade"] == "unknown"
    updated = service.update_task(l4["id"], {"due_date": "2026-10-05", "assignee": "이대리"}, actor="t")
    assert updated["grade"] == "soon" and updated["assignee"] == "이대리"


def test_summary_and_notice_text(env):
    site_id = service.create_site(_site(start_date="2026-09-01"), actor="t")["site"]["id"]
    store.update_task(
        next(t for t in service.list_tasks(site_id) if t["catalog_code"] == "P4")["id"],
        {"due_date": "2026-10-01"},
        actor="t",
    )
    data = service.summary()
    assert data["counts"]["overdue"] >= 1 and data["counts"]["unknown"] >= 1
    text = service.notice_text()
    assert "지연" in text and "가상 현장 A" in text


def test_doc_checklist_and_path_validation(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    task = next(t for t in service.list_tasks(site_id) if t["catalog_code"] == "P1")
    detail = service.get_task(task["id"])
    assert set(detail["missing_docs"]) == {"착공신고서", "인허가 서류"}
    good = env / "착공신고서.pdf"
    good.write_bytes(b"%PDF-1.4 test")
    after = service.set_doc(task["id"], "착공신고서", ready=False, path=str(good), actor="t")
    row = next(d for d in after["docs_checklist"] if d["doc_name"] == "착공신고서")
    assert row["ready"] and len(row["sha256"]) == 64 and after["missing_docs"] == ["인허가 서류"]
    with pytest.raises(ValueError):
        service.set_doc(
            task["id"], "인허가 서류", ready=True, path=str(env.parent / "밖.pdf"), actor="t"
        )  # 허용 폴더 밖


def test_import_sites_rejects_whole_file_on_bad_row(env):
    bad = env / "sites_bad.csv"
    bad.write_text(
        "현장명,지위,도급금액,착공일\nA현장,원도급,1억,2026-09-01\nB현장,하도급,50000000,2026-09-01\n", encoding="utf-8"
    )
    result = service.import_sites(str(bad), actor="t")
    assert result["imported"] == 0 and result["errors"][0]["line"] == 2
    assert store.list_sites() == []  # 하나라도 잘못되면 아무것도 넣지 않는다


def test_import_sites_and_contracts_and_duplicate_skip(env):
    sites = env / "sites.csv"
    sites.write_text(
        "현장명,발주처,지위,도급금액,착공일\n가상 B현장,가상 발주처,원도급,120000000,2026-09-01\n가상 C현장,가상 발주처,하도급,30000000,2026-09-15\n",
        encoding="utf-8",
    )
    first = service.import_sites(str(sites), actor="t")
    assert first["imported"] == 2 and not first["errors"]
    assert service.import_sites(str(sites), actor="t")["skipped_existing"] == 2  # 다시 가져와도 중복 없음
    contracts = env / "contracts.csv"
    contracts.write_text(
        "현장명,상대업체,구분,계약금액,계약일\n가상 B현장,가상 협력사,하도급,45000000,2026-09-20\n", encoding="utf-8"
    )
    assert service.import_contracts(str(contracts), actor="t") == {"imported": 1, "errors": []}
    unknown = env / "contracts_bad.csv"
    unknown.write_text("현장명,구분,계약금액\n없는현장,하도급,1\n", encoding="utf-8")
    assert service.import_contracts(str(unknown), actor="t")["errors"][0]["line"] == 2


def test_import_rejects_path_outside_allowed_dirs(env):
    with pytest.raises(ValueError):
        service.import_sites(str(env.parent / "x.csv"), actor="t")


def test_update_settings_changes_rules_and_regenerates(env):
    site_id = service.create_site(_site(contract_amount="60,000,000"), actor="t")["site"]["id"]
    assert "L2" not in [t["catalog_code"] for t in service.list_tasks(site_id)]
    out = service.update_settings({"prime_notice_min": 50_000_000}, actor="t")
    assert out["settings"]["prime_notice_min"] == 50_000_000
    assert "L2" in [t["catalog_code"] for t in service.list_tasks(site_id)]
    with pytest.raises(ValueError):
        service.update_settings({"nope": 1}, actor="t")


def test_schema_version_set(env):
    store.list_sites()
    with sqlite3.connect(store._DB_PATH) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2


def test_scheduled_action_is_readonly_summary_and_registered(env):
    service.create_site(_site(), actor="t")
    spec = actions.get_action("gongmu_due_notice")
    assert spec is not None and spec.risk_action == "read_page" and not spec.needs_browser
    assert spec.validate({}) == {}
    with pytest.raises(ValueError):
        spec.validate({"x": 1})
    assert "공무 업무 알림" in spec.run({})


def test_ai_registry_is_read_and_draft_only():
    """AI 허용 gongmu API 는 읽기 3개 + 초안 생성뿐 — 상태 변경·서류·확정·취소·가져오기는 없다."""
    entries = {k: (v["method"], v["path"]) for k, v in mcp_server.API_REGISTRY.items() if "gongmu" in v["path"]}
    assert entries == {
        "gongmu.sites": ("GET", "/api/v1/gongmu/sites"),
        "gongmu.tasks": ("GET", "/api/v1/gongmu/tasks"),
        "gongmu.task": ("GET", "/api/v1/gongmu/tasks/{task_id}"),
        "gongmu.draft": ("POST", "/api/v1/gongmu/drafts"),
    }


def test_router_requires_auth_and_works_for_admin(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)  # 로컬 기본값(꺼짐)은 모든 요청을 owner 로 본다
    app = FastAPI()
    app.include_router(gongmu_router)
    client = TestClient(app)
    assert client.get("/gongmu/summary").status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v"}
    assert client.get("/gongmu/summary").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    created = client.post(
        "/gongmu/sites",
        json={"name": "가상 현장 R", "role": "원도급", "contract_amount": 100000000, "start_date": "2026-09-01"},
    )
    assert created.status_code == 200
    site_id = created.json()["site"]["id"]
    assert client.get("/gongmu/tasks", params={"site_id": site_id}).json()["items"]
    assert client.post("/gongmu/sites", json={"name": "", "role": "원도급"}).status_code == 400
    assert client.get("/gongmu/sites/" + "0" * 32).status_code == 404
    assert client.get("/gongmu/sites/not-an-id").status_code == 422


def test_router_path_ids_work_for_every_param_name(env):
    """site_id·task_id·contract_id 경로가 모두 동작해야 한다(공유 Path 객체 결함 재발 방지)."""
    app = FastAPI()
    app.include_router(gongmu_router)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    client = TestClient(app)
    site_id = client.post(
        "/gongmu/sites", json={"name": "가상 현장 P", "role": "원도급", "start_date": "2026-09-01"}
    ).json()["site"]["id"]
    contract = client.post(
        f"/gongmu/sites/{site_id}/contracts", json={"kind": "하도급", "amount": 50000000, "contract_date": "2026-09-10"}
    ).json()["contract"]
    changed = client.post(
        f"/gongmu/contracts/{contract['id']}/changes", json={"date": "2026-09-20", "amount": "55000000"}
    )
    assert changed.status_code == 200 and changed.json()["contract"]["amount"] == 55_000_000
    task_id = client.get("/gongmu/tasks", params={"site_id": site_id}).json()["items"][0]["id"]
    assert client.get(f"/gongmu/tasks/{task_id}").status_code == 200
    assert client.post(f"/gongmu/tasks/{task_id}/status", json={"status": "doing"}).json()["status"] == "doing"
    assert client.patch(f"/gongmu/tasks/{task_id}", json={"assignee": "이대리"}).json()["assignee"] == "이대리"
    assert client.post(f"/gongmu/tasks/{task_id}/docs", json={"doc_name": "서류", "ready": True}).status_code == 200
    assert client.post(f"/gongmu/sites/{site_id}/generate").status_code == 200
    assert client.patch(f"/gongmu/sites/{site_id}", json={"memo": "수정"}).json()["site"]["memo"] == "수정"


def test_concurrent_first_access_does_not_break_seed(env):
    """새 DB 에 여러 요청이 동시에 처음 접속해도 기준표 시드가 충돌하지 않는다(화면이 요청을 동시에 보냄)."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: len(service.list_catalog()), range(16)))
    assert set(results) == {12}


def test_draft_create_confirm_appends_task_memo_once(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    task_id = service.list_tasks(site_id)[0]["id"]
    d = service.create_draft(
        {"kind": "missing_docs", "body": "서류 3건 누락", "site_id": site_id, "task_id": task_id}, actor="ai"
    )
    assert d["status"] == "pending" and d["title"] == "서류 누락 요약"
    assert service.get_task(task_id)["memo"] == ""  # 만들기만으로는 업무가 바뀌지 않는다
    done = service.confirm_draft(d["id"], actor="kim")
    assert done["status"] == "confirmed" and done["decided_by"] == "kim"
    assert "서류 3건 누락" in service.get_task(task_id)["memo"]
    with pytest.raises(ValueError, match="이미 처리"):
        service.confirm_draft(d["id"], actor="kim")  # 두 번 확정해도 메모가 두 번 붙지 않는다
    with pytest.raises(ValueError, match="이미 처리"):
        service.cancel_draft(d["id"], actor="kim")
    assert service.get_task(task_id)["memo"].count("서류 3건 누락") == 1


def test_draft_cancel_leaves_task_untouched_and_validates(env):
    site_id = service.create_site(_site(), actor="t")["site"]["id"]
    task_id = service.list_tasks(site_id)[0]["id"]
    d = service.create_draft({"kind": "hq_report", "body": "보고", "task_id": task_id}, actor="ai")
    assert service.cancel_draft(d["id"], actor="kim")["status"] == "cancelled"
    assert service.get_task(task_id)["memo"] == ""
    assert [x["id"] for x in service.list_drafts("cancelled")] == [d["id"]] and not service.list_drafts("pending")
    for bad in ({"kind": "x", "body": "a"}, {"kind": "hq_report", "body": " "}, {"kind": "hq_report", "body": "a", "task_id": "0" * 32}):
        with pytest.raises(ValueError):
            service.create_draft(bad, actor="ai")
    with pytest.raises(ValueError, match="찾을 수 없"):
        service.confirm_draft("0" * 32, actor="kim")


def test_draft_router_flow(env):
    app = FastAPI()
    app.include_router(gongmu_router)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    client = TestClient(app)
    d = client.post("/gongmu/drafts", json={"kind": "safety_checklist", "body": "점검표"}).json()
    assert client.get("/gongmu/drafts", params={"status": "pending"}).json()["items"][0]["id"] == d["id"]
    assert client.get(f"/gongmu/drafts/{d['id']}").json()["status"] == "pending"
    assert client.post(f"/gongmu/drafts/{d['id']}/confirm").json()["status"] == "confirmed"
    assert client.post(f"/gongmu/drafts/{d['id']}/cancel").status_code == 400
    assert client.post("/gongmu/drafts", json={"kind": "nope", "body": "a"}).status_code == 400
    assert client.get("/gongmu/drafts", params={"status": "zzz"}).status_code == 400
