from scripts.eum.access_explorer import _absolute_url, explore_accessible_pages


class _FakePage:
    def __init__(self):
        self.urls = []

    def evaluate(self, script):
        if "header.shared.menuList" in script:
            return [
                {"menuId": "1", "menuNm": "A", "menuLvVl": 3, "urlAddr": "/web/man/WEBMAN390M00"},
                {"menuId": "2", "menuNm": "B", "menuLvVl": 3, "urlAddr": ""},
            ]
        return {
            "url": self.urls[-1],
            "title": "T",
            "readyState": "complete",
            "inputs": [],
            "buttons": [],
            "tables": [],
        }

    def goto(self, url, wait_until=None, timeout=None):
        self.urls.append(url)

    def wait_for_load_state(self, state, timeout=None):
        return None


def test_absolute_url():
    assert _absolute_url("/web/man/WEBMAN390M00") == "https://eum.cw.or.kr/web/man/WEBMAN390M00"


def test_explore_accessible_pages_uses_live_menu(monkeypatch):
    monkeypatch.setattr("scripts.eum.access_explorer.time.sleep", lambda seconds: None)
    page = _FakePage()

    result = explore_accessible_pages(page)

    assert result["explored_count"] == 1
    assert page.urls == ["https://eum.cw.or.kr/web/man/WEBMAN390M00"]
