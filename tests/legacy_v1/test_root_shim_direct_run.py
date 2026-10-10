"""루트 호환 shim(1단계 분리)이 '파일 경로로 직접 실행·로드'되는 경로에서도 동작하는지 고정한다.

dashboard.py 는 f933506d(루트 shim 19개 제거)로 완전히 삭제됐고 module_boundaries 도
dashboard.py 참조를 뺐다 — 그 shim 전용 시험 2개는 더는 의미가 없어 제거했다. 남은 hiworks·
기타 root shim(hiworks_mail_reader.py, inbox_store.py 등)은 그대로 있어 그 시험들은 유지한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_hiworks_inbox_route_loads_reader_through_the_root_shim(monkeypatch):
    """라우트는 루트의 hiworks_mail_reader.py 를 파일 경로로 읽는다 — shim 이어도 fetch_recent_mails 를 찾아야 한다(500 방지)."""
    import orchestrator_v1.inbox.hiworks_mail_reader as real
    from ai_orchestrator.connectors.hiworks import mail_router as r

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
