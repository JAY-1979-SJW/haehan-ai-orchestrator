"""스마트스토어 로그인 상태 판정 — site_registry._smartstore_is_logged_in 이 넘기는
raw 프로브(현재 URL/제목/본문에서 뽑은 마커)를 해석한다.

marker 필드(site_registry.py 의 page.evaluate 결과와 1:1 대응):
  naverLogin  — 로그인 폼/문구 감지
  smartstore  — 스마트스토어센터 화면 문구 감지
  sellerCenter— 판매자센터 도메인/문구 감지
  challenge   — 보안문자·차단·비정상 접근 문구 감지
"""

from __future__ import annotations

from typing import Any


def classify_probe(raw: dict[str, Any]) -> dict[str, Any]:
    markers = raw.get("markers") or {}
    naver_login = bool(markers.get("naverLogin"))
    smartstore = bool(markers.get("smartstore"))
    seller_center = bool(markers.get("sellerCenter"))
    challenge = bool(markers.get("challenge"))

    if challenge:
        return {"logged_in": False, "reason": "challenge_detected"}
    if naver_login and not (smartstore or seller_center):
        return {"logged_in": False, "reason": "login_form_shown"}
    if smartstore or seller_center:
        return {"logged_in": True, "reason": "smartstore_center_markers"}
    return {"logged_in": False, "reason": "unknown_state"}
