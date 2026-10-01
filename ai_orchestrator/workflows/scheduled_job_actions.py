"""L6 — 예약 작업 허용 목록. 이 목록에 있는 작업만 예약·실행할 수 있다(저장된 문자열을 import 해 실행하지 않는다).

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
위험 등급은 `local_agent.action_risk_policy.classify_action(risk_action)` 으로 판정한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_BLOG_TARGET = "skyjwsin"


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    description: str
    risk_action: str  # classify_action 에 넘기는 이름
    needs_browser: bool
    validate: Callable[[dict[str, Any]], dict[str, Any]]
    run: Callable[[dict[str, Any]], str]


# ── 파라미터 검증 ────────────────────────────────────────────────────────


def _no_params(params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise ValueError("이 작업은 설정값이 없습니다")
    return {}


def _blog_target(params: dict[str, Any]) -> dict[str, Any]:
    from scripts.naver.blog.accounts import BLOG_ACCOUNTS

    extra = set(params) - {"target"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    target = str(params.get("target") or DEFAULT_BLOG_TARGET)
    if target not in BLOG_ACCOUNTS:
        raise ValueError(f"등록되지 않은 블로그 계정: {target}")
    return {"target": target}


# ── 실행 ────────────────────────────────────────────────────────────────


def _run_community(_: dict[str, Any]) -> str:
    from scripts.community.scheduler import run_all_sites

    report = run_all_sites("scheduled")
    sites, ok = report.get("site_count", 0), report.get("ok_count", 0)
    if sites == 0:
        return "등록된 커뮤니티 사이트가 없어 건너뜀"
    if ok == 0:
        first = next((r.get("error") for r in report.get("reports", []) if r.get("error")), "")
        raise RuntimeError(f"모든 사이트 수집 실패 ({sites}개): {first}")
    return f"{ok}/{sites} 사이트 수집·분석 완료"


def _run_naver_login_check(params: dict[str, Any]) -> str:
    from ai_orchestrator.workflows.naver_session_guard import default_deps, ensure_login

    result = ensure_login(params["target"], default_deps())
    if result["action"] in ("failed", "captcha"):
        raise RuntimeError(result["message"])
    return str(result["message"])


def _run_gonobi(_: dict[str, Any]) -> str:
    from scripts.naver.blog.gonobi.runner import run_scrape

    result = run_scrape(delay=0.8)
    return f"총 {result.total}건 · 신규 {result.new}건 · 오류 {result.errors}건"


ACTIONS: dict[str, ActionSpec] = {
    "community_analysis": ActionSpec(
        key="community_analysis",
        label="커뮤니티 자율 분석",
        description="등록된 커뮤니티 사이트를 수집하고 분석 리포트를 저장합니다.",
        risk_action="extract_text",
        needs_browser=True,
        validate=_no_params,
        run=_run_community,
    ),
    "naver_login_check": ActionSpec(
        key="naver_login_check",
        label="네이버 로그인 확인·자동 로그인",
        description="로그인 상태를 확인하고, 로그인돼 있지 않으면 자동으로 로그인합니다.",
        risk_action="detect_login_status",
        needs_browser=True,
        validate=_blog_target,
        run=_run_naver_login_check,
    ),
    "gonobi_collect": ActionSpec(
        key="gonobi_collect",
        label="gonobi 블로그 수집",
        description="gonobi 블로그의 새 글을 수집합니다.",
        risk_action="extract_text",
        needs_browser=False,
        validate=_no_params,
        run=_run_gonobi,
    ),
}


def get_action(key: str) -> ActionSpec | None:
    return ACTIONS.get(key)


def ensure_cdp() -> None:
    """브라우저(CDP, 9222)가 꺼져 있으면 기동한다. 이미 떠 있으면 아무것도 하지 않는다."""
    from scripts.cdp_force_start import _is_cdp_alive, cmd_start

    if _is_cdp_alive():
        return
    if cmd_start() != 0:
        raise RuntimeError("CDP 브라우저를 시작하지 못했습니다")


def catalog() -> list[dict[str, Any]]:
    """화면에 보여 줄 작업 목록(설정 항목 포함)."""
    items: list[dict[str, Any]] = []
    for spec in ACTIONS.values():
        fields: list[dict[str, Any]] = []
        if spec.validate is _blog_target:
            from scripts.naver.blog.accounts import BLOG_ACCOUNTS

            fields.append(
                {
                    "name": "target",
                    "label": "블로그 계정",
                    "type": "select",
                    "options": sorted(BLOG_ACCOUNTS),
                    "default": DEFAULT_BLOG_TARGET,
                }
            )
        items.append(
            {
                "key": spec.key,
                "label": spec.label,
                "description": spec.description,
                "needs_browser": spec.needs_browser,
                "fields": fields,
            }
        )
    return items
