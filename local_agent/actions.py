"""로컬 에이전트 실행 가능 액션 (Stage 1).

원칙:
  - read-only / 안전 작업만.
  - 파일 수정·삭제·전송 액션은 본 모듈에 정의하지 않는다 (구현 자체 금지).
  - 미정의 액션 호출 시 ActionResult(success=False, error_code="UNKNOWN_ACTION").
  - open_url 은 http(s) 만 허용. file:// / javascript: / data: 차단.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import config

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    success: bool
    summary: str
    data: dict
    error: str = ""
    error_code: str = ""


# ── 액션 구현 ────────────────────────────────────────────────────────────

def action_ping(_params: dict) -> ActionResult:
    return ActionResult(
        success=True, summary="pong", data={"pong_at": _now_iso()},
    )


def action_system_info(_params: dict) -> ActionResult:
    """OS / Python 버전 등 비민감 정보만 반환."""
    info = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "python": sys.version.split()[0],
        "agent_version": _agent_version(),
        "host": platform.node(),
    }
    return ActionResult(success=True, summary="system_info", data=info)


def action_list_allowed_apps(_params: dict) -> ActionResult:
    apps = [
        {
            "name": app,
            "executable_stage1": app in config.APPS_EXECUTABLE_STAGE1,
        }
        for app in config.ALLOWED_APPS
    ]
    return ActionResult(
        success=True,
        summary=f"{len(apps)} apps available",
        data={"apps": apps},
    )


def action_open_url(params: dict) -> ActionResult:
    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(False, "open_url 실패", {}, "url 누락",
                            error_code="MISSING_URL")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in config.URL_ALLOWED_SCHEMES:
        return ActionResult(
            False, "open_url 차단", {"url": url},
            f"허용되지 않은 스킴: {parsed.scheme!r} (http/https 만 허용)",
            error_code="URL_SCHEME_NOT_ALLOWED",
        )
    if not parsed.netloc:
        return ActionResult(False, "open_url 차단", {"url": url},
                            "잘못된 URL", error_code="INVALID_URL")

    try:
        webbrowser.open(url, new=2)
    except Exception as e:
        return ActionResult(False, "open_url 실패", {"url": url},
                            f"브라우저 호출 실패: {e}",
                            error_code="BROWSER_OPEN_FAILED")
    return ActionResult(
        success=True, summary=f"opened: {url[:120]}",
        data={"url": url},
    )


def action_capture_screenshot(params: dict) -> ActionResult:
    """Stage 3: 승인된 1회 스크린샷 캡처 + dry-run 자기점검.

    호출 전제 (WebSocket 클라이언트가 보장):
      - risk_level=high 인 capture_screenshot 은 서버가 approved=True 로 dispatch 한
        경우에만 이 함수에 도달. 본 함수도 액션 단계에서 이중 검증한다.
      - params["_task_id"], params["_approved"] 가 주입된다 (민감값 아님).

    입력 옵션:
      - params["options"]["dry_run"] == True 이면 실제 캡처/파일 생성 금지.
        backend 존재 여부와 저장 디렉터리 준비 상태만 점검 후 completed 반환.

    실제 캡처 동작:
      - Pillow.ImageGrab (또는 mss) 으로 전체 화면 1회 캡처.
      - config.LOCAL_AGENT_SCREENSHOT_DIR 하위에 PNG 로 저장.
      - 결과로 basename / width / height 만 반환 — 전체 경로는 보고하지 않는다.

    금지:
      - 서버로 이미지 업로드 금지.
      - 전체 경로 서버 전송 금지 (dry-run 포함).
      - 클립보드 접근 금지.
      - 저장 디렉터리 외부에 파일 생성 금지 (symlink 방어).
      - dry-run 에서 PNG 파일 생성 금지.
    """
    target_dir = config.LOCAL_AGENT_SCREENSHOT_DIR
    options = params.get("options") if isinstance(params, dict) else None
    if not isinstance(options, dict):
        options = {}
    dry_run = bool(options.get("dry_run"))

    if dry_run:
        return _capture_screenshot_dry_run(target_dir)

    # ── 실제 실행 방어 ────────────────────────────────────────────────
    approved = bool(params.get("_approved"))
    if not approved:
        return ActionResult(
            False, "capture_screenshot 승인 플래그 없음", {},
            "action 단계 방어: _approved 플래그 없이 실제 캡처 불가",
            error_code="SCREENSHOT_NOT_APPROVED",
        )

    task_id = str(params.get("_task_id", "")).strip()
    if not task_id:
        return ActionResult(
            False, "capture_screenshot task_id 없음", {},
            "_task_id 누락 — 파일명 생성 불가, 실제 실행 거절",
            error_code="SCREENSHOT_MISSING_TASK_ID",
        )
    safe_task_id = "".join(
        c for c in task_id if c.isalnum() or c in ("-", "_")
    )[:32] or "untagged"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return ActionResult(
            False, "capture_screenshot 실패 (디렉터리 생성 불가)", {},
            str(e)[:200],
            error_code="SCREENSHOT_DIR_UNAVAILABLE",
        )

    # 심볼릭 링크 이탈 방어 — 디렉터리 자체를 먼저 검증 (grab 전에).
    try:
        resolved_dir = target_dir.resolve()
        if not resolved_dir.is_dir():
            raise ValueError("target_dir_not_dir")
    except (OSError, ValueError):
        return ActionResult(
            False, "capture_screenshot 차단 (디렉터리 해석 실패)", {},
            "LOCAL_AGENT_SCREENSHOT_DIR 이 비정상 상태",
            error_code="SCREENSHOT_PATH_ESCAPED",
        )

    try:
        img, width, height = _grab_screen()
    except _ScreenshotDependencyMissing as e:
        return ActionResult(
            False, "capture_screenshot 실패 (의존성 없음)", {},
            str(e),
            error_code="SCREENSHOT_DEPENDENCY_MISSING",
        )
    except Exception as e:  # pragma: no cover - 환경별 실패
        logger.exception("screenshot grab 실패")
        return ActionResult(
            False, "capture_screenshot 실패", {},
            str(e)[:200],
            error_code="SCREENSHOT_CAPTURE_FAILED",
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = f"screenshot_{safe_task_id}_{ts}.png"
    out_path = target_dir / basename

    # 저장 경로가 반드시 화이트리스트 내부인지 재검증 (심볼릭 링크 등 방어)
    try:
        resolved = out_path.resolve()
        resolved.relative_to(resolved_dir)
    except (OSError, ValueError):
        return ActionResult(
            False, "capture_screenshot 차단 (경로 이탈)", {},
            "지정된 스크린샷 디렉터리 바깥에 저장 시도",
            error_code="SCREENSHOT_PATH_ESCAPED",
        )

    try:
        img.save(out_path, format="PNG")
    except OSError as e:
        return ActionResult(
            False, "capture_screenshot 저장 실패", {},
            str(e)[:200],
            error_code="SCREENSHOT_WRITE_FAILED",
        )

    # 서버에는 basename + 크기만 보고 (전체 경로 금지).
    return ActionResult(
        success=True,
        summary=f"screenshot_saved basename={basename} size={width}x{height}",
        data={
            "screenshot_file": basename,
            "width": int(width),
            "height": int(height),
        },
    )


def _capture_screenshot_dry_run(target_dir: Path) -> ActionResult:
    """실제 캡처 없이 backend 준비 상태 + 저장 디렉터리 가용성만 점검.

    반환 summary 형식 (고정 키=값 토큰):
      "dry_run:true screenshot_dir_ready:<bool> backend_available:<name> upload:false"

    `backend_available` 은 "ImageGrab" / "mss" / "none" 중 하나.
    basename / 전체 경로 / 비밀값은 절대 포함하지 않는다.
    """
    dir_ready = _check_screenshot_dir_ready(target_dir)
    backend = _detect_backend()
    summary = (
        f"dry_run:true screenshot_dir_ready:{str(dir_ready).lower()} "
        f"backend_available:{backend} upload:false"
    )
    return ActionResult(
        success=True,
        summary=summary,
        data={
            "dry_run": True,
            "screenshot_dir_ready": dir_ready,
            "backend_available": backend,
            "upload": False,
        },
    )


def _check_screenshot_dir_ready(target_dir: Path) -> bool:
    """mkdir(parents=True, exist_ok=True) 이 성공하고 결과가 디렉터리인지 확인.

    디렉터리 자체를 만들긴 하지만 PNG 파일은 생성하지 않는다. 심볼릭 링크로
    외부 경로를 가리키는 경우 resolve 결과를 기준으로 is_dir 재확인.
    """
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        resolved = target_dir.resolve()
        return bool(resolved.is_dir())
    except OSError:
        return False


def _detect_backend() -> str:
    """캡처 백엔드 가용성만 판단. 실제 grab 은 하지 않는다."""
    try:
        from PIL import ImageGrab  # type: ignore  # noqa: F401
        return "ImageGrab"
    except ImportError:
        pass
    try:
        import mss  # type: ignore  # noqa: F401
        return "mss"
    except ImportError:
        pass
    return "none"


class _ScreenshotDependencyMissing(RuntimeError):
    """Pillow / mss 등 캡처 라이브러리가 설치되지 않음."""


def _grab_screen():
    """가능한 캡처 백엔드를 차례로 시도. (img_like, width, height) 반환.

    - Pillow.ImageGrab (Windows/macOS 내장 지원)
    - mss (크로스 플랫폼 대체)
    """
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        ImageGrab = None  # type: ignore

    if ImageGrab is not None:
        img = ImageGrab.grab(all_screens=False)
        w, h = img.size
        return img, int(w), int(h)

    # mss 폴백 — Pillow 없이 PNG 저장이 가능하도록 얇은 래퍼 제공
    try:
        import mss  # type: ignore
        import mss.tools  # type: ignore
    except ImportError as e:
        raise _ScreenshotDependencyMissing(
            "Pillow(ImageGrab) 또는 mss 가 필요합니다. "
            "pip install pillow 또는 pip install mss"
        ) from e

    class _MSSShot:
        __slots__ = ("_raw", "size")

        def __init__(self, raw):
            self._raw = raw
            self.size = (raw.width, raw.height)

        def save(self, path, format="PNG"):  # noqa: A002 - match PIL signature
            mss.tools.to_png(self._raw.rgb, self._raw.size, output=str(path))

    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(monitor)
        shot = _MSSShot(raw)
        return shot, int(raw.width), int(raw.height)


def action_web_analyze_html(params: dict) -> ActionResult:
    """HTML 문자열 read-only 분석 (Stage 1).

    실제 브라우저 조작이나 HTTP 요청을 수행하지 않고, 넘겨받은 HTML 문자열을
    static 분석한다. 결과에는 password/hidden input value, cookie, token 류,
    HTML 원문 전체가 포함되지 않는다.
    """
    from . import web_reader

    if not isinstance(params, dict):
        params = {}

    html = params.get("html")
    if not isinstance(html, str):
        return ActionResult(
            False, "web_analyze_html 실패", {},
            "html 누락 또는 문자열이 아님",
            error_code="MISSING_HTML",
        )

    base_url = params.get("base_url")
    if base_url is not None and not isinstance(base_url, str):
        return ActionResult(
            False, "web_analyze_html 실패", {},
            "base_url 은 문자열이어야 함",
            error_code="INVALID_BASE_URL",
        )

    hints = params.get("keyword_hints") or []
    if not isinstance(hints, list):
        return ActionResult(
            False, "web_analyze_html 실패", {},
            "keyword_hints 는 list 여야 함",
            error_code="INVALID_HINTS",
        )

    try:
        page = web_reader.analyze_html_structure(
            html=html, base_url=base_url, keyword_hints=hints,
        )
    except Exception as e:
        logger.exception("web_analyze_html 실행 실패")
        return ActionResult(
            False, "web_analyze_html 예외", {},
            str(e)[:200],
            error_code="ANALYZE_FAILED",
        )

    counts = page.get("counts", {}) or {}
    risky = page.get("risky_elements", []) or []
    summary = (
        f"headings={counts.get('headings', 0)} "
        f"links={counts.get('links', 0)} "
        f"buttons={counts.get('buttons', 0)} "
        f"forms={counts.get('forms', 0)} "
        f"tables={counts.get('tables', 0)} "
        f"risky={len(risky)}"
    )
    return ActionResult(
        success=True, summary=summary,
        data={"page_structure": page},
    )


def action_web_open_url_readonly(params: dict) -> ActionResult:
    """실제 브라우저를 read-only 로 열어 현재 페이지 구조를 요약 (Stage 2).

    browser_reader.open_url_readonly 를 호출한다. 클릭/입력/제출/다운로드/
    업로드/쿠키 수집은 일절 수행하지 않으며, 반환 data 에는 HTML 원문
    전체가 포함되지 않는다 (page_structure 요약만 포함).
    """
    from . import browser_reader

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False, "web_open_url_readonly 실패", {},
            "url 누락", error_code="MISSING_URL",
        )

    wait_until = params.get("wait_until", "domcontentloaded")
    if not isinstance(wait_until, str):
        wait_until = "domcontentloaded"

    try:
        timeout_ms = int(params.get("timeout_ms", 15000))
    except (TypeError, ValueError):
        timeout_ms = 15000
    timeout_ms = max(1000, min(timeout_ms, 60000))

    try:
        max_html_chars = int(params.get("max_html_chars", 500000))
    except (TypeError, ValueError):
        max_html_chars = 500000
    max_html_chars = max(1000, min(max_html_chars, 2_000_000))

    hints = params.get("keyword_hints") or []
    if not isinstance(hints, list):
        hints = []

    allow_private_network = bool(params.get("allow_private_network", False))

    try:
        result = browser_reader.open_url_readonly(
            url=url,
            wait_until=wait_until,
            timeout_ms=timeout_ms,
            max_html_chars=max_html_chars,
            keyword_hints=hints,
            allow_private_network=allow_private_network,
        )
    except Exception as e:
        logger.exception("web_open_url_readonly 실행 실패")
        return ActionResult(
            False, "web_open_url_readonly 예외", {},
            str(e)[:200], error_code="BROWSER_OPEN_FAILED",
        )

    if not isinstance(result, dict) or not result.get("ok"):
        code = "BROWSER_OPEN_FAILED"
        reason = "browser open failed"
        if isinstance(result, dict):
            code = str(result.get("error_code", code))
            reason = str(result.get("reason", reason))
        return ActionResult(
            False, "web_open_url_readonly 거절", {},
            reason[:200], error_code=code,
        )

    # HTML 원문은 반환 data 에 포함하지 않는다.
    _title_raw = str(result.get("title") or "")
    _url_cat = str(result.get("url_category") or browser_reader._categorize_url(url))
    _modal_list = list(result.get("modal_candidates") or [])
    _ps = result.get("page_structure") or {}
    _counts = _ps.get("counts") or {}
    data = {
        "url": result.get("url"),
        "current_url": result.get("current_url", ""),
        "title": _title_raw[:300],
        "html_truncated": bool(result.get("html_truncated", False)),
        "login_required_hint": bool(result.get("login_required_hint", False)),
        "login_reason": list(result.get("login_reason") or []),
        "modal_candidates": _modal_list,
        "page_structure": _ps,
        # observe_summary: sanitized 구조화 필드 (orchestrator 전달용)
        "observe_summary": {
            "target_kind": _url_cat,
            "url_category": _url_cat,
            "final_url_sanitized": _safe_final_url(
                str(result.get("current_url") or ""), _url_cat,
            ),
            "title": _title_raw[:300],
            "title_len": len(_title_raw),
            "status_category": "ok",
            "pages_observed_count": 1,
            "error_category": None,
            "blocked_reason": None,
            "login_required_hint": bool(result.get("login_required_hint", False)),
            "modal_candidates_count": len(_modal_list),
            "html_truncated": bool(result.get("html_truncated", False)),
            "page_structure_counts": {
                k: max(0, int(_counts.get(k) or 0))
                for k in ("headings", "links", "buttons", "inputs", "forms", "tables")
            },
            "observed_at": _now_iso(),
        },
        # audit_summary: safe audit counts (raw audit JSONL 읽기 없음)
        "audit_summary": _build_audit_summary(_url_cat, "ok"),
    }
    return ActionResult(
        success=True,
        summary=str(result.get("summary", "web_open_url_readonly ok"))[:300],
        data=data,
    )


def action_web_probe_manual_login(params: dict) -> ActionResult:
    """수동 로그인 확인 모드 — 사용자가 직접 로그인하는 동안 read-only 관찰.

    browser_login_probe.probe_manual_login_flow 를 호출한다. ID/PW 자동 입력,
    클릭, 제출, 쿠키/스토리지 수집을 일절 수행하지 않는다. 반환 data 에는
    HTML 원문 / 쿠키 / 세션 / password / hidden value 가 포함되지 않는다.
    """
    from . import browser_login_probe

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False, "web_probe_manual_login 실패", {},
            "url 누락", error_code="MISSING_URL",
        )

    kwargs: dict = {"url": url}
    for key in ("wait_seconds", "poll_interval_seconds", "max_html_chars"):
        if key in params and params[key] is not None:
            try:
                kwargs[key] = int(params[key])
            except (TypeError, ValueError):
                return ActionResult(
                    False, "web_probe_manual_login 실패", {},
                    f"{key} 값이 정수가 아님", error_code="INVALID_PARAM",
                )

    for key in ("success_url_contains", "success_text_hints", "allowed_hosts"):
        if key in params and params[key] is not None:
            if not isinstance(params[key], list):
                return ActionResult(
                    False, "web_probe_manual_login 실패", {},
                    f"{key} 는 list 여야 함", error_code="INVALID_PARAM",
                )
            kwargs[key] = list(params[key])

    kwargs["allow_private_network"] = bool(
        params.get("allow_private_network", False)
    )

    # 테스트 전용 주입 (프로덕션 호출에는 주어지지 않음).
    if "_browser_factory" in params:
        kwargs["_browser_factory"] = params["_browser_factory"]
    if "_clock" in params:
        kwargs["_clock"] = params["_clock"]

    try:
        result = browser_login_probe.probe_manual_login_flow(**kwargs)
    except Exception as e:
        logger.exception("web_probe_manual_login 실행 실패")
        return ActionResult(
            False, "web_probe_manual_login 예외", {},
            str(e)[:200], error_code="BROWSER_OPEN_FAILED",
        )

    if not isinstance(result, dict) or not result.get("ok"):
        code = "LOGIN_PROBE_FAILED"
        reason = "probe failed"
        data: dict = {}
        if isinstance(result, dict):
            code = str(result.get("error_code", code))
            reason = str(
                result.get("summary") or result.get("reason") or reason
            )
            data = {
                "mode": result.get("mode"),
                "initial": result.get("initial"),
                "last_observation": result.get("last_observation"),
            }
        return ActionResult(
            False, "web_probe_manual_login 거절", data,
            reason[:200], error_code=code,
        )

    after = result.get("after") or {}
    data = {
        "url": result.get("url"),
        "mode": result.get("mode"),
        "initial": result.get("initial"),
        "after": after,
        "login_completed_hint": bool(after.get("login_completed_hint", False)),
        "warnings": list(result.get("warnings") or []),
    }
    return ActionResult(
        success=True,
        summary=str(result.get("summary", "manual login probe ok"))[:300],
        data=data,
    )


def _action_browser_guarded(
    action_name: str, params: dict,
) -> ActionResult:
    """web_*_guarded 액션 공통 디스패처.

    high/critical 로 분류된 호출은 실제 브라우저 API 를 호출하지 않고
    success=True, approval_required=True, action_executed=False 로 반환한다.
    blocked 액션도 동일하게 즉시 거절된다 (차이: summary 에 blocked 표기).
    """
    from . import browser_actions

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False, f"{action_name} 실패", {},
            "url 누락", error_code="MISSING_URL",
        )

    selector = params.get("selector")
    if selector is not None and not isinstance(selector, str):
        return ActionResult(
            False, f"{action_name} 실패", {},
            "selector 는 문자열이어야 함", error_code="INVALID_SELECTOR",
        )

    text = params.get("text")
    if text is not None and not isinstance(text, str):
        return ActionResult(
            False, f"{action_name} 실패", {},
            "text 는 문자열이어야 함", error_code="INVALID_TEXT",
        )

    value = params.get("value")
    if value is not None and not isinstance(value, (str, int, float)):
        return ActionResult(
            False, f"{action_name} 실패", {},
            "value 는 문자열/숫자여야 함", error_code="INVALID_VALUE",
        )
    value_norm: str | None = None
    if value is not None:
        value_norm = str(value)

    try:
        timeout_ms = int(params.get("timeout_ms", 15000))
    except (TypeError, ValueError):
        timeout_ms = 15000
    timeout_ms = max(1000, min(timeout_ms, 60000))

    approved = bool(params.get("approved", False))
    allow_private_network = bool(params.get("allow_private_network", False))

    # 상위 레벨 action 이름 → browser_actions 내부 action 이름.
    internal_action_map = {
        "web_click_guarded": "click",
        "web_type_guarded": "type_text",
        "web_select_guarded": "select_option",
        "web_scroll_guarded": "scroll",
    }
    internal_action = internal_action_map.get(action_name)
    if internal_action is None:
        return ActionResult(
            False, f"{action_name} 미등록", {},
            "지원되지 않는 guarded 액션",
            error_code="UNKNOWN_ACTION",
        )

    try:
        result = browser_actions.perform_browser_action_readwrite_guarded(
            url=url,
            action=internal_action,
            selector=selector,
            text=text,
            value=value_norm,
            timeout_ms=timeout_ms,
            allow_private_network=allow_private_network,
            approved=approved,
        )
    except Exception as e:
        logger.exception("%s 실행 실패", action_name)
        return ActionResult(
            False, f"{action_name} 예외", {},
            str(e)[:200], error_code="BROWSER_ACTION_FAILED",
        )

    if not isinstance(result, dict):
        return ActionResult(
            False, f"{action_name} 비정상 응답", {},
            "result is not dict", error_code="BROWSER_ACTION_FAILED",
        )

    # URL 검증 실패 / 의존성 없음 등은 ok=False.
    if not result.get("ok"):
        return ActionResult(
            False, f"{action_name} 거절",
            {
                "risk": result.get("risk", "critical"),
                "approval_required": bool(result.get("approval_required", True)),
                "action_executed": False,
            },
            str(result.get("reason", "blocked"))[:200],
            error_code=str(result.get("error_code", "BROWSER_ACTION_FAILED")),
        )

    data = {
        "risk": result.get("risk", "critical"),
        "category": result.get("category", "blocked"),
        "approval_required": bool(result.get("approval_required", True)),
        "action_executed": bool(result.get("action_executed", False)),
        "classification": result.get("classification") or {},
    }

    return ActionResult(
        success=True,
        summary=str(result.get("summary", f"{action_name} ok"))[:300],
        data=data,
    )


def action_web_build_site_map_prompt(params: dict) -> ActionResult:
    """site_mapper.build_site_map_prompt_payload 래퍼 (Stage 4 preparation).

    실제 GPT/OpenAI API 를 호출하지 않으며, 외부 네트워크 요청도 하지 않는다.
    page_observation (web_reader 또는 browser_reader 결과) 만 받아 GPT 에게
    넘길 수 있는 범용 관찰 payload 를 만든다. HTML 원문 전체, password/hidden
    value, cookie, token 류 원문은 payload 에 포함되지 않는다.
    """
    from . import site_mapper

    if not isinstance(params, dict):
        params = {}

    page_observation = params.get("page_observation")
    if not isinstance(page_observation, dict):
        return ActionResult(
            False, "web_build_site_map_prompt 실패", {},
            "page_observation dict 누락",
            error_code="MISSING_PAGE_OBSERVATION",
        )

    user_goal = params.get("user_goal")
    if user_goal is not None and not isinstance(user_goal, str):
        return ActionResult(
            False, "web_build_site_map_prompt 실패", {},
            "user_goal 은 문자열이어야 함",
            error_code="INVALID_USER_GOAL",
        )

    domain_profile = params.get("domain_profile")
    if domain_profile is not None and not isinstance(domain_profile, dict):
        return ActionResult(
            False, "web_build_site_map_prompt 실패", {},
            "domain_profile 은 dict 이어야 함",
            error_code="INVALID_DOMAIN_PROFILE",
        )

    hints = params.get("keyword_hints")
    if hints is not None and not isinstance(hints, list):
        return ActionResult(
            False, "web_build_site_map_prompt 실패", {},
            "keyword_hints 는 list 여야 함",
            error_code="INVALID_HINTS",
        )

    max_items = params.get("max_items", 80)

    try:
        payload = site_mapper.build_site_map_prompt_payload(
            page_observation=page_observation,
            user_goal=user_goal,
            domain_profile=domain_profile,
            keyword_hints=hints,
            max_items=max_items,
        )
    except Exception as e:
        logger.exception("web_build_site_map_prompt 실행 실패")
        return ActionResult(
            False, "web_build_site_map_prompt 예외", {},
            str(e)[:200], error_code="SITE_MAP_BUILD_FAILED",
        )

    counts = (payload.get("page_summary") or {}).get("counts", {}) or {}
    heur = payload.get("heuristic_candidates") or {}
    summary = (
        f"links={counts.get('links', 0)} "
        f"buttons={counts.get('buttons', 0)} "
        f"forms={counts.get('forms', 0)} "
        f"tables={counts.get('tables', 0)} "
        f"roles={len(heur.get('page_role_candidates') or [])} "
        f"tasks={len(heur.get('task_candidates') or [])} "
        f"danger={len(heur.get('danger_elements') or [])} "
        f"safe={len(heur.get('safe_navigation_candidates') or [])}"
    )
    return ActionResult(
        success=True, summary=summary,
        data={"site_map_prompt_payload": payload},
    )


def action_web_click_guarded(params: dict) -> ActionResult:
    """안전 click 만 실제 수행. 위험 버튼은 approval_required 로 거절."""
    return _action_browser_guarded("web_click_guarded", params)


def action_web_type_guarded(params: dict) -> ActionResult:
    """일반 입력 필드에만 fill. password 셀렉터/type 은 blocked."""
    return _action_browser_guarded("web_type_guarded", params)


def action_web_select_guarded(params: dict) -> ActionResult:
    """드롭다운 선택 — medium safe_input 으로만 실행."""
    return _action_browser_guarded("web_select_guarded", params)


def action_web_scroll_guarded(params: dict) -> ActionResult:
    """read-only 스크롤 — 키보드/마우스 조작 없이 page.mouse.wheel 1회."""
    return _action_browser_guarded("web_scroll_guarded", params)


def action_scan_file_tree(params: dict) -> ActionResult:
    """PC 파일 트리 read-only 스캔 (Stage 1).

    file_scanner.scan_file_tree 를 호출하여 정리 후보/보존 필수/중복 후보를
    요약한다. 반환 data 에는 absolute_path 가 포함되지 않으므로 서버 전송이
    가능하다. 본 액션은 어떤 경우에도 파일 삭제/이동/이름변경을 하지 않는다.
    """
    from . import file_scanner

    if not isinstance(params, dict):
        params = {}

    root_path = str(params.get("root_path", "")).strip()
    if not root_path:
        return ActionResult(
            False, "scan_file_tree 실패", {},
            "root_path 누락",
            error_code="MISSING_ROOT_PATH",
        )

    kwargs: dict = {"root_path": root_path}
    for key, default in (
        ("max_depth", 5),
        ("max_files", 10000),
        ("max_hash_size_mb", 100),
    ):
        if key in params and params[key] is not None:
            try:
                kwargs[key] = int(params[key])
            except (TypeError, ValueError):
                return ActionResult(
                    False, "scan_file_tree 실패", {},
                    f"{key} 값이 정수가 아님",
                    error_code="INVALID_PARAM",
                )
        else:
            kwargs[key] = default
    for key in ("include_hidden", "compute_hash"):
        kwargs[key] = bool(params.get(key, False))

    try:
        report = file_scanner.scan_file_tree(**kwargs)
    except Exception as e:
        logger.exception("scan_file_tree 실행 실패")
        return ActionResult(
            False, "scan_file_tree 예외", {},
            str(e)[:200],
            error_code="SCAN_FAILED",
        )

    if not isinstance(report, dict) or not report.get("ok"):
        code = str(report.get("error_code", "SCAN_FAILED")) if isinstance(report, dict) else "SCAN_FAILED"
        summary = str(report.get("summary", "scan failed")) if isinstance(report, dict) else "scan failed"
        return ActionResult(
            False, "scan_file_tree 거절", {}, summary,
            error_code=code,
        )

    summary = (
        f"scanned_files={report['scanned_files']} "
        f"preserve={report['preserve_count']} "
        f"candidate_delete={report['delete_candidate_count']} "
        f"review={report['review_count']} "
        f"duplicates={report['duplicate_candidate_count']}"
    )
    return ActionResult(success=True, summary=summary, data=report)


def action_list_files_readonly(params: dict) -> ActionResult:
    """사전 화이트리스트(config.READ_ONLY_DIRS) 디렉터리만 나열."""
    target = str(params.get("dir", "")).strip()
    if not target:
        return ActionResult(False, "dir 누락", {}, error_code="MISSING_DIR")

    target_path = Path(target).resolve()
    if not _is_under_allowed_dirs(target_path):
        return ActionResult(
            False, "허용되지 않은 디렉터리", {"dir": str(target_path)},
            "READ_ONLY_DIRS 화이트리스트 외부 경로",
            error_code="DIR_NOT_ALLOWED",
        )
    if not target_path.exists() or not target_path.is_dir():
        return ActionResult(False, "디렉터리 없음", {"dir": str(target_path)},
                            error_code="DIR_NOT_FOUND")

    entries = []
    try:
        for p in sorted(target_path.iterdir()):
            entries.append({
                "name": p.name,
                "is_dir": p.is_dir(),
                "size": p.stat().st_size if p.is_file() else None,
            })
    except OSError as e:
        return ActionResult(False, "iterdir 실패", {"dir": str(target_path)},
                            str(e), error_code="LIST_FAILED")
    return ActionResult(
        success=True,
        summary=f"{len(entries)} entries",
        data={"dir": str(target_path), "entries": entries},
    )


# ── 디스패치 ──────────────────────────────────────────────────────────────

# 1단계에서 본 모듈에 노출되는 액션. 명시적으로 등록되지 않은 액션은
# UNKNOWN_ACTION 으로 거절된다. 파일 수정/삭제/전송은 의도적으로 미등록.
_ACTIONS = {
    "ping": action_ping,
    "system_info": action_system_info,
    "list_allowed_apps": action_list_allowed_apps,
    "open_url": action_open_url,
    "capture_screenshot": action_capture_screenshot,
    "list_files_readonly": action_list_files_readonly,
    "scan_file_tree": action_scan_file_tree,
    "web_analyze_html": action_web_analyze_html,
    "web_open_url_readonly": action_web_open_url_readonly,
    "web_build_site_map_prompt": action_web_build_site_map_prompt,
    "web_click_guarded": action_web_click_guarded,
    "web_type_guarded": action_web_type_guarded,
    "web_select_guarded": action_web_select_guarded,
    "web_scroll_guarded": action_web_scroll_guarded,
    "web_probe_manual_login": action_web_probe_manual_login,
}

# 명시적 거절 액션 (오해 방지를 위해 별도 표기 — 등록 자체는 안 함)
FORBIDDEN_ACTIONS: frozenset[str] = frozenset({
    "delete_file", "upload_file", "modify_file", "execute_shell",
})


def execute_action(action: str, params: dict) -> ActionResult:
    action = (action or "").strip().lower()
    if action in FORBIDDEN_ACTIONS:
        return ActionResult(
            False, f"{action} 거절", {},
            "1단계 금지 액션 (파일 수정/삭제/전송, unrestricted shell)",
            error_code="ACTION_FORBIDDEN",
        )
    fn = _ACTIONS.get(action)
    if fn is None:
        return ActionResult(
            False, f"{action} 미등록", {},
            "지원되지 않는 액션",
            error_code="UNKNOWN_ACTION",
        )
    try:
        return fn(params or {})
    except Exception as e:
        logger.exception("action %s 실행 실패", action)
        return ActionResult(False, f"{action} 예외", {}, str(e),
                            error_code="EXECUTION_ERROR")


# ── 헬퍼 ──────────────────────────────────────────────────────────────────

def _safe_final_url(current_url: str, url_category: str) -> "str | None":
    """final_url_sanitized 용 sanitize: query/fragment 제거, 허용 대상만 반환."""
    if url_category == "about_blank":
        return "about:blank"
    if not current_url:
        return None
    try:
        parsed = urlparse(current_url)
        host = (parsed.hostname or "").lower()
        if host in ("127.0.0.1", "localhost"):
            port_str = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{host}{port_str}{parsed.path}"
    except Exception:
        pass
    return None


def _build_audit_summary(
    url_category: str,
    status: str,
    error_code: str = "",
) -> dict:
    """안전한 audit summary 생성 (raw audit JSONL 읽기 없음, safe counts만).

    Args:
        url_category: URL 분류 (about_blank, internal_test, public_http 등)
        status: 액션 상태 (ok, blocked, error)
        error_code: 에러 발생 시 에러 코드 (선택)

    Returns:
        audit_summary dict (schema_version, event counts, categories)
    """
    # 기본값
    audit_summary: dict[str, Any] = {
        "audit_schema_version": 1,
        "local_audit_source": "agent_v1",
        "audit_summary_generated_at": _now_iso(),
        "audit_event_count": 1,  # 단일 action 결과
        "allowed_event_count": 0,
        "blocked_event_count": 0,
        "denied_event_count": 0,
        "error_event_count": 0,
        "last_event_category": "web_open_url_readonly",
        "last_event_status": status,
        "audit_event_categories": ["web_open_url_readonly"],
        "target_kind_counts": {url_category: 1},
        "action_kind_counts": {"web_open": 1},
        "policy_decision_counts": {},
    }

    # Status 반영
    if status == "ok":
        audit_summary["allowed_event_count"] = 1
        audit_summary["policy_decision_counts"]["allowed"] = 1
    elif status == "blocked":
        audit_summary["blocked_event_count"] = 1
        audit_summary["policy_decision_counts"]["blocked"] = 1
    elif status == "denied":
        audit_summary["denied_event_count"] = 1
        audit_summary["policy_decision_counts"]["denied"] = 1
    elif status == "error":
        audit_summary["error_event_count"] = 1
        if error_code:
            audit_summary["last_event_status"] = f"error:{error_code[:40]}"

    return audit_summary


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agent_version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return "0.0.0"


def _is_under_allowed_dirs(path: Path) -> bool:
    for base in config.READ_ONLY_DIRS:
        try:
            base_resolved = base.resolve()
        except OSError:
            continue
        try:
            path.relative_to(base_resolved)
            return True
        except ValueError:
            continue
    return False


__all__ = [
    "ActionResult", "execute_action",
    "FORBIDDEN_ACTIONS",
    "action_ping", "action_system_info", "action_list_allowed_apps",
    "action_open_url", "action_capture_screenshot",
    "action_list_files_readonly",
    "action_scan_file_tree",
    "action_web_analyze_html",
    "action_web_open_url_readonly",
    "action_web_build_site_map_prompt",
    "action_web_click_guarded",
    "action_web_type_guarded",
    "action_web_select_guarded",
    "action_web_scroll_guarded",
    "action_web_probe_manual_login",
]
