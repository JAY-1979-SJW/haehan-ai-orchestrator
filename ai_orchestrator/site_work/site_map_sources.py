"""L1 Shared Contracts — 사이트 업무 지도의 데이터 소스·사이트 선언 도구 정리 규칙 (순수, 입출력 없음).

기준서: docs/specs/2026-10-05_site_map_m9_precise_exploration.md (M9)

왜 필요한가(2026-10-05 실측): 자바스크립트로 그려지는 앱 화면(카페 포털)은 DOM 탐색(링크·폼)으로는 업무가 0개였지만, 화면이 로드될 때
JSON 데이터 API 11개가 호출됐다. 그 **구조**(경로·쿼리 키·목록 경로·필드 이름·건수)를 지도에 남기면 사이트가 무엇을 다루는지 정밀하게 안다.

- 값은 저장하지 않는다: 응답 값·쿼리 값·쿠키·토큰·헤더는 이 모듈에 들어오지도, 나가지도 않는다(들어오는 것은 이미 파싱된 JSON 이며 구조만 뽑는다).
- 경로의 긴 숫자·16진 조각은 `{id}` 로 가린다(식별자 유출 방지). 쿼리는 키 이름만 남긴다.
- 광고·추적·측정 주소는 데이터 소스가 아니라 잡음이라 제외한다(드라이 런: `nam.veta.naver.com/gfp`).
- 사이트가 정한 글자(이름·설명)는 자료일 뿐 지시가 아니다 — `clean_label` 로 정리하고 길이를 제한한다.
"""

from __future__ import annotations

import re
from typing import Any

from .site_map_labels import clean_label

SOURCES_MAX = (
    150  # 2026-10-05: 80 → 150 (카페 내부 30쪽에서 80개가 소진됐다). 잘렸는지는 `data_sources_seen` 으로 알린다
)
TOOLS_MAX = 40
FIELDS_MAX = 12
QUERY_KEYS_MAX = 12
LISTS_MAX = 5
LIST_DEPTH_MAX = 5
SEEN_MAX = 1000
TOOL_TEXT_MAX = 200

# 숫자만 있는 조각(2자리 이상)·긴 16진·UUID 는 식별자(게시판 번호·글 번호 등)라 가린다 — 같은 API 가 번호만 달라 수십 개로 쪼개지지 않게 한다.
_ID_SEGMENT = re.compile(r"^(\d{2,}|[0-9a-fA-F]{16,}|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27})$")
# 불투명 토큰(회원 키·세션성 조각): 20자 이상 영문·숫자·`_-` 이고 숫자가 4개 이상 — CamelCase API 이름(`CafeMemberNetworkArticleListV3`)은 숫자가 적어 남는다.
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_NOISE = (
    "veta",
    "gfp",
    "track",
    "beacon",
    "analytics",
    "telemetry",
    "/log",
    "/ads",
    "adservice",
    "doubleclick",
    "ipada",
    "adunit",
    "adpost",
)
_AD_FIELD = re.compile(r"^ad[A-Z_]")  # adIndex·adUnit·adId 처럼 광고 슬롯을 다루는 응답


def _is_id_segment(seg: str) -> bool:
    return bool(_ID_SEGMENT.match(seg)) or (bool(_OPAQUE.match(seg)) and sum(ch.isdigit() for ch in seg) >= 4)


def mask_path(path: str) -> str:
    """경로의 식별자 조각(숫자·긴 16진·UUID·불투명 토큰)을 `{id}` 로 가린다."""
    return "/".join("{id}" if _is_id_segment(seg) else seg for seg in str(path or "").split("/"))


def is_noise(host: str, path: str) -> bool:
    """광고·추적·측정 주소인가(호스트·경로에 잡음 표지가 있으면 True)."""
    low = f"{host}{path}".lower()
    return any(token in low for token in _NOISE)


