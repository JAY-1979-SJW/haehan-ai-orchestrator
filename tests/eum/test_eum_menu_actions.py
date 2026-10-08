from scripts.eum.menu_actions import _abs_url, resolve_menu


def test_abs_url():
    assert _abs_url("/web/man/WEBMAN390M00") == "https://eum.cw.or.kr/web/man/WEBMAN390M00"
    assert _abs_url("https://x.test/a") == "https://x.test/a"


def test_resolve_menu_by_code_name_or_id():
    menu = [
        {"menuId": "M1", "menuNm": "단말기설치현황", "urlAddr": "/web/man/WEBMAN390M00"},
        {"menuId": "M2", "menuNm": "공지사항", "urlAddr": "/web/cen/WEBCEN010M00"},
    ]

    assert resolve_menu(menu, "WEBMAN390M00")["menuId"] == "M1"
    assert resolve_menu(menu, "단말기설치현황")["menuId"] == "M1"
    assert resolve_menu(menu, "M2")["menuNm"] == "공지사항"
    assert resolve_menu(menu, "missing") is None
