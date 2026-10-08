"""Naver Cafe main page read-only collector and action catalog."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from scripts.common.gate import check as gate_check
from scripts.naver.mail.read import cdp
from scripts.naver.cafe import list_collector

CAFE_HOME_URL = "https://section.cafe.naver.com/ca-fe/home"
API_ROOT = "https://apis.naver.com/cafe-home-web/cafe-home"

READONLY_ENDPOINTS: dict[str, str] = {
    "user": "/v1/member/identifier",
    "home": "/v1/homepc",
    "recent_visit": "/v1/home/visitcafes",
    "feed_substitute": "/v1/feed-substitute?count=6",
    "recommend": "/v2/cafes/recommend",
    "power_cafes": "/v1/powercafes",
    "mynews": "/v12/mynews",
    "note_count": "/v1/member/note-count",
    "notices": "/v1/cafe-notices?page=1",
}


@dataclass(frozen=True)
class CafeMainFeature:
    key: str
    label: str
    kind: str
    supported: bool
    read_only: bool = True
    approval_required: bool = False
    approval_gate: str = ""
    method: str = "GET"
    endpoint_hint: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeMainActionPlan:
    action: str
    label: str
    approval_gate: str
    approval_required: bool = True
    final_submit_blocked: bool = True
    safe_to_prepare: bool = True
    method_hint: str = "POST"
    endpoint_hint: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CafeMainReport:
    ok: bool
    code: str = "ok"
    href: str = ""
    title: str = ""
    user: dict[str, Any] = field(default_factory=dict)
    endpoint_statuses: dict[str, dict[str, Any]] = field(default_factory=dict)
    sections: dict[str, Any] = field(default_factory=dict)
    features: list[CafeMainFeature] = field(default_factory=list)
    action_plans: list[CafeMainActionPlan] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "href": self.href,
            "title": self.title,
            "user": self.user,
            "endpoint_statuses": self.endpoint_statuses,
            "sections": self.sections,
            "features": [feature.to_dict() for feature in self.features],
            "action_plans": [plan.to_dict() for plan in self.action_plans],
            "messages": list(self.messages),
        }


def _message_result(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    if str(message.get("status") or "") != "200":
        return None
    return message.get("result")


def _cafes(rows: Any, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [list_collector.normalize_api_cafe(row, source=source).to_dict() for row in rows if isinstance(row, dict)]


def _articles_from_mynews(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    messages = ((result.get("myNewsActivities") or {}).get("messages") or [])
    out: list[dict[str, Any]] = []
    for row in messages[:30]:
        if not isinstance(row, dict):
            continue
        view = row.get("view") or {}
        web = row.get("webDirection") or {}
        direction = row.get("direction") or {}
        out.append({
            "category": row.get("category", ""),
            "message_key": row.get("messageKey", ""),
            "header": view.get("header", ""),
            "content": view.get("content", ""),
            "cafe_name": view.get("cafeName", ""),
            "write_time": view.get("writeTime", ""),
            "unread": bool(view.get("unread")),
            "url": web.get("url", ""),
            "cafe_id": direction.get("cafeId", ""),
            "article_id": direction.get("articleId", ""),
        })
    return out


def _notices(result: Any) -> list[dict[str, Any]]:
    rows = result.get("notices") if isinstance(result, dict) else []
    out: list[dict[str, Any]] = []
    for row in (rows or [])[:20]:
        if not isinstance(row, dict):
            continue
        out.append({
            "notice_id": row.get("noticeId", ""),
            "subject": row.get("subject", ""),
            "created_at": row.get("createdAt", "") or row.get("regDate", ""),
        })
    return out


def build_feature_catalog() -> list[CafeMainFeature]:
    return [
        CafeMainFeature("user_status", "로그인/사용자 식별", "read", True, endpoint_hint="/v1/member/identifier"),
        CafeMainFeature("my_cafes", "내 카페", "read", True, endpoint_hint="/v1/homepc,/v1/cafes/join"),
        CafeMainFeature("favorite_cafes", "즐겨찾는 카페", "read", True, endpoint_hint="/v1/cafes/favorite"),
        CafeMainFeature("manage_cafes", "관리 카페", "read", True, endpoint_hint="/v1/cafes/manage"),
        CafeMainFeature("recent_visit", "최근 방문 카페", "read", True, endpoint_hint="/v1/home/visitcafes"),
        CafeMainFeature("recommend_cafes", "추천 카페", "read", True, endpoint_hint="/v2/cafes/recommend"),
        CafeMainFeature("power_cafes", "파워 카페", "read", True, endpoint_hint="/v1/powercafes"),
        CafeMainFeature("feed_substitute", "피드 설정 후보", "read", True, endpoint_hint="/v1/feed-substitute"),
        CafeMainFeature("mynews", "내 소식", "read", True, endpoint_hint="/v12/mynews"),
        CafeMainFeature("note_count", "쪽지 수", "read", True, endpoint_hint="/v1/member/note-count"),
        CafeMainFeature("service_notices", "카페 공지", "read", True, endpoint_hint="/v1/cafe-notices"),
        CafeMainFeature(
            "favorite_toggle",
            "카페 즐겨찾기 변경",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_favorite_update",
            method="POST/DELETE",
            endpoint_hint="/v1/config/favorite-cafes",
        ),
        CafeMainFeature(
            "group_update",
            "카페 그룹 편집",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_group_update",
            method="POST/PUT/DELETE",
            endpoint_hint="/v1/config/cafe-groups,/v1/config/join-cafes/groups",
        ),
        CafeMainFeature(
            "mail_reception_toggle",
            "카페 메일 수신 변경",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_mail_reception_update",
            method="PUT",
        ),
        CafeMainFeature(
            "mynews_update",
            "내 소식 읽음/삭제/알림 설정",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_mynews_update",
            method="PUT/DELETE",
            endpoint_hint="/v1/mynews,/v1/mynews/comment-configs,/v1/mynews/notice-alarm",
        ),
        CafeMainFeature(
            "feed_config_update",
            "피드 키워드/메뉴/멤버 설정",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_feed_config_update",
            method="POST/PUT/DELETE",
            endpoint_hint="/settings/feed",
        ),
        CafeMainFeature(
            "join_or_leave",
            "카페 가입/탈퇴",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_membership_update",
            method="POST/DELETE",
        ),
        CafeMainFeature(
            "create_cafe",
            "카페 만들기",
            "write",
            True,
            read_only=False,
            approval_required=True,
            approval_gate="naver_cafe_create",
            method="POST",
            endpoint_hint="/v2/create-cafes",
        ),
    ]


def prepare_main_action(action: str, **fields: Any) -> CafeMainActionPlan:
    catalog = {feature.key: feature for feature in build_feature_catalog()}
    feature = catalog.get(action)
    if feature is None or feature.read_only:
        raise ValueError(f"unsupported_state_changing_cafe_main_action:{action}")
    return CafeMainActionPlan(
        action=action,
        label=feature.label,
        approval_gate=feature.approval_gate,
        method_hint=feature.method,
        endpoint_hint=feature.endpoint_hint,
        fields={k: v for k, v in fields.items() if v not in (None, "")},
        steps=[
            "Collect current Cafe main page state read-only.",
            f"Prepare {feature.label} with supplied fields.",
            f"Require approval gate {feature.approval_gate} before any state-changing request.",
            "Block final submit by default.",
        ],
        warnings=["This plan does not execute the state-changing action."],
    )


def build_fetch_expression() -> str:
    endpoint_json = __import__("json").dumps(READONLY_ENDPOINTS, ensure_ascii=False)
    return f"""
