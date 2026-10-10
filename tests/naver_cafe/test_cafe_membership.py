"""가입 카페 변동(신규 가입·탈퇴) 반영·분석 — 순수 규칙·이력 저장소·업무 흐름·라우터. 가짜 수집기만 쓴다(실제 브라우저·네이버 접속 없음).

기준서: docs/specs/2026-10-05_cafe_membership_changes.md
2026-10-05 드라이 런: 로그인이 풀리면 목록 API 가 200 + 빈 목록을 준다 → 그 결과로 비교하면 전부 "탈퇴"로 오판된다.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_cafe import membership_diff as diff
from ai_orchestrator.connectors.naver_cafe import membership_service as service
from ai_orchestrator.connectors.naver_cafe import membership_store as store
from ai_orchestrator.connectors.naver_cafe import naver_cafe_router as router_module
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user


def cafe(i: int, name: str | None = None) -> dict:
    return {
        "cafe_id": f"cafe{i}",
        "cafe_name": name or f"카페{i}",
        "clubid": str(1000 + i),
        "href": f"https://cafe.naver.com/cafe{i}",
        "member_count": 0,
    }


def cafes(*ids: int) -> list[dict]:
    return [cafe(i) for i in ids]


# ── 순수 규칙 ─────────────────────────────────────────────────


def test_first_collection_is_a_baseline_without_new_or_left():
    r = diff.compute_changes(None, cafes(1, 2, 3), source="api")
    assert r["status"] == diff.STATUS_BASELINE and r["baseline"] is True and r["persist"] is True
    assert r["new"] == [] and r["left"] == [] and r["total"] == 3


def test_new_left_and_renamed_are_detected_by_cafe_id():
    previous = diff.snapshot_entries(cafes(1, 2, 3))
    current = [cafe(1), cafe(3, "이름 바뀜"), cafe(4)]
    r = diff.compute_changes(previous, current, source="api")
    assert r["status"] == diff.STATUS_OK and r["persist"] is True
    assert [e["cafe_id"] for e in r["new"]] == ["cafe4"] and [e["cafe_id"] for e in r["left"]] == ["cafe2"]
    assert r["renamed"] == [{"cafe_id": "cafe3", "from": "카페3", "to": "이름 바뀜"}]
    assert r["total"] == 3 and r["previous_total"] == 3


def test_unchanged_collection_has_no_changes():
    previous = diff.snapshot_entries(cafes(1, 2))
    r = diff.compute_changes(previous, cafes(1, 2), source="api")
    assert r["status"] == diff.STATUS_OK and r["new"] == r["left"] == r["renamed"] == []


@pytest.mark.parametrize("previous", [None, diff.snapshot_entries(cafes(1, 2, 3))])
def test_empty_result_is_blocked_never_treated_as_everyone_left(previous):
    r = diff.compute_changes(previous, [], source="api")
    assert r["status"] == diff.STATUS_BLOCKED and r["reason"] == "empty_result" and r["persist"] is False
    assert r["left"] == [] and "로그인" in r["warning"]  # 전부 탈퇴로 기록하지 않는다


def test_non_api_source_is_blocked_even_for_the_first_collection():
    for previous in (None, diff.snapshot_entries(cafes(1))):
        r = diff.compute_changes(previous, cafes(1, 2), source="dom")
        assert r["status"] == diff.STATUS_BLOCKED and r["reason"] == "non_api_source" and r["persist"] is False


def test_duplicate_ids_are_blocked():
    r = diff.compute_changes(diff.snapshot_entries(cafes(1)), [cafe(1), cafe(1)], source="api")
    assert r["status"] == diff.STATUS_BLOCKED and r["reason"] == "duplicate_ids"


def test_mass_drop_needs_confirmation_and_is_not_persisted_until_confirmed():
    previous = diff.snapshot_entries(cafes(1, 2, 3, 4, 5, 6))
    r = diff.compute_changes(previous, cafes(1, 2), source="api")  # 6 → 2 (절반 이상 감소)
    assert r["status"] == diff.STATUS_NEEDS_CONFIRMATION and r["reason"] == "mass_drop" and r["persist"] is False
    assert len(r["left"]) == 4  # 후보는 보여 주되 반영하지 않는다
    confirmed = diff.compute_changes(previous, cafes(1, 2), source="api", confirm_mass_change=True)
    assert confirmed["status"] == diff.STATUS_OK and confirmed["persist"] is True and len(confirmed["left"]) == 4


def test_small_previous_list_does_not_trigger_the_mass_drop_rule():
    r = diff.compute_changes(diff.snapshot_entries(cafes(1, 2)), cafes(1), source="api")  # 2 → 1: 카페 하나 탈퇴일 뿐
    assert r["status"] == diff.STATUS_OK and [e["cafe_id"] for e in r["left"]] == ["cafe2"]


def test_snapshot_entries_keep_only_id_name_clubid_and_activity_fields_and_drop_idless_items():
    raw = [
        {"cafe_id": "a", "cafe_name": "  공백   정리 ", "clubid": 7, "href": "x", "member_count": 9, "token": "SECRET", "cafeThumbnailPcUrl": "http://img", "new_articles": "12", "last_visit": "2026-10-01 09:00:00", "favorite": 1},
        {"cafe_name": "id 없음"},
    ]
    (entry,) = diff.snapshot_entries(raw)
    assert entry["cafe_id"] == "a" and entry["name"] == "공백 정리" and entry["clubid"] == "7"
    assert entry["new_articles"] == 12 and entry["last_visit"] == "2026-10-01 09:00:00" and entry["favorite"] is True and entry["dormant"] is False
    assert set(entry) == {"cafe_id", "name", "clubid", "new_articles", "last_update", "last_visit", "favorite", "manage", "dormant", "power", "open_type"}
    assert "SECRET" not in str(entry) and "img" not in str(entry)  # 정해진 필드 밖의 값(이미지 주소·토큰 등)은 저장하지 않는다
    assert diff.snapshot_entries([{"cafe_id": "z", "new_articles": "나쁨"}])[0]["new_articles"] == 0  # 숫자가 아니면 0


def test_activity_fields_do_not_create_membership_changes():
    """새 글 수가 바뀌어도 신규·탈퇴·이름 변경이 아니다 — 변동 비교는 id·이름만 본다."""
    previous = diff.snapshot_entries([{**cafe(1), "new_articles": 3}])
    r = diff.compute_changes(previous, [{**cafe(1), "new_articles": 99}], source="api")
    assert r["status"] == diff.STATUS_OK and r["new"] == r["left"] == r["renamed"] == []


# ── 이력 저장소 ───────────────────────────────────────────────


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "cafe")
    return tmp_path


def test_store_snapshot_roundtrip_retention_and_totals(env, monkeypatch):
    assert store.latest_snapshot() is None
    monkeypatch.setattr(store, "HISTORY_MAX", 3)
    for i in range(5):
        store.save_snapshot(diff.snapshot_entries(cafes(*range(i + 1))), now_iso=f"2026-10-0{i + 1}T09:00:00+09:00")
    assert len(list((env / "cafe" / "my_cafes_history").glob("*.json"))) == 3  # 오래된 것은 정리
    assert len(store.latest_snapshot() or []) == 5
    assert [t["total"] for t in store.history_totals()] == [3, 4, 5]


def test_store_changes_log_is_bounded_newest_first_and_skips_broken_lines(env, monkeypatch):
    monkeypatch.setattr(store, "CHANGES_MAX", 3)
    for i in range(5):
        store.append_change({"at": f"t{i}", "new": [], "left": []})
    (env / "cafe" / "my_cafes_changes.jsonl").open("a", encoding="utf-8").write("{깨진 줄\n")
    assert [c["at"] for c in store.recent_changes(10)] == [
        "t4",
        "t3",
        "t2",
    ]  # 3줄만 유지(오래된 것 정리) + 깨진 줄 건너뜀, 최신순


def test_store_corrupt_latest_snapshot_means_baseline_not_crash(env):
    d = env / "cafe" / "my_cafes_history"
    d.mkdir(parents=True)
    (d / "2026-10-01.json").write_text("{깨짐", encoding="utf-8")
    assert store.latest_snapshot() is None


# ── 업무 흐름 ─────────────────────────────────────────────────


def test_service_baseline_then_join_and_leave_are_recorded(env):
    first = service.apply_collection(cafes(1, 2, 3), source="api", now="2026-10-05T09:00:00+09:00")
    assert first["changes"]["status"] == "baseline" and first["persist_current"] is True
    assert first["activity"]["total"] == 3  # 반영되는 수집은 활동 분석을 함께 돌려준다
    second = service.apply_collection([cafe(1), cafe(3), cafe(4)], source="api", now="2026-10-06T09:00:00+09:00")
    ch = second["changes"]
    assert [e["cafe_id"] for e in ch["new"]] == ["cafe4"] and [e["cafe_id"] for e in ch["left"]] == ["cafe2"]
    log = store.recent_changes()
    assert len(log) == 1 and log[0]["total"] == 3 and log[0]["previous_total"] == 3
    again = service.apply_collection(
        [cafe(1), cafe(3), cafe(4)], source="api", now="2026-10-07T09:00:00+09:00"
    )  # 같은 수집 반복 = 변동 0(안정)
    assert again["changes"]["new"] == [] and again["changes"]["left"] == [] and len(store.recent_changes()) == 1


def test_service_blocked_collection_writes_nothing(env):
    service.apply_collection(cafes(1, 2), source="api", now="2026-10-05T09:00:00+09:00")
    before = store.latest_snapshot()
    for bad, source in (([], "api"), (cafes(1, 2, 3), "dom")):
        out = service.apply_collection(bad, source=source, now="2026-10-06T09:00:00+09:00")
        assert out["persist_current"] is False and out["changes"]["status"] == "blocked"
        assert out["activity"] is None  # 막힌 수집으로는 분석하지 않는다
    assert store.latest_snapshot() == before and store.recent_changes() == []  # 이력도 변동 기록도 그대로


def test_service_mass_drop_needs_confirmation_then_applies(env):
    service.apply_collection(cafes(1, 2, 3, 4, 5, 6), source="api", now="2026-10-05T09:00:00+09:00")
    held = service.apply_collection(cafes(1), source="api", now="2026-10-06T09:00:00+09:00")
    assert (
        held["changes"]["status"] == "needs_confirmation"
        and held["persist_current"] is False
        and store.recent_changes() == []
    )
    done = service.apply_collection(cafes(1), source="api", confirm_mass_change=True, now="2026-10-07T09:00:00+09:00")
    assert done["persist_current"] is True and store.recent_changes()[0]["confirmed_mass_change"] is True


def test_service_recent_summarizes_trend_and_log(env):
    service.apply_collection(cafes(1, 2), source="api", now="2026-10-05T09:00:00+09:00")
    service.apply_collection(cafes(1, 2, 3), source="api", now="2026-10-06T09:00:00+09:00")
    out = service.recent(10)
    assert (
        out["summary"]["snapshots"] == 2
        and out["summary"]["current_total"] == 3
        and out["summary"]["net_change_since_first"] == 1
    )
    assert out["summary"]["joined_in_log"] == 1 and out["summary"]["left_in_log"] == 0
    assert out["activity"]["total"] == 3  # 최근 스냅샷의 활동 분석
    assert len(service.recent(10_000)["changes"]) <= service.CHANGES_LIMIT_MAX  # 상한


# ── 라우터(가짜 수집기) ───────────────────────────────────────


@pytest.fixture
def client(env, monkeypatch):
    import scripts.browser.cdp.connection as wc
    import scripts.naver.cafe.collection.explorer as explorer

    monkeypatch.setattr(explorer, "_DATA_DIR", env / "my_cafes_dir")
    state = {"result": (cafes(1, 2, 3), "api"), "closed": 0, "new_pages": 0}

    class FakeContext:
        def new_page(self):
            state["new_pages"] += 1
            return object()

    monkeypatch.setattr(wc, "get_context", lambda: FakeContext())
    monkeypatch.setattr(wc, "close_page", lambda _page: state.__setitem__("closed", state["closed"] + 1))
    monkeypatch.setattr(wc, "run_on_browser_thread", lambda fn, timeout=0: fn())
    monkeypatch.setattr(explorer, "get_my_cafes_with_source", lambda _page: state["result"])
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", False)
    app = FastAPI()
    app.include_router(router_module.naver_cafe_router)
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim", "actor": "kim"}
    c = TestClient(app)
    c.state = state  # type: ignore[attr-defined]
    c.data_dir = env / "my_cafes_dir"  # type: ignore[attr-defined]
    return c


def test_collect_route_returns_changes_saves_list_and_closes_its_tab(client):
    out = client.post("/naver-cafe/collect-my-cafes").json()
    assert out["ok"] is True and out["count"] == 3 and out["source"] == "api" and len(out["cafes"]) == 3  # 기존 키 호환
    assert out["changes"]["status"] == "baseline" and out["activity"]["total"] == 3
    assert json.loads((client.data_dir / "my_cafes.json").read_text(encoding="utf-8"))[0]["cafe_id"] == "cafe1"
    assert client.state["closed"] == 1 and client.state["new_pages"] == 1  # 자기 탭 하나를 만들어 쓰고 닫았다(빈 탭 재사용 없음)
    client.state["result"] = ([cafe(1), cafe(3), cafe(4)], "api")
    second = client.post("/naver-cafe/collect-my-cafes").json()["changes"]
    assert [e["cafe_id"] for e in second["new"]] == ["cafe4"] and [e["cafe_id"] for e in second["left"]] == ["cafe2"]
    changes = client.get("/naver-cafe/my-cafes/changes").json()
    assert changes["summary"]["joined_in_log"] == 1 and changes["summary"]["left_in_log"] == 1


def test_collect_route_does_not_overwrite_the_saved_list_with_a_blocked_result(client):
    client.post("/naver-cafe/collect-my-cafes")
    saved = (client.data_dir / "my_cafes.json").read_text(encoding="utf-8")
    client.state["result"] = ([], "api")  # 로그인 만료로 빈 목록
    out = client.post("/naver-cafe/collect-my-cafes").json()
    assert out["changes"]["status"] == "blocked" and out["changes"]["reason"] == "empty_result"
    assert (client.data_dir / "my_cafes.json").read_text(encoding="utf-8") == saved  # 저장본 보존
    client.state["result"] = (cafes(1, 2, 3, 9), "dom")
    assert client.post("/naver-cafe/collect-my-cafes").json()["changes"]["reason"] == "non_api_source"
    assert (client.data_dir / "my_cafes.json").read_text(encoding="utf-8") == saved


def test_collect_route_mass_drop_is_held_until_confirmed(client):
    client.state["result"] = (cafes(1, 2, 3, 4, 5, 6), "api")
    client.post("/naver-cafe/collect-my-cafes")
    client.state["result"] = (cafes(1), "api")
    held = client.post("/naver-cafe/collect-my-cafes").json()["changes"]
    assert held["status"] == "needs_confirmation"
    assert len(json.loads((client.data_dir / "my_cafes.json").read_text(encoding="utf-8"))) == 6  # 아직 반영 안 됨
    ok = client.post("/naver-cafe/collect-my-cafes", params={"confirm_mass_change": "true"}).json()["changes"]
    assert ok["status"] == "ok" and len(ok["left"]) == 5
    assert len(json.loads((client.data_dir / "my_cafes.json").read_text(encoding="utf-8"))) == 1


def test_changes_route_requires_admin_or_owner(client):
    client.app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v", "actor": "v"}
    monkey = pytest.MonkeyPatch()
    monkey.setattr(auth_module.config, "AUTH_ENABLED", True)
    try:
        assert client.get("/naver-cafe/my-cafes/changes").status_code in (401, 403)
        assert client.post("/naver-cafe/collect-my-cafes").status_code in (401, 403)
    finally:
        monkey.undo()
