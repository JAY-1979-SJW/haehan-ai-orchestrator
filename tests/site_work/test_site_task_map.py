"""사이트 업무 지도 — 분류·위험 등급·병합·저장·변환. 브라우저·네트워크 없이 가상 스냅샷만 사용."""

from __future__ import annotations

import json

import pytest

from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store
from scripts.explorer import task_mapper

NOW = "2026-10-03T12:00:00+09:00"
LATER = "2026-10-04T09:00:00+09:00"


def _snap(url="https://www.example-kiscon.test/gongsi/ksc_dft.asp", *, inputs=None, buttons=None, links=None, forms=None):
    """공개 업체검색 화면과 같은 모양의 가상 스냅샷(page_snapshot.collect 형식)."""
    return {
        "url": url,
        "title": "업체정보입력검색",
        "frames": [
            {
                "idx": 0,
                "url": url,
                "inputs": inputs
                if inputs is not None
                else [
                    {"tag": "INPUT", "type": "text", "name": "txtSangHo", "id": "", "placeholder": "업체명", "aria": "", "required": False, "visible": True},
                    {"tag": "INPUT", "type": "text", "name": "txtCeo", "id": "", "placeholder": "대표자", "aria": "", "required": False, "visible": True},
                    {"tag": "INPUT", "type": "hidden", "name": "EP_STATUS", "id": "", "placeholder": "", "aria": "", "required": False, "visible": False},
                ],
                "buttons": buttons or [],
                "links": links if links is not None else [{"text": "검색", "href": "#", "target": "", "visible": True}],
                "forms": forms if forms is not None else [{"id": "", "action": url, "method": "get", "name": "frm1"}],
                "headings": [],
            }
        ],
    }


# ── 위험 등급 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texts", "risk"),
    [
        (["검색"], "read"),
        (["조회", "다음"], "read"),
        (["저장"], "write"),
        (["수정 완료"], "write"),
        (["등록"], "write"),
        (["제출"], "submit"),
        (["신고하기"], "submit"),
        (["삭제"], "submit"),
        (["로그아웃"], "submit"),
        (["저장", "제출"], "submit"),  # 가장 높은 등급이 이긴다
        (["submitForm"], "submit"),
        (["display"], "read"),  # 'pay' 로 오인하지 않는다
        (["/pay/confirm.do"], "submit"),
        ([], "read"),
    ],
)
def test_risk_of(texts, risk):
    assert tm.risk_of(texts) == risk


# ── 스냅샷 → 업무 ─────────────────────────────────────────────────────────


def test_public_search_form_becomes_read_search_task():
    (t,) = tm.tasks_from_snapshot(_snap(), now=NOW)
    assert (t["category"], t["risk"], t["auth"], t["state"]) == ("search", "read", "public", "observed")
    assert [f["name"] for f in t["fields"]] == ["txtSangHo", "txtCeo"]  # hidden 은 제외
    assert t["control"] == "검색"
    # Recorder 호환 단계: navigate → change(매개변수 자리) → click
    assert [s["type"] for s in t["steps"]] == ["navigate", "change", "change", "click"]
    assert t["steps"][1]["value"] == "{{txtSangHo}}"
    assert t["steps"][1]["selectors"][0] == ["[name='txtSangHo']"]
    assert t["steps"][1]["selectors"][1] == ["aria/업체명"]
    assert t["steps"][-1]["selectors"][0] == ["aria/검색"]


def test_no_values_are_stored():
    snap = _snap()
    snap["frames"][0]["inputs"][0]["value"] = "비밀 업체명"  # 혹시 스냅샷에 값이 섞여 들어와도
    text = json.dumps(tm.tasks_from_snapshot(snap, now=NOW), ensure_ascii=False)
    assert "비밀 업체명" not in text


def test_submit_and_write_tasks_have_no_click_step():
    sub = tm.tasks_from_snapshot(_snap(links=[{"text": "신고", "href": "#", "target": "", "visible": True}]), now=NOW)[0]
    wr = tm.tasks_from_snapshot(_snap(links=[], buttons=[{"text": "저장", "id": "", "aria": "", "cls": "", "visible": True}]), now=NOW)[0]
    assert (sub["risk"], sub["category"]) == ("submit", "submit")
    assert (wr["risk"], wr["category"]) == ("write", "input")
    for t in (sub, wr):
        assert t["steps"][-1]["type"] == "change"  # 마지막 클릭(제출·저장)은 사람 몫


