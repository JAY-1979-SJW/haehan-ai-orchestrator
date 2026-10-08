"""사이트 도구 공용 함수(N7 중복 통합) 시험 — 출력 문구·반환값이 통합 전과 같은지 확인."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from scripts.site_engine.catalog_helpers import load_or_build_catalog, print_keyed_summary, select_named_targets
from scripts.site_engine.execution_gate import matches_credential_extraction

# ── catalog_helpers ──────────────────────────────────────────────────


def test_load_or_build_catalog_reads_existing(tmp_path: Path) -> None:
    path = tmp_path / "cat.json"
    path.write_text(json.dumps({"a": 1}), encoding="utf-8")
    called: list[str] = []

    def build() -> dict:
        called.append("build")
        return {}

    out = load_or_build_catalog(path, tmp_path / "default.json", build, lambda c, p: None)
    assert out == {"a": 1}
    assert called == []


def test_load_or_build_catalog_builds_and_saves_default(tmp_path: Path) -> None:
    default = tmp_path / "default.json"
    saved: list[tuple[dict, Path]] = []
    out = load_or_build_catalog(None, default, lambda: {"built": True}, lambda c, p: saved.append((c, p)))
    assert out == {"built": True}
    assert saved == [({"built": True}, default)]


def test_select_named_targets() -> None:
    targets = {"mail": {"url": "m"}, "board": {"url": "b"}}
    assert select_named_targets(targets, None, "X") == targets
    assert select_named_targets(targets, "all", "X") is not targets
    assert select_named_targets(targets, " MAIL ", "X") == {"mail": {"url": "m"}}
    with pytest.raises(KeyError, match="unknown Hiworks service: nope"):
        select_named_targets(targets, "nope", "Hiworks service")


def test_print_keyed_summary_format(capsys: pytest.CaptureFixture[str]) -> None:
    print_keyed_summary(
        "Title",
        [{"key": "k1", "summary": {"a_total": 3}}, {"key": "k2"}],
        (("a", "a_total"), ("b", "b_total")),
        Path("out.json"),
    )
    assert capsys.readouterr().out.splitlines() == [
        "=" * 60,
        "Title",
        "=" * 60,
        "- k1: a=3 b=0",
        "- k2: a=0 b=0",
        f"saved: {Path('out.json')}",
    ]


def test_hiworks_and_naver_wrappers_keep_messages(capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.hiworks.actions import print_prepare_plan_summary
    from scripts.hiworks.service_explorer import selected_targets
    from scripts.naver.common.content import print_action_summary, select_targets

    print_prepare_plan_summary({"services": [{"key": "mail", "summary": {"fillable_inputs": 2, "buttons_gated": 1}}]})
    print_action_summary({"targets": [{"key": "blog", "summary": {"input_total": 4}}]}, Path("x.json"))
    lines = capsys.readouterr().out.splitlines()
    assert "Hiworks section prepare plan" in lines
    assert "- mail: fillable=2 blocked_inputs=0 buttons_cataloged=0 buttons_gated=1" in lines
    assert "Naver blog/cafe action catalog" in lines
    assert "- blog: inputs=4 buttons=0 submit_gated=0 unknown_gated=0" in lines
    with pytest.raises(KeyError, match="unknown Hiworks service: zzz"):
        selected_targets("zzz")
    with pytest.raises(KeyError, match="unknown Naver content target: zzz"):
        select_targets("zzz")


# ── execution_gate.matches_credential_extraction ─────────────────────


def test_matches_credential_extraction() -> None:
    cred = frozenset({"password"})
    extract = frozenset({"extract"})
    assert matches_credential_extraction("Extract_Password", cred, extract)
    assert not matches_credential_extraction("input_password", cred, extract)
    assert not matches_credential_extraction("extract_name", cred, extract)


# ── login_detector.manual_only_login (gabia/kakao auth.login) ────────


class _FakePage:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.visited: list[str] = []

    def goto(self, url: str, timeout: int) -> None:
        self.visited.append(url)
        if self.fail:
            raise RuntimeError("boom")


@pytest.mark.parametrize("site", ["gabia", "kakao"])
def test_site_login_manual_flow(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, site: str) -> None:
    import importlib

    from scripts.auth.login_detector import monitor_for_login

    auth = importlib.import_module(f"scripts.{site}.auth")
    monkeypatch.setattr(auth, "is_logged_in", lambda page: False)
    page = _FakePage(fail=True)
    with caplog.at_level(logging.DEBUG):
        out = auth.login(page)
    assert out == {
        "ok": False,
        "reason": "manual_login_required",
        "user": "",
        "needs_manual": True,
        "monitor": monitor_for_login,
    }
    assert len(page.visited) == 1
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith(f"{site}: 로그인 페이지 이동 실패: boom") for m in messages)
    assert f"{site}: 수동 로그인 대기 (최대 5분)" in messages


@pytest.mark.parametrize("site", ["gabia", "kakao"])
def test_site_login_reuses_session(monkeypatch: pytest.MonkeyPatch, site: str) -> None:
    import importlib

    auth = importlib.import_module(f"scripts.{site}.auth")
    monkeypatch.setattr(auth, "is_logged_in", lambda page: True)
    page = _FakePage()
    assert auth.login(page) == {"ok": True, "reason": "기존 세션 재사용", "user": "", "needs_manual": False}
    assert page.visited == []


# ── hanafax.excel_merge_fit ──────────────────────────────────────────


class _Col:
    """Excel COM Column 흉내 — ColumnWidth 는 일반 속성."""

    def __init__(self) -> None:
        self.ColumnWidth = 8.43


class _Cell:
    """Excel COM Cell 흉내 — Width(포인트) = 5 + 7 × 열의 ColumnWidth(선형)."""

    def __init__(self, col: _Col) -> None:
        self._col = col

    def __getattr__(self, name: str) -> float:
        if name == "Width":
            return 5.0 + 7.0 * self._col.ColumnWidth
        raise AttributeError(name)


class _Sheet:
    def __init__(self) -> None:
        self.cols: dict[int, _Col] = {}
        self.Columns = lambda col: self.cols.setdefault(col, _Col())
        self.Cells = lambda row, col: _Cell(self.Columns(col))


def test_calibrate_col_width_for_points_linear() -> None:
    from scripts.hanafax.excel_merge_fit import calibrate_col_width_for_points

    ws = _Sheet()
    calibrate_col_width_for_points(ws, 3, 75.0)
    assert ws.cols[3].ColumnWidth == pytest.approx(10.0)
