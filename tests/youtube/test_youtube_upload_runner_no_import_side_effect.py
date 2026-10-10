"""scripts.youtube.upload.runner — import 만으로 CDP 브라우저 연결이 생기면 안 된다.

재발방지 — IMPORT_TIME_SIDE_EFFECTS.md 조사(2026-10-10) 중 발견: 이 파일은 예전에
모듈 최상단에서 바로 `CDP()` 를 만들고 `atexit.register(cdp.close)` 까지 했다 —
`import scripts.youtube.upload.runner` 한 줄만으로 실제 CDP 브라우저 연결 시도가
일어나던 안티패턴(오늘 찾은 bearer resolver import-time 등록 결함과 같은 종류).
CDP 생성·실행은 `main()`(`if __name__ == "__main__":` 가드) 안으로 옮겼다 — 이
시험은 import 시점에 CDP 가 전혀 만들어지지 않는지 모킹으로 고정한다.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock


def test_import_does_not_create_cdp_connection(monkeypatch):
    fake_cdp_cls = MagicMock(name="CDP")
    monkeypatch.setitem(
        sys.modules,
        "scripts.browser.cdp.cdp_helper",
        type(sys)("scripts.browser.cdp.cdp_helper"),
    )
    sys.modules["scripts.browser.cdp.cdp_helper"].CDP = fake_cdp_cls
    sys.modules.pop("scripts.youtube.upload.runner", None)

    module = importlib.import_module("scripts.youtube.upload.runner")

    assert fake_cdp_cls.call_count == 0, "import 만 했는데 CDP() 가 생성됨"
    assert module.cdp is None, "import 직후 모듈 전역 cdp 는 아직 None 이어야 한다(main() 에서 생성)"

    sys.modules.pop("scripts.youtube.upload.runner", None)
