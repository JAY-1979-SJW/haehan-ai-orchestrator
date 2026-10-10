"""L6 Business Workflows — 벤더 공식 API 목록 조회 (AI 허용 읽기 전용).

기준서: docs/specs/2026-10-04_ai_employee.md (E1)

`configs/vendor_apis.json` 을 읽기만 한다. 파일이 없거나 깨졌으면 조용히 빈 결과로 넘기지 않고 오류를 낸다
(AI 가 "공식 API 없음"으로 오해해 화면 자동화로 가는 것을 막는다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import vendor_directory as vd

_FILE = Path(__file__).resolve().parents[2] / "configs" / "vendor_apis.json"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError("벤더 공식 API 목록을 읽을 수 없습니다(configs/vendor_apis.json)") from e
    if not isinstance(data, dict) or not isinstance(data.get("vendors"), list):
        raise ValueError("벤더 공식 API 목록 형식이 올바르지 않습니다")
    return data


def lookup(query: str = "") -> dict[str, Any]:
    """검색어로 벤더 공식 API 를 찾는다. 결과가 없으면 found=false 로 알리고 '없다고 단정하지 말 것'을 함께 전한다."""
    query = str(query or "")[:100]
    items = vd.find_vendors(_load(), query)
    return {
        "query": query,
        "found": bool(items),
        "count": len(items),
        "vendors": [vd.describe(v) for v in items],
        "status_guide": vd.STATUS_GUIDE,
        "rule": vd.RULE,
        **({} if items else {"note": "목록에 없습니다. 공식 API 가 없다는 뜻은 아닙니다(미조사). 사이트 지도를 확인하고, 없으면 사용자에게 공식 문서 조사를 요청하세요."}),
    }
