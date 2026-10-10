"""수동 통합 시험이 수집·자동 실행만으로 실제 브라우저를 건드리지 않는지 구조로 고정한다.

2026-10-05 실측: 사용자 9222 데몬 Chrome 에 Gmail 안내 페이지·YouTube 검색 탭이 반복해서 열리고 Chrome 이 사라졌다. 원인 중 하나가
`tests/integration/manual/` 의 시험이 파일 이름으로 직접 지정되면(영향 시험 선택) 수집돼 실제 `get_page()` 로 접속하던 것이다.
(이 시험은 브라우저를 실행하지 않는다 — 소스 구조와 훅 동작만 본다.)
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

MANUAL = Path(__file__).resolve().parent.parent / "integration" / "manual"
BROWSER_CALLS = ("get_page", "open_page", "goto", "connect_over_cdp", "sync_playwright", "close(")


def _manual_files() -> list[Path]:
    return sorted(p for p in MANUAL.glob("*.py") if p.name != "conftest.py")


def test_manual_files_have_no_import_time_browser_calls():
    files = _manual_files()
    assert files, "수동 시험 파일을 하나도 찾지 못했습니다(시험이 공허해짐)"
    for path in files:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
                continue
            src = ast.unparse(node)
            if "__main__" in src.split("\n", 1)[0]:
                continue  # `if __name__ == "__main__":` 아래는 직접 실행할 때만 돈다
            assert not any(call in src for call in BROWSER_CALLS), (
                f"{path.name}: 모듈 최상위에서 브라우저를 조작합니다(수집만 해도 실행됨): {src.splitlines()[0][:60]}"
            )


def _load_conftest():
    spec = importlib.util.spec_from_file_location("manual_conftest_under_test", MANUAL / "conftest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Item:
    def __init__(self, nodeid: str):
        self.nodeid = nodeid
        self.markers: list[object] = []

    def add_marker(self, marker):
        self.markers.append(marker)


def test_conftest_skips_manual_tests_even_when_named_explicitly(monkeypatch):
    conftest = _load_conftest()
    monkeypatch.delenv(conftest.RUN_MANUAL_ENV, raising=False)
    manual = _Item("tests/integration/manual/test_gmail.py::test_list_inbox")
    manual_win = _Item("tests\\integration\\manual\\test_gmail_direct.py::test_gmail_serial")
    other = _Item("tests/site_work/test_site_task_map.py::test_x")
    conftest.pytest_collection_modifyitems(None, [manual, manual_win, other])
    assert len(manual.markers) == 1 and len(manual_win.markers) == 1  # 건너뛰기 표시가 붙었다
    assert other.markers == []  # 다른 시험은 건드리지 않는다


def test_conftest_runs_manual_tests_only_when_explicitly_enabled(monkeypatch):
    conftest = _load_conftest()
    monkeypatch.setenv(conftest.RUN_MANUAL_ENV, "1")
    item = _Item("tests/integration/manual/test_gmail.py::test_list_inbox")
    conftest.pytest_collection_modifyitems(None, [item])
    assert item.markers == []