def test_password_form_is_login_and_never_read():
    snap = _snap(
        inputs=[
            {"tag": "INPUT", "type": "text", "name": "id", "id": "", "placeholder": "아이디", "aria": "", "required": True, "visible": True},
            {"tag": "INPUT", "type": "password", "name": "pw", "id": "", "placeholder": "", "aria": "", "required": True, "visible": True},
        ],
        links=[],
        buttons=[{"text": "로그인", "id": "", "aria": "", "cls": "", "visible": True}],
    )
    (t,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert (t["category"], t["risk"], t["auth"]) == ("login", "submit", "login")
    assert not any(s["type"] == "click" for s in t["steps"])


def test_menu_only_page_and_error_frames_are_skipped():
    assert tm.tasks_from_snapshot(_snap(inputs=[]), now=NOW) == []
    snap = _snap()
    snap["frames"].append({"idx": 1, "url": "x", "error": "boom"})
    assert len(tm.tasks_from_snapshot(snap, now=NOW)) == 1


def test_inputs_grouped_by_form_key_when_present():
    snap = _snap()
    snap["frames"][0]["inputs"][0]["form"] = "frm1"
    snap["frames"][0]["inputs"][1]["form"] = "headerSearch"
    ids = sorted(t["id"] for t in tm.tasks_from_snapshot(snap, now=NOW))
    assert ids == ["gongsi_ksc_dft_asp#frm1", "gongsi_ksc_dft_asp#headersearch"]


def test_menu_links_outside_the_form_do_not_raise_risk():
    """실사이트(KISCON) 실측 회귀: 같은 화면의 메뉴 링크('발급 확인' 등)가 검색 업무를 submit 으로 올리면 안 된다."""
    snap = _snap(
        inputs=[
            {"tag": "INPUT", "type": "text", "name": "txtSangHo", "id": "", "placeholder": "업체명", "aria": "", "required": False, "visible": True, "form": "0:frm1"},
        ],
        links=[
            {"text": "검색", "href": "#", "target": "", "visible": True, "form": "0:frm1"},
            {"text": "제재처분확인서 발급", "href": "javascript:void(0)", "target": "", "visible": True, "form": ""},
            {"text": "건설업체정보조회안내", "href": "javascript:void(0)", "target": "", "visible": True, "form": ""},
        ],
        forms=[{"id": "", "action": "https://www.example-kiscon.test/gongsi/ksc_dft.asp", "method": "get", "name": "frm1"}],
    )
    (t,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert (t["risk"], t["category"], t["control"]) == ("read", "search", "검색")


def test_page_wide_form_uses_proximity_to_pick_controls():
    """폼 하나가 메뉴·푸터까지 감싸는 사이트(KISCON 실측): 입력창 근처 컨트롤만 이 업무의 동작 버튼."""
    snap = _snap(
        inputs=[{"tag": "INPUT", "type": "text", "name": "txtSangHo", "id": "", "placeholder": "업체명", "aria": "", "required": False, "visible": True, "form": "0:frm1", "pos": 500}],
        links=[
            {"text": "제재처분확인서 발급", "href": "javascript:void(0)", "target": "", "visible": True, "form": "0:frm1", "pos": 120},
            {"text": "건설업체정보조회안내", "href": "javascript:void(0)", "target": "", "visible": True, "form": "0:frm1", "pos": 130},
            {"text": "검색", "href": "#", "target": "", "visible": True, "form": "0:frm1", "pos": 520},
            {"text": "신고센터", "href": "javascript:void(0)", "target": "", "visible": True, "form": "0:frm1", "pos": 900},
        ],
        forms=[{"id": "", "action": "https://www.example-kiscon.test/gongsi/ksc_dft.asp", "method": "get", "name": "frm1"}],
    )
    (t,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert (t["risk"], t["category"], t["control"]) == ("read", "search", "검색")


def test_hidden_inputs_do_not_widen_the_proximity_range():
    """실사이트 실측 회귀: 화면 밖 hidden 입력창(위치가 흩어짐)이 근접 범위를 문서 전체로 넓히면 안 된다."""
    snap = _snap(
        inputs=[
            {"tag": "INPUT", "type": "hidden", "name": "hid", "id": "", "placeholder": "", "aria": "", "required": False, "visible": False, "form": "0:f", "pos": 10},
            {"tag": "INPUT", "type": "text", "name": "q", "id": "", "placeholder": "", "aria": "", "required": False, "visible": True, "form": "0:f", "pos": 500},
        ],
        links=[
            {"text": "발급", "href": "javascript:void(0)", "target": "", "visible": True, "form": "0:f", "pos": 100},
            {"text": "검색", "href": "#", "target": "", "visible": True, "form": "0:f", "pos": 510},
        ],
    )
    (t,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert (t["risk"], t["control"]) == ("read", "검색")


def test_legacy_snapshot_without_form_keys_stays_conservative():
    snap = _snap(links=[{"text": "검색", "href": "#", "target": "", "visible": True}, {"text": "신고", "href": "#", "target": "", "visible": True}])
    (t,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert t["risk"] == "submit"  # 소속을 알 수 없으면 넓게 보고 높은 등급을 택한다


def test_submit_control_inside_the_form_still_raises_risk():
    snap = _snap(
        inputs=[{"tag": "INPUT", "type": "text", "name": "a", "id": "", "placeholder": "", "aria": "", "required": False, "visible": True, "form": "0:f"}],
        buttons=[{"text": "제출", "id": "", "aria": "", "cls": "", "visible": True, "form": "0:f"}],
        links=[],
    )
    assert tm.tasks_from_snapshot(snap, now=NOW)[0]["risk"] == "submit"


# ── 병합·상태 ─────────────────────────────────────────────────────────────


def _map_with(task_snapshot=None):
    m = tm.empty_map("www.example-kiscon.test", now=NOW)
    return tm.merge_tasks(m, tm.tasks_from_snapshot(task_snapshot or _snap(), now=NOW), now=NOW)


def test_merge_same_structure_keeps_verified_state():
    m = _map_with()
    tid = m["tasks"][0]["id"]
    m = tm.mark_verified(m, tid, now=NOW)
    again = tm.merge_tasks(m, tm.tasks_from_snapshot(_snap(), now=LATER), now=LATER)
    t = again["tasks"][0]
    assert (t["state"], t["verified_at"], t["observed_at"]) == ("verified", NOW, LATER)
    assert len(again["tasks"]) == 1


def test_merge_changed_structure_resets_verification_and_keeps_human_edits():
    m = _map_with()
    tid = m["tasks"][0]["id"]
    m = tm.set_classification(m, tid, name="업체정보 검색", purpose="협력업체 상태 확인", category="search")
    m = tm.mark_verified(m, tid, now=NOW)
    changed = _snap(inputs=[{"tag": "INPUT", "type": "text", "name": "newName", "id": "", "placeholder": "상호", "aria": "", "required": False, "visible": True}])
    out = tm.merge_tasks(m, tm.tasks_from_snapshot(changed, now=LATER), now=LATER)
    t = out["tasks"][0]
    assert t["state"] == "observed" and [f["name"] for f in t["fields"]] == ["newName"]
    assert (t["name"], t["purpose"]) == ("업체정보 검색", "협력업체 상태 확인")  # 사람이 정한 값 유지
    assert t["changes"][-1]["was"] == "verified"


def test_risk_never_lowered_by_reobservation():
    m = _map_with(_snap(links=[{"text": "신고", "href": "#", "target": "", "visible": True}]))
    assert m["tasks"][0]["risk"] == "submit"
    safer = _snap(links=[{"text": "검색", "href": "#", "target": "", "visible": True}], inputs=[{"tag": "INPUT", "type": "text", "name": "q", "id": "", "placeholder": "", "aria": "", "required": False, "visible": True}])
    out = tm.merge_tasks(m, tm.tasks_from_snapshot(safer, now=LATER), now=LATER)
    assert out["tasks"][0]["risk"] == "submit"


def test_mark_failed_goes_stale_and_counts():
    m = _map_with()
    tid = m["tasks"][0]["id"]
    m = tm.mark_failed(tm.mark_failed(m, tid, now=LATER), tid, now=LATER)
    assert (m["tasks"][0]["state"], m["tasks"][0]["failures"]) == ("stale", 2)
    assert tm.mark_verified(m, tid, now=LATER)["tasks"][0]["failures"] == 0
    with pytest.raises(ValueError, match="찾을 수 없"):
        tm.mark_failed(m, "nope", now=LATER)


def test_set_classification_rejects_unknown_category_and_cannot_touch_risk():
    m = _map_with()
    tid = m["tasks"][0]["id"]
    with pytest.raises(ValueError, match="분류"):
        tm.set_classification(m, tid, category="bogus")
    with pytest.raises(TypeError):
        tm.set_classification(m, tid, risk="read")  # type: ignore[call-arg]  # 위험 등급은 사람도 이 경로로 낮추지 못한다


def test_lookup_ranks_and_empty_query():
    m = _map_with()
    assert [t["id"] for t in tm.lookup(m, "txtsangho 업체")] == [m["tasks"][0]["id"]]
    assert tm.lookup(m, "전혀없는말") == []
    assert len(tm.lookup(m, "")) == 1


def test_functions_do_not_mutate_inputs():
    m = _map_with()
    before = json.dumps(m, sort_keys=True)
    tid = m["tasks"][0]["id"]
    tm.mark_verified(m, tid, now=LATER)
    tm.merge_tasks(m, tm.tasks_from_snapshot(_snap(), now=LATER), now=LATER)
    tm.set_classification(m, tid, name="x")
    assert json.dumps(m, sort_keys=True) == before


def test_validate_map_rejects_bad_shapes():
    for bad in (None, {"version": 99, "host": "a", "tasks": []}, {"version": 1, "host": "a", "tasks": [{"id": "x", "risk": "nope", "state": "observed"}]}):
        with pytest.raises(ValueError):
            tm.validate_map(bad)


# ── 저장소 ────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "site_task_map")
    return tmp_path


def test_store_roundtrip_atomic_and_listing(isolated_store):
    m = _map_with()
    path = store.save(m)
    assert path.exists() and not list(path.parent.glob("*.tmp"))
    assert store.load("www.example-kiscon.test") == m
    assert store.list_hosts() == ["www.example-kiscon.test"]
    assert store.load("other.example.test")["tasks"] == []  # 없으면 빈 지도


def test_store_rejects_bad_host_and_corrupt_file(isolated_store):
    for host in ("../etc", "a/b", "", "bad host", "x..y"):
        with pytest.raises(ValueError):
            store.load(host)
    store.save(_map_with())
    (isolated_store / "site_task_map" / "www.example-kiscon.test.json").write_text("{깨짐", encoding="utf-8")
    with pytest.raises(ValueError, match="읽을 수 없"):
        store.load("www.example-kiscon.test")  # 조용히 빈 지도로 덮어쓰지 않는다


def test_failed_save_keeps_previous_map(isolated_store, monkeypatch):
    m = _map_with()
    store.save(m)
    bad = dict(m, tasks=[{"id": "x"}])
    with pytest.raises(ValueError):
        store.save(bad)
    assert store.load("www.example-kiscon.test") == m


# ── 변환 어댑터 ───────────────────────────────────────────────────────────


def test_merge_snapshots_ignores_other_hosts(isolated_store):
    out = task_mapper.merge_snapshots("www.example-kiscon.test", [_snap(), _snap(url="https://evil.test/x")])
    assert out["observed"] == 1 and out["skipped_other_host"] == 1
    assert store.load("www.example-kiscon.test")["tasks"][0]["risk"] == "read"


def test_import_auto_sitemap_creates_unclassified_tasks_only_for_form_pages(isolated_store, tmp_path):
    f = tmp_path / "auto.json"
    f.write_text(
        json.dumps(
            {
                "host": "www.example-kiscon.test",
                "pages": [
                    {"url": "https://www.example-kiscon.test/a/list.asp", "title": "목록", "forms_count": 1, "form_summary": {"submit": "#btn"}},
                    {"url": "https://www.example-kiscon.test/b/delete.asp", "title": "삭제", "forms_count": 1, "form_summary": {}},
                    {"url": "https://www.example-kiscon.test/c", "title": "메뉴만", "forms_count": 0},
                    {"url": "https://www.example-kiscon.test/d", "error": "goto"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = task_mapper.import_auto_sitemap(f)
    by_url = {t["url"].rsplit("/", 1)[-1]: t for t in out["map"]["tasks"]}
    assert set(by_url) == {"list.asp", "delete.asp"}
    assert by_url["list.asp"]["category"] == "unclassified" and by_url["list.asp"]["risk"] == "read"
    assert by_url["delete.asp"]["risk"] == "submit"


# ── 탐색 기록: 접근 구분 승격·탐색한 사실 ───────────────────────────────────


def test_stronger_auth_only_moves_up():
    assert tm.stronger_auth("public", "login") == "login"
    assert tm.stronger_auth("login", "public") == "login"  # 공개로 되돌리지 않는다
    assert tm.stronger_auth("login", "certificate") == "certificate"
    assert tm.stronger_auth("certificate", "login") == "certificate"
    assert tm.stronger_auth("public", "알수없음") == "public"


def test_note_exploration_records_fact_without_mutating_input():
    base = tm.empty_map("a.test", now=NOW)
    out = tm.note_exploration(base, pages=8, auth="login", now=LATER)
    assert out["auth"] == "login" and out["explored"] == {"at": LATER, "pages": 8} and out["updated_at"] == LATER
    assert base["auth"] == "public" and "explored" not in base
    assert tm.validate_map(out)  # 저장 형식 검증을 통과한다


def test_merge_snapshots_marks_login_site_and_remembers_empty_exploration(isolated_store):
    out = task_mapper.merge_snapshots("www.example-kiscon.test", [], auth="login", explored_pages=5)
    saved = store.load("www.example-kiscon.test")
    assert out["map"]["auth"] == "login" and saved["auth"] == "login" and saved["explored"]["pages"] == 5 and saved["tasks"] == []
    again = task_mapper.merge_snapshots("www.example-kiscon.test", [], auth="public", explored_pages=2)  # 나중에 공개로 탐색해도
    assert again["map"]["auth"] == "login"  # 더 엄격한 구분이 유지된다


# ── M6-a: 버튼 업무·편집 영역·위험 키워드·점검표 ───────────────────────────


def _btn(text, **kw):
    return {"text": text, "id": "", "aria": "", "cls": "", "visible": True, "form": "", "pos": 1, **kw}


@pytest.mark.parametrize(
    ("label", "risk"),
    [("출금", "submit"), ("세금계산서 발행", "submit"), ("발행하기", "submit"), ("공동인증서 로그인", "submit"), ("인증서 선택", "submit"), ("납부", "submit"),
     ("글쓰기", "write"), ("이체", "submit"), ("조회", "read"), ("거래내역 조회", "read"), ("검색", "read"), ("다운로드", "read"), ("다음", "read")],
)
def test_business_risk_words(label, risk):
    assert tm.risk_of([label]) == risk


def test_button_only_screen_becomes_button_tasks_with_risk_and_no_click_for_non_read():
    snap = _snap("https://tax.example.test/issue", inputs=[], links=[], forms=[], buttons=[_btn("세금계산서 발행"), _btn("거래내역 조회"), _btn("")])
    tasks = tm.tasks_from_snapshot(snap, now=NOW)
    by = {t["control"]: t for t in tasks}
    assert set(by) == {"세금계산서 발행", "거래내역 조회"}  # 이름 없는 버튼은 건너뛴다
    issue, look = by["세금계산서 발행"], by["거래내역 조회"]
    assert (issue["risk"], issue["category"], issue["fields"]) == ("submit", "submit", [])
    assert [s["type"] for s in issue["steps"]] == ["navigate"]  # 제출 버튼은 클릭 단계를 만들지 않는다
    assert (look["risk"], look["category"]) == ("read", "navigate") and [s["type"] for s in look["steps"]] == ["navigate", "click"]
    assert issue["id"] != look["id"] and tm.validate_map(dict(tm.empty_map("tax.example.test", now=NOW), tasks=tasks))  # 한글 이름도 id 가 겹치지 않는다


def test_buttons_used_by_a_field_task_are_not_repeated_and_cap_keeps_risky_first():
    snap = _snap(buttons=[_btn("검색")])
    snap["frames"][0]["links"] = []
    assert [t["control"] for t in tm.tasks_from_snapshot(snap, now=NOW)] == ["검색"]  # 입력창 업무가 쓴 버튼은 따로 만들지 않는다
    many = _snap("https://x.example.test/p", inputs=[], links=[], forms=[], buttons=[_btn(f"보기{i}") for i in range(10)] + [_btn("송금")])
    got = tm.tasks_from_snapshot(many, now=NOW)
    assert len(got) == tm._BUTTON_TASKS_MAX and "송금" in [t["control"] for t in got]  # 상한이 있어도 위험한 버튼은 놓치지 않는다


def test_editable_area_counts_as_input_field():
    editable = {"tag": "EDITABLE", "type": "editable", "name": "editable_1", "id": "", "placeholder": "", "aria": "본문", "required": False, "visible": True}
    snap = _snap("https://blog.example.test/write", inputs=[editable], links=[], forms=[], buttons=[_btn("발행")])
    (task,) = tm.tasks_from_snapshot(snap, now=NOW)
    assert task["fields"][0]["type"] == "editable" and task["risk"] == "submit"


def test_coverage_warns_when_screens_read_but_no_task():
    empty = {"url": "https://x.example.test/", "title": "", "frames": [{"idx": 0, "url": "https://x.example.test/", "inputs": [{"type": "hidden", "name": "a", "visible": False}], "buttons": [_btn("   ")], "links": [], "forms": []}]}
    cov = tm.coverage_of([(empty, tm.tasks_from_snapshot(empty, now=NOW))])
    assert cov["tasks"] == 0 and cov["unrecognized"] == 1 and "단정하지 말고" in cov["warning"]
    good = _snap()
    ok = tm.coverage_of([(good, tm.tasks_from_snapshot(good, now=NOW))])
    assert ok["tasks"] == 1 and "warning" not in ok and ok["pages_read"] == 1
    assert tm.coverage_of([])["pages_read"] == 0 and "warning" not in tm.coverage_of([])  # 읽은 화면이 없으면 경고하지 않는다(폼 화면이 없는 사이트)


def test_merge_snapshots_stores_coverage_with_exploration(isolated_store):
    out = task_mapper.merge_snapshots("tax.example.test", [_snap("https://tax.example.test/a", inputs=[], links=[], forms=[], buttons=[_btn("발행")])], auth="login", explored_pages=3)
    cov = store.load("tax.example.test")["explored"]["coverage"]
    assert out["observed"] == 1 and cov["buttons_only"] == 1 and cov["tasks"] == 1


def test_other_host_snapshots_are_reported_not_silently_dropped(isolated_store):
    other = _snap("https://other.example.test/a")
    out = task_mapper.merge_snapshots("tax.example.test", [other], auth="public", explored_pages=2)
    cov = store.load("tax.example.test")["explored"]["coverage"]
    assert out["skipped_other_host"] == 1 and cov["skipped_other_host"] == 1 and "다른 호스트" in cov["warning"]


# ── 실제 앱 시험에서 발견: '블로그 마켓 가입' 버튼이 조회로 저장돼 있었다 ───────────


@pytest.mark.parametrize(("label", "risk"), [("블로그 마켓 가입", "submit"), ("회원가입", "submit"), ("가입하기", "submit"), ("공제가입번호 조회", "read"), ("가입자 조회", "read")])
def test_signup_buttons_are_submit_but_lookups_about_membership_stay_read(label, risk):
    assert tm.risk_of([label]) == risk


def _stored_read_task(control="블로그 마켓 가입"):
    snap = _snap("https://m.example.test/dir", inputs=[], links=[], forms=[], buttons=[_btn("조회")])
    (task,) = tm.tasks_from_snapshot(snap, now=NOW)
    return dict(task, control=control, risk="read", steps=[{"type": "navigate", "url": task["url"]}, {"type": "click", "selectors": [[f"text/{control}"]]}])


def test_effective_risk_rechecks_old_stored_tasks_with_current_rules():
    old = _stored_read_task()  # 규칙이 늘기 전에 read 로 저장된 업무
    assert tm.effective_risk(old) == "submit" and tm.effective_risk(dict(old, control="조회")) == "read"
    with pytest.raises(ValueError, match=r"조회\(read\) 업무만"):
        tm.validate_run_request(old, {})  # 서버가 실행 직전에 다시 판정해 막는다
    shown = tm.with_effective_risk(dict(tm.empty_map("m.example.test", now=NOW), tasks=[old]))
    assert shown["tasks"][0]["risk"] == "submit" and old["risk"] == "read"  # 응답에만 반영, 저장본은 그대로


def test_merge_raises_risk_of_same_structure_task_and_drops_click():
    old = _stored_read_task()
    new = dict(old, risk="submit", steps=[{"type": "navigate", "url": old["url"]}], category="submit")
    merged = tm.merge_tasks(dict(tm.empty_map("m.example.test", now=NOW), tasks=[old]), [new], now=LATER)
    (task,) = merged["tasks"]
    assert task["risk"] == "submit" and [s["type"] for s in task["steps"]] == ["navigate"] and task["state"] == "observed"
    back = tm.merge_tasks(merged, [dict(old)], now=LATER)  # 다시 read 로 관찰돼도 내리지 않는다
    assert back["tasks"][0]["risk"] == "submit"
