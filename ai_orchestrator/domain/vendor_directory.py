"""L1 Shared Contracts — 벤더 공식 API 목록 조회 규칙 (순수 함수, 파일·네트워크 없음).

기준서: docs/specs/2026-10-04_ai_employee.md (E1)

`configs/vendor_apis.json` 의 항목을 검색어로 찾고, AI 에게 줄 요약으로 바꾼다. AI 는 읽기만 한다(목록 수정은 사람이 검토해서 한다).
상태 의미는 한 곳(STATUS_GUIDE)에 두어 AI 가 상태를 제멋대로 해석하지 않게 한다.
"""

from __future__ import annotations

from typing import Any

STATUS_GUIDE = {
    "available": "바로 쓸 수 있음 — 앱에 이미 연결돼 있다(list_api_endpoints 로 호출 방법 확인)",
    "registered": "앱 등록 완료 — 연결돼 있다(list_api_endpoints 로 확인)",
    "not_registered": "공식 API 는 있으나 아직 신청하지 않음 — 사용자에게 신청이 필요하다고 알린다(화면 조작으로 우회하지 않는다)",
    "paid_declined": "공식 API 는 있으나 유료라 사용하지 않기로 사용자가 결정함 — API 신청을 권하지 말고 사이트 지도(sitemap.lookup)의 화면 조작으로 처리한다. 최종 실행(송금·결제·서명·신고)은 사람이 한다",
    "unknown": "공식 API 가 확인되지 않았거나 미확인 — 사이트 지도(sitemap.lookup)로 처리하거나 탐색을 제안한다",
}
RULE = "공식 API 가 있으면 그것을 쓰고, 없을 때만 사이트 지도·화면 자동화를 쓴다. 이 목록은 낡았을 수 있으니 docs 주소로 최종 확인은 사람이 한다."
RESULT_LIMIT = 8
_FIELDS = ("name", "docs", "cost", "status", "auth", "supported", "not_supported", "caveats")


def _matches(vendor: dict[str, Any], terms: list[str]) -> bool:
    haystack = [str(k).lower() for k in vendor.get("keywords", [])] + [str(vendor.get("name", "")).lower()]
    return any(t in h or h in t for t in terms for h in haystack if h)


def find_vendors(raw: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """검색어(공백 구분, 부분일치)와 겹치는 벤더 요약. 검색어가 비면 전체의 이름·상태 요약."""
    vendors = [v for v in raw.get("vendors", []) if isinstance(v, dict)]
    terms = [t for t in query.lower().split() if t]
    if not terms:
        return [{"name": v.get("name", ""), "status": v.get("status", "unknown"), "docs": v.get("docs", "")} for v in vendors]
    found = [v for v in vendors if _matches(v, terms)]
    return [{field: v.get(field, [] if field in ("supported", "not_supported", "caveats") else "") for field in _FIELDS} for v in found[:RESULT_LIMIT]]


def describe(vendor: dict[str, Any]) -> dict[str, Any]:
    """상태 의미(AI 가 따를 행동)를 항목에 덧붙인다."""
    status = str(vendor.get("status") or "unknown")
    return dict(vendor, status_meaning=STATUS_GUIDE.get(status, STATUS_GUIDE["unknown"]))
