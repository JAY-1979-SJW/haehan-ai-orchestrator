from scripts.eum.navigation import available_webman_codes, find_menu_by_code


def test_available_webman_codes_extracts_codes():
    menu = [
        {"menuNm": "A", "urlAddr": "/web/man/WEBMAN390M00"},
        {"menuNm": "B", "urlAddr": "/web/man/WEBMAN400M00"},
        {"menuNm": "C", "urlAddr": ""},
    ]

    assert available_webman_codes(menu) == {"WEBMAN390M00", "WEBMAN400M00"}


def test_find_menu_by_code():
    menu = [{"menuNm": "Install", "urlAddr": "/web/man/WEBMAN390M00"}]

    assert find_menu_by_code(menu, "WEBMAN390M00")["menuNm"] == "Install"
    assert find_menu_by_code(menu, "WEBMAN381M00") is None
