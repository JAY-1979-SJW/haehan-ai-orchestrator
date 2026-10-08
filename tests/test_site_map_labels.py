"""사이트 업무 지도 품질(M7 S1.2) — 이름 정리·전역 메뉴 분리·예전 형식 정리. 브라우저 없이 가짜 스냅샷으로 검증한다.

2026-10-05 네이버 카페 실검증: 버튼 원문 텍스트(줄바꿈·화면 수치 포함)가 업무 이름이 되고, 모든 화면에 있는 상단 메뉴가 화면마다 업무로 쌓여
17건 중 실질 업무가 2~3건이었다. 근거: W3C accname 1.2(이름은 하위 텍스트를 이어 붙인 한 줄, 길이 제한 없음)·ARIA 랜드마크·Playwright 로케이터.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.site_work import site_map_labels as lab
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store
from scripts.explorer import task_mapper

NOW = "2026-10-05T09:00:00+09:00"
HOST = "cafe.example-site.test"
MATE = "네이버 메이트\n누적 인용\n362만 인용"  # 실검증에서 이름에 섞여 들어갔던 실제 형태


def _btn(text, *, landmark="", aria="", visible=True):
    return {"text": text, "id": "", "aria": aria, "cls": "", "visible": visible, "landmark": landmark}


def _snap(path, buttons):
    url = f"https://{HOST}{path}"
    return {
        "url": url,
        "title": "건설공무 : 네이버 카페",
        "frames": [{"url": url, "buttons": buttons, "inputs": [], "links": [], "forms": [], "headings": []}],
    }


# ── 이름 정리(clean_label) ─────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "aria", "expected"),
    [
        (MATE, "", "네이버 메이트"),  # 첫 의미 있는 줄 — 화면 수치("362만 인용")는 이름이 아니다
        ("  카페정보 \n", "", "카페정보"),
        ("나의\t활동", "", "나의 활동"),  # 공백 정규화(accname flat string 규칙)
        ("362만 인용\n네이버 메이트", "", "네이버 메이트"),  # 수치 줄이 앞이어도 건너뛴다
        ("12,345건", "", "12,345건"),  # 수치 줄뿐이면 그대로(이름을 비우지 않는다)
        ("글쓰기", "새 글 쓰기", "새 글 쓰기"),  # 명시적 aria-label 이 내용보다 우선(accname 2번째 단계)
        ("a" * 90, "", "a" * lab.LABEL_MAX),
        ("나쁜\x00이름\x07​", "", "나쁜이름"),  # 제어문자·제로폭 문자 제거(사이트가 정한 글자는 자료일 뿐)
        ("", "", ""),
    ],
)
def test_clean_label(text, aria, expected):
    assert lab.clean_label(text, aria) == expected


def test_clean_label_prefix_is_stable_when_trailing_numbers_change():
    """실행용 이름은 첫 줄이라 사이트가 뒤에 붙이는 수치가 바뀌어도 같다 — 재개가 깨지지 않는 이유."""
    assert lab.clean_label("네이버 메이트\n누적 인용\n362만 인용") == lab.clean_label(
        "네이버 메이트\n누적 인용\n380만 인용"
    )


# ── 업무 생성: 이름·전역 랜드마크·위험 컨트롤 ──────────────────────


def _tasks(buttons, path="/0moo"):
    return tm.tasks_from_snapshot(_snap(path, buttons), now=NOW)


def test_button_task_uses_clean_label_for_name_and_control():
    (t,) = _tasks([_btn(MATE)])
    assert t["control"] == "네이버 메이트" and "\n" not in t["name"] and "362" not in t["name"]
    assert t["steps"][-1]["selectors"][0] == ["aria/네이버 메이트"]  # 안정적인 앞부분으로 찾는다


def test_read_buttons_in_global_landmarks_are_not_tasks():
    tasks = _tasks(
        [
            _btn("카페정보", landmark="navigation"),
            _btn("나의활동", landmark="banner"),
            _btn("저작권", landmark="contentinfo"),
            _btn("전체글보기", landmark="main"),
        ]
    )
    assert [t["control"] for t in tasks] == ["전체글보기"]  # 본문(main) 컨트롤만 업무


def test_risky_buttons_stay_tasks_even_in_global_landmarks():
    """위험 등급 게이트가 항상 적용되도록 삭제·발행 같은 컨트롤은 전역 영역에 있어도 업무로 남긴다."""
    tasks = _tasks([_btn("글 삭제", landmark="navigation"), _btn("카페정보", landmark="navigation")])
    assert [(t["control"], t["risk"]) for t in tasks] == [("글 삭제", "submit")]


def test_duplicate_labels_in_one_screen_become_one_task():
    assert len(_tasks([_btn("카페정보"), _btn("카페정보\n새소식 3"), _btn("카페정보", visible=False)])) == 1


def test_global_nav_labels_only_read_controls_of_global_landmarks():
    snap = _snap(
        "/0moo",
        [
            _btn("카페정보", landmark="navigation"),
            _btn("글 삭제", landmark="navigation"),
            _btn("전체글보기", landmark="main"),
            _btn("숨김", landmark="banner", visible=False),
        ],
    )
    assert lab.global_nav_labels(snap, risk_of=tm.risk_of) == ["카페정보"]


# ── 빈도 규칙·병합·정리 ────────────────────────────────────────


def _nav_task(label, path):
    return _tasks([_btn(label)], path=path)[0]


def test_split_by_frequency_moves_only_repeated_read_navigation():
    tasks = [_nav_task("카페정보", p) for p in ("/a", "/b", "/c")] + [
        _nav_task("전체글보기", "/a"),
        _nav_task("글 삭제", "/a"),
        _nav_task("글 삭제", "/b"),
        _nav_task("글 삭제", "/c"),
    ]
    kept, labels = lab.split_by_frequency(tasks)
    assert labels == ["카페정보"]  # 3개 화면에 반복된 읽기 이동 버튼만
    assert sorted(t["control"] for t in kept) == [
        "글 삭제",
        "글 삭제",
        "글 삭제",
        "전체글보기",
    ]  # 위험 버튼은 반복돼도 남는다


def test_split_by_frequency_needs_enough_pages():
    tasks = [_nav_task("카페정보", "/a"), _nav_task("카페정보", "/b")]
    assert lab.split_by_frequency(tasks) == (tasks, [])


def test_merge_global_nav_is_additive_sorted_and_bounded():
    base = tm.empty_map(HOST, now=NOW)
    once = lab.merge_global_nav(base, ["나의활동", "카페정보"], now=NOW)
    assert once["global_nav"] == ["나의활동", "카페정보"] and once["global_nav_at"] == NOW
    assert lab.merge_global_nav(once, ["카페정보"], now="later") is once  # 새로 아는 것이 없으면 그대로
    many = lab.merge_global_nav(base, [f"메뉴{i:03d}" for i in range(100)], now=NOW)
    assert len(many["global_nav"]) == lab.GLOBAL_NAV_MAX


def _legacy(label_text, **over):
    t = _tasks([_btn(label_text)])[0]
    t.update(control=label_text, **over)  # 예전 형식: 원문 텍스트가 실행용 이름
    return t


def test_prune_legacy_removes_only_unverified_read_navigation_in_old_format_or_global():
    site_map = tm.empty_map(HOST, now=NOW)
    legacy = _legacy(MATE)
    verified = _legacy("네이버 메이트\n다른 줄", state="verified")
    human = _legacy("사람이 다룸\n두 번째 줄", purpose="공무 확인용")
    risky = _tasks([_btn("글 삭제")])[0]
    clean_global = _tasks([_btn("카페정보")])[0]
    clean_local = _tasks([_btn("전체글보기")], path="/b")[0]
    site_map["tasks"] = [legacy, verified, human, risky, clean_global, clean_local]
    site_map["global_nav"] = ["카페정보"]
    pruned, removed = lab.prune_legacy(site_map)
    assert removed == 2  # 예전 형식 1건 + 전역 메뉴 1건
    assert {t["id"] for t in pruned["tasks"]} == {verified["id"], human["id"], risky["id"], clean_local["id"]}


# ── 합치기 연동(탐색 실행) ─────────────────────────────────────


@pytest.fixture
def maps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")


def test_exploration_records_global_nav_once_and_keeps_screen_tasks(maps):
    menu = ["카페정보", "나의활동", MATE]
    snaps = [_snap(f"/0moo/{n}", [_btn(m) for m in menu] + [_btn(f"{n} 게시판 검색")]) for n in ("a", "b", "c", "d")]
    out = task_mapper.merge_snapshots(HOST, snaps, explored_pages=4)["map"]
    assert out["global_nav"] == sorted(["카페정보", "나의활동", "네이버 메이트"])
    assert sorted(t["control"] for t in out["tasks"]) == [
        f"{n} 게시판 검색" for n in ("a", "b", "c", "d")
    ]  # 화면마다 다른 것만 업무(16건 → 4건)
    assert all("\n" not in t["name"] for t in out["tasks"])


def test_single_page_record_does_not_guess_global_menu(maps):
    out = task_mapper.merge_snapshots(HOST, [_snap("/0moo", [_btn("카페정보"), _btn("전체글보기")])])[
        "map"
    ]  # 탐색 실행이 아닌 한 화면 기록
    assert "global_nav" not in out and len(out["tasks"]) == 2


def test_reexploration_cleans_legacy_but_keeps_verified(maps):
    old = tm.empty_map(HOST, now=NOW)
    old["tasks"] = [_legacy(MATE), _legacy("전체글보기\n(3)", state="verified")]
    store.save(old)
    out = task_mapper.merge_snapshots(HOST, [_snap(f"/p{n}", [_btn("카페정보")]) for n in range(3)], explored_pages=3)[
        "map"
    ]
    assert [t["control"] for t in out["tasks"]] == [
        "전체글보기\n(3)"
    ]  # 예전 형식 미검증 이동 업무와 전역 메뉴는 정리, 검증된 업무는 보존
    assert out["global_nav"] == ["카페정보"]
