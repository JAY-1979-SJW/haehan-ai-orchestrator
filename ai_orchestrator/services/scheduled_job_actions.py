"""L6 — 예약 작업 허용 목록. 이 목록에 있는 작업만 예약·실행할 수 있다(저장된 문자열을 import 해 실행하지 않는다).

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
위험 등급은 `contracts.action_risk_policy.classify_action(risk_action)` 으로 판정한다.
`USER_DELEGATED`(발행·전송) 작업은 예약 시각마다 사용자가 승인해야 실행된다(services/scheduled_job_service).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_USER_DELEGATED,
    classify_action,
)

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


def _mail_account_params(params: dict[str, Any]) -> dict[str, Any]:
    """네이버 메일 작업 공통: 대상 계정(등록된 네이버 계정만)."""
    return _blog_target(params)


def _mail_fetch_params(params: dict[str, Any]) -> dict[str, Any]:
    extra = set(params) - {"target", "unseen_only", "limit"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    base = _blog_target({"target": params["target"]} if "target" in params else {})
    unseen = params.get("unseen_only", True)
    if isinstance(unseen, str):
        unseen = unseen.strip().lower() not in ("false", "0", "no", "all")
    try:
        limit = int(params["limit"]) if params.get("limit") not in (None, "") else 20
    except (TypeError, ValueError) as e:
        raise ValueError("가져올 개수는 숫자여야 합니다") from e
    if not 1 <= limit <= 50:
        raise ValueError("가져올 개수는 1~50 이어야 합니다")
    return {**base, "unseen_only": bool(unseen), "limit": limit}


def _mail_send_params(params: dict[str, Any]) -> dict[str, Any]:
    from scripts.naver.mail.imap import sender

    extra = set(params) - {"target", "to", "subject", "body"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    base = _blog_target({"target": params["target"]} if "target" in params else {})
    to = sender.parse_recipients(str(params.get("to") or ""))
    subject, body = sender.validate_content(str(params.get("subject") or ""), str(params.get("body") or ""))
    return {**base, "to": ", ".join(to), "subject": subject, "body": body}


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
    from ai_orchestrator.connectors.naver_auth.session_guard import (
        default_deps,
        ensure_login,
    )

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

    from ai_orchestrator.core.telegram_sender import send_message

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
        from scripts.browser.cdp.connection import get_page
        from scripts.naver.blog.automation.account_probe import (
            alias_to_blog_id,
            read_alias,
        )
        from scripts.naver.blog.core.writer import write_post

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

    from scripts.browser.cdp.connection import run_on_browser_thread

    return run_on_browser_thread(job, timeout=900)


def _in_new_tab(fn: Callable[[Any], Any]) -> Any:
    """공유 CDP 연결에서 새 탭을 열어 `fn(page)` 를 실행하고 탭을 닫는다(사용자가 보던 탭은 건드리지 않는다)."""

    def job() -> Any:
        import contextlib

        from scripts.browser.cdp.connection import open_page

        page = open_page(allow_new_tab=True, reason="naver-mail-imap-setting")
        try:
            return fn(page)
        finally:
            with contextlib.suppress(Exception):  # 탭 정리 실패는 결과에 영향 없음
                page.close()

    from scripts.browser.cdp.connection import run_on_browser_thread

    return run_on_browser_thread(job, timeout=180)


def _run_naver_mail_check(params: dict[str, Any]) -> str:
    """웹메일 'IMAP/SMTP 사용' 설정 상태 + IMAP/SMTP 로그인 점검(읽기 전용). 하나라도 안 되면 해결 방법과 함께 실패로 기록."""
    from scripts.naver.mail.imap import protocol, settings

    account = params["target"]
    state = _in_new_tab(settings.read_state)
    protocol_result = protocol.check(account)
    enabled = {True: "사용함", False: "사용 안 함"}.get(state["enabled"], "확인 못함(" + str(state["reason"]) + ")")
    line = f"웹메일 IMAP/SMTP 설정: {enabled} | " + protocol.describe(protocol_result)
    if state["enabled"] is False:
        raise RuntimeError(line + " → '네이버 메일 IMAP/SMTP 켜기' 작업을 실행(승인)하세요")
    if not protocol_result["ok"]:
        raise RuntimeError(line)
    return line


def _run_naver_mail_enable(params: dict[str, Any]) -> str:
    """웹메일에서 'IMAP/SMTP 사용'을 '사용함'으로 저장한다(이미 사용함이면 변경 없음). 승인 후에만 실행된다."""
    from scripts.naver.mail.imap import settings

    account = params["target"]
    result = _in_new_tab(lambda page: settings.enable(page, account))
    reasons = {
        "not_logged_in": "네이버에 로그인돼 있지 않아 설정을 바꾸지 않았습니다(먼저 '네이버 로그인 확인' 작업으로 로그인하세요)",
        "page_not_ready": "설정 화면을 읽지 못해 바꾸지 않았습니다(화면 구조가 바뀌었을 수 있습니다)",
        "other_account": f"다른 계정({result.get('account')})으로 로그인돼 있어 바꾸지 않았습니다(계정은 자동 전환하지 않습니다)",
        "not_saved": "저장했지만 반영이 확인되지 않았습니다. 네이버 메일 환경설정을 직접 확인하세요",
    }
    if not result["ok"]:
        raise RuntimeError(reasons.get(result["reason"], "설정을 켜지 못했습니다: " + str(result["reason"])))
    return "이미 사용함으로 설정돼 있습니다(변경 없음)" if not result["changed"] else "IMAP/SMTP 를 '사용함'으로 저장하고 반영을 확인했습니다"


def _run_naver_mail_fetch(params: dict[str, Any]) -> str:
    """IMAP 으로 받은편지함 최근 메일 헤더를 읽는다(읽음 표시는 바뀌지 않는다)."""
    from scripts.naver.mail.imap import reader

    result = reader.list_messages(params["target"], unseen_only=params["unseen_only"], limit=params["limit"])
    if not result["ok"]:
        raise RuntimeError(reader.describe(result))
    return reader.describe(result)


def _run_naver_mail_send(params: dict[str, Any]) -> str:
    """SMTP 로 메일 1통을 보낸다. 회차 승인을 받은 뒤에만 호출된다."""
    from scripts.naver.mail.imap import sender

    result = sender.send_mail(params["target"], params["to"], params["subject"], params["body"])
    if not result["ok"]:
        raise RuntimeError(result["message"])
    if result["refused"]:
        raise RuntimeError(f"일부 수신자에게 전달되지 않았습니다: {result['refused']}")
    return f"메일을 보냈습니다 (수신자 {len(result['recipients'])}명)"


def _fax_send_params(params: dict[str, Any]) -> dict[str, Any]:
    """승인서 id 하나만 받는다. 수신자·제목·문서는 승인서에서 읽는다(여기서 바꿀 수 없다)."""
    from ai_orchestrator.connectors.hanafax import authorization_store as fax_store

    extra = set(params) - {"authorization_id"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    auth_id = str(params.get("authorization_id") or "").strip()
    row = fax_store.get_authorization(auth_id) if auth_id else None
    if row is None:
        raise ValueError("팩스 발송 승인서를 찾을 수 없습니다")
    if not row["approved"] or row["revoked"]:
        raise ValueError("승인되지 않았거나 취소된 팩스 발송 승인서입니다")
    return {"authorization_id": auth_id}


def _mail_bulk_params(params: dict[str, Any]) -> dict[str, Any]:
    """승인서 id 하나만 받는다. 수신자·내용·첨부는 승인서에서 읽는다(여기서 바꿀 수 없다)."""
    from ai_orchestrator.connectors.naver_mail import bulk_store as bulk_store

    extra = set(params) - {"authorization_id"}
    if extra:
        raise ValueError(f"알 수 없는 설정값: {sorted(extra)}")
    auth_id = str(params.get("authorization_id") or "").strip()
    row = bulk_store.get_authorization(auth_id) if auth_id else None
    if row is None:
        raise ValueError("메일 대량 발송 승인서를 찾을 수 없습니다")
    if not row["approved"] or row["revoked"]:
        raise ValueError("승인되지 않았거나 취소된 메일 대량 발송 승인서입니다")
    return {"authorization_id": auth_id}


def _run_naver_mail_bulk_send(params: dict[str, Any]) -> str:
    """승인서 범위 안에서 메일을 한 명씩 차례로 보내는 백그라운드 실행을 시작한다(오래 걸려 예약 루프를 막지 않는다)."""
    from ai_orchestrator.connectors.naver_mail import bulk_service as bulk_service

    auth_id = params["authorization_id"]
    if bulk_service.status(auth_id)["running"]:
        return "이미 발송 중입니다(이번 실행은 건너뜀)"
    bulk_service.start(auth_id)  # 멈춘·취소된 승인서면 ValueError 로 회차가 실패로 기록된다
    return "차례 발송을 시작했습니다. 진행 상황은 메일함의 대량 발송 화면에서 확인하세요"


def _run_gongmu_due_notice(_: dict[str, Any]) -> str:
    """새 기간(월·연) 업무를 앱 안 DB 에 추가하고 지연·임박 업무를 요약한다. 외부 접속·발송 없음(읽기 전용 요약)."""
    from ai_orchestrator.gongmu import gongmu_service as gongmu

    gongmu.generate_all(actor="scheduled")
    return gongmu.notice_text()


def _run_hanafax_send(params: dict[str, Any]) -> str:
    """승인서 범위 안에서 팩스를 자동 발송한다(구현은 connectors/hanafax/send_job — 하나팩스 도구 안으로 모았다)."""
    from ai_orchestrator.connectors.hanafax import send_job

    return send_job.run_send(params)


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
    "naver_mail_check": ActionSpec(
        key="naver_mail_check",
        label="네이버 메일 IMAP/SMTP 점검",
        description="웹메일의 IMAP/SMTP 사용 설정과 IMAP·SMTP 로그인을 읽기 전용으로 점검합니다(메일을 읽음 처리하거나 보내지 않습니다).",
        risk_action="read_page",
        needs_browser=True,
        validate=_mail_account_params,
        run=_run_naver_mail_check,
    ),
    "naver_mail_enable": ActionSpec(
        key="naver_mail_enable",
        label="네이버 메일 IMAP/SMTP 켜기",
        description="웹메일 환경설정에서 'IMAP/SMTP 사용'을 '사용함'으로 저장합니다. 계정 보안 설정 변경이라 실행할 때마다 승인이 필요합니다.",
        risk_action="enable_mail_protocol",
        needs_browser=True,
        validate=_mail_account_params,
        run=_run_naver_mail_enable,
    ),
    "naver_mail_fetch": ActionSpec(
        key="naver_mail_fetch",
        label="네이버 메일 받은편지함 읽기",
        description="IMAP 으로 받은편지함 최근 메일의 보낸 사람·제목·날짜를 가져옵니다(읽음 표시는 바뀌지 않습니다).",
        risk_action="read_page",
        needs_browser=False,
        validate=_mail_fetch_params,
        run=_run_naver_mail_fetch,
    ),
    "naver_mail_send": ActionSpec(
        key="naver_mail_send",
        label="네이버 메일 보내기",
        description="정한 수신자·제목·본문으로 메일을 보냅니다. 실행 시각마다 앱에서 내용을 확인하고 승인해야 전송됩니다.",
        risk_action="send_email",
        needs_browser=False,
        validate=_mail_send_params,
        run=_run_naver_mail_send,
    ),
    "hanafax_send": ActionSpec(
        key="hanafax_send",
        label="하나팩스 자동 발송",
        description="미리 승인한 발송 승인서(수신자·제목·문서·한도)의 범위 안에서만 팩스를 보냅니다. 승인 후 내용이 바뀌면 멈춥니다. 승인서가 드라이런이면 전송하지 않습니다.",
        risk_action="fax_send_authorized",
        needs_browser=False,
        validate=_fax_send_params,
        run=_run_hanafax_send,
    ),
    "naver_mail_bulk_send": ActionSpec(
        key="naver_mail_bulk_send",
        label="네이버 메일 순차 대량 발송",
        description="미리 승인한 대량 발송 승인서(수신자·내용·첨부·한도)의 범위 안에서만 메일을 한 명씩 간격을 두고 보냅니다. 승인 후 내용이 바뀌거나 멈춘 승인서는 보내지 않습니다. 드라이런 승인서는 전송하지 않습니다.",
        risk_action="mail_send_authorized",
        needs_browser=False,
        validate=_mail_bulk_params,
        run=_run_naver_mail_bulk_send,
    ),
    "gongmu_due_notice": ActionSpec(
        key="gongmu_due_notice",
        label="공무 업무 기한 알림",
        description="공무 업무판에서 기한이 지났거나 임박한 업무를 요약합니다(새 달·해 업무도 앱 안에 자동 추가). 외부 사이트 접속·발송은 하지 않습니다.",
        risk_action="read_page",
        needs_browser=False,
        validate=_no_params,
        run=_run_gongmu_due_notice,
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
    from scripts.browser.cdp.cdp_force_start import _is_cdp_alive, cmd_start

    if _is_cdp_alive():
        return
    if cmd_start() != 0:
        raise RuntimeError("CDP 브라우저를 시작하지 못했습니다")


def catalog() -> list[dict[str, Any]]:
    """화면에 보여 줄 작업 목록(설정 항목 포함)."""
    items: list[dict[str, Any]] = []
    for spec in ACTIONS.values():
        fields: list[dict[str, Any]] = []
        if spec.validate in (_blog_target, _mail_account_params, _mail_fetch_params, _mail_send_params):
            from scripts.naver.blog.accounts import BLOG_ACCOUNTS

            fields.append(
                {
                    "name": "target",
                    "label": "블로그 계정" if spec.validate is _blog_target else "네이버 계정",
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
        if spec.validate is _mail_fetch_params:
            fields += [
                {"name": "unseen_only", "label": "안 읽은 메일만", "type": "select", "options": ["true", "false"], "option_labels": {"true": "안 읽은 메일만", "false": "전체"}, "default": "true"},
                {"name": "limit", "label": "가져올 개수 (1~50)", "type": "line", "options": [], "default": "20"},
            ]
        if spec.validate is _mail_send_params:
            fields += [
                {"name": "to", "label": "받는 사람 (쉼표로 구분, 최대 10명)", "type": "line", "options": [], "default": ""},
                {"name": "subject", "label": "제목", "type": "line", "options": [], "default": ""},
                {"name": "body", "label": "본문", "type": "text", "options": [], "default": ""},
            ]
        if spec.validate is _fax_send_params:
            from ai_orchestrator.connectors.hanafax import (
                authorization_store as fax_store,
            )

            approved = [a for a in fax_store.list_authorizations() if a["approved"] and not a["revoked"]]
            fields.append(
                {
                    "name": "authorization_id",
                    "label": "발송 승인서",
                    "type": "select",
                    "options": [a["id"] for a in approved],
                    # 이름이 같은 승인서를 구분하도록 수신 곳 수·승인 날짜를 붙이고, 실제로 전송하는 승인서는 눈에 띄게 표시한다
                    "option_labels": {
                        a["id"]: (
                            f"{a['name']} · {len(a['recipients'])}곳 · {str(a.get('approved_at') or '')[:10]} 승인 · "
                            + ("⚠ 실전송" if a["live"] else "드라이런")
                        )
                        for a in approved
                    },
                    # 화면은 첫 항목을 보여 주므로 기본값도 같게 한다(선택을 건드리지 않고 저장해도 빈 값이 가지 않도록)
                    "default": approved[0]["id"] if approved else "",
                }
            )
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
