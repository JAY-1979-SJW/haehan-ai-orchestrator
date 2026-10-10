"""로컬 에이전트 실행 가능 액션 (Stage 1).

원칙:
  - read-only / 안전 작업만.
  - 파일 수정·삭제·전송 액션은 본 모듈에 정의하지 않는다 (구현 자체 금지).
  - 미정의 액션 호출 시 ActionResult(success=False, error_code="UNKNOWN_ACTION").
  - open_url 은 http(s) 만 허용. file:// / javascript: / data: 차단.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.browser_tool.router import route_browser_task_with_params
from ai_orchestrator.contracts.agent_result_limits import RESULT_FULL_MAX_CHARS
from core.agent_runtime.browser import browser_actions
from core.agent_runtime.common import config

_BOOT = Path(__file__).resolve().parents[3]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

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
        success=True,
        summary="pong",
        data={"pong_at": _now_iso()},
    )


def action_ws_noop(_params: dict) -> ActionResult:
    """WS delivery path 검증 전용 no-op. 외부 부작용 없음."""
    return ActionResult(success=True, summary="ws_noop_ok", data={})


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
    err = _validate_open_url_params(url, params)
    if err is not None:
        return err

    dry_run = params.get("dry_run", True)
    if not isinstance(dry_run, bool):
        dry_run = str(dry_run).lower() in ("true", "1", "yes")

    if not dry_run:
        return ActionResult(
            False,
            "open_url 실패",
            {"dry_run": False},
            "actual open_url requires approval and is not enabled in this stage",
            error_code="ACTUAL_EXECUTION_NOT_ENABLED",
        )

    return ActionResult(
        success=True,
        summary="open_url_dry_run_ok",
        data={
            "action": "open_url",
            "dry_run": True,
            "url": url,
            "would_open_browser": False,
            "external_network_call": False,
            "requires_approval": False,
            "policy_decision": "dry_run_allowed",
        },
    )


_OPEN_URL_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "session_token",
        "device_token",
        "cookie",
        "cookies",
        "session",
        "client_secret",
        "secret",
        "api_secret",
        "api_key",
        "auth",
        "authorization",
    }
)


def _validate_open_url_params(url: str, params: dict) -> ActionResult | None:
    """URL + 민감정보 공통 검증. 문제 있으면 ActionResult 반환, 없으면 None."""
    if not url:
        return ActionResult(False, "open_url 실패", {}, "url 누락", error_code="MISSING_URL")
    for key in params:
        if key.lower() in _OPEN_URL_SENSITIVE_KEYS:
            return ActionResult(
                False,
                "open_url 차단",
                {},
                f"민감정보 포함: {key!r}",
                error_code="SENSITIVE_DATA_DETECTED",
            )
    parsed = urlparse(url)
    if parsed.scheme.lower() not in config.URL_ALLOWED_SCHEMES:
        return ActionResult(
            False,
            "open_url 차단",
            {},
            f"허용되지 않은 스킴: {parsed.scheme!r} (http/https 만 허용)",
            error_code="URL_SCHEME_NOT_ALLOWED",
        )
    if not parsed.netloc:
        return ActionResult(False, "open_url 차단", {}, "잘못된 URL", error_code="INVALID_URL")
    return None


def action_open_url_execute(params: dict) -> ActionResult:
    """승인된 actual open_url 실행. _approved=True 없이는 webbrowser.open 호출 금지.

    이 함수는 반드시 서버가 _approved=True 를 주입한 경우에만 브라우저를 연다.
    사용자가 payload 에 approved=True 를 직접 넣어도 이 함수는 _approved 키만 신뢰한다.
    _approved 는 websocket_client.py 가 서버 task.approved 필드를 기반으로 주입한다.
    """
    approved = bool(params.get("_approved", False))
    if not approved:
        return ActionResult(
            False,
            "open_url_execute 차단",
            {},
            "승인 플래그 없이 actual 실행 불가 (_approved=True 필요)",
            error_code="OPEN_URL_NOT_APPROVED",
        )

    url = str(params.get("url", "")).strip()
    err = _validate_open_url_params(url, params)
    if err is not None:
        return err

    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    approval_id = str(params.get("_approval_id", "") or "").strip()
    task_id = str(params.get("_task_id", "") or "").strip()

    try:
        webbrowser.open(url)
    except Exception as e:
        logger.exception("open_url_execute webbrowser.open 실패")
        return ActionResult(
            False,
            "open_url_execute 실패",
            {},
            str(e)[:200],
            error_code="BROWSER_OPEN_FAILED",
        )

    data: dict = {
        "action": "open_url_execute",
        "dry_run": False,
        "would_open_browser": True,
        "external_network_call": "browser_possible",
        "policy_decision": "approved_execution",
        "url_scheme": parsed.scheme,
        "url_host": parsed.netloc,
        "normalized_url": normalized,
    }
    if approval_id:
        data["approval_id"] = approval_id
    if task_id:
        data["execution_task_id"] = task_id

    return ActionResult(
        success=True,
        summary="open_url_execute_ok",
        data=data,
    )


def _screenshot_prepare_dir(target_dir: Path) -> tuple[Path | None, ActionResult | None]:
    """저장 디렉터리 생성 + 심볼릭 링크 이탈 방어. (resolved_dir, 오류결과)."""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, ActionResult(
            False,
            "capture_screenshot 실패 (디렉터리 생성 불가)",
            {},
            str(e)[:200],
            error_code="SCREENSHOT_DIR_UNAVAILABLE",
        )

    # 심볼릭 링크 이탈 방어 — 디렉터리 자체를 먼저 검증 (grab 전에).
    try:
        resolved_dir = target_dir.resolve()
        if not resolved_dir.is_dir():
            raise ValueError("target_dir_not_dir")
    except (OSError, ValueError):
        return None, ActionResult(
            False,
            "capture_screenshot 차단 (디렉터리 해석 실패)",
            {},
            "LOCAL_AGENT_SCREENSHOT_DIR 이 비정상 상태",
            error_code="SCREENSHOT_PATH_ESCAPED",
        )
    return resolved_dir, None


def _screenshot_grab_or_error():
    """화면 캡처. 성공 시 (img, width, height), 실패 시 ActionResult."""
    try:
        return _grab_screen()
    except _ScreenshotDependencyMissing as e:
        return ActionResult(
            False,
            "capture_screenshot 실패 (의존성 없음)",
            {},
            str(e),
            error_code="SCREENSHOT_DEPENDENCY_MISSING",
        )
    except Exception as e:  # pragma: no cover - 환경별 실패
        logger.exception("screenshot grab 실패")
        return ActionResult(
            False,
            "capture_screenshot 실패",
            {},
            str(e)[:200],
            error_code="SCREENSHOT_CAPTURE_FAILED",
        )


def _screenshot_save(img, target_dir: Path, resolved_dir: Path, basename: str) -> tuple[ActionResult | None, int]:
    """경로 이탈 재검증 + PNG 저장 + 크기 조회. (오류결과, file_size)."""
    out_path = target_dir / basename

    # 저장 경로가 반드시 화이트리스트 내부인지 재검증 (심볼릭 링크 등 방어)
    try:
        resolved = out_path.resolve()
        resolved.relative_to(resolved_dir)
    except (OSError, ValueError):
        return ActionResult(
            False,
            "capture_screenshot 차단 (경로 이탈)",
            {},
            "지정된 스크린샷 디렉터리 바깥에 저장 시도",
            error_code="SCREENSHOT_PATH_ESCAPED",
        ), 0

    try:
        img.save(out_path, format="PNG")
    except OSError as e:
        return ActionResult(
            False,
            "capture_screenshot 저장 실패",
            {},
            str(e)[:200],
            error_code="SCREENSHOT_WRITE_FAILED",
        ), 0

    try:
        file_size = int(out_path.stat().st_size)
    except OSError:
        file_size = 0
    return None, file_size


def _screenshot_guard(params: dict) -> tuple[ActionResult | None, str]:
    """승인 플래그 / task_id 검증. (오류결과, task_id)."""
    approved = bool(params.get("_approved"))
    if not approved:
        return ActionResult(
            False,
            "capture_screenshot 승인 플래그 없음",
            {},
            "action 단계 방어: _approved 플래그 없이 실제 캡처 불가",
            error_code="SCREENSHOT_NOT_APPROVED",
        ), ""

    task_id = str(params.get("_task_id", "")).strip()
    if not task_id:
        return ActionResult(
            False,
            "capture_screenshot task_id 없음",
            {},
            "_task_id 누락 — 파일명 생성 불가, 실제 실행 거절",
            error_code="SCREENSHOT_MISSING_TASK_ID",
        ), ""
    return None, task_id


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
    guard_err, task_id = _screenshot_guard(params)
    if guard_err is not None:
        return guard_err
    safe_task_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))[:32] or "untagged"

    resolved_dir, dir_err = _screenshot_prepare_dir(target_dir)
    if dir_err is not None:
        return dir_err
    assert resolved_dir is not None  # _screenshot_prepare_dir 계약: dir_err 가 None 이면 항상 Path(동작 변경 없음, mypy 용 타입 좁히기)

    grabbed = _screenshot_grab_or_error()
    if isinstance(grabbed, ActionResult):
        return grabbed
    img, width, height = grabbed

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    basename = f"screenshot_{safe_task_id}_{ts}.png"

    save_err, file_size = _screenshot_save(img, target_dir, resolved_dir, basename)
    if save_err is not None:
        return save_err

    # storage_ref: 디스크 경로가 아닌 참조 키. agent_id 가 주입돼 있으면 3-tier,
    # 없으면 2-tier 형식 ("{task_id}/{basename}"). 절대경로/드라이브 경로 금지.
    agent_id_safe = "".join(c for c in str(params.get("_agent_id", "")).strip() if c.isalnum() or c in ("-", "_"))[:64]
    if agent_id_safe:
        storage_ref = f"{agent_id_safe}/{safe_task_id}/{basename}"
    else:
        storage_ref = f"{safe_task_id}/{basename}"

    approval_id = str(params.get("_approval_id", "") or "").strip()

    data: dict = {
        "action": "capture_screenshot",
        "dry_run": False,
        "screenshot_taken": True,
        "file_basename": basename,
        "file_ext": ".png",
        "file_size_bytes": file_size,
        "image_width": int(width),
        "image_height": int(height),
        "storage_ref": storage_ref,
        "policy_decision": "approved_execution",
        "redaction_applied": False,
        "execution_task_id": task_id,
    }
    if approval_id:
        data["approval_id"] = approval_id
    sensitive_warning = str(params.get("_sensitive_screen_warning", "") or "").strip()[:80]
    if sensitive_warning:
        data["sensitive_screen_warning"] = sensitive_warning

    # 서버에는 basename + 크기만 보고 (전체 경로 금지).
    return ActionResult(
        success=True,
        summary=f"screenshot_saved basename={basename} size={width}x{height}",
        data=data,
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
    summary = f"dry_run:true screenshot_dir_ready:{str(dir_ready).lower()} backend_available:{backend} upload:false"
    return ActionResult(
        success=True,
        summary=summary,
        data={
            "action": "capture_screenshot",
            "dry_run": True,
            "screenshot_taken": False,
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
            "Pillow(ImageGrab) 또는 mss 가 필요합니다. pip install pillow 또는 pip install mss"
        ) from e

    class _MSSShot:
        __slots__ = ("_raw", "size")

        def __init__(self, raw):
            self._raw = raw
            self.size = (raw.width, raw.height)

        def save(self, path, format="PNG"):
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
    from core.agent_runtime.browser import web_reader

    if not isinstance(params, dict):
        params = {}

    html = params.get("html")
    if not isinstance(html, str):
        return ActionResult(
            False,
            "web_analyze_html 실패",
            {},
            "html 누락 또는 문자열이 아님",
            error_code="MISSING_HTML",
        )

    base_url = params.get("base_url")
    if base_url is not None and not isinstance(base_url, str):
        return ActionResult(
            False,
            "web_analyze_html 실패",
            {},
            "base_url 은 문자열이어야 함",
            error_code="INVALID_BASE_URL",
        )

    hints = params.get("keyword_hints") or []
    if not isinstance(hints, list):
        return ActionResult(
            False,
            "web_analyze_html 실패",
            {},
            "keyword_hints 는 list 여야 함",
            error_code="INVALID_HINTS",
        )

    try:
        page = web_reader.analyze_html_structure(
            html=html,
            base_url=base_url,
            keyword_hints=hints,
        )
    except Exception as e:
        logger.exception("web_analyze_html 실행 실패")
        return ActionResult(
            False,
            "web_analyze_html 예외",
            {},
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
        success=True,
        summary=summary,
        data={"page_structure": page},
    )


def _readonly_open_options(params: dict) -> dict:
    """web_open_url_readonly 입력 파라미터 정규화 (검증 거절은 호출부에서)."""
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
    background_approved = bool(
        params.get("background_approved", False)
        or params.get("allow_background_after_approval", False)
        or params.get("_approved", False)
    )
    headless = params.get("headless")
    if headless is None:
        headless = background_approved
    else:
        headless = bool(headless)
    try:
        keep_open_ms = int(params.get("keep_open_ms", 0))
    except (TypeError, ValueError):
        keep_open_ms = 0
    keep_open_ms = max(0, min(keep_open_ms, 30000))
    browser_channel = str(params.get("browser_channel", "") or "").strip().lower()
    if browser_channel not in {"", "chromium", "chrome", "msedge"}:
        browser_channel = ""
    return {
        "wait_until": wait_until,
        "timeout_ms": timeout_ms,
        "max_html_chars": max_html_chars,
        "hints": hints,
        "allow_private_network": allow_private_network,
        "background_approved": background_approved,
        "headless": headless,
        "keep_open_ms": keep_open_ms,
        "browser_channel": browser_channel,
    }


def _readonly_open_data(result: dict, url: str, background_approved: bool) -> dict:
    """browser_reader 결과 → 반환 data (HTML 원문 제외)."""
    from core.agent_runtime.browser import browser_reader

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
        "browser_headless": bool(result.get("headless", True)),
        "browser_keep_open_ms": int(result.get("keep_open_ms", 0) or 0),
        "browser_channel": str(result.get("browser_channel") or "chromium")[:40],
        "background_approved": background_approved,
        "login_required_hint": bool(result.get("login_required_hint", False)),
        "login_reason": list(result.get("login_reason") or []),
        "modal_candidates": _modal_list,
        "page_structure": _ps,
        # observe_summary: sanitized 구조화 필드 (orchestrator 전달용)
        "observe_summary": {
            "target_kind": _url_cat,
            "url_category": _url_cat,
            "final_url_sanitized": _safe_final_url(
                str(result.get("current_url") or ""),
                _url_cat,
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
            "browser_headless": bool(result.get("headless", True)),
            "browser_keep_open_ms": int(result.get("keep_open_ms", 0) or 0),
            "browser_channel": str(result.get("browser_channel") or "chromium")[:40],
            "background_approved": background_approved,
            "page_structure_counts": {
                k: max(0, int(_counts.get(k) or 0))
                for k in ("headings", "links", "buttons", "inputs", "forms", "tables")
            },
            "observed_at": _now_iso(),
        },
        # audit_summary: safe audit counts (raw audit JSONL 읽기 없음)
        "audit_summary": _build_audit_summary(_url_cat, "ok"),
    }
    return data


def action_web_open_url_readonly(params: dict) -> ActionResult:
    """실제 브라우저를 read-only 로 열어 현재 페이지 구조를 요약 (Stage 2).

    browser_reader.open_url_readonly 를 호출한다. 클릭/입력/제출/다운로드/
    업로드/쿠키 수집은 일절 수행하지 않으며, 반환 data 에는 HTML 원문
    전체가 포함되지 않는다 (page_structure 요약만 포함).
    """
    from core.agent_runtime.browser import browser_reader

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False,
            "web_open_url_readonly 실패",
            {},
            "url 누락",
            error_code="MISSING_URL",
        )

    opts = _readonly_open_options(params)
    wait_until = opts["wait_until"]
    timeout_ms = opts["timeout_ms"]
    max_html_chars = opts["max_html_chars"]
    hints = opts["hints"]
    allow_private_network = opts["allow_private_network"]
    background_approved = opts["background_approved"]
    headless = opts["headless"]
    if headless and not background_approved:
        return ActionResult(
            False,
            "web_open_url_readonly 백그라운드 거절",
            {},
            "headless background execution requires user-approved background_approved=True",
            error_code="BACKGROUND_NOT_APPROVED",
        )
    keep_open_ms = opts["keep_open_ms"]
    browser_channel = opts["browser_channel"]

    try:
        result = browser_reader.open_url_readonly(
            url=url,
            wait_until=wait_until,
            timeout_ms=timeout_ms,
            max_html_chars=max_html_chars,
            keyword_hints=hints,
            allow_private_network=allow_private_network,
            headless=headless,
            keep_open_ms=keep_open_ms,
            browser_channel=browser_channel,
        )
    except Exception as e:
        logger.exception("web_open_url_readonly 실행 실패")
        return ActionResult(
            False,
            "web_open_url_readonly 예외",
            {},
            str(e)[:200],
            error_code="BROWSER_OPEN_FAILED",
        )

    if not isinstance(result, dict) or not result.get("ok"):
        code = "BROWSER_OPEN_FAILED"
        reason = "browser open failed"
        if isinstance(result, dict):
            code = str(result.get("error_code", code))
            reason = str(result.get("reason", reason))
        return ActionResult(
            False,
            "web_open_url_readonly 거절",
            {},
            reason[:200],
            error_code=code,
        )

    data = _readonly_open_data(result, url, background_approved)
    return ActionResult(
        success=True,
        summary=str(result.get("summary", "web_open_url_readonly ok"))[:300],
        data=data,
    )


def _probe_login_kwargs(params: dict, url: str) -> dict | ActionResult:
    """web_probe_manual_login 인자 검증·구성. 검증 실패 시 ActionResult."""
    kwargs: dict = {"url": url}
    for key in ("wait_seconds", "poll_interval_seconds", "max_html_chars"):
        if key in params and params[key] is not None:
            try:
                kwargs[key] = int(params[key])
            except (TypeError, ValueError):
                return ActionResult(
                    False,
                    "web_probe_manual_login 실패",
                    {},
                    f"{key} 값이 정수가 아님",
                    error_code="INVALID_PARAM",
                )

    for key in ("success_url_contains", "success_text_hints", "allowed_hosts"):
        if key in params and params[key] is not None:
            if not isinstance(params[key], list):
                return ActionResult(
                    False,
                    "web_probe_manual_login 실패",
                    {},
                    f"{key} 는 list 여야 함",
                    error_code="INVALID_PARAM",
                )
            kwargs[key] = list(params[key])

    kwargs["allow_private_network"] = bool(params.get("allow_private_network", False))

    # 테스트 전용 주입 (프로덕션 호출에는 주어지지 않음).
    if "_browser_factory" in params:
        kwargs["_browser_factory"] = params["_browser_factory"]
    if "_clock" in params:
        kwargs["_clock"] = params["_clock"]
    return kwargs


def action_web_probe_manual_login(params: dict) -> ActionResult:
    """수동 로그인 확인 모드 — 사용자가 직접 로그인하는 동안 read-only 관찰.

    browser_login_probe.probe_manual_login_flow 를 호출한다. ID/PW 자동 입력,
    클릭, 제출, 쿠키/스토리지 수집을 일절 수행하지 않는다. 반환 data 에는
    HTML 원문 / 쿠키 / 세션 / password / hidden value 가 포함되지 않는다.
    """
    from core.agent_runtime.browser import browser_login_probe

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False,
            "web_probe_manual_login 실패",
            {},
            "url 누락",
            error_code="MISSING_URL",
        )

    kwargs = _probe_login_kwargs(params, url)
    if isinstance(kwargs, ActionResult):
        return kwargs

    try:
        result = browser_login_probe.probe_manual_login_flow(**kwargs)
    except Exception as e:
        logger.exception("web_probe_manual_login 실행 실패")
        return ActionResult(
            False,
            "web_probe_manual_login 예외",
            {},
            str(e)[:200],
            error_code="BROWSER_OPEN_FAILED",
        )

    if not isinstance(result, dict) or not result.get("ok"):
        code = "LOGIN_PROBE_FAILED"
        reason = "probe failed"
        data: dict = {}
        if isinstance(result, dict):
            code = str(result.get("error_code", code))
            reason = str(result.get("summary") or result.get("reason") or reason)
            data = {
                "mode": result.get("mode"),
                "initial": result.get("initial"),
                "last_observation": result.get("last_observation"),
            }
        return ActionResult(
            False,
            "web_probe_manual_login 거절",
            data,
            reason[:200],
            error_code=code,
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


def _guarded_field_error(action_name: str, selector, text, value) -> ActionResult | None:
    """guarded 액션의 selector/text/value 타입 검증 (순서 고정)."""
    if selector is not None and not isinstance(selector, str):
        return ActionResult(
            False,
            f"{action_name} 실패",
            {},
            "selector 는 문자열이어야 함",
            error_code="INVALID_SELECTOR",
        )
    if text is not None and not isinstance(text, str):
        return ActionResult(
            False,
            f"{action_name} 실패",
            {},
            "text 는 문자열이어야 함",
            error_code="INVALID_TEXT",
        )
    if value is not None and not isinstance(value, (str, int, float)):
        return ActionResult(
            False,
            f"{action_name} 실패",
            {},
            "value 는 문자열/숫자여야 함",
            error_code="INVALID_VALUE",
        )
    return None


def _action_browser_guarded(
    action_name: str,
    params: dict,
) -> ActionResult:
    """web_*_guarded 액션 공통 디스패처.

    high/critical 로 분류된 호출은 실제 브라우저 API 를 호출하지 않고
    success=True, approval_required=True, action_executed=False 로 반환한다.
    blocked 액션도 동일하게 즉시 거절된다 (차이: summary 에 blocked 표기).
    """

    if not isinstance(params, dict):
        params = {}

    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(
            False,
            f"{action_name} 실패",
            {},
            "url 누락",
            error_code="MISSING_URL",
        )

    selector = params.get("selector")
    text = params.get("text")
    value = params.get("value")
    field_err = _guarded_field_error(action_name, selector, text, value)
    if field_err is not None:
        return field_err
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
            False,
            f"{action_name} 미등록",
            {},
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
            False,
            f"{action_name} 예외",
            {},
            str(e)[:200],
            error_code="BROWSER_ACTION_FAILED",
        )

    if not isinstance(result, dict):
        return ActionResult(
            False,
            f"{action_name} 비정상 응답",
            {},
            "result is not dict",
            error_code="BROWSER_ACTION_FAILED",
        )

    # URL 검증 실패 / 의존성 없음 등은 ok=False.
    if not result.get("ok"):
        return ActionResult(
            False,
            f"{action_name} 거절",
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
    from core.agent_runtime.browser import site_mapper

    if not isinstance(params, dict):
        params = {}

    page_observation = params.get("page_observation")
    if not isinstance(page_observation, dict):
        return ActionResult(
            False,
            "web_build_site_map_prompt 실패",
            {},
            "page_observation dict 누락",
            error_code="MISSING_PAGE_OBSERVATION",
        )

    user_goal = params.get("user_goal")
    if user_goal is not None and not isinstance(user_goal, str):
        return ActionResult(
            False,
            "web_build_site_map_prompt 실패",
            {},
            "user_goal 은 문자열이어야 함",
            error_code="INVALID_USER_GOAL",
        )

    domain_profile = params.get("domain_profile")
    if domain_profile is not None and not isinstance(domain_profile, dict):
        return ActionResult(
            False,
            "web_build_site_map_prompt 실패",
            {},
            "domain_profile 은 dict 이어야 함",
            error_code="INVALID_DOMAIN_PROFILE",
        )

    hints = params.get("keyword_hints")
    if hints is not None and not isinstance(hints, list):
        return ActionResult(
            False,
            "web_build_site_map_prompt 실패",
            {},
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
            False,
            "web_build_site_map_prompt 예외",
            {},
            str(e)[:200],
            error_code="SITE_MAP_BUILD_FAILED",
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
        success=True,
        summary=summary,
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
    from core.agent_runtime.tools import file_scanner

    if not isinstance(params, dict):
        params = {}

    root_path = str(params.get("root_path", "")).strip()
    if not root_path:
        return ActionResult(
            False,
            "scan_file_tree 실패",
            {},
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
                    False,
                    "scan_file_tree 실패",
                    {},
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
            False,
            "scan_file_tree 예외",
            {},
            str(e)[:200],
            error_code="SCAN_FAILED",
        )

    if not isinstance(report, dict) or not report.get("ok"):
        code = str(report.get("error_code", "SCAN_FAILED")) if isinstance(report, dict) else "SCAN_FAILED"
        summary = str(report.get("summary", "scan failed")) if isinstance(report, dict) else "scan failed"
        return ActionResult(
            False,
            "scan_file_tree 거절",
            {},
            summary,
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
            False,
            "허용되지 않은 디렉터리",
            {"dir": str(target_path)},
            "READ_ONLY_DIRS 화이트리스트 외부 경로",
            error_code="DIR_NOT_ALLOWED",
        )
    if not target_path.exists() or not target_path.is_dir():
        return ActionResult(False, "디렉터리 없음", {"dir": str(target_path)}, error_code="DIR_NOT_FOUND")

    entries = []
    try:
        for p in sorted(target_path.iterdir()):
            entries.append(
                {
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "size": p.stat().st_size if p.is_file() else None,
                }
            )
    except OSError as e:
        return ActionResult(False, "iterdir 실패", {"dir": str(target_path)}, str(e), error_code="LIST_FAILED")
    return ActionResult(
        success=True,
        summary=f"{len(entries)} entries",
        data={"dir": str(target_path), "entries": entries},
    )


def action_browser_inspect(params: dict) -> ActionResult:
    """browser.inspect action (dry_run mode only).

    This is a thin adapter that delegates to Browser Tool Router for policy
    enforcement and backend selection. Maintains backward compatibility with
    existing ActionResult format.

    Args:
        params: dict with optional keys:
          - dry_run: bool (default False)
          - url: str (optional)

    Returns:
        ActionResult with dry_run mock or blocked response.
    """
    # Delegate to Browser Tool Router
    router_result = route_browser_task_with_params("inspect", params)

    # Convert BrowserResult to ActionResult (thin adapter pattern)
    if router_result.success:
        summary = "browser_inspect_dry_run_ok"
    else:
        summary = "browser_inspect_blocked"

    return ActionResult(
        success=router_result.success,
        summary=summary,
        data=router_result.data,
        error=router_result.error,
        error_code=router_result.error_code,
    )


def action_cdp_run(params: dict) -> ActionResult:
    """CDP 브라우저 자동화 실행 — cdp_cli.py(CLI 진입부) 전체 기능 래핑.

    params:
        site    (str)  : google | gmail | naver | g2b | gov24 | ...
        task    (str)  : cloud | list | compose | read | search | click | ...
        args    (list) : 작업별 인수 (선택)
        timeout (int)  : 최대 실행 시간(초, 기본 90)
        no_wait (bool) : while-loop 생략 여부 (기본 True)

    반환:
        ActionResult.data = {"output": "...", "exit_code": 0}
    """
    site = str(params.get("site", "google")).strip()
    task = str(params.get("task", "")).strip()
    args = params.get("args") or []
    timeout = int(params.get("timeout", 90))
    no_wait = bool(params.get("no_wait", True))

    root = repo_root()
    script = root / "scripts" / "entry" / "cdp_cli.py"

    cmd = [sys.executable, str(script), site]
    if task:
        cmd.append(task)
    cmd.extend(str(a) for a in args)
    if no_wait:
        cmd.append("--no-wait")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(root),
            encoding="utf-8",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        success = proc.returncode == 0
        return ActionResult(
            success=success,
            summary=f"cdp {site}/{task} {'ok' if success else 'fail'}",
            data={"output": output.strip(), "exit_code": proc.returncode, "site": site, "task": task, "args": args},
            error="" if success else output[-400:],
            error_code="" if success else "CDP_RUN_ERROR",
        )
    except subprocess.TimeoutExpired:
        return ActionResult(
            success=False,
            summary=f"cdp {site}/{task} timeout",
            data={"site": site, "task": task, "timeout": timeout},
            error=f"{timeout}초 초과",
            error_code="CDP_TIMEOUT",
        )


def _build_claude_command(  # noqa: PLR0913 - 키워드 전용 인자(옵션 조립 순수 함수), 묶으면 호출부만 복잡해짐
    *,
    root: Path,
    prompt: str,
    max_budget_usd: float,
    model: str,
    resume_session_id: str,
    allowed_tools: list[str],
    restricted: bool = False,
) -> list[str]:
    """action_run_claude_agent()의 claude -p 커맨드 조립 — 분리 이유는 순수 가독성/복잡도
    관리(C901)이며, 동작(옵션 순서·"--" 구분자 등)은 기존과 동일하게 유지한다.
    """
    cmd = ["claude", "-p"]
    if restricted:
        # 읽기 전용 호출(작업 분배의 계획자·조사/검토/종합): --allowedTools 는 "권한 확인 없이 허용"일 뿐
        # 사용 가능 도구를 제한하지 않는다(2026-10-02 실측: Read/Grep/Glob 만 허용했는데 Bash 가 실행됨,
        # 프로젝트 설정이 bypassPermissions). 그래서 도구 집합 자체를 닫는다.
        #  --restricted         : 코드 실행 도구·WebFetch 제거, 사용자/프로젝트 설정(bypass 포함) 무시, 파일 도구를 작업 폴더로 제한
        #  --strict-mcp-config  : --mcp-config 를 주지 않으므로 MCP 서버를 하나도 로드하지 않는다
        #  --tools              : 쓸 수 있는 내장 도구를 목록으로 한정
        cmd += ["--restricted", "--strict-mcp-config"]
    else:
        cmd += ["--mcp-config", str(root / ".mcp.json")]
    cmd += ["--output-format", "json", "--max-budget-usd", str(max_budget_usd)]
    if model:
        cmd += ["--model", model]
    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    if allowed_tools:
        joined = ",".join(allowed_tools)
        if restricted:
            cmd += ["--tools", joined]
        cmd += ["--allowedTools", joined]
    # "--" 로 옵션 파싱을 끊는다: --allowedTools 는 실측상 다음 토큰들을 계속
    # 도구 이름으로 먹어치우는 greedy 옵션이라(공식 --help의 "<tools...>" 표기와
    # 일치), 구분자 없이 prompt를 바로 이어 붙이면 "prompt 인자가 없다" 오류가 난다
    # (2026-09-28 실측 확인).
    cmd += ["--", prompt]
    return cmd


def _apply_restricted(params: dict, allowed_tools: list[str]) -> tuple[bool, list[str]]:
    """restricted 파라미터 해석. 제한 모드에서는 MCP 도구(mcp__*)를 쓸 수 없으므로 내장 도구 이름만 남긴다."""
    restricted = params.get("restricted") is True
    if restricted:
        allowed_tools = [t for t in allowed_tools if not t.startswith("mcp__")]
    return restricted, allowed_tools


_RESULT_FULL_MAX_CHARS = RESULT_FULL_MAX_CHARS  # result_max_chars 상한(정본: ai_orchestrator/contracts/agent_result_limits.py)


def action_run_claude_agent(params: dict) -> ActionResult:
    """Claude Code를 헤드리스로 실행해 MCP(haehan-orchestrator)로 앱 작업을 시킨다.

    앱 버튼 → 이 액션(작업 큐 경유) → `claude -p` 서브프로세스 → Claude가 MCP
    클라이언트로 .mcp.json의 haehan-orchestrator에 접속해 list_api_endpoints/
    call_api/snapshot_page/act_on_page/navigate_page 등 도구를 쓴다. 실제 쓰기
    작업(발행/발송/삭제 등)은 이 액션과 무관하게 기존 gates/approval.py 승인
    플로우를 그대로 거친다 — 이 액션은 그 요청을 만드는 트리거일 뿐이다.
    (docs/specs/2026-09-28_cdp_universal_automation_and_mcp_trigger.md §5.1)

    params:
      prompt        (str, 필수) — Claude에게 줄 지시문
      timeout       (int, 선택, 기본 300초, 30~1800 사이로 강제)
      max_budget_usd(float, 선택, 기본 2.0) — 이 1회 호출의 API 비용 상한
        (공식 --max-budget-usd, subagent 비용 포함, 초과 시 Claude Code가 스스로 중단)
      allowed_tools (list[str], 선택, 기본 없음) — 헤드리스 세션에서 권한 프롬프트
        없이 자동 실행을 허용할 도구 이름(예: "mcp__haehan-orchestrator__snapshot_page").
        공식 --allowedTools 플래그에 그대로 전달한다(허용목록 방식 권장,
        code.claude.com/docs/en/cli-reference 2026-09-28 확인). 비워두면(기본값)
        MCP 도구 호출은 전부 거부된다 — 이 액션의 호출자가 이번 작업에 실제로
        필요한 도구만 명시적으로 골라 넣어야 한다(--dangerously-skip-permissions
        같은 전체 우회는 쓰지 않음, 이 프로젝트 승인 원칙에 위배).
      model         (str, 선택) — 공식 --model 플래그에 그대로 전달(별칭 "sonnet"/
        "opus"/"haiku"/"fable" 또는 전체 모델명). 비우면 CLI 기본값 사용.
      restricted (bool, 선택, 기본 False) — True 면 읽기 전용 제한 모드로 실행한다: --restricted(코드 실행 도구
        제거·설정 무시·bypassPermissions 거부) + --strict-mcp-config(MCP 없음) + --tools(allowed_tools 로 도구 집합 한정).
        allowed_tools 의 mcp__* 이름은 무시한다. 작업 분배의 계획자·읽기 전용 역할이 사용한다.
      result_max_chars (int, 선택, 기본 0=사용 안 함, 최대 20000) — 주면 data["result_full"] 에 결과
        전문(이 길이까지)을 추가로 담는다. data["result"] 는 기존대로 2000자 제한(채팅 등 기존 호출 불변).
      resume_session_id (str, 선택) — 공식 -r/--resume 플래그. 같은 대화의 후속
        메시지에 이전 응답의 session_id를 넘기면 --system-prompt-snapshot(기본
        on) 덕분에 시스템 프롬프트/CLAUDE.md 재렌더링 없이 이어서 답해 매 요청마다
        수만 토큰을 새로 캐시 생성하던 지연을 줄인다(2026-09-30 실측: 콜드 스타트
        cache_creation_input_tokens 36172 vs resume 시 캐시 재사용 — 공식 문서
        code.claude.com/docs/en/cli-reference 확인, --help의 --system-prompt-snapshot
        설명 "a resume sends the record as-is" 근거).

    반환:
      ActionResult.data = {"result": "...", "session_id": "...", "cost_usd": 0.0, "num_turns": N}
      session_id는 다음 호출의 resume_session_id로 재사용할 수 있다.
    """
    prompt = str(params.get("prompt", "")).strip()
    if not prompt:
        return ActionResult(False, "run_claude_agent 실패", {}, "prompt 누락", error_code="MISSING_PROMPT")

    try:
        timeout = int(params.get("timeout", 300))
    except (TypeError, ValueError):
        timeout = 300
    timeout = max(30, min(timeout, 1800))

    try:
        max_budget_usd = float(params.get("max_budget_usd", 2.0))
    except (TypeError, ValueError):
        max_budget_usd = 2.0

    raw_allowed_tools = params.get("allowed_tools") or []
    if not isinstance(raw_allowed_tools, list):
        raw_allowed_tools = [raw_allowed_tools]
    allowed_tools = [str(t).strip() for t in raw_allowed_tools if str(t).strip()]
    restricted, allowed_tools = _apply_restricted(params, allowed_tools)

    model = str(params.get("model", "")).strip()
    resume_session_id = str(params.get("resume_session_id", "")).strip()
    try:
        result_max_chars = max(0, min(int(params.get("result_max_chars", 0) or 0), _RESULT_FULL_MAX_CHARS))
    except (TypeError, ValueError):
        result_max_chars = 0

    root = repo_root()
    cmd = _build_claude_command(
        root=root,
        prompt=prompt,
        max_budget_usd=max_budget_usd,
        model=model,
        resume_session_id=resume_session_id,
        allowed_tools=allowed_tools,
        restricted=restricted,
    )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(root),
            # 에이전트는 Electron(Node spawn)이 stdin 을 열린 빈 파이프로 넘겨 띄운다 — 그대로 상속하면
            # claude -p 가 입력을 3초 기다린 뒤 시작한다(2026-10-04 실측: 18.6초 → 15.1초).
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return ActionResult(
            False,
            "run_claude_agent 실패",
            {},
            "claude CLI를 찾을 수 없습니다 (PATH 확인 필요)",
            error_code="CLAUDE_CLI_NOT_FOUND",
        )
    except subprocess.TimeoutExpired:
        return ActionResult(
            success=False,
            summary=f"run_claude_agent timeout({timeout}s)",
            data={"timeout": timeout},
            error=f"{timeout}초 초과",
            error_code="CLAUDE_AGENT_TIMEOUT",
        )

    raw_stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(raw_stdout) if raw_stdout else {}
    except json.JSONDecodeError:
        payload = {}

    is_error = bool(payload.get("is_error", proc.returncode != 0))
    full_text = str(payload.get("result", "") or "")
    result_text = full_text[:2000]
    success = proc.returncode == 0 and not is_error

    data = {
        "result": result_text,
        "session_id": payload.get("session_id", ""),
        "cost_usd": payload.get("total_cost_usd"),
        "num_turns": payload.get("num_turns"),
    }
    if result_max_chars:
        # 작업 분배(계획 JSON·하위 작업 결과)처럼 긴 결과가 필요한 호출자만 선택한다. 기존 호출은 변화 없음.
        data["result_full"] = full_text[:result_max_chars]

    return ActionResult(
        success=success,
        summary=(result_text[:300] if success else f"실패(exit={proc.returncode})"),
        data=data,
        error="" if success else ((proc.stderr or "")[:400] or result_text[:400]),
        error_code="" if success else "CLAUDE_AGENT_ERROR",
    )


# ── KRAS 서식 액션 ────────────────────────────────────────────────────────


def action_kras_form_create_session(params: dict) -> ActionResult:
    """KRAS 서식 세션 생성 — prefill 자동 주입 포함.

    params:
      form_type   (str, 필수) — 예: "risk_assessment", "tbm_log"
      project_id  (str|int)   — 미지정 시 KRAS_PROJECT_ID 환경변수 사용
      site_id     (str|int)   — 선택
    """
    from core.agent_runtime.tools import kras_connector

    form_type = str(params.get("form_type", "")).strip()
    if not form_type:
        return ActionResult(False, "form_type 필수", {}, "form_type 파라미터 없음", error_code="MISSING_PARAM")

    project_id = params.get("project_id") or os.getenv("KRAS_PROJECT_ID", "")
    if not project_id:
        return ActionResult(
            False,
            "project_id 필수",
            {},
            "project_id 파라미터 또는 KRAS_PROJECT_ID 환경변수 없음",
            error_code="MISSING_PARAM",
        )

    site_id = params.get("site_id")
    try:
        session = kras_connector.create_form_session(form_type, project_id, site_id)
        return ActionResult(
            success=True,
            summary=f"KRAS 세션 생성: {session.get('display_name', form_type)}",
            data=session,
        )
    except Exception as exc:
        logger.exception("kras.form.create_session 실패")
        return ActionResult(False, "KRAS 세션 생성 실패", {}, str(exc), error_code="KRAS_API_ERROR")


def action_kras_form_get_session(params: dict) -> ActionResult:
    """KRAS 서식 세션 상태 조회.

    params:
      session_id  (str, 필수)
    """
    from core.agent_runtime.tools import kras_connector

    session_id = str(params.get("session_id", "")).strip()
    if not session_id:
        return ActionResult(False, "session_id 필수", {}, "session_id 파라미터 없음", error_code="MISSING_PARAM")
    try:
        session = kras_connector.get_form_session(session_id)
        return ActionResult(
            success=True,
            summary=f"KRAS 세션: {session.get('status', '?')}",
            data=session,
        )
    except Exception as exc:
        logger.exception("kras.form.get_session 실패")
        return ActionResult(False, "KRAS 세션 조회 실패", {}, str(exc), error_code="KRAS_API_ERROR")


def action_kras_form_list_forms(_params: dict) -> ActionResult:
    """KRAS 사용 가능한 서식 목록 조회."""
    from core.agent_runtime.tools import kras_connector

    try:
        forms = kras_connector.list_forms()
        return ActionResult(
            success=True,
            summary=f"KRAS 서식 {len(forms)}개",
            data={"forms": forms, "count": len(forms)},
        )
    except Exception as exc:
        logger.exception("kras.form.list_forms 실패")
        return ActionResult(False, "KRAS 서식 목록 조회 실패", {}, str(exc), error_code="KRAS_API_ERROR")


# ── 디스패치 ──────────────────────────────────────────────────────────────

# 1단계에서 본 모듈에 노출되는 액션. 명시적으로 등록되지 않은 액션은
# UNKNOWN_ACTION 으로 거절된다. 파일 수정/삭제/전송은 의도적으로 미등록.
_ACTIONS = {
    "ping": action_ping,
    "ws_noop": action_ws_noop,
    "system_info": action_system_info,
    "list_allowed_apps": action_list_allowed_apps,
    "open_url": action_open_url,
    "open_url_execute": action_open_url_execute,
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
    "browser.inspect": action_browser_inspect,
    "cdp.run": action_cdp_run,
    "run_claude_agent": action_run_claude_agent,
    # KRAS 서식 작성 연동 (kras_connector.py)
    "kras.form.create_session": action_kras_form_create_session,
    "kras.form.get_session": action_kras_form_get_session,
    "kras.form.list_forms": action_kras_form_list_forms,
}

# 명시적 거절 액션 (오해 방지를 위해 별도 표기 — 등록 자체는 안 함)
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "delete_file",
        "upload_file",
        "modify_file",
        "execute_shell",
    }
)


def execute_action(action: str, params: dict) -> ActionResult:
    action = (action or "").strip().lower()
    if action in FORBIDDEN_ACTIONS:
        return ActionResult(
            False,
            f"{action} 거절",
            {},
            "1단계 금지 액션 (파일 수정/삭제/전송, unrestricted shell)",
            error_code="ACTION_FORBIDDEN",
        )
    fn = _ACTIONS.get(action)
    if fn is None:
        return ActionResult(
            False,
            f"{action} 미등록",
            {},
            "지원되지 않는 액션",
            error_code="UNKNOWN_ACTION",
        )
    try:
        return fn(params or {})
    except Exception as e:
        logger.exception("action %s 실행 실패", action)
        return ActionResult(False, f"{action} 예외", {}, str(e), error_code="EXECUTION_ERROR")


# ── 헬퍼 ──────────────────────────────────────────────────────────────────


def _safe_final_url(current_url: str, url_category: str) -> str | None:
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
    except Exception:  # noqa: S110, BLE001
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
    return datetime.now(UTC).isoformat()


def _agent_version() -> str:
    try:
        from local_agent import __version__

        return __version__
    except Exception:  # noqa: BLE001 - 로컬 에이전트 액션 디스패처 -- 각 액션 실행 실패를 ActionResult(False, ...)로 변환해 반환(fail-closed), 버전 조회/로컬호스트 URL 정규화 실패는 안전한 기본값으로 폴백
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
    "FORBIDDEN_ACTIONS",
    "ActionResult",
    "action_browser_inspect",
    "action_capture_screenshot",
    "action_list_allowed_apps",
    "action_list_files_readonly",
    "action_open_url",
    "action_open_url_execute",
    "action_ping",
    "action_scan_file_tree",
    "action_system_info",
    "action_web_analyze_html",
    "action_web_build_site_map_prompt",
    "action_web_click_guarded",
    "action_web_open_url_readonly",
    "action_web_probe_manual_login",
    "action_web_scroll_guarded",
    "action_web_select_guarded",
    "action_web_type_guarded",
    "execute_action",
]