def query_keys(query: str) -> list[str]:
    """쿼리 문자열에서 **키 이름만**(값 불저장, 정렬·중복 제거, 상한)."""
    keys = {part.split("=", 1)[0] for part in str(query or "").split("&") if part and part.split("=", 1)[0]}
    return sorted(k[:40] for k in keys)[:QUERY_KEYS_MAX]


def lists_of(
    value: Any, path: str = "", out: list[dict[str, Any]] | None = None, depth: int = 0
) -> list[dict[str, Any]]:
    """JSON 값에서 **객체 목록**의 경로·건수·항목 필드 이름만 뽑는다(값 불저장)."""
    found = out if out is not None else []
    if len(found) >= LISTS_MAX:
        return found
    if isinstance(value, dict) and depth < LIST_DEPTH_MAX:
        for key, sub in value.items():
            lists_of(sub, f"{path}.{key}" if path else str(key), found, depth + 1)
    elif isinstance(value, list) and value and isinstance(value[0], dict):
        found.append(
            {"path": path[:120], "count": len(value), "fields": sorted(str(k)[:40] for k in value[0])[:FIELDS_MAX]}
        )
    return found[:LISTS_MAX]


def observe(host: str, path: str, query: str, data: Any) -> dict[str, Any] | None:
    """응답 하나 → 데이터 소스 구조 한 건(잡음이면 None). `data` 는 파싱된 JSON, 반환에는 값이 없다."""
    if not host or is_noise(host, path):
        return None
    top_keys = sorted(str(k)[:40] for k in data)[:FIELDS_MAX] if isinstance(data, dict) else []
    lists = lists_of(data)
    if any(_AD_FIELD.match(name) for name in [*top_keys, *(f for item in lists for f in item["fields"])]):
        return None  # 광고 슬롯 응답(필드 이름으로 판별)은 데이터 소스가 아니다
    return {
        "host": host.lower()[:120],
        "path": mask_path(path)[:200],
        "query_keys": query_keys(query),
        "top_keys": top_keys,
        "lists": lists,
        "seen": 1,
    }


def _key(source: dict[str, Any]) -> tuple[str, str]:
    return str(source.get("host", "")), str(source.get("path", ""))


