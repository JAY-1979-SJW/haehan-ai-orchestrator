"""Manual/integration tests — excluded from automated pytest collection.

These tests require a live browser session, Gmail login, or external
network access and must be run explicitly by a developer, not by CI.

`collect_ignore_glob` 는 폴더 단위 수집에서만 막는다 — 파일 이름을 직접 넘기면(예: verify_change 의 영향 시험 선택) 그대로 수집돼
사용자 9222 브라우저를 실제로 조작한다(2026-10-05 실측: Gmail 안내 페이지 이동). 그래서 수집돼도 건너뛴다.
실제로 실행하려면 `HAEHAN_RUN_MANUAL=1` 을 켠다.
"""

import os

import pytest

collect_ignore_glob = ["*.py"]

RUN_MANUAL_ENV = "HAEHAN_RUN_MANUAL"


def pytest_collection_modifyitems(config, items):
    if os.environ.get(RUN_MANUAL_ENV) == "1":
        return
    skip = pytest.mark.skip(reason=f"수동 통합 시험 — 실제 9222 브라우저를 조작합니다. {RUN_MANUAL_ENV}=1 로만 실행")
    for item in items:
        if "integration/manual/" in str(item.nodeid).replace("\\", "/"):
            item.add_marker(skip)
