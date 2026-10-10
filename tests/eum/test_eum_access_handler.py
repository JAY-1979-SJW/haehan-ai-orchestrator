"""EUM 접근 차단 복구 — 결과 로그가 op_log 정본 함수로 남는다.

배경: handle_access_block 은 끝에서 `log.op(...)` 를 불렀지만 `get_logger()` 가 돌려주는 logging.Logger 에는
op 메서드가 없어 복구 결과를 돌려주기 직전에 항상 AttributeError 로 끝났다(S2 이동으로 mypy 가 타입을 보게 되며 발견).
"""

from __future__ import annotations

from scripts.eum import access_handler


class _FakePage:
    def __init__(self) -> None:
        self.reloaded = False

    def click(self, selector: str) -> None:
        return None

    def reload(self) -> None:
        self.reloaded = True

    def query_selector(self, selector: str):
        return None  # 차단 메시지가 더 이상 없다 = 복구됨


def test_handle_access_block_records_result_with_op_log(monkeypatch):
    monkeypatch.setattr(access_handler.time, "sleep", lambda seconds: None)
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(access_handler, "log_op", lambda name, **kw: calls.append((name, kw)))
    page = _FakePage()

    result = access_handler.handle_access_block(page, "access_blocked", target_button="확인")

    assert page.reloaded
    assert result["recovered"] is True
    assert calls == [("eum_access_recovery", {"ok": True, "category": "access_blocked", "retries": 0, "error": ""})]
