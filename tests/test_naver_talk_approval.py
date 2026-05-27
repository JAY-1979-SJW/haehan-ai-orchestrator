from scripts.naver import talk


class _FakeLocator:
    def __init__(self, calls):
        self.calls = calls
        self.first = self

    def click(self, timeout=0):
        self.calls.append(("click", timeout))

    def fill(self, value, timeout=0):
        self.calls.append(("fill", value, timeout))


class _FakePage:
    def __init__(self):
        self.calls = []

    def goto(self, url, timeout=0, wait_until=""):
        self.calls.append(("goto", url, timeout, wait_until))

    def get_by_text(self, text, exact=False):
        self.calls.append(("get_by_text", text, exact))
        return _FakeLocator(self.calls)

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return _FakeLocator(self.calls)


def test_naver_talk_confirm_requires_approval_token(monkeypatch):
    page = _FakePage()
    monkeypatch.setattr(talk, "ensure_naver_login", lambda page, return_url: {"ok": True})
    monkeypatch.setattr(talk, "handle_page_popups", lambda page, timeout_s: None)
    monkeypatch.setattr(talk.time, "sleep", lambda seconds: None)

    result = talk.NaverTalk(page).send_message("customer", "reply draft", confirm=True)

    assert result["ok"] is False
    assert result["mode"] == "filled_not_sent"
    assert result["error"] == "approval_required"
    assert not any(call == ("locator", 'button:has-text("전송"), .btn_send') for call in page.calls)


def test_naver_talk_send_with_approval_token_clicks_send(monkeypatch):
    page = _FakePage()
    monkeypatch.setattr(talk, "ensure_naver_login", lambda page, return_url: {"ok": True})
    monkeypatch.setattr(talk, "handle_page_popups", lambda page, timeout_s: None)
    monkeypatch.setattr(talk, "log_critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(talk.time, "sleep", lambda seconds: None)

    result = talk.NaverTalk(page).send_message(
        "customer",
        "reply draft",
        confirm=True,
        approval_confirm=talk.TALK_SEND_CONFIRM_TEXT,
    )

    assert result["ok"] is True
    assert result["mode"] == "sent"
    assert ("locator", 'button:has-text("전송"), .btn_send') in page.calls
