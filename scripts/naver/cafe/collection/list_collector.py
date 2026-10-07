"""Read-only Naver Cafe list collection helpers.

This module normalizes the Cafe home API response used by
``https://section.cafe.naver.com``. It does not launch or close browsers and
contains no state-changing actions.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import websocket  # type: ignore

from scripts.common.gate import check as gate_check
from scripts.naver.mail.read import cdp

CAFE_HOME_URL = "https://section.cafe.naver.com/ca-fe/home"
API_BASE = "https://apis.naver.com/cafe-home-web/cafe-home/v1/cafes"
API_TYPES = ("join", "favorite", "manage")


@dataclass(frozen=True)
class CafeListItem:
    cafe_id: int
    name: str
    cafe_url: str
    url: str
    new_articles: int = 0
    last_update_date: str = ""
    last_visit_date: str = ""
    favorite: bool = False
    manage: bool = False
    power: bool = False
    has_new_article: bool = False
    source: str = "join"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeListReport:
    ok: bool
    code: str = "ok"
    joined_total: int = 0
    favorite_total: int = 0
    manage_total: int = 0
    joined: list[CafeListItem] = field(default_factory=list)
    favorites: list[CafeListItem] = field(default_factory=list)
    manages: list[CafeListItem] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "joined_total": self.joined_total,
            "favorite_total": self.favorite_total,
            "manage_total": self.manage_total,
            "joined": [item.to_dict() for item in self.joined],
            "favorites": [item.to_dict() for item in self.favorites],
            "manages": [item.to_dict() for item in self.manages],
            "messages": list(self.messages),
        }


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def normalize_api_cafe(row: dict[str, Any], *, source: str = "join") -> CafeListItem:
    cafe_url = str(row.get("cafeUrl") or "").strip()
    return CafeListItem(
        cafe_id=_to_int(row.get("cafeId")),
        name=str(row.get("cafeName") or row.get("mobileCafeName") or "").strip(),
        cafe_url=cafe_url,
        url=f"https://cafe.naver.com/{cafe_url}" if cafe_url else "",
        new_articles=_to_int(row.get("articleNewCounts")),
        last_update_date=str(row.get("lastUpdateDate") or ""),
        last_visit_date=str(row.get("lastVisitDate") or ""),
        favorite=bool(row.get("favoriteCafe")),
        manage=bool(row.get("manageCafe")),
        power=bool(row.get("powerCafe")),
        has_new_article=bool(row.get("hasNewArticle")),
        source=source,
    )


def parse_api_payload(
    payload: dict[str, Any] | str, *, source: str = "join"
) -> tuple[list[CafeListItem], dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise ValueError("invalid_cafe_api_payload")
    if str(message.get("status") or "") != "200":
        raise ValueError("cafe_api_status_not_200")
    result = message.get("result") or {}
    cafes = result.get("cafes") or []
    page_info = result.get("pageInfo") or {}
    return [normalize_api_cafe(row, source=source) for row in cafes if isinstance(row, dict)], page_info


def build_report(raw: dict[str, Any]) -> CafeListReport:
    joined = [normalize_api_cafe(row, source="join") for row in raw.get("joined", [])]
    favorites = [normalize_api_cafe(row, source="favorite") for row in raw.get("favorites", [])]
    manages = [normalize_api_cafe(row, source="manage") for row in raw.get("manages", [])]
    return CafeListReport(
        ok=True,
        joined_total=_to_int(raw.get("joinTotal"), len(joined)),
        favorite_total=_to_int(raw.get("favoriteTotal"), len(favorites)),
        manage_total=_to_int(raw.get("manageTotal"), len(manages)),
        joined=joined,
        favorites=favorites,
        manages=manages,
        messages=["Collected Naver Cafe list through Cafe home read-only APIs."],
    )


def build_fetch_expression(*, per_page: int = 100) -> str:
    per_page = max(1, min(int(per_page), 100))
    return f"""
(async () => {{
  async function get(type, page = 1, perPage = {per_page}) {{
    const url = `{API_BASE}/${{type}}?page=${{page}}&perPage=${{perPage}}`;
    const r = await fetch(url, {{credentials: "include"}});
    const j = await r.json();
    const result = j && j.message && j.message.result || {{}};
    return {{pageInfo: result.pageInfo || {{}}, cafes: result.cafes || []}};
  }}
  async function all(type) {{
    const first = await get(type, 1, {per_page});
    const total = first.pageInfo.totalCount || first.cafes.length;
    const pages = Math.max(1, Math.ceil(total / {per_page}));
    let cafes = [...first.cafes];
    for (let p = 2; p <= pages; p++) {{
      cafes = cafes.concat((await get(type, p, {per_page})).cafes);
    }}
    return {{total, cafes}};
  }}
  const join = await all("join");
  const favorite = await all("favorite");
  const manage = await all("manage");
  return {{
    joinTotal: join.total,
    favoriteTotal: favorite.total,
    manageTotal: manage.total,
    joined: join.cafes,
    favorites: favorite.cafes,
    manages: manage.cafes,
    href: location.href,
    title: document.title
  }};
}})()
""".strip()


def evaluate_async(target_id: str, expr: str, *, port: int, timeout: float = 30.0) -> Any:
    for page in cdp.list_pages(port):
        if page.get("id") != target_id:
            continue
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=8, suppress_origin=True)
        try:
            event = cdp._send(  # type: ignore[attr-defined]
                ws,
                1,
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": True},
                timeout=timeout,
            )
        finally:
            ws.close()
        return event.get("result", {}).get("result", {}).get("value")
    raise RuntimeError("cdp_target_not_found")


def collect_cafe_list_from_target(
    target_id: str,
    *,
    port: int,
    per_page: int = 100,
    wait_s: float = 2.0,
) -> CafeListReport:
    gate_check("scan_page", context="naver_cafe_list_collect")
    cdp.navigate(target_id, CAFE_HOME_URL, port=port)
    time.sleep(max(0.0, wait_s))
    raw = evaluate_async(target_id, build_fetch_expression(per_page=per_page), port=port)
    if not isinstance(raw, dict):
        return CafeListReport(
            ok=False, code="invalid_fetch_result", messages=["Cafe API fetch did not return an object."]
        )
    return build_report(raw)
