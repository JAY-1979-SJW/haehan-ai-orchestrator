"""웹 자동녹화 worker (F-4S-8a dry-run + F-4S-8b local execute).

설계 원칙:
- 입력: F-4S-7 web_recording_queue JSON.
- 기본 동작: dry-run (실행계획 JSON + Markdown 리포트만 생성).
- execute 모드: --execute 명시 시에만 실제 브라우저 실행 허용.

[execute 허용 범위]
- 허용 URL: localhost / 127.0.0.1 / ::1 / allow_hosts 로 지정한 내부 host 만.
- 외부 사이트(naver.com, youtube.com, google.com, hometax.go.kr 등) 녹화 금지.
- 로그인/인증 필요 URL 금지.
- 허용 브라우저 호출: chromium.launch / browser.new_context(record_video_dir) /
  context.new_page / page.goto / page.wait_for_timeout / page.screenshot /
  context.close / browser.close.
- 금지 브라우저 호출: page.click / page.fill / page.type / page.press /
  page.keyboard / page.mouse / page.evaluate / page.route /
  storage_state / cookies / input_value / download / upload.

[공통 금지]
- click/fill/type/press/submit/upload/download/login/purchase/comment/post step.
- API key / client_secret / cookie / session / storage 접근/기록 금지.
- OAuth / 네이버·유튜브 업로드 / LTX API 호출 금지.
- .env 커밋 금지.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse


ALLOWED_STEP_TYPES = (
    "open_url",
    "wait",
    "capture_scene",
    "scroll_plan",
    "overlay_caption",
)

FORBIDDEN_STEP_TYPES = (
    "click",
    "fill",
    "type",
    "press",
    "submit",
    "upload",
    "download",
    "login",
    "purchase",
    "comment",
    "post",
    "hover",
    "drag",
    "select_option",
    "set_storage",
    "set_cookie",
)

VALID_VIEWPORTS: Dict[str, Dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "wide": {"width": 1920, "height": 1080},
    "mobile": {"width": 390, "height": 844},
}

DEFAULT_RECORDINGS_SUBDIR = "recordings"

_EXTERNAL_PLATFORM_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "naver.com",
    "blog.naver.com",
    "cafe.naver.com",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
)

# execute 모드: 허용 host 기본값 (localhost 계열만)
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = ("localhost", "127.0.0.1", "::1")

# execute 모드에서 기본 차단되는 외부 host
_FORBIDDEN_EXECUTE_HOSTS: tuple[str, ...] = (
    "naver.com",
    "youtube.com",
    "youtu.be",
    "google.com",
    "hometax.go.kr",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "kakao.com",
    "daum.net",
)

_LOGIN_URL_HINTS = (
    "login", "signin", "sign-in", "/auth/", "/oauth",
    "회원", "로그인", "mypage", "마이페이지",
)

DEFAULT_MAX_RECORD_SECONDS = 60


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ensure_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _looks_like_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def _is_external_platform(url: str) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except (ValueError, TypeError):
        return False
    return any(domain in host for domain in _EXTERNAL_PLATFORM_DOMAINS)


def _normalize_viewport(viewport: Any) -> Dict[str, Any]:
    if not isinstance(viewport, dict):
        name = "desktop"
        spec = VALID_VIEWPORTS[name]
        return {"name": name, "width": spec["width"], "height": spec["height"]}
    name = _ensure_str(viewport.get("name")).strip().lower() or "desktop"
    if name not in VALID_VIEWPORTS:
        spec = VALID_VIEWPORTS["desktop"]
        return {"name": "desktop", "width": spec["width"], "height": spec["height"]}
    spec = VALID_VIEWPORTS[name]
    width = viewport.get("width") or spec["width"]
    height = viewport.get("height") or spec["height"]
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        width = spec["width"]
        height = spec["height"]
    return {"name": name, "width": width, "height": height}


# ---------------------------------------------------------------------------
# Loading / validation
# ---------------------------------------------------------------------------


def load_recording_queue(path: Path) -> Dict[str, Any]:
    """F-4S-7 web_recording_queue JSON 을 로드."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("recording queue root must be an object")
    return data