(async () => {{
  const apiRoot = "{API_ROOT}";
  const endpoints = {endpoint_json};
  const responses = {{}};
  for (const [key, path] of Object.entries(endpoints)) {{
    try {{
      const response = await fetch(apiRoot + path, {{credentials: "include"}});
      const text = await response.text();
      let json = null;
      try {{ json = JSON.parse(text); }} catch (e) {{}}
      responses[key] = {{
        ok: response.ok,
        httpStatus: response.status,
        contentType: response.headers.get("content-type") || "",
        payload: json,
        textSample: json ? "" : text.slice(0, 500)
      }};
    }} catch (e) {{
      responses[key] = {{ok: false, error: String(e)}};
    }}
  }}
  return {{href: location.href, title: document.title, responses}};
}})()
""".strip()


def build_report(raw: dict[str, Any]) -> CafeMainReport:
    responses = raw.get("responses") if isinstance(raw, dict) else {}
    responses = responses if isinstance(responses, dict) else {}
    results = {key: _message_result((row or {}).get("payload")) for key, row in responses.items() if isinstance(row, dict)}
    home = results.get("home") if isinstance(results.get("home"), dict) else {}
    my_cafe = home.get("myCafe") if isinstance(home, dict) else {}
    recommend = results.get("recommend") if isinstance(results.get("recommend"), dict) else {}
    power = results.get("power_cafes") if isinstance(results.get("power_cafes"), dict) else {}
    recent = results.get("recent_visit") if isinstance(results.get("recent_visit"), dict) else {}
    feed = results.get("feed_substitute") if isinstance(results.get("feed_substitute"), dict) else {}
    mynews = results.get("mynews") if isinstance(results.get("mynews"), dict) else {}
    notices = results.get("notices") if isinstance(results.get("notices"), dict) else {}

    sections = {
        "my_cafes": _cafes((my_cafe or {}).get("cafes"), source="home"),
        "recent_visit_cafes": _cafes(((recent or {}).get("recentlyVisitCafe") or {}).get("cafes"), source="recent_visit"),
        "recommend_cafes": _cafes((recommend or {}).get("cafes"), source="recommend"),
        "recommend_themes": (recommend or {}).get("themes", []),
        "power_cafes": _cafes((power or {}).get("cafes"), source="power"),
        "feed_configurable_menus": (feed or {}).get("feedConfigurableMenus", []),
        "feed_themes": (feed or {}).get("themes", []),
        "mynews_counts": (mynews or {}).get("myNewsCounts", {}),
        "mynews_items": _articles_from_mynews(mynews),
        "note_count": results.get("note_count"),
        "service_notices": _notices(notices),
    }
    statuses = {
        key: {
            "ok": bool((row or {}).get("ok")),
            "http_status": (row or {}).get("httpStatus"),
            "message_status": (((row or {}).get("payload") or {}).get("message") or {}).get("status"),
            "error": (row or {}).get("error", ""),
        }
        for key, row in responses.items()
        if isinstance(row, dict)
    }
    return CafeMainReport(
        ok=True,
        href=str(raw.get("href") or ""),
        title=str(raw.get("title") or ""),
        user=results.get("user") if isinstance(results.get("user"), dict) else {},
        endpoint_statuses=statuses,
        sections=sections,
        features=build_feature_catalog(),
        action_plans=[
            prepare_main_action("favorite_toggle"),
            prepare_main_action("group_update"),
            prepare_main_action("mail_reception_toggle"),
            prepare_main_action("mynews_update"),
            prepare_main_action("feed_config_update"),
            prepare_main_action("join_or_leave"),
            prepare_main_action("create_cafe"),
        ],
        messages=["Collected Naver Cafe main page read-only APIs and built state-changing action plans."],
    )


def collect_main_from_target(target_id: str, *, port: int) -> CafeMainReport:
    gate_check("scan_page", context="naver_cafe_main_collect")
    cdp.navigate(target_id, CAFE_HOME_URL, port=port)
    raw = list_collector.evaluate_async(target_id, build_fetch_expression(), port=port, timeout=40.0)
    if not isinstance(raw, dict):
        return CafeMainReport(ok=False, code="invalid_fetch_result", messages=["Cafe main fetch did not return an object."])
    return build_report(raw)


def execute_main_action_plan(plan: CafeMainActionPlan, *, force: bool = False) -> dict[str, Any]:
    gate_check(plan.approval_gate, risk="approve", force=force, cafe_action=plan.action)
    return {"ok": False, "blocked": plan.final_submit_blocked, "plan": plan.to_dict()}
