"""셀렉터 헬스체크 코어 테스트 (브라우저 없이 fake page 로 검증).

실제 CDP 없이도 판정 로직·선행조건 처리·리포트를 검증한다.
"""

from __future__ import annotations

import pytest

from tools.selector_health.core import (
    ERROR,
    HIDDEN,
    MISSING,
    OK,
    SKIPPED,
    SelectorCheck,
    SiteSpec,
    format_report,
    run_site_checks,
)


class FakeLocator:
    def __init__(self, total: int, visible: int, raise_on_count: bool = False):
        self._total = total
        self._visible = visible
        self._raise = raise_on_count

    def count(self):
        if self._raise:
            raise RuntimeError("bad selector")
        return self._total

    def nth(self, i):
        return _FakeNth(i < self._visible)

    @property
    def first(self):
        return _FakeNth(self._visible > 0)


class _FakeNth:
    def __init__(self, visible: bool):
        self._v = visible

    def is_visible(self, timeout=None):
        return self._v

    def click(self, timeout=None):
        return None


class FakePage:
    """selector -> (total, visible) 매핑으로 동작하는 가짜 페이지."""

    def __init__(self, table: dict[str, tuple[int, int]], bad: set[str] | None = None):
        self.table = table
        self.bad = bad or set()
        self.goto_called = []

    def goto(self, url, **kw):
        self.goto_called.append(url)

    def wait_for_timeout(self, ms):
        return None

    def locator(self, sel):
        if sel in self.bad:
            return FakeLocator(0, 0, raise_on_count=True)
        total, vis = self.table.get(sel, (0, 0))
        return FakeLocator(total, vis)


def _spec(checks, preconditions=None):
    return SiteSpec(
        key="t",
        title="테스트",
        url="https://example.test",
        checks=checks,
        preconditions=preconditions or {},
        settle_s=0,
    )


def test_present_and_visible_is_ok():
    page = FakePage({".a": (1, 1)})
    res = run_site_checks(page, _spec([SelectorCheck("A", ".a")]))
    assert res[0].status == OK
    assert res[0].is_problem is False


def test_missing_selector_detected():
    page = FakePage({})
    res = run_site_checks(page, _spec([SelectorCheck("A", ".gone")]))
    assert res[0].status == MISSING
    assert res[0].is_problem is True


def test_hidden_selector_detected_when_visibility_expected():
    page = FakePage({".h": (1, 0)})
    res = run_site_checks(page, _spec([SelectorCheck("H", ".h", expect="visible")]))
    assert res[0].status == HIDDEN
    assert res[0].is_problem is True


def test_hidden_is_ok_when_only_presence_expected():
    page = FakePage({".h": (1, 0)})
    res = run_site_checks(page, _spec([SelectorCheck("H", ".h", expect="present")]))
    assert res[0].status == OK
    assert res[0].is_problem is False


def test_error_selector_reported():
    page = FakePage({}, bad={".bad"})
    res = run_site_checks(page, _spec([SelectorCheck("B", ".bad")]))
    assert res[0].status == ERROR
    assert res[0].is_problem is True


def test_precondition_satisfied_runs_check():
    page = FakePage({".tag": (1, 1)})
    spec = _spec(
        [SelectorCheck("TAG", ".tag", requires="panel")],
        preconditions={"panel": lambda p: True},
    )
    res = run_site_checks(page, spec)
    assert res[0].status == OK


def test_precondition_failed_skips_not_false_alarm():
    """선행조건 미충족은 MISSING 이 아니라 SKIPPED — 오탐 방지 핵심."""
    page = FakePage({})
    spec = _spec(
        [SelectorCheck("TAG", ".tag", requires="panel")],
        preconditions={"panel": lambda p: False},
    )
    res = run_site_checks(page, spec)
    assert res[0].status == SKIPPED
    assert res[0].is_problem is False


def test_precondition_exception_skips():
    def boom(p):
        raise RuntimeError("no panel")

    page = FakePage({})
    spec = _spec([SelectorCheck("T", ".t", requires="p")], preconditions={"p": boom})
    res = run_site_checks(page, spec)
    assert res[0].status == SKIPPED


def test_undefined_precondition_skips():
    page = FakePage({})
    spec = _spec([SelectorCheck("T", ".t", requires="없는조건")])
    res = run_site_checks(page, spec)
    assert res[0].status == SKIPPED


def test_report_contains_counts_and_problem_total():
    page = FakePage({".a": (1, 1)})
    spec = _spec([SelectorCheck("A", ".a"), SelectorCheck("B", ".gone")])
    res = run_site_checks(page, spec)
    txt = format_report(spec, res)
    assert "총 2건" in txt
    assert "문제 1건" in txt


def test_registered_specs_load():
    """등록된 사이트 명세가 정상 로드되고 필수 필드를 갖는지."""
    from tools.selector_health import load_specs

    specs = load_specs()
    assert "naver_blog" in specs
    sp = specs["naver_blog"]
    assert sp.checks, "체크 항목이 비어 있다"
    # 발행 패널 선행조건이 정의돼 있어야 태그 셀렉터를 오탐하지 않는다
    reqs = {c.requires for c in sp.checks if c.requires}
    assert reqs <= set(sp.preconditions), f"선행조건 미정의: {reqs - set(sp.preconditions)}"


@pytest.mark.parametrize("name", ["TAG_INPUT"])
def test_tag_input_requires_publish_panel(name):
    """2026-08-14 사고 재발 방지: 태그 입력창은 발행 패널 안에만 있다."""
    from tools.selector_health import load_specs

    c = next(c for c in load_specs()["naver_blog"].checks if c.name == name)
    assert c.requires == "publish_panel"