def validate_recording_queue(queue: Any) -> Dict[str, Any]:
    """recording queue 전체 구조 검증.

    반환: {"items": [...], "errors": [...]}
    items 는 dict list. queue 자체가 비정상이면 errors 에 사유.
    """
    errors: List[str] = []
    if isinstance(queue, dict):
        raw_items = queue.get("queue")
    elif isinstance(queue, list):
        raw_items = queue
    else:
        errors.append("recording_queue:not_object_or_list")
        return {"items": [], "errors": errors}

    if not isinstance(raw_items, list):
        errors.append("recording_queue:queue_field_missing_or_invalid")
        return {"items": [], "errors": errors}

    items = [it for it in raw_items if isinstance(it, dict)]
    if len(items) != len(raw_items):
        errors.append("recording_queue:non_dict_items_skipped")
    return {"items": items, "errors": errors}


def validate_recording_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """단일 recording item 의 step / target_url / viewport 검증.

    반환:
      {
        "blocked_steps": [{"step_no": .., "type": ..}, ...],
        "allowed_steps": [{"step_no": .., "type": ..}, ...],
        "warnings": [...],
        "errors": [...],
      }
    실제 click/fill/type/press 등이 step 에 등장하면 blocked_steps 에 기록.
    """
    warnings: List[str] = []
    errors: List[str] = []
    allowed: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    if not isinstance(item, dict):
        errors.append("item:not_object")
        return {
            "allowed_steps": allowed,
            "blocked_steps": blocked,
            "warnings": warnings,
            "errors": errors,
        }

    target_url = _ensure_str(item.get("target_url")).strip() or None
    if not target_url:
        warnings.append("target_url_missing")
    else:
        if not _looks_like_url(target_url):
            warnings.append("target_url_invalid")
        elif _is_external_platform(target_url):
            warnings.append("external_target_review_required")

    steps = item.get("recording_steps") or []
    if not isinstance(steps, list):
        errors.append("recording_steps:not_list")
        steps = []

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            errors.append(f"step:{idx}:not_object")
            continue
        step_type = _ensure_str(step.get("type")).strip().lower()
        step_no = step.get("step_no") or idx
        entry = {"step_no": step_no, "type": step_type}
        if step_type in FORBIDDEN_STEP_TYPES:
            blocked.append(entry)
            continue
        if step_type not in ALLOWED_STEP_TYPES:
            blocked.append({**entry, "reason": "unknown_step_type"})
            continue
        allowed.append(entry)

    return {
        "allowed_steps": allowed,
        "blocked_steps": blocked,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Simulation / execution plan
# ---------------------------------------------------------------------------


def _coerce_record_seconds(item: Dict[str, Any]) -> int:
    raw = item.get("duration_seconds")
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 30
    if n <= 0:
        return 30
    return n


def _output_paths(
    item: Dict[str, Any],
    *,
    output_dir: Path,
) -> Dict[str, str]:
    rec_id = _ensure_str(item.get("recording_id")) or "recording_unknown"
    base = Path(output_dir) / DEFAULT_RECORDINGS_SUBDIR
    return {
        "output_video_path": str(base / f"{rec_id}.mp4"),
        "output_metadata_path": str(base / f"{rec_id}.json"),
    }


def simulate_recording_item(
    item: Dict[str, Any],
    *,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """단일 item 에 대한 dry-run 실행계획.

    실제 브라우저 실행/녹화 없이 어떤 url 을 어떤 viewport 로 몇 초 녹화할지
    "would_*" 형태로만 기록한다. 파일도 만들지 않는다.
    """
    out_dir = Path(output_dir) if output_dir else Path("runs/video")
    validation = validate_recording_item(item)
    target_url = _ensure_str(item.get("target_url")).strip() or None
    record_seconds = _coerce_record_seconds(item)
    viewport = _normalize_viewport(item.get("viewport"))
    paths = _output_paths(item, output_dir=out_dir)

    has_target = bool(target_url)
    has_blocked = bool(validation["blocked_steps"])
    has_errors = bool(validation["errors"])

    if not has_target or has_errors:
        status = "blocked"
    elif has_blocked:
        status = "blocked"
    else:
        status = "validated"

    return {
        "recording_id": _ensure_str(item.get("recording_id")) or None,
        "source_queue_id": _ensure_str(item.get("source_queue_id")) or None,
        "title": _ensure_str(item.get("title")),
        "status": status,
        "would_open_url": target_url,
        "would_record_seconds": record_seconds if has_target else 0,
        "viewport": viewport,
        "steps_count": len(item.get("recording_steps") or []),
        "allowed_steps": validation["allowed_steps"],
        "blocked_steps": validation["blocked_steps"],
        "output_video_path": paths["output_video_path"],
        "output_metadata_path": paths["output_metadata_path"],
        "warnings": validation["warnings"],
        "errors": validation["errors"],
        "dry_run": True,
    }


def build_execution_plan(
    queue: Any,
    *,
    output_dir: Path,
    dry_run: bool = True,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """recording queue 전체 → dry-run execution plan.

    dry_run=False 는 NotImplementedError — execute_recording_plan 을 사용할 것.
    """
    if not dry_run:
        raise NotImplementedError(
            "use execute_recording_plan() for actual recording — "
            "requires --execute flag and internal URLs only"
        )

    out_dir = Path(output_dir)
    queue_validation = validate_recording_queue(queue)
    items = queue_validation["items"]

    if isinstance(max_items, int) and max_items > 0:
        items = items[:max_items]

    simulated: List[Dict[str, Any]] = []
    for item in items:
        simulated.append(simulate_recording_item(item, output_dir=out_dir))

    validated_count = sum(1 for r in simulated if r["status"] == "validated")
    blocked_count = sum(1 for r in simulated if r["status"] == "blocked")
    warning_count = sum(len(r["warnings"]) for r in simulated)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": True,
        "output_dir": str(out_dir),
        "queue_errors": queue_validation["errors"],
        "total_items": len(simulated),
        "validated_count": validated_count,
        "blocked_count": blocked_count,
        "warning_count": warning_count,
        "allowed_step_types": list(ALLOWED_STEP_TYPES),
        "forbidden_step_types": list(FORBIDDEN_STEP_TYPES),
        "items": simulated,
        "notes": [
            "F-4S-8a 웹 자동녹화 worker dry-run",
            "실제 브라우저 실행 / page.goto / browser.launch 미수행",
            "실제 mp4 파일 생성 미수행 — output path 는 계획 문자열일 뿐",
            "click/fill/type/press 등 자동 입력 step 은 본 worker 에서 차단",
            "실제 녹화는 F-4S-8b 에서 사람 검수 후 별도 승인",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_worker_markdown_report(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# 웹 자동녹화 worker dry-run 리포트 (F-4S-8a)")
    lines.append("")
    lines.append(f"- generated_at: {result.get('generated_at')}")
    lines.append(f"- dry_run: {result.get('dry_run')}")
    lines.append(f"- total_items: {result.get('total_items')}")
    lines.append(f"- validated_count: {result.get('validated_count')}")
    lines.append(f"- blocked_count: {result.get('blocked_count')}")
    lines.append(f"- warning_count: {result.get('warning_count')}")
    lines.append("- 허용 step: open_url / wait / capture_scene / scroll_plan / overlay_caption")
    lines.append("- 금지 step: click / fill / type / press / submit / upload / download / login / purchase / comment / post")
    lines.append("- 실제 브라우저 실행 없음 / 실제 mp4 생성 없음")
    lines.append("")

    queue_errors = result.get("queue_errors") or []
    if queue_errors:
        lines.append("## queue_errors")
        for e in queue_errors:
            lines.append(f"- {e}")
        lines.append("")

    items = result.get("items") or []
    if not items:
        lines.append("## items")
        lines.append("- (비어 있음)")
        lines.append("")
        return "\n".join(lines)

    lines.append("## items")
    for it in items:
        lines.append(
            f"### {it.get('recording_id')} — {it.get('title') or '(제목 없음)'}"
        )
        lines.append(f"- status: {it.get('status')}")
        lines.append(f"- would_open_url: {it.get('would_open_url') or '(미지정)'}")
        lines.append(f"- would_record_seconds: {it.get('would_record_seconds')}")
        vp = it.get("viewport") or {}
        lines.append(
            f"- viewport: {vp.get('name')} ({vp.get('width')}x{vp.get('height')})"
        )
        lines.append(f"- steps_count: {it.get('steps_count')}")
        lines.append(f"- allowed_steps: {len(it.get('allowed_steps') or [])}")
        lines.append(f"- blocked_steps: {len(it.get('blocked_steps') or [])}")
        for b in it.get("blocked_steps") or []:
            reason = f" reason={b.get('reason')}" if b.get("reason") else ""
            lines.append(
                f"  - blocked step_no={b.get('step_no')} type={b.get('type')}{reason}"
            )
        for w in it.get("warnings") or []:
            lines.append(f"- warning: {w}")
        for e in it.get("errors") or []:
            lines.append(f"- error: {e}")
        lines.append(f"- output_video_path: {it.get('output_video_path')}")
        lines.append(f"- output_metadata_path: {it.get('output_metadata_path')}")
        lines.append(f"- dry_run: {it.get('dry_run')}")
        lines.append("")

    lines.append("## 다음 단계")
    lines.append("- F-4S-8b: 실제 브라우저 실행/녹화는 별도 worker 에서 승인 후 구현")
    lines.append("- 내부 URL / 로그인 불필요 화면 우선, click/fill/type 없음, 저장 경로 고정, 사람 검수")
    lines.append("")
    return "\n".join(lines)


def write_worker_result_files(
    result: Dict[str, Any],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Path]:
    """dry-run 결과 JSON + Markdown 을 파일로 저장."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"web_recording_worker_{ts}"
    json_path = out_path / f"{base}.json"
    md_path = out_path / f"{base}.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_worker_markdown_report(result), encoding="utf-8")
    return {"json": json_path, "md": md_path}


# ---------------------------------------------------------------------------
# Execute mode — internal URL only (F-4S-8b)
# ---------------------------------------------------------------------------


def _coerce_allow_hosts(allow_hosts: Any) -> tuple[str, ...]:
    if allow_hosts is None:
        return DEFAULT_ALLOWED_HOSTS
    if isinstance(allow_hosts, (list, tuple)):
        merged = set(DEFAULT_ALLOWED_HOSTS)
        for h in allow_hosts:
            if isinstance(h, str) and h.strip():
                merged.add(h.strip().lower())
        return tuple(merged)
    return DEFAULT_ALLOWED_HOSTS


def is_allowed_recording_url(
    url: str,
    allow_hosts: Any = None,
) -> bool:
    """URL 이 실제 녹화 허용 대상인지 확인.

    허용 조건:
    - scheme 이 http 또는 https
    - host 가 allow_hosts (기본: localhost / 127.0.0.1 / ::1) 중 하나
    - _FORBIDDEN_EXECUTE_HOSTS 에 포함되지 않을 것
    - 로그인 힌트 없을 것
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False

    # 기본 차단 외부 host
    for forbidden in _FORBIDDEN_EXECUTE_HOSTS:
        if host == forbidden or host.endswith("." + forbidden):
            return False

    # 로그인 힌트
    full_lower = url.lower()
    for hint in _LOGIN_URL_HINTS:
        if hint in full_lower:
            return False

    # allow_hosts 확인
    allowed = _coerce_allow_hosts(allow_hosts)
    return host in allowed


def validate_execute_allowed(
    queue: Any,
    allow_hosts: Any = None,
) -> Dict[str, Any]:
    """execute 모드 전 queue 전체 검증.

    반환:
      {
        "allowed_items": [...],   # 실행 가능한 item
        "blocked_items": [...],   # 실행 불가 item (이유 포함)
        "errors": [...],
        "can_execute": bool,
      }
    blocked_item 이 하나라도 있으면 can_execute=False — 전체 중단.
    """
    errors: List[str] = []
    allowed_items: List[Dict[str, Any]] = []
    blocked_items: List[Dict[str, Any]] = []

    queue_result = validate_recording_queue(queue)
    errors.extend(queue_result["errors"])
    items = queue_result["items"]

    for item in items:
        rec_id = _ensure_str(item.get("recording_id")) or "unknown"
        item_errors: List[str] = []
        target_url = _ensure_str(item.get("target_url")).strip() or None

        if not target_url:
            item_errors.append("target_url_missing")
        elif not is_allowed_recording_url(target_url, allow_hosts=allow_hosts):
            item_errors.append(f"url_not_allowed_for_execute:{target_url}")

        # forbidden step check
        val = validate_recording_item(item)
        if val["blocked_steps"]:
            for bs in val["blocked_steps"]:
                item_errors.append(f"forbidden_step:{bs.get('type')}")

        if item_errors:
            blocked_items.append({
                "recording_id": rec_id,
                "title": _ensure_str(item.get("title")),
                "reasons": item_errors,
            })
        else:
            allowed_items.append(item)

    can_execute = len(blocked_items) == 0 and len(errors) == 0 and len(allowed_items) > 0
    return {
        "allowed_items": allowed_items,
        "blocked_items": blocked_items,
        "errors": errors,
        "can_execute": can_execute,
    }


def _get_sync_playwright():
    """Playwright sync_api 를 lazy import.

    playwright 가 설치되지 않은 환경에서도 모듈 로드가 가능하도록 지연 임포트.
    execute 모드에서만 호출된다.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
        return sync_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is required for execute mode: "
            "pip install playwright && playwright install chromium"
        ) from exc


def execute_recording_item(
    item: Dict[str, Any],
    *,
    output_dir: Path,
    allow_hosts: Any = None,
    headless: bool = True,
    max_record_seconds: int = DEFAULT_MAX_RECORD_SECONDS,
    take_screenshot: bool = False,
) -> Dict[str, Any]:
    """단일 item 을 실제 브라우저로 녹화 (내부 URL 전용).

    허용 브라우저 호출만 사용:
    - chromium.launch / new_context(record_video_dir) / new_page
    - page.goto / page.wait_for_timeout / page.screenshot
    - context.close / browser.close

    금지: page.click / page.fill / page.type / page.press / page.keyboard /
          page.mouse / page.evaluate / storage_state / cookies / route 등.
    """
    rec_id = _ensure_str(item.get("recording_id")) or "recording_unknown"
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    target_url = _ensure_str(item.get("target_url")).strip() or None
    viewport = _normalize_viewport(item.get("viewport"))
    out_dir = Path(output_dir)
    video_dir = out_dir / DEFAULT_RECORDINGS_SUBDIR / rec_id
    video_dir.mkdir(parents=True, exist_ok=True)

    warnings: List[str] = []
    screenshot_paths: List[str] = []

    # URL guard
    if not target_url:
        return {
            "recording_id": rec_id,
            "status": "blocked",
            "reason": "target_url_missing",
            "started_at": started_at,
            "finished_at": started_at,
            "success": False,
            "dry_run": False,
        }
    if not is_allowed_recording_url(target_url, allow_hosts=allow_hosts):
        return {
            "recording_id": rec_id,
            "status": "blocked",
            "reason": f"url_not_allowed:{target_url}",
            "started_at": started_at,
            "finished_at": started_at,
            "success": False,
            "dry_run": False,
        }

    # step guard
    val = validate_recording_item(item)
    if val["blocked_steps"]:
        blocked_types = [bs.get("type") for bs in val["blocked_steps"]]
        return {
            "recording_id": rec_id,
            "status": "blocked",
            "reason": f"forbidden_steps:{blocked_types}",
            "started_at": started_at,
            "finished_at": started_at,
            "success": False,
            "dry_run": False,
        }

    steps = item.get("recording_steps") or []
    steps_executed: List[str] = []
    video_path: Optional[str] = None
    browser = None
    context = None

    sync_playwright = _get_sync_playwright()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": viewport["width"], "height": viewport["height"]},
                record_video_dir=str(video_dir),
                record_video_size={"width": viewport["width"], "height": viewport["height"]},
            )
            page = context.new_page()

            page.goto(target_url, wait_until="networkidle", timeout=30000)
            steps_executed.append("open_url")

            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_type = _ensure_str(step.get("type")).strip().lower()
                if step_type in FORBIDDEN_STEP_TYPES:
                    warnings.append(f"forbidden_step_skipped:{step_type}")
                    continue
                if step_type == "wait":
                    wait_ms = int(step.get("wait_seconds") or 2) * 1000
                    page.wait_for_timeout(wait_ms)
                    steps_executed.append("wait")
                elif step_type == "capture_scene":
                    dur = min(int(step.get("duration_seconds") or 5), max_record_seconds)
                    page.wait_for_timeout(dur * 1000)
                    if take_screenshot:
                        sc_path = video_dir / f"scene_{len(screenshot_paths)+1:03d}.png"
                        page.screenshot(path=str(sc_path))
                        screenshot_paths.append(str(sc_path))
                    steps_executed.append("capture_scene")
                elif step_type == "scroll_plan":
                    # scroll 은 page.evaluate 없이는 수행 불가 — wait 로 대체
                    wait_ms = int(step.get("wait_seconds") or 1) * 1000
                    page.wait_for_timeout(wait_ms)
                    steps_executed.append("scroll_plan(wait_only)")
                    warnings.append("scroll_plan:actual_scroll_skipped_use_wait_only")
                elif step_type == "overlay_caption":
                    steps_executed.append("overlay_caption(skipped_post_process)")
                elif step_type == "open_url":
                    # 이미 goto 했으므로 skip
                    steps_executed.append("open_url(already_done)")

            # video path 수집 (context.close 전)
            if page.video:
                video_path = str(page.video.path())

            context.close()
            browser.close()

    except Exception as exc:  # noqa: BLE001
        finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if context:
            try:
                context.close()
            except Exception:  # noqa: BLE001
                pass
        if browser:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                pass
        return {
            "recording_id": rec_id,
            "status": "failed",
            "error": str(exc),
            "started_at": started_at,
            "finished_at": finished_at,
            "success": False,
            "dry_run": False,
        }

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # metadata JSON 저장
    metadata: Dict[str, Any] = {
        "recording_id": rec_id,
        "source_queue_id": _ensure_str(item.get("source_queue_id")) or None,
        "target_url": target_url,
        "viewport": viewport,
        "steps_executed": steps_executed,
        "video_dir": str(video_dir),
        "video_path": video_path,
        "screenshot_paths": screenshot_paths,
        "warnings": warnings,
        "started_at": started_at,
        "finished_at": finished_at,
        "success": True,
    }
    meta_path = video_dir / f"{rec_id}_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "recording_id": rec_id,
        "source_queue_id": _ensure_str(item.get("source_queue_id")) or None,
        "title": _ensure_str(item.get("title")),
        "status": "executed",
        "target_url": target_url,
        "viewport": viewport,
        "steps_executed": steps_executed,
        "video_dir": str(video_dir),
        "video_path": video_path,
        "screenshot_paths": screenshot_paths,
        "output_metadata_path": str(meta_path),
        "warnings": warnings,
        "started_at": started_at,
        "finished_at": finished_at,
        "success": True,
        "dry_run": False,
    }


def execute_recording_plan(
    queue: Any,
    *,
    output_dir: Path,
    allow_hosts: Any = None,
    headless: bool = True,
    max_record_seconds: int = DEFAULT_MAX_RECORD_SECONDS,
    take_screenshot: bool = False,
    max_items: Optional[int] = None,
) -> Dict[str, Any]:
    """execute 모드 — 내부 URL 에 한해 실제 브라우저 녹화.

    validate_execute_allowed 통과 시에만 녹화를 시작한다.
    blocked item 이 하나라도 있으면 전체 실행을 중단한다.
    """
    out_dir = Path(output_dir)
    validation = validate_execute_allowed(queue, allow_hosts=allow_hosts)

    if not validation["can_execute"]:
        blocked_reasons = [
            f"{b['recording_id']}: {b['reasons']}"
            for b in validation["blocked_items"]
        ]
        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dry_run": False,
            "status": "blocked",
            "reason": "validate_execute_allowed failed",
            "blocked_items": validation["blocked_items"],
            "errors": validation["errors"],
            "blocked_reasons": blocked_reasons,
            "executed_count": 0,
            "blocked_count": len(validation["blocked_items"]),
            "items": [],
            "notes": ["execute 차단 — blocked item 해결 후 재시도"],
        }

    items = validation["allowed_items"]
    if isinstance(max_items, int) and max_items > 0:
        items = items[:max_items]

    results: List[Dict[str, Any]] = []
    for item in items:
        result = execute_recording_item(
            item,
            output_dir=out_dir,
            allow_hosts=allow_hosts,
            headless=headless,
            max_record_seconds=max_record_seconds,
            take_screenshot=take_screenshot,
        )
        results.append(result)

    executed_count = sum(1 for r in results if r.get("status") == "executed")
    failed_count = sum(1 for r in results if r.get("status") == "failed")
    blocked_count = sum(1 for r in results if r.get("status") == "blocked")

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dry_run": False,
        "output_dir": str(out_dir),
        "total_items": len(results),
        "executed_count": executed_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "allowed_step_types": list(ALLOWED_STEP_TYPES),
        "forbidden_step_types": list(FORBIDDEN_STEP_TYPES),
        "items": results,
        "notes": [
            "F-4S-8b 웹 자동녹화 worker — 내부 URL 전용 실행",
            "click/fill/type/press/keyboard/mouse/evaluate 사용 금지",
            "cookie/storage_state/OAuth 접근 금지",
            "외부 사이트 / 로그인 화면 녹화 금지",
        ],
    }
