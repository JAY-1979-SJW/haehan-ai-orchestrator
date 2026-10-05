"""tests/ 공용 픽스처 — 격리된 헤드리스 Chrome(외부 접속·사용자 9222 브라우저 없음).

`browser` 는 모듈 범위이며 이 픽스처를 쓰는 시험만 Chrome 을 띄운다. 못 띄우는 환경에서는 그 시험만 건너뛴다.
(각 시험 파일이 같은 픽스처를 복사해 두던 것을 한곳으로 모았다 — audit-kit DUP-02.)
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        instance = pw.chromium.launch(channel="chrome", headless=True)
    except Exception as exc:  # noqa: BLE001 - Chrome 을 못 띄우는 환경은 이 시험만 건너뛴다
        pw.stop()
        pytest.skip(f"헤드리스 Chrome 을 띄울 수 없음: {type(exc).__name__}")
    yield instance
    instance.close()
    pw.stop()
