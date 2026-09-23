"""앱 동작 매니페스트 + 디스패처 — 채팅(자율 에이전트)이 앱 내부 기능을 호출.

완전성: 라이브 FastAPI 앱을 introspect 해 모든 POST 동작을 자동 인벤토리(손으로 안 고름 → 누락 0).
안전성: DESTRUCTIVE(발송·결제·삭제 등) 만 차단. 나머지는 자유 실행.
       표준 (RequestModel, user) 시그니처만 자동 호출, 그 외는 안전하게 폴백.
"""

from __future__ import annotations

import inspect
import re

# 파괴적 동작만 차단: 발송·결제·삭제·투찰·입찰·팩스·환불 등 되돌릴 수 없는 외부 영향
_DESTRUCTIVE = re.compile(
    r"send|발송|전송|보내|결제|구매|주문하기|송금|이체|삭제|delete|remove|탈퇴|투찰|입찰|낙찰|"
    r"submit|제출|approve|승인|reject|거절|배포|deploy|webhook|"
    r"login|signup|revoke|cancel|취소|환불|fax|팩스|dispatch|consent|확정",
    re.IGNORECASE,
)


def _classify(blob: str) -> str:
    return "DESTRUCTIVE" if _DESTRUCTIVE.search(blob) else "SAFE"


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
    """모든 POST 동작 인벤토리. (introspect 기반이라 항상 최신·누락 0)"""
    man = []
    for path, ep, name in _post_routes():
        doc = (ep.__doc__ or "").strip()
        risk = _classify(f"{path} {name} {doc}")
        man.append(
            {
                "path": path,
                "func": name,
                "risk": risk,
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


def run_action(path: str, params: dict | None, user: dict, confirmed: bool = False) -> dict:
    """동작 1개 실행. DESTRUCTIVE 만 차단, 나머지는 즉시 실행."""
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
    if risk == "DESTRUCTIVE" and not confirmed:
        return {
            "ok": False,
            "needs_confirm": True,
            "risk": risk,
            "message": (f"'{path}' 은(는) 발송·결제·삭제 등 되돌릴 수 없는 동작입니다. 사용자 확인이 필요합니다."),
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
