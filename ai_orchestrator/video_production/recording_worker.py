"""웹 자동녹화 worker dry-run (F-4S-8a).

설계 원칙:
- 입력: F-4S-7 web_recording_queue JSON.
- 출력: dry-run 실행계획 JSON + Markdown 리포트.
- 실제 브라우저 실행 / 페이지 이동 / 화면 녹화 / 업로드 일체 금지.
- 허용 step type: open_url / wait / capture_scene / scroll_plan / overlay_caption.
- 금지 step type: click / fill / type / press / submit / upload / download /
  login / purchase / comment / post / hover / drag / select_option /
  set_storage / set_cookie.
- target_url 누락 → status="blocked", warning=target_url_missing.
- target_url 이 외부 플랫폼이면 warning=external_target_review_required.
- API key / client_secret / cookie / session / storage 일체 접근/기록 금지.
- Playwright/Selenium import 금지. page.goto / browser.launch / new_context 금지.
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

    이번 단계에서 dry_run=False 는 허용되지 않는다 (NotImplementedError).
    실제 브라우저 실행은 후속 단계 F-4S-8b 에서 분리해 구현한다.
    """
    if not dry_run:
        raise NotImplementedError(
            "actual browser recording is not implemented in F-4S-8a — "
            "use F-4S-8b worker after explicit approval"
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
    """dry-run 결과 JSON + Markdown 을 파일로 저장.

    실제 mp4/메타데이터 파일은 만들지 않는다 — 파일 경로 문자열은 계획일 뿐이다.
    """
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
