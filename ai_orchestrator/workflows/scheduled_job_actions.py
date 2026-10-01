"""L6 — 예약 작업 허용 목록. 이 목록에 있는 작업만 예약·실행할 수 있다(저장된 문자열을 import 해 실행하지 않는다).

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
위험 등급은 `local_agent.action_risk_policy.classify_action(risk_action)` 으로 판정한다.
`USER_DELEGATED`(발행·전송) 작업은 예약 시각마다 사용자가 승인해야 실행된다(services/scheduled_job_service).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_orchestrator.local_agent.action_risk_policy import GRADE_USER_DELEGATED, classify_action

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


MAX_TEXT = 1000
MAX_TITLE = 100
MAX_BODY = 20000
MAX_TAGS = 30
MAX_TAG_LEN = 40
VISIBILITIES = {"public": "전체 공개", "neighbors": "이웃 공개", "mutual": "서로이웃 공개", "private": "비공개"}


def _telegram_params(params: dict[str, Any]) -> dict[str, Any]:
    extra = set(params) - {"text"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    text = str(params.get("text") or "").strip()
    if not text:
        raise ValueError("보낼 문구를 입력하세요")
    if len(text) > MAX_TEXT:
        raise ValueError(f"문구는 {MAX_TEXT}자 이하여야 합니다")
    return {"text": text}


def _blog_publish_params(params: dict[str, Any]) -> dict[str, Any]:
    from scripts.naver.blog.accounts import BLOG_ACCOUNTS

    extra = set(params) - {"target", "title", "body", "tags", "visibility"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    target = str(params.get("target") or DEFAULT_BLOG_TARGET)
    if target not in BLOG_ACCOUNTS:
        raise ValueError(f"등록되지 않은 블로그 계정: {target}")
    title = str(params.get("title") or "").strip()
    if not title or len(title) > MAX_TITLE:
        raise ValueError(f"제목은 1~{MAX_TITLE}자여야 합니다")
    body = str(params.get("body") or "").strip()
    if not body or len(body) > MAX_BODY:
        raise ValueError(f"본문은 1~{MAX_BODY}자여야 합니다")
    raw_tags = params.get("tags") or ""
    tags = [t.strip() for t in (raw_tags.split(",") if isinstance(raw_tags, str) else raw_tags) if str(t).strip()]
    if len(tags) > MAX_TAGS or any(len(t) > MAX_TAG_LEN for t in tags):
        raise ValueError(f"태그는 {MAX_TAGS}개 이하, 각 {MAX_TAG_LEN}자 이하여야 합니다")
    visibility = str(params.get("visibility") or "public")
    if visibility not in VISIBILITIES:
        raise ValueError(f"공개 범위는 {sorted(VISIBILITIES)} 중 하나여야 합니다")
    return {"target": target, "title": title, "body": body, "tags": ", ".join(tags), "visibility": visibility}


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


def _run_telegram(params: dict[str, Any]) -> str:
    import html

    from ai_orchestrator.clients.telegram_sender import send_message

    result = send_message(html.escape(params["text"]))
    if result.get("skipped"):
        raise RuntimeError("텔레그램 설정(TELEGRAM_BOT_TOKEN·TELEGRAM_APPROVER_CHAT_ID)이 없어 보내지 못했습니다")
    if not result.get("ok"):
        # 오류 원문에는 요청 주소(토큰 포함)가 들어갈 수 있어 화면·기록에는 남기지 않는다(서버 로그에만 있음)
        raise RuntimeError("텔레그램 전송에 실패했습니다 (자세한 내용은 서버 로그)")
    return "텔레그램으로 보냈습니다"


def _run_blog_publish(params: dict[str, Any]) -> str:
    """대상 계정으로 로그인돼 있을 때만 발행한다. 다른 계정이거나 로그아웃이면 전환·로그인하지 않고 중단한다(세션 보존)."""

    def job() -> str:
        from scripts.naver.blog.automation.account_probe import alias_to_blog_id, read_alias
        from scripts.naver.blog.core.writer import write_post
        from scripts.web_connector import get_page

        page = get_page()
        alias = read_alias(page)
        if alias is None:
            raise RuntimeError("네이버에 로그인돼 있지 않아 발행하지 않았습니다 (먼저 \"네이버 로그인 확인\" 작업으로 로그인하세요)")
        if alias_to_blog_id(alias) != params["target"]:
            raise RuntimeError(f"대상 계정({params['target']})이 아닌 계정으로 로그인돼 있어 발행하지 않았습니다 (계정은 자동으로 전환하지 않습니다)")
        tags = [t.strip() for t in params["tags"].split(",") if t.strip()]
        result = write_post(
            page,
            title=params["title"],
            body=params["body"],
            tags=tags,
            auto_tags=False,
            visibility=params["visibility"],
            require_approval=False,  # 이 예약의 회차 승인이 발행 승인이다
        )
        if not result.get("ok"):
            raise RuntimeError("블로그 발행에 실패했습니다: " + str(result.get("error") or result.get("reason") or "")[:100])
        return f"발행했습니다 (글번호 {result.get('log_no') or '확인 안 됨'})"

    from scripts.web_connector import run_on_browser_thread

    return run_on_browser_thread(job, timeout=900)


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
    "telegram_notify": ActionSpec(
        key="telegram_notify",
        label="텔레그램 알림 보내기",
        description="정한 문구를 내 텔레그램으로 보냅니다. 실행 시각마다 앱에서 승인해야 전송됩니다.",
        risk_action="send_message",
        needs_browser=False,
        validate=_telegram_params,
        run=_run_telegram,
    ),
    "blog_publish": ActionSpec(
        key="blog_publish",
        label="네이버 블로그 발행",
        description="정한 제목·본문·태그로 블로그 글을 발행합니다. 실행 시각마다 앱에서 내용을 확인하고 승인해야 발행됩니다.",
        risk_action="blog_publish",
        needs_browser=True,
        validate=_blog_publish_params,
        run=_run_blog_publish,
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
        if spec.validate is _blog_publish_params:
            from scripts.naver.blog.accounts import BLOG_ACCOUNTS

            fields += [
                {"name": "target", "label": "블로그 계정", "type": "select", "options": sorted(BLOG_ACCOUNTS), "default": DEFAULT_BLOG_TARGET},
                {"name": "title", "label": "제목", "type": "line", "options": [], "default": ""},
                {"name": "body", "label": "본문", "type": "text", "options": [], "default": ""},
                {"name": "tags", "label": "태그 (쉼표로 구분)", "type": "line", "options": [], "default": ""},
                {
                    "name": "visibility",
                    "label": "공개 범위",
                    "type": "select",
                    "options": list(VISIBILITIES),
                    "option_labels": VISIBILITIES,
                    "default": "public",
                },
            ]
        if spec.validate is _telegram_params:
            fields.append(
                {"name": "text", "label": "보낼 문구", "type": "text", "options": [], "default": ""}
            )
        items.append(
            {
                "key": spec.key,
                "requires_approval": classify_action(spec.risk_action) == GRADE_USER_DELEGATED,
                "label": spec.label,
                "description": spec.description,
                "needs_browser": spec.needs_browser,
                "fields": fields,
            }
        )
    return items