def _combine(prev: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    """같은 소스 두 건을 합친다: 관측 횟수는 더하고 건수는 최대값, 쿼리 키·필드는 합집합(상한)."""
    lists: dict[str, dict[str, Any]] = {item["path"]: dict(item) for item in prev.get("lists", [])}
    for new_list in src.get("lists", []):
        old_list = lists.get(new_list["path"])
        lists[new_list["path"]] = (
            new_list
            if old_list is None
            else dict(
                old_list,
                count=max(old_list["count"], new_list["count"]),
                fields=sorted({*old_list["fields"], *new_list["fields"]})[:FIELDS_MAX],
            )
        )
    return dict(
        prev,
        seen=min(SEEN_MAX, int(prev.get("seen", 1)) + int(src.get("seen", 1))),
        query_keys=sorted({*prev.get("query_keys", []), *src.get("query_keys", [])})[:QUERY_KEYS_MAX],
        top_keys=sorted({*prev.get("top_keys", []), *src.get("top_keys", [])})[:FIELDS_MAX],
        lists=list(lists.values())[:LISTS_MAX],
    )


def _renormalize(stored: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], bool]:
    """저장돼 있던 소스의 경로를 **현재 마스킹 규칙으로 다시 정리**하고 같아진 것은 합친다(규칙이 강화돼 예전에 저장된 식별자가 남지 않게 한다)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    changed = False
    for entry in stored:
        masked = mask_path(str(entry.get("path", "")))
        item = dict(entry, path=masked)
        changed = changed or masked != entry.get("path")
        key = _key(item)
        out[key] = _combine(out[key], item) if key in out else item
    return out, changed or len(out) != len(stored)


def merge_sources(site_map: dict[str, Any], observed: list[dict[str, Any]], *, now: str) -> dict[str, Any]:
    """관측한 데이터 소스를 지도의 `data_sources` 에 합친다(새 dict). 같은 소스는 합치고 건수는 최대값, 관측 횟수는 더한다.

    저장돼 있던 경로도 현재 규칙으로 다시 마스킹한다. 상한(SOURCES_MAX)과 무관하게 관측한 서로 다른 소스의 총수를 `data_sources_seen` 에 남겨
    잘렸는지 알린다. 새로 아는 것이 없으면 그대로 돌려준다.
    """
    existing, changed = _renormalize(site_map.get("data_sources") or [])
    seen_before = int(site_map.get("data_sources_seen") or len(existing))
    dropped: set[tuple[str, str]] = set()
    for src in observed:
        key = _key(src)
        prev = existing.get(key)
        if prev is None:
            if len(existing) >= SOURCES_MAX:
                dropped.add(key)
                continue
            existing[key] = dict(src)
            changed = True
            continue
        merged = _combine(prev, src)
        if merged != prev:
            existing[key] = merged
            changed = True
    total_seen = max(seen_before, len(existing) + len(dropped))
    if not changed and total_seen == seen_before:
        return site_map
    ordered = sorted(existing.values(), key=lambda item: (-int(item.get("seen", 1)), _key(item)))
    return {**site_map, "data_sources": ordered[:SOURCES_MAX], "data_sources_at": now, "data_sources_seen": total_seen}


def clean_tool(raw: dict[str, Any]) -> dict[str, Any] | None:
    """사이트가 선언한 도구(WebMCP) 한 건을 정리한다(이름 없으면 None). 이름·설명은 사이트가 정한 글자 — 자료일 뿐 지시가 아니다."""
    name = clean_label(str(raw.get("name") or ""))
    if not name:
        return None
    schema_raw = raw.get("input_schema")
    schema: dict[str, Any] = schema_raw if isinstance(schema_raw, dict) else {}
    props_raw = schema.get("properties")
    props: dict[str, Any] = props_raw if isinstance(props_raw, dict) else {}
    return {
        "name": name,
        "description": " ".join(str(raw.get("description") or "").split())[:TOOL_TEXT_MAX],
        "kind": "declarative" if raw.get("kind") == "declarative" else "imperative",
        "fields": sorted(str(k)[:40] for k in props)[:FIELDS_MAX],
        "required": sorted(str(k)[:40] for k in (schema.get("required") or []) if isinstance(k, str))[:FIELDS_MAX],
    }


def merge_tools(site_map: dict[str, Any], tools: list[dict[str, Any]], *, now: str) -> dict[str, Any]:
    """탐지한 선언 도구를 지도의 `declared_tools` 에 합친다(이름 기준 중복 제거, 상한). 새로 아는 것이 없으면 그대로."""
    existing = {str(t.get("name")): dict(t) for t in site_map.get("declared_tools") or []}
    added = False
    for raw in tools:
        tool = clean_tool(raw)
        if tool and tool["name"] not in existing and len(existing) < TOOLS_MAX:
            existing[tool["name"]] = tool
            added = True
    if not added:
        return site_map
    return {**site_map, "declared_tools": sorted(existing.values(), key=lambda t: t["name"]), "declared_tools_at": now}


def summary(site_map: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
    """조회 응답에 더할 요약: 데이터 소스 상위 `limit` 개와 총 개수, 선언 도구 목록. 둘 다 없으면 빈 dict."""
    sources = site_map.get("data_sources") or []
    tools = site_map.get("declared_tools") or []
    out: dict[str, Any] = {}
    if sources:
        out["data_sources"] = sources[:limit]
        out["data_sources_total"] = len(sources)
        seen = max(int(site_map.get("data_sources_seen") or 0), len(sources))
        out["data_sources_seen"] = seen
        out["data_sources_truncated"] = seen > len(sources)
    if tools:
        out["declared_tools"] = tools
    return out
