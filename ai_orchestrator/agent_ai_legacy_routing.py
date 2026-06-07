"""LEGACY — agent-ai/chat 의 옛 라우팅(분류기 기반). 현재 미사용·비활성.

free_agent(자율 도구호출 에이전트, agent_ai_proxy_router._run_free_agent_task)로 대체됨.
참고·복원용으로 보존하며, 활성 경로(agent_ai_proxy_router)는 이 모듈을 import 하지 않는다.
job 저장소(_BROWSER_TASKS/_TASK_LOCK)는 활성 라우터와 분리해 이 모듈 자체 보유한다.
"""

from __future__ import annotations

import json
import re
from threading import Lock, Thread

from . import openai_proxy_caller as _caller

# ── 작업 의도 힌트 ────────────────────────────────────────────────
_TASK_HINT = re.compile(
    r"https?://|\.com|\.kr|사이트|로그인|들어가|접속|조회|정리해|수집|크롤|페이지에서|"
    r"클릭|입력|주문|상품|단말기|연락처|목록|스크랩|추출해|가져와|확인해|"
    r"세션|현황|분석해|분석 ?해|카페 ?분석|상태",
    re.IGNORECASE,
)

# 사이트명 → 시작 URL (분류기가 URL을 못 줄 때 메시지에서 매핑)
_KNOWN_SITES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"eum|공제회|단말기", re.IGNORECASE), "https://eum.cw.or.kr/web/man/WEBMAN390M00"),
    (re.compile(r"스마트스토어|스토어|판매자", re.IGNORECASE), "https://sell.smartstore.naver.com/"),
    (re.compile(r"가비아|gabia|도메인", re.IGNORECASE), "https://my.gabia.com/"),
    (re.compile(r"하이웍스|hiworks|팩스", re.IGNORECASE), "https://office.hiworks.com/"),
    (re.compile(r"카페", re.IGNORECASE), "https://section.cafe.naver.com/ca-fe/home"),
    (re.compile(r"네이버", re.IGNORECASE), "https://www.naver.com"),
]


def _resolve_url(url: str | None, message: str) -> str | None:
    """분류기 url이 유효(http)면 그대로, 아니면 메시지에서 알려진 사이트로 매핑."""
    if url and url.lower().startswith("http"):
        return url
    for rx, mapped in _KNOWN_SITES:
        if rx.search(message):
            return mapped
    return None


# 브라우저 의도 동사 — 사이트명과 함께 있으면 LLM 분류 없이 브라우저로 직행(결정론적).
_BROWSER_INTENT = re.compile(
    r"연결|열어|열기|띄워|띄우|접속|들어가|들어와|이동|가줘|가봐|보여줘|로그인|"
    r"open|connect|go ?to",
    re.IGNORECASE,
)


_OP_CATALOG = (
    "- session_status: 외부 사이트 로그인 세션 현황(네이버/스토어/EUM/가비아/하이웍스 등 로그인 여부)\n"
    "- cafe_analyze: 이미 수집된 네이버 카페 글을 AI로 분석(흐름·뜨는 주제·수익기회)\n"
    "- community_analyze: 특정 사이트 URL의 글을 수집+AI분석 (url 필수)\n"
    "- browser: 그 외 모든 웹사이트 작업(연결·열기·접속·이동·로그인·조회·정리·클릭·입력·수집 등). "
    "사이트명만 말해도(예: '네이버 연결해줘', '스마트스토어 열어') 여기로 분류.\n"
    "- chat: 위에 해당 없는 일반 질문·대화·조언"
)


def _op_session_status() -> str:
    from scripts.ops.session_probe import probe_all

    d = probe_all()
    sites = d.get("sites", [])
    if not sites:
        return "세션 점검 실패 — CDP 브라우저가 떠 있는지 확인하세요."
    li = sum(1 for s in sites if s.get("status") == "LOGGED_IN")
    lines = [f"{'✅' if s.get('status') == 'LOGGED_IN' else '❌'} {s.get('key')}" for s in sites]
    return f"🔐 로그인 세션 현황 — {li}/{len(sites)} 로그인\n" + "  ".join(lines)


def _fmt_report(rep: dict, header: str) -> str:
    if not rep.get("ok"):
        return f"{header} 분석 실패: {rep.get('error', '')}"
    trends = " / ".join(rep.get("trends", [])[:4])
    opps = " / ".join(o.get("idea", "") for o in rep.get("opportunities", [])[:3])
    return f"📊 {header}\n흐름: {rep.get('summary', '')}\n🔥 {trends}\n💰 {opps}"


