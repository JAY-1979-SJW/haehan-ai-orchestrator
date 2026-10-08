"""사이트 업무 지도 M8 — 메뉴 색인·주소 열기 업무·중복 정리. 브라우저 없이 가짜 스냅샷으로 검증한다.

2026-10-05 실검증: 카탈로그 사이트 20쪽을 탐색해도 지도 업무가 전부 "장바구니 담기"(쓰기)여서 AI 가 읽을 수단이 없었다.
기준서: docs/specs/2026-10-05_site_map_link_read_tasks.md
"""

from __future__ import annotations

import pytest

from ai_orchestrator.site_work import site_map_labels as lab
from ai_orchestrator.site_work import site_map_menu as menu
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store
from scripts.explorer import task_mapper

NOW = "2026-10-05T12:00:00+09:00"
HOST = "shop.example-site.test"
BASE = f"https://{HOST}"


def _link(text, path, *, href=None, **extra):
    """스냅샷 링크 한 건. extra: landmark·group·visible·form."""
    base = {"landmark": "", "group": "", "visible": True, "form": ""}
    return {
        "text": text,
        "href": path if href is None else href,
        "abs": f"{BASE}{path}" if href is None else "",
        **base,
        **extra,
    }


def _snap(links, path="/"):
    return {
        "url": f"{BASE}{path}",
        "title": "상점",
        "frames": [{"url": f"{BASE}{path}", "links": links, "buttons": [], "inputs": [], "forms": [], "headings": []}],
    }


def _menu(links):
    return menu.menu_from_snapshot(_snap(links), risk_of=tm.risk_of, skip_fragments=tm.EXPLORE_SKIP_URL)


# ── 메뉴 색인 ──────────────────────────────────────────────────


def test_navigation_and_complementary_landmarks_are_menu_but_main_and_footer_links_are_not():
    got = _menu(
        [
            _link("추리", "/cat/mystery", landmark="navigation"),
            _link("공지", "/notice", landmark="complementary"),
            _link("상품 하나", "/p/1", landmark="main"),
            _link("개인정보", "/privacy", landmark="contentinfo"),
        ]
    )
    assert [m["label"] for m in got] == ["추리", "공지"]


def test_list_group_of_five_or_more_is_menu_without_landmarks():
    cats = [_link(f"분류{i}", f"/c/{i}", group="9") for i in range(5)]
    few = [_link(f"작은{i}", f"/s/{i}", group="3") for i in range(4)]  # 4개는 메뉴가 아니다(이동 링크·탭 정도)
    assert len(_menu(cats + few)) == 5


def test_product_cards_with_deep_links_are_not_menu():
    """상품 카드의 링크는 li 직계가 아니라 group 이 비어 있다 — 40개가 있어도 메뉴로 번지지 않는다."""
    cards = [_link(f"상품{i}", f"/p/{i}") for i in range(40)]
    assert _menu(cards) == []


def test_menu_excludes_other_hosts_unsafe_schemes_forms_hidden_and_risky_labels():
    got = _menu(
        [
            _link("외부", "", landmark="navigation", href="https://other.test/x"),
            _link("스크립트", "", landmark="navigation", href="javascript:void(0)"),
            _link("메일", "", landmark="navigation", href="mailto:a@b.c"),
            _link("폼 안 링크", "/f", landmark="navigation", form="0:search"),
            _link("숨김", "/h", landmark="navigation", visible=False),
            _link("로그아웃", "/logout", landmark="navigation"),
            _link("회원 삭제", "/members", landmark="navigation"),
            _link("정상", "/ok", landmark="navigation"),
        ]
    )
    assert [m["label"] for m in got] == ["정상"]


def test_menu_dedupes_by_href_strips_fragment_and_cleans_label():
    got = _menu(
        [
            _link("추리\n12개", "/c/m", landmark="navigation"),
            _link("추리 다시", "/c/m#top", landmark="navigation", href="/c/m#top"),
        ]
    )
    assert got == [{"label": "추리", "href": f"{BASE}/c/m"}]


def test_merge_menu_is_additive_bounded_and_returns_same_object_when_nothing_new():
    base = tm.empty_map(HOST, now=NOW)
    one = menu.merge_menu(base, [{"label": "A", "href": f"{BASE}/a"}], now=NOW)
    assert one["menu"] == [{"label": "A", "href": f"{BASE}/a"}] and one["menu_at"] == NOW
    assert menu.merge_menu(one, [{"label": "A2", "href": f"{BASE}/a"}], now="later") is one
    many = menu.merge_menu(base, [{"label": f"L{i}", "href": f"{BASE}/{i}"} for i in range(menu.MENU_MAX + 40)], now=NOW)
    assert len(many["menu"]) == menu.MENU_MAX and many["menu_total_seen"] == menu.MENU_MAX + 40  # 잘렸다는 것(관측 총수 > 저장 수)을 알 수 있다
    assert menu.merge_menu(many, [{"label": "again", "href": f"{BASE}/0"}], now="later") is many  # 이미 아는 주소만이면 그대로


# ── 주소 열기 검증 ─────────────────────────────────────────────


def _v(url):
    return menu.validate_open_url(url, HOST, risk_of=tm.risk_of, skip_fragments=tm.EXPLORE_SKIP_URL)


