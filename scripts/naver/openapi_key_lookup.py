"""네이버 개발자센터 — 등록된 애플리케이션의 Client ID/Secret 조회 (CDP, 읽기 전용).

새 앱을 만드는 게 아니라 이미 등록된 앱(예: 해한AI검색)의 키를 읽어와
다른 PC의 userData/.env 설정에 그대로 재사용하기 위한 용도.

Client Secret 은 화면에서 "보기" 버튼을 눌러야 노출되는 값이라
반드시 caller 가 사용자 확인을 받은 뒤 confirm_secret_reveal=True 로 호출해야 한다.
반환값은 호출자가 로그/콘솔에 출력하지 않는다는 전제(CLAUDE.md 보안 금지선).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.cdp_helper import CDP  # noqa: E402


def lookup_naver_openapi_keys(app_id: str, confirm_secret_reveal: bool) -> dict:
    """등록된 애플리케이션의 Client ID(+ 확인 시 Secret)를 조회.

    Args:
        app_id: 개발자센터 애플리케이션 ID (Client ID 그 자체, URL 경로에 쓰임)
        confirm_secret_reveal: True 여야 Client Secret "보기"를 클릭한다.
            False 면 Client ID만 반환(민감값 노출 없음).
    """
    cdp = CDP(port=9222)
    try:
        cdp.navigate(f"https://developers.naver.com/apps/#/myapps/{app_id}/overview")
        time.sleep(2)

        url = cdp.js("location.href")
        if app_id not in url:
            return {"ok": False, "error": "navigate_failed", "hint": "로그인 세션이 만료되었을 수 있습니다"}

        client_id = _read_row_value(cdp, "Client ID")
        if not client_id:
            return {"ok": False, "error": "client_id_not_found"}

        result = {"ok": True, "client_id": client_id}

        if confirm_secret_reveal:
            cdp.js('document.querySelector(".button-green-o").click()')
            time.sleep(1)
            client_secret = _read_row_value(cdp, "Client Secret")
            if client_secret:
                result["client_secret"] = client_secret

        return result
    finally:
        cdp.close()


def _read_row_value(cdp: CDP, label: str) -> str:
    js = f"""
    (function() {{
      var els = Array.from(document.querySelectorAll("*")).filter(e =>
        e.childNodes.length && Array.from(e.childNodes).some(n =>
          n.nodeType === 3 && n.textContent.trim() === {label!r}));
      if (!els.length) return "";
      var row = els[0].closest("div").parentElement;
      var input = row.querySelector("input.inp");
      return input ? input.value : "";
    }})()
    """
    return cdp.js(js) or ""
