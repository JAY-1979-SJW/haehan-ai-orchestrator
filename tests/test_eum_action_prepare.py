from scripts.eum import deregistration, registration


class _FakeLocator:
    def count(self):
        return 1


class _FakePage:
    def __init__(self, menu=None):
        self.fills = []
        self.clicks = []
        self.gotos = []
        self.menu = menu

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append((url, wait_until, timeout))

    def fill(self, selector, value):
        self.fills.append((selector, value))

    def locator(self, selector):
        return _FakeLocator()

    def click(self, selector):
        self.clicks.append(selector)

    def wait_for_selector(self, selector, timeout=None):
        return True

    def evaluate(self, script):
        return self.menu or []


class _CountLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    def count(self):
        return self._count

    def inner_text(self, timeout=None):
        return self._text


class _SelectorPage:
    def __init__(self, visible_selectors):
        self.visible_selectors = set(visible_selectors)
        self.fills = []
        self.clicks = []
        self.gotos = []

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append((url, wait_until, timeout))

    def wait_for_load_state(self, state, timeout=None):
        return True

    def fill(self, selector, value):
        self.fills.append((selector, value))

    def locator(self, selector):
        if selector == "body":
            return _CountLocator(1, "")
        return _CountLocator(1 if selector in self.visible_selectors else 0)

    def click(self, selector):
        self.clicks.append(selector)

    def evaluate(self, script, arg=None):
        return None


def test_register_device_prepares_without_submit(monkeypatch):
    page = _FakePage([{"urlAddr": "/web/man/WEBMAN381M00"}])
    monkeypatch.setattr(registration, "get_page", lambda: page)
    monkeypatch.setattr(registration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(registration._time, "sleep", lambda seconds: None)

    result = registration.register_device("P-001", "Project", "D-001", "Seoul")

    assert result["success"] is True
    assert result["prepared"] is True
    assert result["submitted"] is False
    assert page.fills
    assert page.clicks == []


def test_register_device_clicks_only_when_submit_true(monkeypatch):
    page = _FakePage([{"urlAddr": "/web/man/WEBMAN381M00"}])
    monkeypatch.setattr(registration, "get_page", lambda: page)
    monkeypatch.setattr(registration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(registration._time, "sleep", lambda seconds: None)

    result = registration.register_device("P-001", "Project", "D-001", "Seoul", submit=True)

    assert result["submitted"] is True
    assert page.clicks


def test_deregister_device_prepares_without_submit(monkeypatch):
    page = _FakePage([{"urlAddr": "/web/man/WEBMAN382M00"}])
    monkeypatch.setattr(deregistration, "get_page", lambda: page)
    monkeypatch.setattr(deregistration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(deregistration.time, "sleep", lambda seconds: None)

    result = deregistration.deregister_device("D-001")

    assert result["success"] is True
    assert result["prepared"] is True
    assert result["submitted"] is False
    assert page.fills
    assert page.clicks == []


def test_deregister_device_clicks_only_when_submit_true(monkeypatch):
    page = _FakePage([{"urlAddr": "/web/man/WEBMAN382M00"}])
    monkeypatch.setattr(deregistration, "get_page", lambda: page)
    monkeypatch.setattr(deregistration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(deregistration.time, "sleep", lambda seconds: None)

    result = deregistration.deregister_device("D-001", submit=True)

    assert result["submitted"] is True
    assert page.clicks


def test_register_device_uses_direct_page_even_when_menu_unavailable(monkeypatch):
    page = _FakePage([{"urlAddr": "/web/man/WEBMAN390M00"}])
    monkeypatch.setattr(registration, "get_page", lambda: page)
    monkeypatch.setattr(registration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(registration._time, "sleep", lambda seconds: None)

    result = registration.register_device("P-001", "Project", "D-001", "Seoul")

    assert result["success"] is True
    assert result["prepared"] is True
    assert page.gotos


def test_register_device_uses_form_analysis_selectors(monkeypatch, tmp_path):
    analysis_path = tmp_path / "form_analysis.json"
    analysis_path.write_text(
        """
{
  "WEBMAN381M00": {
    "url": "https://eum.cw.or.kr/web/man/WEBMAN381M00",
    "fields": [
      {"id": "menuSearchKeyowrd", "selector": "#menuSearchKeyowrd", "placeholder": "menu"},
      {"id": "projectCode", "selector": "#projectCode", "label": "project"},
      {"id": "terminalNo", "selector": "#terminalNo", "label": "terminal"},
      {"id": "location", "selector": "#location", "label": "location"}
    ],
    "buttons": [
      {"text": "닫기", "selector": "#close"},
      {"text": "Save", "selector": "#save"}
    ]
  }
}
""",
        encoding="utf-8",
    )
    page = _SelectorPage(["#projectCode", "#terminalNo", "#location", "#save"])
    monkeypatch.setattr(registration, "FORM_ANALYSIS_PATH", analysis_path)
    monkeypatch.setattr(registration, "get_page", lambda: page)
    monkeypatch.setattr(registration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(registration._time, "sleep", lambda seconds: None)

    result = registration.register_device("P-001", "Project", "D-001", "Seoul", submit=True)

    assert result["success"] is True
    assert ("#projectCode", "P-001") in page.fills
    assert ("#terminalNo", "D-001") in page.fills
    assert ("#location", "Seoul") in page.fills
    assert page.clicks == ["#save"]


def test_deregister_device_uses_form_analysis_selectors(monkeypatch, tmp_path):
    analysis_path = tmp_path / "form_analysis.json"
    analysis_path.write_text(
        """
{
  "WEBMAN382M00": {
    "url": "https://eum.cw.or.kr/web/man/WEBMAN382M00",
    "fields": [
      {"id": "menuSearchKeyowrd", "selector": "#menuSearchKeyowrd", "placeholder": "menu"},
      {"id": "terminalNo", "selector": "#terminalNo", "label": "terminal"},
      {"id": "removeDate", "selector": "#removeDate", "label": "remove date"}
    ],
    "buttons": [
      {"text": "닫기", "selector": "#close"},
      {"text": "Remove", "selector": "#remove"}
    ]
  }
}
""",
        encoding="utf-8",
    )
    page = _SelectorPage(["#terminalNo", "#removeDate", "#remove"])
    monkeypatch.setattr(deregistration, "FORM_ANALYSIS_PATH", analysis_path)
    monkeypatch.setattr(deregistration, "get_page", lambda: page)
    monkeypatch.setattr(deregistration, "ensure_logged_in", lambda page: True)
    monkeypatch.setattr(deregistration.time, "sleep", lambda seconds: None)

    result = deregistration.deregister_device("D-001", "2026-05-13", submit=True)

    assert result["success"] is True
    assert ("#terminalNo", "D-001") in page.fills
    assert ("#removeDate", "2026-05-13") in page.fills
    assert page.clicks == ["#remove"]
