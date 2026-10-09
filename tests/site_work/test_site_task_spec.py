"""사이트 업무 `never`(자동 실행 불가) 분류·후보 목록·업무 명세(M12) — 순수 규칙·서비스·라우터·지도 이력 연동. 임시 폴더만 사용(실사이트·브라우저 없음).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md
사용자·창 E 요구 4건을 시험으로 고정한다:
  (1) never 는 후보 목록에 '자동 실행 불가'로 표시되고 명세·실행 계획에서 빠진다
  (2) never 에는 승인 요청도 만들 수 없다(승인으로 우회 불가)
  (3) 기존 실행 게이트와 모순 없이 never 가 우선한다(승인 후 실행되는 경로가 never 에는 열리지 않는다)
  (4) 지도 갱신으로 never 표시가 사라지면 지문이 바뀌어 map_changed 로 사람에게 되돌린다
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.site_work import site_map_history as hist
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_service as map_service
from ai_orchestrator.site_work import site_task_map_store as store
from ai_orchestrator.site_work import site_task_spec as sts
from ai_orchestrator.site_work import site_task_spec_service as spec_service
from ai_orchestrator.site_work.site_task_map_router import site_task_map_router
from scripts.site_engine.execution_gate import require_approval_for_action
from scripts.site_engine.site_types import SiteCapability
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

HOST = "spec.example-test.kr"
NOW = "2026-10-05T12:00:00+09:00"


def _field(name: str, ftype: str = "text", label: str = "") -> dict[str, Any]:
    return {"name": name, "id": "", "type": ftype, "role": "textbox", "label": label or name, "required": True}


def _task(
    task_id: str,
    *,
    risk: str = "read",
    control: str = "조회",
    fields: list[dict[str, Any]] | None = None,
    never: str = "",
    name: str = "",
) -> dict[str, Any]:
    fields = fields if fields is not None else [_field("q")]
    task: dict[str, Any] = {
        "id": task_id, "name": name or f"업무 {task_id}", "category": "search", "purpose": "", "risk": risk, "auth": "public", "state": "observed",
        "url": f"https://{HOST}/{task_id}", "host": HOST, "fields": fields, "control": control, "outputs": ["제목", "날짜"],
        "steps": tm.recorder_steps(f"https://{HOST}/{task_id}", fields, risk=risk, control=control), "fingerprint": f"fp-{task_id}",
        "observed_at": NOW, "verified_at": "", "failures": 0, "changes": [],
    }  # fmt: skip
    if never:
        task["never"] = never
    return task


def _map(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    site_map = tm.empty_map(HOST, now=NOW)
    site_map["tasks"] = tasks
    return site_map


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "site_task_map")
    return tmp_path / "site_task_map"


# ── 분류 규칙(순수) ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texts", "kind"),
    [
        (["계좌 이체하기"], sts.NEVER_PAYMENT),
        (["결제 진행"], sts.NEVER_PAYMENT),
        (["Pay now"], sts.NEVER_PAYMENT),
        (["전자서명 하기"], sts.NEVER_SIGNATURE),
        (["공동인증서 로그인"], sts.NEVER_SIGNATURE),
        (["회원 탈퇴"], sts.NEVER_DELETE),
        (["Delete account"], sts.NEVER_DELETE),
        (["도메인 연장 신청"], sts.NEVER_IRREVERSIBLE),
        (["네임서버 변경"], sts.NEVER_IRREVERSIBLE),
        (["OTP 인증번호 입력"], sts.NEVER_OTP),
    ],
)
def test_never_kind_by_text_for_non_read(texts, kind):
    assert sts.never_kind(texts, [], risk="submit") == kind


def test_never_kind_by_field_type_and_unclassified_fail_closed():
    assert sts.never_kind(["로그인"], [_field("pw", "password")], risk="submit") == sts.NEVER_CREDENTIAL
    assert sts.never_kind([], [_field("code", label="OTP 인증번호")], risk="read") == sts.NEVER_OTP
    assert sts.never_kind([], [], risk="submit") == sts.NEVER_UNCLASSIFIED  # 제출인데 판정할 근거가 전혀 없다 — 막는다
    assert (
        sts.never_kind(["문의 접수"], [_field("msg")], risk="submit") == ""
    )  # 평범한 제출은 never 가 아니다(사람 승인 대상)


def test_read_tasks_are_not_blocked_by_words_in_their_name():
    assert sts.never_kind(["결제 내역 조회", "삭제된 글 보기"], [_field("q")], risk="read") == ""


def test_never_marker_is_sticky_through_merge():
    old = _task("t1", risk="submit", control="이체", never=sts.NEVER_PAYMENT)
    new = _task("t1", risk="submit", control="이체")  # 새로 관찰했을 때 표시가 없어도
    assert sts.carry_never(old, new) == sts.NEVER_PAYMENT
    merged = tm.merge_tasks(_map([old]), [new], now=NOW)["tasks"][0]
    assert merged["never"] == sts.NEVER_PAYMENT


def test_tasks_from_snapshot_marks_never_buttons_and_leaves_normal_tasks_untouched():
    url = f"https://{HOST}/board"
    snapshot = {
        "url": url, "title": "게시판", "frames": [{"idx": 0, "url": url, "inputs": [], "forms": [], "headings": [], "links": [],
        "buttons": [{"text": "결제하기", "aria": "", "visible": True, "landmark": "main"}, {"text": "목록 보기", "aria": "", "visible": True, "landmark": "main"}]}],
    }  # fmt: skip
    by_name = {t["name"].split(" (")[0]: t for t in tm.tasks_from_snapshot(snapshot, now=NOW)}
    assert by_name["결제하기"]["never"] == sts.NEVER_PAYMENT and by_name["결제하기"]["risk"] == "submit"
    assert "never" not in by_name["목록 보기"]  # 표시가 없는 업무는 키 자체가 없다(기존 형식·지문 불변)


# ── (1) 후보 목록·명세·실행 계획에서 never 제외 ───────────────────


def test_candidates_show_never_as_not_runnable_and_count_them(env):
    store.save(
        _map(
            [
                _task("ok"),
                _task("sub", risk="submit", control="문의 접수", fields=[_field("msg")]),
                _task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT),
            ]
        )
    )
    got = spec_service.candidates(HOST)
    by_key = {i["task_key"]: i for i in got["items"]}
    assert by_key["ok"]["availability"] == "AI 가 실행 가능" and by_key["ok"]["ai_runnable"]
    assert by_key["sub"]["availability"] == "사람 승인 필요" and not by_key["sub"]["ai_runnable"]
    assert (
        by_key["pay"]["availability"] == "자동 실행 불가"
        and by_key["pay"]["never"] == "payment"
        and not by_key["pay"]["ai_runnable"]
    )
    assert got["count"] == 3 and got["ai_runnable"] == 1 and got["never"] == 1


def test_never_task_gets_no_spec_no_plan_and_map_is_untouched(env):
    store.save(_map([_task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT)]))
    before = store.load(HOST)
    with pytest.raises(ValueError, match="자동 실행 불가"):
        spec_service.create_spec(HOST, "pay")
    with pytest.raises(ValueError, match="자동 실행 불가"):
        sts.build_spec(before["tasks"][0], "submit", map_rev=1, placeholders=[])
    assert "spec" not in store.load(HOST)["tasks"][0]  # 명세가 저장되지 않았다


def test_spec_for_read_and_submit_tasks_has_no_values_and_clear_approval_points(env):
    store.save(
        _map(
            [
                _task("ok"),
                _task("sub", risk="submit", control="문의 접수", fields=[_field("msg"), _field("pw", "password")]),
            ]
        )
    )
    read = spec_service.create_spec(HOST, "ok")
    assert (
        read["spec"]["inputs"] == [{"name": "q", "type": "text", "required": True, "sensitive": False}]
        and read["plan"]["executes"] is True
    )
    assert (
        read["spec"]["map_rev"] == 1 and read["spec"]["approval_points"] == [] and read["spec"]["irreversible_at"] == ""
    )
    # 비밀번호 칸이 있는 업무는 credential never 이므로 명세 대상이 아니다 → 평범한 제출 업무로 다시 검증
    store.save(_map([_task("sub", risk="submit", control="문의 접수", fields=[_field("msg")])]))
    sub = spec_service.create_spec(HOST, "sub")
    assert sub["plan"]["executes"] is False and "누르지 않음" in sub["plan"]["final_action"]
    assert sub["spec"]["irreversible_at"] and sub["spec"]["approval_points"]
    assert "value" not in str(sub["spec"]["inputs"])  # 입력 값은 명세에 없다


def test_spec_saved_in_map_does_not_bump_map_rev_and_flags_map_changed_later(env):
    store.save(_map([_task("ok")]))
    spec_service.create_spec(HOST, "ok")
    assert store.load(HOST)["map_rev"] == 1  # 명세 저장은 구조가 아니다
    assert spec_service.get_spec(HOST, "ok")["map_changed"] is False
    grown = store.load(HOST)
    store.save(dict(grown, tasks=[*grown["tasks"], _task("new")]))  # 구조가 바뀌어 rev 2(기존 업무의 명세는 그대로)
    assert spec_service.get_spec(HOST, "ok")["map_changed"] is True  # 명세를 만든 뒤 지도가 바뀌었다
    with pytest.raises(ValueError, match="명세를 찾을 수 없"):
        spec_service.get_spec(HOST, "new")


def test_validate_spec_rejects_non_read_without_irreversible_or_approval_points():
    with pytest.raises(ValueError, match="되돌릴 수 없는 지점"):
        sts.validate_spec(
            {"task_key": "t", "inputs": [], "risk": "submit", "irreversible_at": "", "approval_points": []}
        )
    assert sts.validate_spec({"task_key": "t", "inputs": [], "risk": "read"})["task_key"] == "t"


# ── (2) 승인 요청도 만들 수 없다 ─────────────────────────────────


def test_assert_approvable_refuses_never_but_allows_normal_submit(env):
    store.save(
        _map(
            [
                _task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT),
                _task("sub", risk="submit", control="문의 접수", fields=[_field("msg")]),
            ]
        )
    )
    with pytest.raises(ValueError, match="승인 요청을 만들 수 없습니다"):
        spec_service.assert_approvable(HOST, "pay")
    spec_service.assert_approvable(HOST, "sub")  # 평범한 제출은 사람 승인 대상이므로 통과
    with pytest.raises(ValueError, match="찾을 수 없"):
        spec_service.assert_approvable(HOST, "ghost")


def test_never_marker_from_current_rules_applies_even_to_old_maps_without_stored_marker(env):
    old = _task("pay", risk="submit", control="송금하기")  # 표시 없이 저장된 옛 업무
    store.save(_map([old]))
    with pytest.raises(ValueError, match="승인 요청을 만들 수 없습니다"):
        spec_service.assert_approvable(HOST, "pay")


# ── (3) 기존 실행 게이트와 모순 없이 never 가 우선 ─────────────────


def test_run_is_refused_for_never_even_if_stored_risk_says_read():
    task = _task("odd", risk="read", control="조회", never=sts.NEVER_DELETE)  # 저장된 등급이 read 로 잘못 남은 경우에도
    with pytest.raises(ValueError, match="자동 실행 불가"):
        tm.validate_run_request(task, {"q": "x"})
    assert tm.with_effective_risk(_map([task]))["tasks"][0]["never"] == "delete"  # 응답에도 표시된다


def test_normal_submit_is_refused_by_read_only_rule_and_never_message_differs():
    with pytest.raises(ValueError, match="조회\\(read\\) 업무만"):
        tm.validate_run_request(_task("sub", risk="submit", control="문의 접수"), {"q": "x"})


def test_engine_gate_already_treats_delete_and_sign_as_approval_required_and_never_is_stricter(env):
    assert require_approval_for_action("delete item", SiteCapability.DELETE) and require_approval_for_action(
        "sign document", SiteCapability.SIGN
    )
    store.save(
        _map(
            [
                _task("del", risk="submit", control="삭제", never=sts.NEVER_DELETE),
                _task("sig", risk="submit", control="서명", never=sts.NEVER_SIGNATURE),
            ]
        )
    )
    for key in (
        "del",
        "sig",
    ):  # 엔진은 승인 후 실행을 허용하지만 never 는 승인 요청 자체를 막는다 — 더 엄격할 뿐 모순은 없다
        with pytest.raises(ValueError, match="승인 요청을 만들 수 없습니다"):
            spec_service.assert_approvable(HOST, key)


# ── (4) 지도 갱신으로 never 표시가 사라지면 map_changed ────────────


def test_dropping_a_never_marker_changes_fingerprint_and_pin_check_returns_map_changed(env):
    with_never = _map([_task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT)])
    without = _map([_task("pay", risk="submit", control="이체")])
    a, b = hist.structure(with_never), hist.structure(without)
    assert hist.fingerprint(a) != hist.fingerprint(b)
    changed = hist.diff(a, b)
    assert (
        changed["tasks_changed"] == ["pay"]
        and changed["never_removed"] == ["pay"]
        and "pay" in changed["stale_candidates"]
    )
    assert hist.pin_check(1, 2, hist.fingerprint(b), hist.fingerprint(a))["state"] == "map_changed"


def test_run_task_returns_map_changed_when_pinned_map_had_never_marker(env):
    store.save(_map([_task("ok"), _task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT)]))
    pinned = store.load(HOST)["map_rev"]
    # 사람이 표시를 지운 새 지도(구조 변경) — 고정한 버전으로 실행하려 하면 map_changed
    store.save(_map([_task("ok"), _task("pay", risk="submit", control="이체")]))
    map_service.configure_runner(lambda host, task_id, values: {"ok": True})
    try:
        assert map_service.run_task(HOST, "ok", {"q": "x"}, map_rev=pinned)["state"] == "map_changed"
    finally:
        map_service.configure_runner(None)


def test_structure_without_never_is_unchanged_so_old_maps_keep_their_fingerprint():
    plain = hist.structure(_map([_task("ok")]))
    assert "never" not in plain["tasks"]["ok"]


# ── 라우터 ───────────────────────────────────────────────────────


def _client(role: str | None) -> TestClient:
    app = FastAPI()
    app.include_router(site_task_map_router)
    if role:
        app.dependency_overrides[get_current_user] = lambda: {"role": role, "username": "kim"}
    return TestClient(app)


def test_routes_require_role_and_refuse_never_with_400(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    store.save(_map([_task("ok"), _task("pay", risk="submit", control="이체", never=sts.NEVER_PAYMENT)]))
    assert _client(None).get(f"/site-map/{HOST}/candidates").status_code in (401, 403)
    assert _client("viewer").post(f"/site-map/{HOST}/spec", json={"task_key": "ok"}).status_code == 403
    admin = _client("admin")
    cand = admin.get(f"/site-map/{HOST}/candidates").json()
    assert cand["never"] == 1 and {i["task_key"]: i["availability"] for i in cand["items"]}["pay"] == "자동 실행 불가"
    assert admin.post(f"/site-map/{HOST}/spec", json={"task_key": "ok"}).json()["plan"]["executes"] is True
    refused = admin.post(f"/site-map/{HOST}/spec", json={"task_key": "pay"})
    assert refused.status_code == 400 and "자동 실행 불가" in refused.json()["detail"]
    assert admin.get(f"/site-map/{HOST}/spec", params={"task_key": "ok"}).json()["map_changed"] is False
    assert admin.get(f"/site-map/{HOST}/spec", params={"task_key": "nope"}).status_code == 404
    assert admin.get(f"/site-map/{HOST}/spec").status_code == 422
