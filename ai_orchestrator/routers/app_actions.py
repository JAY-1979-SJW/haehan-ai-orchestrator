"""앱 동작 매니페스트 + 디스패처 — 채팅(자율 에이전트)이 앱 내부 기능을 호출.

완전성: 라이브 FastAPI 앱을 introspect 해 모든 POST 동작을 자동 인벤토리(손으로 안 고름 → 누락 0).
안전성: DESTRUCTIVE(발송·결제·삭제 등) 만 차단. 나머지는 자유 실행.
       표준 (RequestModel, user) 시그니처만 자동 호출, 그 외는 안전하게 폴백.
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 파괴적 동작만 차단: 발송·결제·삭제·투찰·입찰·팩스·환불 등 되돌릴 수 없는 외부 영향
# 2026-09-29 defect_index #39 확장: build_manifest() 가 FastAPI _IncludedRouter 버그로
# 계속 빈 리스트를 반환해(수정 완료) tests/app_contracts/test_app_action_coverage.py 의
# test_destructive_actions_never_auto_safe 가 그동안 공허하게(비교 대상 0건) 통과하고
# 있었음 — 실제 데이터로 처음 돌려보니 register/upload/setup/reset/publish 계열이
# 전부 SAFE로 새는 게 드러남(디바이스 토큰 발급, 실제 발행 가능한 blog write-to-naver
# 의 publish=True 분기, 외부에서 인증없이 가져갈 수 있는 public-media 업로드 등).
_DESTRUCTIVE = re.compile(
    r"send|발송|전송|보내|결제|구매|주문하기|송금|이체|삭제|delete|remove|탈퇴|투찰|입찰|낙찰|"
    r"submit|제출|approve|승인|reject|거절|배포|deploy|webhook|"
    r"login|signup|revoke|cancel|취소|환불|fax|팩스|dispatch|consent|확정|"
    r"register|upload|setup|reset|export|publish|발행",
    re.IGNORECASE,
)


def _classify(blob: str) -> str:
    return "DESTRUCTIVE" if _DESTRUCTIVE.search(blob) else "SAFE"


_app_ref: list[Any] = [None]  # 앱 시작점(asgi)이 주입한다 — 라우터가 asgi 를 거꾸로 import 하지 않게(층 역참조 제거)


def configure_app(app: Any) -> None:
    _app_ref[0] = app


def _get_app():
    return _app_ref[0]


def _post_routes() -> list[tuple]:
    # FastAPI 0.137+ 부터 include_router() 가 즉시 라우트를 펼치지 않고 지연 래퍼
    # (_IncludedRouter) 로 저장한다 — app.routes 를 바로 순회하면 각 서브라우터가
    # path/methods 없는 래퍼 1개로만 보여 실제 POST 라우트를 거의 못 찾았음
    # (2026-09-29 defect_index #39, 공식 fastapi.routing.iter_route_contexts 로 해결
    # — pip 설치본 site-packages/fastapi/routing.py 소스로 RouteContext 시그니처 직접 확인).
    from fastapi.routing import iter_route_contexts

    routes = getattr(_get_app(), "routes", [])
    out = []
    for ctx in iter_route_contexts(routes):
        methods = ctx.methods or set()
        ep = getattr(ctx.original_route, "endpoint", None)
        path = ctx.path
        if ep and path and "POST" in methods:
            out.append((path, ep, ctx.name or ""))
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


def _build_call_kwargs(ep, params: dict, user: dict) -> dict | None:
    """엔드포인트 시그니처에서 호출 인자를 구성. 자동 호출 불가 형태면 None."""
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
            return None
    return kwargs


def run_action(path: str, params: dict | None, user: dict, confirmed: bool = False) -> dict:
    """동작 1개 실행. DESTRUCTIVE 만 차단, 나머지는 즉시 실행."""
    from scripts.browser.cdp.connection import run_on_browser_thread

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
        kwargs = _build_call_kwargs(ep, params, user)
        if kwargs is None:
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
    except Exception as e:  # noqa: BLE001 - 액션 실행 결과 래핑 - 실행 중 예외를 에러 딕셔너리로 변환해 반환(이미 실패로 처리), 결제/삭제 등 위험 조작 없음
        logger.warning("앱 액션 실행 실패: %s", type(e).__name__)
        return {"ok": False, "error": f"실행 오류: {str(e)[:160]}"}
