"""앱 동작 매니페스트 + 디스패처 — 채팅(자율 에이전트)이 앱 내부 기능을 호출.

완전성: 라이브 FastAPI 앱을 introspect 해 모든 POST 동작을 자동 인벤토리(손으로 안 고름 → 누락 0).
안전성: 위험도 분류 후 SAFE만 자동 실행, DESTRUCTIVE/CONFIRM 은 사용자 확인 필요로 차단(자동실행 금지).
       표준 (RequestModel, user) 시그니처만 자동 호출, 그 외는 안전하게 폴백.
"""

from __future__ import annotations

import inspect
import re

# 위험(자동실행 금지): 발송·결제·삭제·투찰·발행·승인·배포·로그인·등록·웹훅·팩스 등
_DESTRUCTIVE = re.compile(
    r"send|발송|전송|보내|결제|구매|주문하기|송금|이체|삭제|delete|remove|탈퇴|투찰|입찰|낙찰|"
    r"submit|제출|발행|publish|게시|upload|업로드|approve|승인|reject|거절|배포|deploy|webhook|"
    r"login|signup|register|revoke|cancel|취소|환불|fax|팩스|setup|reset|export|dispatch|consent|확정",
    re.IGNORECASE,
)
# 안전(자동 가능): 분석·조회·수집·검색·생성초안·계획·현황·통계
_SAFE = re.compile(
    r"analyze|분석|status|현황|상태|list|목록|조회|collect|수집|search|검색|refresh|새로고침|"
    r"preview|미리보기|generate|생성|draft|초안|plan|계획|fetch|정산|stats|통계|seo|dashboard|summary",
    re.IGNORECASE,
)


def _classify(blob: str) -> str:
    if _DESTRUCTIVE.search(blob):
        return "DESTRUCTIVE"
    if _SAFE.search(blob):
        return "SAFE"
    return "CONFIRM"


def _get_app():
    from ai_orchestrator.server import app

    return app


def _post_routes() -> list[tuple]:
    routes = getattr(_get_app(), "routes", [])
    out = []
    for r in routes:
        methods = getattr(r, "methods", None) or set()
        ep = getattr(r, "endpoint", None)
        path = getattr(r, "path", None)
        if ep and path and "POST" in methods:
            out.append((path, ep, getattr(r, "name", "")))
    return out


def build_manifest() -> list[dict]:
    """모든 POST 동작 인벤토리 + 위험도. (introspect 기반이라 항상 최신·누락 0)"""
    man = []
    for path, ep, name in _post_routes():
        doc = (ep.__doc__ or "").strip()
        man.append(
            {
                "path": path,
                "func": name,
                "risk": _classify(f"{path} {name} {doc}"),
                "desc": doc.split("\n")[0][:80],
            }
        )
    return man


def list_actions(query: str = "") -> list[dict]:
    """매니페스트 검색(질의 단어 모두 포함). 질의 없으면 전체."""
    man = build_manifest()
    q = (query or "").lower().strip()
    if not q:
        return man
    terms = q.split()
    return [a for a in man if all(t in f"{a['path']} {a['func']} {a['desc']}".lower() for t in terms)]


def run_action(path: str, params: dict | None, user: dict) -> dict:
    """동작 1개 실행. SAFE만 자동, 그 외는 needs_confirm. 표준 시그니처만 자동 호출."""
    from scripts.web_connector import run_on_browser_thread

    params = params or {}
    target = next(((ep, name) for p, ep, name in _post_routes() if p == path), None)
    if target is None:
        return {
            "ok": False,
            "error": f"동작을 찾을 수 없습니다: {path}. list_app_actions 로 정확한 path 를 확인하세요.",
        }
    ep, name = target

    risk = _classify(f"{path} {name} {ep.__doc__ or ''}")
    if risk != "SAFE":
        return {
            "ok": False,
            "needs_confirm": True,
            "risk": risk,
            "message": (
                f"'{path}' 은(는) {risk}(위험·민감) 동작이라 자동 실행하지 않았습니다. "
                "사용자에게 무엇을 할지 알리고 확인을 받은 뒤 진행하세요."
            ),
        }

    # 표준 (RequestModel, user) 형태만 자동 호출 — 그 외는 폴백(안전).
    try:
        from pydantic import BaseModel

        kwargs: dict = {}
        for pname, par in inspect.signature(ep).parameters.items():
            ann = par.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                kwargs[pname] = ann(**params)
            elif pname in ("user", "current_user", "actor"):
                kwargs[pname] = user
            elif pname in params:
                kwargs[pname] = params[pname]
            elif par.default is not inspect.Parameter.empty:
                continue  # 기본값 사용
            else:
                return {
                    "ok": False,
                    "error": f"'{path}' 은(는) 자동 호출 형태가 아닙니다. 해당 탭 버튼으로 진행하거나 브라우저 도구를 쓰세요.",
                }

        def _call():
            res = ep(**kwargs)
            if inspect.iscoroutine(res):
                import asyncio

                res = asyncio.run(res)
            return res

        result = run_on_browser_thread(_call, timeout=180)
        import json as _json

        txt = result if isinstance(result, str) else _json.dumps(result, ensure_ascii=False, default=str)
        return {"ok": True, "result": txt[:2000]}
    except Exception as e:
        return {"ok": False, "error": f"실행 오류: {str(e)[:160]}"}
