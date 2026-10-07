"""루트 호환 shim(1단계 분리)이 '파일 경로로 직접 실행·로드'되는 경로에서도 동작하는지 고정한다.

shim 은 import 때 sys.modules 를 실제 모듈로 바꿔치기한다. 그래서
① `python dashboard.py` 처럼 스크립트로 직접 실행하면 아무 일도 하지 않고,
② spec_from_file_location 으로 파일을 읽어 exec_module 한 객체에는 실제 모듈의 속성이 없다.
이 시험은 두 경로를 재현해 고친 뒤에도 유지되게 한다.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_shim_forwards_direct_execution(monkeypatch):
    """`python dashboard.py` → 실제 모듈의 `__main__` 블록(run_dashboard → Flask.run)까지 도달해야 한다."""
    import flask

    calls: list[dict] = []
    monkeypatch.setattr(flask.Flask, "run", lambda self, *a, **k: calls.append(k))
    monkeypatch.setattr(sys, "argv", ["dashboard.py"])
    with pytest.raises(SystemExit) as exc:  # 실제 서버가 끝나면 shim 도 정상 종료(코드 없음 = 0)한다
        runpy.run_path(str(ROOT / "dashboard.py"), run_name="__main__")
    assert exc.value.code in (None, 0)
    assert calls, "dashboard shim 이 직접 실행을 전달하지 않아 서버가 시작되지 않음"


def test_dashboard_shim_import_still_aliases_real_module():
    import dashboard
    import orchestrator_v1.monitoring.dashboard as real

    assert dashboard is real


def test_hiworks_inbox_route_loads_reader_through_the_root_shim(monkeypatch):
    """라우트는 루트의 hiworks_mail_reader.py 를 파일 경로로 읽는다 — shim 이어도 fetch_recent_mails 를 찾아야 한다(500 방지)."""
    import orchestrator_v1.inbox.hiworks_mail_reader as real
    from ai_orchestrator.connectors import hiworks_mail_router as r

    monkeypatch.setattr(real, "fetch_recent_mails", lambda limit=20: [{"subject": "ok"}])
    monkeypatch.setattr(r, "log_event", lambda *a, **k: None)
    out = r.api_inbox(limit=5, user={"actor": "a", "role": "admin"})
    assert out["ok"] is True and out["items"] == [{"subject": "ok"}]


@pytest.mark.parametrize("name", ["inbox_store", "monitor", "log_analyzer", "telegram_notifier", "notice_router"])
def test_other_root_shims_have_no_main_block_to_forward(name):
    """직접 실행을 전달해야 하는 `__main__` 블록이 dashboard 말고는 없는지 — 새로 생기면 이 시험이 알려 준다."""
    real = {
        "inbox_store": "orchestrator_v1/inbox/inbox_store.py",
        "monitor": "orchestrator_v1/monitoring/monitor.py",
        "log_analyzer": "orchestrator_v1/monitoring/log_analyzer.py",
        "telegram_notifier": "orchestrator_v1/monitoring/telegram_notifier.py",
        "notice_router": "orchestrator_v1/inbox/notice_router.py",
    }[name]
    assert "__main__" not in (ROOT / real).read_text(encoding="utf-8")
