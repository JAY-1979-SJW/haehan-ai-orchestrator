"""통합 라우터 — scripts 레이어 명령 디스패처 v1.0

cdp_client.py 의 CLI 파서에서 라우팅 책임만 분리.
모든 서비스 명령은 이 모듈의 dispatch()를 통해 처리된다.

추가 서비스 등록 방법:
    1. scripts/<service>/router.py 작성 (run_<service>(task, sub, args) 함수)
    2. _SERVICE_ROUTERS 에 항목 추가

게이트 정책:
    - 서비스 진입 시 gate.check() 자동 실행 (서비스별 위험 등급 적용)
    - 브라우저 명령(goto/click 등)은 각 함수 내부 gate 적용
"""

from __future__ import annotations

from typing import Any

from scripts.common.logger import get_logger

_log = get_logger(__name__)

# ── 서비스 라우터 레지스트리 ──────────────────────────────────────────
# cmd → (module_path, run_fn_name, gate_op)
# gate_op: None 이면 게이트 생략

_SERVICE_ROUTERS: dict[str, tuple[str, str]] = {
    "naver": ("scripts.naver.router", "run_naver"),
    "google": ("scripts.google.router", "run_google"),
    "gmail": ("scripts.google.router", "run_google"),
    "youtube": ("scripts.youtube.router", "run_youtube"),
    "kakao": ("scripts.kakao.router", "run_kakao"),
    "eum": ("scripts.eum.router", "run_eum"),
    "hiworks": ("scripts.hiworks.router", "run_hiworks"),
    "smartstore": ("scripts.naver.smartstore.api.router", "run_smartstore"),
    "gabia": ("scripts.gabia.router", "run_gabia"),
    "g2b": ("scripts.g2b.router", "run_g2b"),
    "hanafax": ("scripts.hanafax.router", "run_hanafax"),
    "local": ("tools.local_cli_router", "run_local_agent"),
    "explore": ("scripts.explorer.router", "run_explorer"),
}

# ── 브라우저 명령 목록 ────────────────────────────────────────────────
_BROWSER_CMDS = frozenset(
    {
        "check-login",
        "goto",
        "wait-login",
        "save-session",
        "write-blog",
        "paste-image",
        "handle-draft-popup",
        "is-ready",
        "verify-input",
        "verify-text",
        "scan-links",
        "scan-page",
        "type-into",
        "click-button",
        "click-link",
        "install-watcher",
        "detect-popup",
        "close-popups",
        "poll-events",
        "auto-handle",
    }
)

# ── 시스템 명령 목록 ─────────────────────────────────────────────────
_SYSTEM_CMDS = frozenset(
    {
        "popup-monitor",
        "chrome-ui",
        "chrome-ui-monitor",
        "analyze",
        "explore",
        "auto-login",
        "gate",
        "op-log",
    }
)


def dispatch(cmd: str, task: str, sub: str, args: list[str]) -> None:
    """전체 명령 디스패치.

    cdp_client.py main()에서 호출. cmd 에 따라:
    - 서비스 명령 → 해당 service/router.py 위임
    - 브라우저/시스템 명령 → cdp_client 내부 처리 (False 반환)
    """
    # 서비스 라우터 위임
    if cmd in _SERVICE_ROUTERS:
        module_path, fn_name = _SERVICE_ROUTERS[cmd]
        _call_service(cmd, module_path, fn_name, task, sub, args)
        return

    # cdp_client 내부 처리 대상
    if cmd in _BROWSER_CMDS or cmd in _SYSTEM_CMDS:
        raise _DelegateToCdpClient()

    raise ValueError(f"알 수 없는 명령: {cmd}")


def _call_service(
    cmd: str,
    module_path: str,
    fn_name: str,
    task: str,
    sub: str,
    args: list[str],
) -> None:
    """서비스 라우터 함수 동적 호출."""
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name)

    _log.info("서비스 라우팅: %s → %s.%s task=%s", cmd, module_path, fn_name, task)

    # google/gmail 은 site 인자가 추가로 필요
    if cmd in ("google", "gmail"):
        fn(cmd, task, sub, args)
    else:
        fn(task, sub, args)


class _DelegateToCdpClient(Exception):
    """cdp_client 내부 처리로 위임 신호."""


def is_service_cmd(cmd: str) -> bool:
    """서비스 라우터가 처리하는 명령이면 True."""
    return cmd in _SERVICE_ROUTERS


def list_services() -> list[dict[str, str]]:
    """등록된 서비스 목록 반환."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for cmd, (module, fn) in _SERVICE_ROUTERS.items():
        if module not in seen:
            seen.add(module)
            result.append({"cmd": cmd, "module": module, "fn": fn})
        else:
            # alias (gmail → google router)
            result.append({"cmd": cmd, "module": module, "fn": fn, "alias": True})
    return result
