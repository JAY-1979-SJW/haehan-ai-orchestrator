"""MCP 도구 이름 단일 정의 — L1 Shared Contracts.

mcp_server.py(도구 등록)와 routers/ai_agent_router.py(claude -p --allowedTools 허용 목록)가
같은 이름을 각자 적어 어긋나는 것을 막기 위해 여기 한 곳에서 정의한다. `mcp` 패키지에
의존하지 않으므로 어떤 파이썬 환경에서도 import 된다.

서버에 등록된 실제 도구 집합과 ALL_TOOL_NAMES 의 일치는 tests/site_work/test_ai_agent_allowed_tools.py 가
검사한다(도구를 추가하면 여기 그룹에도 넣어야 통과).
"""

from __future__ import annotations

MCP_SERVER_NAME = "haehan-orchestrator"
MCP_TOOL_PREFIX = f"mcp__{MCP_SERVER_NAME}__"

# 조회(캐시/설정 읽기)
LOOKUP = ("list_products", "list_orders", "list_settlements", "list_reviews", "list_stats", "list_cafe_boards")
# CDP 수집 + 셀러센터 이동
COLLECT = (
    "collect_products",
    "collect_orders",
    "collect_settlements",
    "collect_reviews",
    "collect_stats",
    "open_seller_center",
)
# 앱 API/화면 범용 조작
PAGE = ("list_api_endpoints", "call_api", "snapshot_page", "act_on_page", "navigate_page")
# 상세설명 콘텐츠(내부 섹션 렌더러 — 외부 유료 AI 호출 없음)
CONTENT = ("generate_description", "render_description", "save_template", "list_templates", "get_template")
# 상품 등록·수정 — 임시저장까지만 진행, 최종 저장은 사용자가 직접
REGISTER = ("auto_register_product", "edit_product")
# 기본 허용에서 제외: 삭제/설정 변경은 명시 지시 시 allowed_tools 로 직접 열어야 한다
RESTRICTED = ("delete_template", "add_cafe_board")

DEFAULT_ALLOWED = (*LOOKUP, *COLLECT, *PAGE, *CONTENT, *REGISTER)
ALL_TOOL_NAMES = frozenset((*DEFAULT_ALLOWED, *RESTRICTED))


def qualified(names: tuple[str, ...]) -> list[str]:
    """claude --allowedTools 용 정식 이름(mcp__<서버>__<도구>)으로 변환."""
    return [MCP_TOOL_PREFIX + n for n in names]