def _op_cafe_analyze() -> str:
    from pathlib import Path

    cafe_dir = Path(__file__).resolve().parents[1] / "data" / "cafe"
    files = sorted(cafe_dir.glob("classified_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return "수집된 카페 글이 없습니다 — 먼저 카페 게시글을 수집하세요."
    articles = json.loads(files[0].read_text(encoding="utf-8"))
    arts = sorted(articles, key=lambda a: int(str(a.get("view_count", "0")).replace(",", "") or 0), reverse=True)
    posts = [
        {
            "title": a.get("title", ""),
            "views": a.get("view_count", ""),
            "comments": a.get("comment_count", ""),
            "date": a.get("date", ""),
        }
        for a in arts
    ][:300]
    from scripts.community.analyzer import analyze_posts

    return _fmt_report(analyze_posts(posts, context="네이버 카페 수집글"), f"카페 분석 ({len(posts)}건)")


def _op_community_analyze(url: str | None) -> str:
    if not url:
        return "분석할 사이트 URL이 필요합니다 (예: https://...)."
    from scripts.community.analyzer import analyze_posts
    from scripts.community.universal_extractor import extract_posts
    from scripts.web_connector import get_page, run_on_browser_thread

    # Playwright(sync)는 단일 전용 스레드에서만 실행.
    ex = run_on_browser_thread(lambda: extract_posts(get_page(), url, max_posts=40), timeout=180)
    if not ex.get("ok"):
        return f"수집 실패: {ex.get('error', '')}"
    return _fmt_report(analyze_posts(ex.get("posts", []), context=url), f"{url} 분석")


# ── 비동기 브라우저 작업(job) 저장소 (legacy 자체 보유) ──────────────
_BROWSER_TASKS: dict[str, dict] = {}
_TASK_LOCK = Lock()


def _format_browser(r: dict) -> str:
    if r.get("blocked"):
        return f"⛔ 위험 동작이라 멈췄습니다.\n{r.get('result', '')}\n직접 승인이 필요합니다."
    return f"✅ 작업 결과\n{r.get('result', '')}"


def _op_browser(instruction: str, url: str | None) -> str | None:
    try:
        from scripts.browser_agent.agent import run_browser_task
        from scripts.web_connector import get_domain_page, get_page, run_on_browser_thread
    except Exception:
        return None

    def _pick():
        return get_domain_page(url) if url else get_page()

    try:
        # 1차: 로그인 대기 없이 실행(login_wait=False) — 로그인 필요하면 즉시 반환.
        r = run_on_browser_thread(
            lambda: run_browser_task(_pick(), instruction=instruction, start_url=url, max_steps=12, login_wait=False),
            timeout=240,
        )
    except Exception as e:
        import logging
        import traceback

        logging.getLogger(__name__).warning("[_op_browser] 실패: %s\n%s", e, traceback.format_exc())
        if "connect" in str(e).lower() or "cdp" in str(e).lower():
            return None
        return f"⚠ 브라우저 작업 중 오류: {str(e)[:150]}"

    if not r.get("needs_login"):
        return _format_browser(r)

    # 로그인 필요 → 비동기: 백그라운드로 로그인 대기+작업 재개, 즉시 안내 반환.
    import uuid

    job_id = uuid.uuid4().hex[:12]
    with _TASK_LOCK:
        if len(_BROWSER_TASKS) > 50:  # 저장소 비대 방지
            for k in list(_BROWSER_TASKS)[:-40]:
                _BROWSER_TASKS.pop(k, None)
        _BROWSER_TASKS[job_id] = {"status": "pending"}

    def _resume() -> None:
        from scripts.browser_agent.agent import run_browser_task as _rt
        from scripts.web_connector import get_domain_page as _gdp
        from scripts.web_connector import get_page as _gp
        from scripts.web_connector import run_on_browser_thread as _rbt

        try:
            res = _rbt(
                lambda: _rt(
                    _gdp(url) if url else _gp(),
                    instruction=instruction,
                    start_url=url,
                    max_steps=12,
                    login_wait=True,
                ),
                timeout=300,
            )
            txt = (
                _format_browser(res)
                if not res.get("needs_login")
                else "⏱ 로그인 대기 시간이 초과됐습니다. 로그인 후 다시 명령해 주세요."
            )
        except Exception as e:
            txt = f"⚠ 작업 오류: {str(e)[:150]}"
        with _TASK_LOCK:
            _BROWSER_TASKS[job_id] = {"status": "done", "result": txt}

    Thread(target=_resume, daemon=True).start()
    return (
        "🔐 로그인이 필요합니다 — 화면에 뜬 브라우저에서 해당 사이트에 로그인해 주세요.\n"
        "로그인하면 작업이 자동으로 이어지고, 잠시 후 결과가 여기에 표시됩니다.\n\n"
        f"[[JOB:{job_id}]]"
    )


def _route_app_task(message: str, model: str | None) -> str | None:
    """모든 자연어를 분류기에 통과(키워드 제약 없음). 작업이면 실행, 일반 대화면
    None 반환 → GPT가 그대로 응답.
    """
    # 결정론적 직행: 알려진 사이트명 + 브라우저 의도(연결/열기/접속 등) → LLM 분류 생략.
    direct_url = _resolve_url("", message)
    if direct_url and _BROWSER_INTENT.search(message):
        return _op_browser(message, direct_url)

    classify = _caller.call_openai_chat(
        message=(
            "사용자 메시지를 아래 작업 중 하나로 분류해 JSON만 출력(설명 금지).\n"
            f"{_OP_CATALOG}\n"
            '{"op":"...", "url":"http로 시작하는 URL 또는 빈문자열", "instruction":"수행할 작업 한 줄"}\n\n'
            f"메시지: {message[:500]}"
        ),
        model=model,
    )
    if not classify.ok:
        return None
    m = re.search(r"\{.*\}", classify.text, re.S)
    if not m:
        return None
    try:
        task = json.loads(m.group(0))
    except Exception:
        return None
    op = task.get("op", "chat")
    url = _resolve_url((task.get("url") or "").strip(), message)
    if op == "session_status":
        return _op_session_status()
    if op == "cafe_analyze":
        return _op_cafe_analyze()
    if op == "community_analyze":
        return _op_community_analyze(url)
    if op == "browser":
        return _op_browser(task.get("instruction") or message, url)
    return None  # chat
