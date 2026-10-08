from scripts.eum.capabilities import _web_code, build_capabilities, find_capability, save_capabilities


def test_web_code_extracts_known_prefixes():
    assert _web_code("https://eum.cw.or.kr/web/man/WEBMAN390M00") == "WEBMAN390M00"
    assert _web_code("/web/cen/WEBCEN100M00") == "WEBCEN100M00"
    assert _web_code("/main") is None


def test_build_capabilities_summarizes_pages():
    source = {
        "pages": [
            {
                "ok": True,
                "menuId": "M1",
                "menuNm": "단말기설치현황",
                "url": "https://eum.cw.or.kr/web/man/WEBMAN390M00",
                "title": "단말기설치현황",
                "bodyTextSample": "단말기 조회 초기화 엑셀",
                "inputs": [{"visible": True, "id": "x"}, {"visible": False, "id": "hidden"}],
                "buttons": [{"visible": True, "text": "조회"}, {"visible": True, "text": "엑셀"}],
                "tables": [{"headers": ["NO", "단말기번호"]}],
            },
            {"ok": False, "menuNm": "bad"},
        ]
    }

    result = build_capabilities(source)

    assert result["page_count"] == 1
    item = result["capabilities"][0]
    assert item["code"] == "WEBMAN390M00"
    assert item["category"] == "terminal"
    assert item["input_count"] == 1
    assert item["actions"]["search"] is True
    assert item["actions"]["excel"] is True


def test_find_capability(monkeypatch, tmp_path):
    path = tmp_path / "caps.json"
    save_capabilities(
        {
            "capabilities": [
                {
                    "code": "WEBMAN390M00",
                    "menu_name": "단말기설치현황",
                    "url": "https://eum.cw.or.kr/web/man/WEBMAN390M00",
                }
            ]
        },
        path,
    )

    assert find_capability("WEBMAN390M00", path)["menu_name"] == "단말기설치현황"
    assert find_capability("설치현황", path)["code"] == "WEBMAN390M00"
    assert find_capability("missing", path) is None
