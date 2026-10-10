"""NaverCafe 증분 수집 계층 테스트.

실제 네이버 접속 없음. FakePage / FakeRow 로 어댑터 목록 파싱을 흉내낸다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import pytest

from ai_orchestrator.sites import job_state, runner, session_manager
from ai_orchestrator.sites.adapters import naver_cafe_collection as nc
from ai_orchestrator.sites.adapters.naver_cafe_adapter import NaverCafeAdapter


# ── Fake DOM (test_naver_cafe_adapter.py 와 동일 패턴) ──────────
@dataclass
class FakeEl:
    text: str = ""
    attrs: dict = field(default_factory=dict)

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str:
        return self.attrs.get(name, "")


@dataclass
class FakeRow:
    link: FakeEl | None = None
    author: FakeEl | None = None
    date: FakeEl | None = None

    def query_selector(self, selector: str):
        if selector == NaverCafeAdapter.LINK_SELECTOR:
            return self.link
        if selector == NaverCafeAdapter.AUTHOR_SELECTOR:
            return self.author
        if selector == NaverCafeAdapter.DATE_SELECTOR:
            return self.date
        return None


@dataclass
class FakePage:
    url: str = ""
    visible_selectors: set = field(default_factory=set)
    rows: list = field(default_factory=list)
    history: list = field(default_factory=list)

    def goto(self, target: str) -> None:
        self.history.append(("goto", target))
        self.url = target

    def query_selector(self, selector: str):
        return object() if selector in self.visible_selectors else None

    def query_selector_all(self, selector: str):
        if selector == NaverCafeAdapter.ROW_SELECTOR:
            return list(self.rows)
        return []


# ── Fixtures ────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path / "secrets"))
    monkeypatch.setattr(job_state, "_JOBS_PATH", tmp_path / "site_jobs.jsonl")
    job_state.clear()
    session_manager.clear_meta_for_tests("naver_cafe")
    yield


def _fake_sleeper():
    def _sleep(_secs: float) -> None:
        return None

    return _sleep


def _counting_clock():
    n = {"v": 0}

    def clock() -> float:
        n["v"] += 1
        return float(n["v"])

    return clock


def _row(pid: str, title: str, author: str, date: str, href: str | None = None):
    href = href or f"/some_cafe/articles/{pid}"
    return FakeRow(
        link=FakeEl(text=title, attrs={"href": href}),
        author=FakeEl(text=author),
        date=FakeEl(text=date),
    )


def _logged_in_page(rows):
    return FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors={"a#gnb_logout_button"},
        rows=rows,
    )


# ────────────────────────────────────────────────────────────────
# 1) URL 빌더
# ────────────────────────────────────────────────────────────────
def test_build_board_url_requires_ids():
    with pytest.raises(ValueError):
        nc.build_board_url("", "1")
    with pytest.raises(ValueError):
        nc.build_board_url("1", "")


def test_build_board_url_includes_page_param():
    url = nc.build_board_url("111", "22", page=3)
    assert "search.clubid=111" in url
    assert "search.menuid=22" in url
    assert "search.page=3" in url
    assert url.startswith("https://cafe.naver.com/ArticleList.nhn?")


# ────────────────────────────────────────────────────────────────
# 2) post_id 파싱 안정성 (2가지 URL 케이스)
# ────────────────────────────────────────────────────────────────
def test_post_id_parsing_modern_and_legacy():
    adapter = NaverCafeAdapter()
    rows = [
        _row("101", "모던", "a", "2026.04.23.", href="/some_cafe/articles/101"),
        _row("202", "레거시", "b", "2026.04.22.", href="/ArticleRead.nhn?clubid=111&articleid=202"),
    ]
    page = _logged_in_page(rows)
    result = adapter.collect_list(page, cursor="https://cafe.naver.com/some_cafe", page_num=1, max_pages=1)
    ids = {it["post_id"] for it in result["items"]}
    assert ids == {"101", "202"}


# ────────────────────────────────────────────────────────────────
# 3) 기존 id 존재 시 중복 제거
# ────────────────────────────────────────────────────────────────
def test_filter_skips_known_ids():
    raw = [
        {"post_id": "1", "title": "a", "author": "x", "date": "d", "url": "u1"},
        {"post_id": "2", "title": "b", "author": "y", "date": "d", "url": "u2"},
        {"post_id": "3", "title": "c", "author": "z", "date": "d", "url": "u3"},
    ]
    new, skipped = nc.filter_new_posts(raw, existing={"2"})
    ids = {p["post_id"] for p in new}
    assert ids == {"1", "3"}
    assert skipped == 1
    # created_at 로 매핑됐는지
    assert all("created_at" in p for p in new)
    assert all("date" not in p for p in new)


# ────────────────────────────────────────────────────────────────
# 4) 신규 글만 필터링 (같은 호출 내 중복도 제거)
# ────────────────────────────────────────────────────────────────
def test_filter_deduplicates_within_batch():
    raw = [
        {"post_id": "9", "title": "t", "author": "a", "date": "d", "url": "u"},
        {"post_id": "9", "title": "t", "author": "a", "date": "d", "url": "u"},
        {"post_id": "", "title": "empty", "author": "a", "date": "d", "url": "u"},
    ]
    new, skipped = nc.filter_new_posts(raw, existing=set())
    assert [p["post_id"] for p in new] == ["9"]
    assert skipped == 2  # 1개 중복 + 1개 빈 id


# ────────────────────────────────────────────────────────────────
# 5) merge 로 저장 파일이 정상 축적 + 중복 제거
# ────────────────────────────────────────────────────────────────
def test_save_load_merge_roundtrip(tmp_path):
    path = tmp_path / "data" / "naver_cafe_posts.json"

    # 최초 쓰기
    rec0 = nc.load_stored(path)  # 파일 없음 → 빈 레코드
    assert rec0["posts"] == []

    batch1 = [
        {"post_id": "1", "title": "첫", "author": "a", "date": "2026.04.23.", "url": "u1"},
        {"post_id": "2", "title": "두", "author": "b", "date": "2026.04.22.", "url": "u2"},
    ]
    new1, _ = nc.filter_new_posts(batch1, existing=set())
    rec1 = nc.merge_record(rec0, new1, club_id="111", menu_id="22")
    nc.save_stored(path, rec1)

    # 재로드 + 두 번째 배치 (하나는 중복, 하나는 신규)
    rec2 = nc.load_stored(path)
    assert {p["post_id"] for p in rec2["posts"]} == {"1", "2"}
    assert rec2["club_id"] == "111"

    batch2 = [
        {"post_id": "2", "title": "두-업데이트", "author": "b", "date": "d", "url": "u2"},
        {"post_id": "3", "title": "세", "author": "c", "date": "d", "url": "u3"},
    ]
    existing = nc.existing_ids(rec2)
    new2, skipped = nc.filter_new_posts(batch2, existing)
    assert [p["post_id"] for p in new2] == ["3"]
    assert skipped == 1
    rec3 = nc.merge_record(rec2, new2, club_id="111", menu_id="22")
    nc.save_stored(path, rec3)

    # 최종: 3건, 중복 없음
    final = json.loads(path.read_text(encoding="utf-8"))
    assert final["site"] == "naver_cafe"
    assert final["club_id"] == "111"
    assert {p["post_id"] for p in final["posts"]} == {"1", "2", "3"}


# ────────────────────────────────────────────────────────────────
# 6) 세션 ACTIVE → 바로 수집 + 저장
# ────────────────────────────────────────────────────────────────
def test_active_session_collects_and_persists(tmp_path):
    adapter = NaverCafeAdapter()
    rows = [
        _row("10", "A", "auth1", "2026.04.23."),
        _row("11", "B", "auth2", "2026.04.23."),
    ]
    page = _logged_in_page(rows)
    store = tmp_path / "data" / "naver_cafe_posts.json"

    msg = nc.run_naver_cafe_collect_job(
        adapter,
        page,
        job_id="nc-collect-1",
        club_id="111",
        menu_id="22",
        store_path=store,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == "JOB_DONE"
    rec = json.loads(store.read_text(encoding="utf-8"))
    ids = {p["post_id"] for p in rec["posts"]}
    assert ids == {"10", "11"}
    # 두 번째 실행 — 신규 0건 (중복 제거 확인)
    msg2 = nc.run_naver_cafe_collect_job(
        adapter,
        FakePage(
            url="https://cafe.naver.com/some_cafe",
            visible_selectors={"a#gnb_logout_button"},
            rows=rows,
        ),
        job_id="nc-collect-2",
        club_id="111",
        menu_id="22",
        store_path=store,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg2 == "JOB_DONE"
    rec2 = json.loads(store.read_text(encoding="utf-8"))
    assert {p["post_id"] for p in rec2["posts"]} == {"10", "11"}


# ────────────────────────────────────────────────────────────────
# 7) 세션 만료 → PAUSED_FOR_REAUTH (자동 재로그인 없음)
# ────────────────────────────────────────────────────────────────
def test_expired_session_pauses(tmp_path):
    adapter = NaverCafeAdapter()
    page = FakePage()
    # goto 시 항상 로그인 페이지로 리다이렉트
    original_goto = page.goto

    def goto(target: str):
        original_goto(target)
        page.url = "https://nid.naver.com/nidlogin.login"

    page.goto = goto  # type: ignore[method-assign]

    store = tmp_path / "data" / "posts.json"
    msg = nc.run_naver_cafe_collect_job(
        adapter,
        page,
        job_id="nc-expired",
        club_id="111",
        menu_id="22",
        store_path=store,
        auto_reauth=False,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == runner.MSG_SESSION_EXPIRED
    rec = job_state.get("nc-expired")
    assert rec.status == "PAUSED_FOR_REAUTH"
    # 저장 파일은 만들어지지 않아야 한다
    assert not store.exists()


# ────────────────────────────────────────────────────────────────
# 8) 재인증 후 resume → 정상 수집
# ────────────────────────────────────────────────────────────────
def test_resume_after_reauth_collects(tmp_path):
    adapter = NaverCafeAdapter()

    # 최초 goto 에서는 로그인 페이지로 리다이렉트 → PAUSED.
    page = FakePage()
    state = {
        "logged_in": False,
        "rows": [
            _row("30", "X", "a", "2026.04.23."),
        ],
    }
    original_goto = page.goto

    def goto(target: str):
        original_goto(target)
        if state["logged_in"]:
            page.url = "https://cafe.naver.com/some_cafe"
            page.visible_selectors.add("a#gnb_logout_button")
            page.rows = list(state["rows"])
        else:
            page.url = "https://nid.naver.com/nidlogin.login"

    page.goto = goto  # type: ignore[method-assign]

    store = tmp_path / "data" / "posts.json"
    msg1 = nc.run_naver_cafe_collect_job(
        adapter,
        page,
        job_id="nc-resume",
        club_id="111",
        menu_id="22",
        store_path=store,
        auto_reauth=False,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg1 == runner.MSG_SESSION_EXPIRED
    assert job_state.get("nc-resume").status == "PAUSED_FOR_REAUTH"

    # 사람이 로그인 완료했다고 가정
    state["logged_in"] = True

    def _work_resume(p):
        record = nc.load_stored(store)
        outcome = nc.collect_new_posts(
            adapter,
            p,
            nc.existing_ids(record),
            club_id="111",
            menu_id="22",
            page_num=1,
            max_pages=1,
        )
        if outcome["new_posts"]:
            nc.save_stored(
                store,
                nc.merge_record(record, outcome["new_posts"], club_id="111", menu_id="22"),
            )
        return f"resumed new={len(outcome['new_posts'])}"

    msg2 = runner.resume_job(
        adapter,
        page,
        job_id="nc-resume",
        work=_work_resume,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg2 == "JOB_DONE"
    rec = json.loads(store.read_text(encoding="utf-8"))
    assert {p["post_id"] for p in rec["posts"]} == {"30"}


# ────────────────────────────────────────────────────────────────
# 9) 민감정보가 로그에 남지 않음
# ────────────────────────────────────────────────────────────────
def test_logs_do_not_leak_sensitive_tokens(caplog, tmp_path):
    caplog.set_level(logging.INFO)
    adapter = NaverCafeAdapter()
    rows = [_row("1", "t", "a", "d")]
    page = _logged_in_page(rows)
    store = tmp_path / "data" / "posts.json"

    nc.run_naver_cafe_collect_job(
        adapter,
        page,
        job_id="nc-log-check",
        club_id="111",
        menu_id="22",
        store_path=store,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    text = " ".join(r.getMessage() for r in caplog.records).lower()
    for forbidden in ("cookie:", "session=", "token=", "authorization:", "password", "otp"):
        assert forbidden not in text, f"로그에 민감 패턴 노출: {forbidden}"


# ────────────────────────────────────────────────────────────────
# 10) load_stored: 파손된 JSON 은 빈 레코드로 fallback
# ────────────────────────────────────────────────────────────────
def test_load_stored_handles_corrupt_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    rec = nc.load_stored(path)
    assert rec["posts"] == []
    assert rec["site"] == "naver_cafe"
