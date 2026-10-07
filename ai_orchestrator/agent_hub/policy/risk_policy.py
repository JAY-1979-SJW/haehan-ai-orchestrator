"""로컬 에이전트 액션 risk 정책 정의 (Stage 1/2 공용).

로컬 에이전트(Windows PC)에서 지원 가능한 액션들의 위험도(risk_level)를
중앙에서 관리한다. 미등록 액션은 UNKNOWN_ACTION으로 거절된다.

이 모듈은 로컬 에이전트 task risk 평가 및 approval gate를 위한
정책만 포함한다. 웹 브라우징 액션의 requires_approval는
agent 패키지의 action_registry 모듈에서 별도로 관리된다.

risk_level 분류:
  - low: 즉시 실행 가능, 승인 불필요
    (ping, system_info, list_allowed_apps, open_url, browser.*inspect/plan_*)
  - medium: 큐 대기, 기본 검증
    (list_files_readonly, browser.execute_click/execute_type)
  - high: 승인 대기, approval token 필수
    (capture_screenshot, open_url_execute)
"""

# 액션 → risk_level 매핑
ACTION_RISK: dict[str, str] = {
    "ping": "low",
    "system_info": "low",
    "list_allowed_apps": "low",
    "open_url": "low",
    "web_open_url_readonly": "low",
    "open_url_execute": "high",
    "list_files_readonly": "medium",
    "capture_screenshot": "high",
    "ws_noop": "low",
    "safe_echo": "low",
    "safe_desktop_capability": "low",
    "safe_app_presence_known_paths": "low",
    "safe_app_capability_matrix": "low",
    # ── CAD 읽기 액션 (local_worker / AutoCAD COM) ────────────────────
    "detect_cad_apps": "low",
    "check_cad_app_status": "low",
    "search_drawings": "low",
    "read_layers": "low",
    "read_blocks": "low",
    "read_block_references": "low",
    "read_entities": "low",
    "read_texts": "low",
    "read_geometry": "low",
    "read_dimensions": "low",
    "read_modelspace": "low",
    "cad_inventory_collect": "medium",
    "cad_inventory_collect_and_push": "medium",
    # browser automation actions (BROWSER-4E)
    "browser.inspect": "low",
    "browser.plan_click": "low",
    "browser.plan_type": "low",
    "browser.plan_submit": "low",
    "browser.plan_open_url": "low",
    "browser.execute_click": "medium",
    "browser.execute_type": "medium",
    "browser.open_url_controlled": "medium",
    "browser.open_click_close_controlled": "medium",
    "browser.open_type_close_controlled": "medium",
    # Claude Code 헤드리스 트리거 (docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md §5.1)
    # medium: 큐 대기, 기본 검증만 — 이 액션 자체는 "Claude Code 세션 하나를 돌린다"일 뿐이고,
    # 실제 쓰기 작업(발행/발송/삭제 등)은 이 액션과 무관하게 gates/approval.py 승인을 그대로 거친다.
    "run_claude_agent": "medium",
}

# 서버가 즉시 응답 가능한 액션 (PC 의존 없음)
_SERVER_AUTO_COMPLETE: frozenset[str] = frozenset(
    {
        "ping",
        "system_info",
        "list_allowed_apps",
    }
)

# 허용된 PC 측 앱 (실제 실행은 browser/open_url 만 가능)
ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