def test_validate_open_url_accepts_same_host_http_and_strips_fragment():
    assert _v(f"{BASE}/cat/mystery/page-2.html#x") == f"{BASE}/cat/mystery/page-2.html"
    assert _v(f"http://{HOST}/a") == f"http://{HOST}/a"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "https://other.test/a",
        f"ftp://{HOST}/a",
        f"file://{HOST}/a",
        "javascript:alert(1)",
        f"https://user:pw@{HOST}/a",
        f"https://{HOST}:8443/a",
        f"https://{HOST}/a b",
        f"https://{HOST}/" + "x" * 400,
        f"https://{HOST}/logout",
        f"https://{HOST}/members/delete?id=3",
        f"https://{HOST}/pay/now",
    ],
)
def test_validate_open_url_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        _v(bad)


def test_validate_open_url_rejects_host_lookalike():
    with pytest.raises(ValueError):
        _v(f"https://{HOST}.evil.test/a")
    with pytest.raises(ValueError):
        _v(f"https://evil.test/{HOST}")


def test_open_page_task_is_read_and_has_url_placeholder_only():
    t = tm.open_page_task(HOST, f"{BASE}/", now=NOW)
    assert t["id"] == menu.OPEN_PAGE_ID and t["risk"] == "read" and t["category"] == "navigate"
    assert tm.step_placeholders(t["steps"]) == ["url"]
    assert tm.effective_risk(t) == "read"


def test_run_request_for_open_page_accepts_only_a_safe_url():
    t = tm.open_page_task(HOST, f"{BASE}/", now=NOW)
    assert tm.validate_run_request(t, {"url": f"{BASE}/c/1"}) == {"url": f"{BASE}/c/1"}
    for params in ({"url": "https://other.test/"}, {"url": f"{BASE}/logout"}, {}, {"url": f"{BASE}/a", "q": "x"}):
        with pytest.raises(ValueError):
            tm.validate_run_request(t, params)
    with pytest.raises(ValueError):
        tm.validate_run_request(t, "not-a-dict")  # type: ignore[arg-type]


def test_navigate_steps_with_fixed_urls_still_have_no_placeholders():
    assert tm.step_placeholders([{"type": "navigate", "url": f"{BASE}/a"}]) == []


# ── 중복 정리 ──────────────────────────────────────────────────


def _btn_task(i, **over):
    t = {
        "id": f"/p{i}#btn_ab12",
        "risk": "write",
        "state": "observed",
        "control": "Add to basket",
        "name": f"Add to basket (페이지 {i})",
        "purpose": "",
    }
    t.update(over)
    return t


def test_collapse_duplicate_actions_keeps_one_with_seen_pages_and_clean_name():
    site_map = {"tasks": [_btn_task(i) for i in range(21)]}
    out, removed = lab.collapse_duplicate_actions(site_map)
    assert removed == 20 and len(out["tasks"]) == 1
    (t,) = out["tasks"]
    assert (
        t["name"] == "Add to basket" and t["seen_pages"] == lab.SEEN_PAGES_MAX and t["risk"] == "write"
    )  # 위험 등급은 그대로


def test_collapse_prefers_verified_and_never_drops_verified_or_purposeful_tasks():
    tasks = [_btn_task(1), _btn_task(2, state="verified"), _btn_task(3, purpose="장바구니 시험용")]
    out, removed = lab.collapse_duplicate_actions({"tasks": tasks})
    ids = {t["id"] for t in out["tasks"]}
    assert removed == 1 and ids == {"/p2#btn_ab12", "/p3#btn_ab12"}
    keeper = next(t for t in out["tasks"] if t["id"] == "/p2#btn_ab12")
    assert keeper["seen_pages"] == 3


def test_collapse_ignores_read_tasks_other_controls_and_single_tasks():
    tasks = [
        _btn_task(1),
        _btn_task(2, control="Save", name="Save (x)"),
        {"id": "/a#btn_cd", "risk": "read", "state": "observed", "control": "Add to basket", "name": "x"},
    ]
    out, removed = lab.collapse_duplicate_actions({"tasks": tasks})
    assert removed == 0 and out["tasks"] == tasks


# ── 탐색 합치기 연동 ───────────────────────────────────────────


@pytest.fixture
def maps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")


def test_exploration_stores_menu_open_page_task_and_collapses_buttons(maps):
    def page(n):
        links = [_link(f"분류{i}", f"/c/{i}", group="4") for i in range(6)]
        snap = _snap(links, path=f"/p/{n}")
        snap["frames"][0]["buttons"] = [
            {"text": "Add to basket", "id": "", "aria": "", "cls": "", "visible": True, "landmark": "main"}
        ]
        return snap

    out = task_mapper.merge_snapshots(HOST, [page(n) for n in range(4)], explored_pages=4)["map"]
    assert len(out["menu"]) == 6
    ids = [t["id"] for t in out["tasks"]]
    assert menu.OPEN_PAGE_ID in ids
    adds = [t for t in out["tasks"] if t.get("control") == "Add to basket"]
    assert len(adds) == 1 and adds[0]["seen_pages"] == 4  # 화면마다 쌓이던 같은 쓰기 버튼이 하나로


def test_map_without_menu_gets_no_open_page_task(maps):
    out = task_mapper.merge_snapshots(HOST, [_snap([_link("상품", "/p/1")])], explored_pages=1)["map"]
    assert "menu" not in out and menu.OPEN_PAGE_ID not in [t["id"] for t in out["tasks"]]
