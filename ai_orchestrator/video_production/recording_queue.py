"""웹 자동녹화 큐 빌더 (F-4S-7).

설계 원칙:
- 입력: F-4S-6 video_queue JSON 또는 brief/리포트.
- 출력: 웹 자동녹화 지시서 큐(JSON/MD). 실제 녹화/브라우저 실행 없음.
- 허용 step type: open_url / wait / capture_scene / scroll_plan / overlay_caption.
- 금지 step type: click / fill / type / press / login / submit / upload / hover / drag.
- 외부 사이트 자동 접근 금지 — 대표님 제작 웹/내부 대시보드 녹화 우선.
- 로그인 필요한 URL 은 risk_notes 에 "수동 인증 필요 또는 제외" 로 표시.
- API key / client_secret / cookie / session / storage_state 일체 접근/기록 금지.
- LTX API / OAuth / 업로드 호출 일체 금지.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


VALID_VIEWPORTS: Dict[str, Dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "wide": {"width": 1920, "height": 1080},
    "mobile": {"width": 390, "height": 844},
}

DEFAULT_VIEWPORT = "desktop"
DEFAULT_MAX_ITEMS = 5

ALLOWED_STEP_TYPES = (
    "open_url",
    "wait",
    "capture_scene",
    "scroll_plan",
    "overlay_caption",
)

# 의도적으로 금지되는 step type (자동 클릭/입력/제출/업로드 등)
FORBIDDEN_STEP_TYPES = (
    "click",
    "fill",
    "type",
    "press",
    "login",
    "submit",
    "upload",
    "hover",
    "drag",
    "select_option",
    "set_storage",
    "set_cookie",
)

# duration mapping
_DURATION_BY_TYPE = {"short": 30, "long": 90}

# 로그인 필수 추정 도메인/패턴 — 자동 녹화 대상에서 제외/수동 인증 표시
_LOGIN_REQUIRED_HINTS = (
    "login", "signin", "sign-in", "auth", "oauth",
    "회원", "로그인", "마이페이지", "mypage",
    "admin", "dashboard?token=",
)

_EXTERNAL_PLATFORM_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "naver.com",
    "blog.naver.com",
    "cafe.naver.com",
    "instagram.com",
    "facebook.com",
)

_WHITESPACE = re.compile(r"\s+")


def _ensure_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_text(text: Any, *, max_len: Optional[int] = None) -> str:
    s = _ensure_str(text).strip()
    s = _WHITESPACE.sub(" ", s)
    if max_len is not None and len(s) > max_len:
        s = s[:max_len].rstrip() + "…"
    return s


# ---------------------------------------------------------------------------
# Loading / extraction
# ---------------------------------------------------------------------------


def load_video_queue(path: Path) -> Dict[str, Any]:
    """F-4S-6 video queue JSON 을 로드."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("video queue root must be an object")
    return data


def extract_recording_candidates(video_queue: Any) -> List[Dict[str, Any]]:
    """video_queue dict / queue list / brief list 어떤 형태든 후보 list 로 정규화."""
    if isinstance(video_queue, list):
        return [item for item in video_queue if isinstance(item, dict)]
    if not isinstance(video_queue, dict):
        return []
    queue = video_queue.get("queue")
    if isinstance(queue, list):
        return [item for item in queue if isinstance(item, dict)]
    briefs = video_queue.get("ltx_video_briefs")
    if isinstance(briefs, list):
        return [item for item in briefs if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# Target URL resolution
# ---------------------------------------------------------------------------


def _is_external_platform(url: str) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except (ValueError, TypeError):
        return False
    return any(domain in host for domain in _EXTERNAL_PLATFORM_DOMAINS)


def _is_login_required(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return any(hint in lower for hint in _LOGIN_REQUIRED_HINTS)


def _looks_like_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def normalize_recording_target(
    item: Dict[str, Any],
    *,
    default_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """video queue item → 녹화용 target 정보 (target_url, source_basis_url, warnings).

    우선순위:
    1) item.target_url 있고 정상 url 이면 사용
    2) default_base_url 사용 (대표님 제작 웹/내부 페이지 권장 입력)
    3) source_basis 의 첫 url — 외부 플랫폼이면 reference 로만 보존, target_url 은 None
    """
    warnings: List[str] = []
    candidate_url: Optional[str] = None
    source_url: Optional[str] = None

    explicit_target = _ensure_str(item.get("target_url")).strip()
    if explicit_target and _looks_like_url(explicit_target):
        candidate_url = explicit_target

    sources = item.get("source_basis") or []
    if isinstance(sources, list) and sources:
        first = sources[0]
        if isinstance(first, dict):
            url_str = _ensure_str(first.get("url")).strip()
            if url_str:
                source_url = url_str

    if candidate_url is None and default_base_url:
        base = _ensure_str(default_base_url).strip()
        if _looks_like_url(base):
            candidate_url = base
        else:
            warnings.append(f"recording:invalid_base_url:{base!r} — 무시됨")

    target_url: Optional[str] = candidate_url
    if target_url and _is_external_platform(target_url):
        warnings.append(
            f"recording:external_target:{urlparse(target_url).netloc} — 외부 플랫폼은 자동 녹화 대상에서 제외 권장"
        )
    if target_url is None:
        warnings.append(
            "recording:target_url_missing — 수동 지정 필요 (대표님 제작 웹/내부 페이지 URL 입력)"
        )

    if target_url and _is_login_required(target_url):
        warnings.append(
            "recording:login_required — 수동 인증 필요 또는 자동 녹화 대상에서 제외"
        )

    return {
        "target_url": target_url,
        "source_basis_url": source_url,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Recording steps
# ---------------------------------------------------------------------------


def _viewport_block(name: str) -> Dict[str, Any]:
    name_norm = (name or "").strip().lower()
    if name_norm not in VALID_VIEWPORTS:
        name_norm = DEFAULT_VIEWPORT
    spec = VALID_VIEWPORTS[name_norm]
    return {"name": name_norm, "width": spec["width"], "height": spec["height"]}


def _step_caption_for_scene(scene: Dict[str, Any], item_title: str) -> str:
    cap = _normalize_text(scene.get("caption"), max_len=80) if isinstance(scene, dict) else ""
    if cap:
        return cap
    return _normalize_text(item_title, max_len=60) or "(no caption)"


def _step_visual_note(scene: Dict[str, Any]) -> str:
    if not isinstance(scene, dict):
        return ""
    return _normalize_text(scene.get("visual_direction"), max_len=160)


def build_scene_recording_steps(queue_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """video queue item 의 scene_plan → 녹화 step 시퀀스.

    구조:
      step1: open_url (target_url 또는 about:blank 안내)
      step2: wait (페이지 로드 대기)
      stepN: capture_scene (각 scene_plan 항목당 1개)
      마지막: overlay_caption (자막 오버레이 안내, 실제 적용은 사람이 결정)
    """
    target_url = queue_item.get("target_url")
    title = _ensure_str(queue_item.get("title"))
    scene_plan = queue_item.get("scene_plan") or []
    duration_total = int(queue_item.get("duration_seconds") or _DURATION_BY_TYPE.get(
        queue_item.get("duration_type") or "short", 30
    ))

    steps: List[Dict[str, Any]] = []
    step_no = 1
    steps.append(
        {
            "step_no": step_no,
            "type": "open_url",
            "description": "대상 웹 페이지 열기 (브라우저 실행은 후속 worker 단계)",
            "url": target_url,
            "wait_seconds": 3,
        }
    )
    step_no += 1
    steps.append(
        {
            "step_no": step_no,
            "type": "wait",
            "description": "초기 렌더링/네트워크 idle 대기",
            "wait_seconds": 2,
        }
    )

    if not scene_plan:
        step_no += 1
        steps.append(
            {
                "step_no": step_no,
                "type": "capture_scene",
                "description": "전체 화면 정지 녹화",
                "duration_seconds": max(5, duration_total // 2),
                "caption": _normalize_text(title, max_len=60) or "(no caption)",
            }
        )
    else:
        per_scene = max(3, duration_total // max(1, len(scene_plan)))
        for idx, scene in enumerate(scene_plan):
            step_no += 1
            note = _step_visual_note(scene)
            description = "핵심 화면 정지 녹화"
            if note:
                description = f"핵심 화면 정지 녹화 — {note}"
            steps.append(
                {
                    "step_no": step_no,
                    "type": "capture_scene",
                    "description": description,
                    "duration_seconds": per_scene,
                    "caption": _step_caption_for_scene(scene, title),
                    "scene_purpose": _ensure_str(scene.get("purpose")) if isinstance(scene, dict) else "",
                }
            )
            # 긴 scene 사이에는 선택적 scroll_plan 안내 (실제 스크롤 실행은 worker 단계)
            if isinstance(scene, dict) and scene.get("purpose") in ("핵심 정보 1", "핵심 정보 2", "정리 / CTA"):
                step_no += 1
                steps.append(
                    {
                        "step_no": step_no,
                        "type": "scroll_plan",
                        "description": "다음 섹션으로 천천히 스크롤 (worker 단계에서 실행)",
                        "direction": "down",
                        "amount_px": 600,
                        "wait_seconds": 1,
                    }
                )

    step_no += 1
    steps.append(
        {
            "step_no": step_no,
            "type": "overlay_caption",
            "description": "후처리 단계에서 자막 오버레이 적용 (worker 단계, 사람 검수 후)",
            "captions": [
                _normalize_text(p, max_len=80)
                for p in (queue_item.get("subtitle_points") or [])[:5]
            ],
        }
    )
    return steps


def _editing_notes(queue_item: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    notes.append("BGM/효과음은 저작권 검증된 라이선스만 사용")
    notes.append("얼굴/번호판 등 식별 가능 요소는 모자이크/블러 처리")
    notes.append("법령/단가/안전 표현은 자막에 출처 또는 갱신일자 표기")
    notes.append("실제 녹화/렌더/업로드는 별도 승인 단계에서만 수행")
    if queue_item.get("review_required"):
        notes.append("source video queue 가 review_required=True — 사람 검수 후에만 진행")
    return notes


def _narration_points(queue_item: Dict[str, Any]) -> List[str]:
    base: List[str] = []
    hook = _normalize_text(queue_item.get("hook"), max_len=160)
    if hook:
        base.append(hook)
    for scene in queue_item.get("scene_plan") or []:
        if not isinstance(scene, dict):
            continue
        narration = _normalize_text(scene.get("narration"), max_len=160)
        if narration:
            base.append(narration)
    if not base:
        title = _normalize_text(queue_item.get("title"), max_len=80)
        if title:
            base.append(title)
    seen: List[str] = []
    for n in base:
        if n and n not in seen:
            seen.append(n)
    return seen


# ---------------------------------------------------------------------------
# Risk notes
# ---------------------------------------------------------------------------


def _augment_risk_notes(
    base_notes: Sequence[str],
    target_info: Dict[str, Any],
) -> List[str]:
    notes: List[str] = list(base_notes or [])
    for w in target_info.get("warnings") or []:
        notes.append(w)
    notes.append("실제 브라우저 실행/녹화/업로드는 자동 수행 금지 — 별도 승인 worker 단계에서만 진행")
    notes.append("click/fill/type/press 등 자동 입력 step 은 본 큐에 포함되지 않는다")
    seen: List[str] = []
    for n in notes:
        if n and n not in seen:
            seen.append(n)
    return seen


def _needs_review(risk_notes: Sequence[str], source_review: bool) -> bool:
    if source_review:
        return True
    text = " ".join(risk_notes or []).lower()
    triggers = ("수동 인증", "수동 지정", "외부 플랫폼", "최종 검수", "url_missing", "login_required")
    if any(t in text for t in triggers):
        return True
    return True  # PoC 단계 — 항상 검수 필요


# ---------------------------------------------------------------------------
# Build queue
# ---------------------------------------------------------------------------


def _format_recording_id(idx: int) -> str:
    return f"recording_{idx:03d}"


def _coerce_max_items(max_items: Any) -> int:
    try:
        n = int(max_items)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS
    if n <= 0:
        return DEFAULT_MAX_ITEMS
    return n


def build_recording_queue(
    video_queue: Any,
    *,
    default_base_url: Optional[str] = None,
    viewport: str = DEFAULT_VIEWPORT,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> List[Dict[str, Any]]:
    candidates = extract_recording_candidates(video_queue)
    if not candidates:
        return []
    max_n = _coerce_max_items(max_items)
    viewport_block = _viewport_block(viewport)
    out: List[Dict[str, Any]] = []
    for source in candidates:
        if len(out) >= max_n:
            break
        title = _normalize_text(source.get("title"), max_len=120)
        if not title:
            continue
        target_info = normalize_recording_target(
            source, default_base_url=default_base_url
        )
        target_url = target_info["target_url"]
        duration_type = source.get("duration_type") or "short"
        duration_total = _DURATION_BY_TYPE.get(duration_type, 30)
        item_for_steps = {
            "title": title,
            "target_url": target_url,
            "scene_plan": source.get("scene_plan") or [],
            "subtitle_points": source.get("subtitle_points") or [],
            "duration_type": duration_type,
            "duration_seconds": duration_total,
        }
        recording_steps = build_scene_recording_steps(item_for_steps)
        risk_notes = _augment_risk_notes(source.get("risk_notes") or [], target_info)
        review_required = _needs_review(risk_notes, bool(source.get("review_required")))
        out.append(
            {
                "recording_id": _format_recording_id(len(out) + 1),
                "source_queue_id": _ensure_str(source.get("queue_id")) or None,
                "status": "draft",
                "title": title,
                "target_url": target_url,
                "source_basis_url": target_info.get("source_basis_url"),
                "viewport": dict(viewport_block),
                "duration_seconds": duration_total,
                "duration_type": duration_type,
                "recording_steps": recording_steps,
                "subtitle_points": [
                    _normalize_text(s, max_len=160)
                    for s in (source.get("subtitle_points") or [])
                    if _normalize_text(s)
                ],
                "narration_points": _narration_points(source),
                "editing_notes": _editing_notes(source),
                "risk_notes": risk_notes,
                "review_required": review_required,
                "source_basis": [
                    {
                        "platform": _ensure_str(s.get("platform")),
                        "source_type": _ensure_str(s.get("source_type")),
                        "url": _ensure_str(s.get("url")),
                        "title": _normalize_text(s.get("title"), max_len=120),
                    }
                    for s in (source.get("source_basis") or [])
                    if isinstance(s, dict)
                ],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Markdown / file output
# ---------------------------------------------------------------------------


def render_recording_queue_markdown(recording_queue: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# 웹 자동녹화 큐 (PoC)")
    lines.append("")
    lines.append(f"- 총 recording item: {len(recording_queue)}")
    lines.append("- 실제 브라우저 실행 / 녹화 / 업로드는 본 큐에서 수행하지 않는다")
    lines.append("- 허용 step: open_url / wait / capture_scene / scroll_plan / overlay_caption")
    lines.append("- 금지 step: click / fill / type / press / login / submit / upload / hover / drag")
    lines.append("")
    if not recording_queue:
        lines.append("## 큐 비어 있음")
        lines.append("- 입력 video queue 가 없거나 제목 누락 항목만 존재합니다.")
        lines.append("")
        return "\n".join(lines)

    for item in recording_queue:
        lines.append(f"## {item.get('recording_id')} — {item.get('title')}")
        lines.append(f"- source_queue_id: {item.get('source_queue_id') or '-'}")
        lines.append(f"- status: {item.get('status')}")
        vp = item.get("viewport") or {}
        lines.append(
            f"- viewport: {vp.get('name')} ({vp.get('width')}x{vp.get('height')})"
        )
        lines.append(f"- duration_seconds: {item.get('duration_seconds')}")
        lines.append(f"- target_url: {item.get('target_url') or '(미지정 — 수동 입력 필요)'}")
        if item.get("source_basis_url"):
            lines.append(f"- source_basis_url: {item.get('source_basis_url')}")
        lines.append(f"- review_required: {item.get('review_required')}")

        steps = item.get("recording_steps") or []
        if steps:
            lines.append("- recording_steps:")
            for st in steps:
                base = (
                    f"  - step {st.get('step_no')} [{st.get('type')}] "
                    f"{st.get('description', '')}"
                )
                lines.append(base)
                if st.get("type") == "open_url" and st.get("url"):
                    lines.append(f"    - url: {st.get('url')}")
                if st.get("type") == "capture_scene":
                    lines.append(
                        f"    - duration: {st.get('duration_seconds')}s caption='{st.get('caption')}'"
                    )
                if st.get("type") == "scroll_plan":
                    lines.append(
                        f"    - direction: {st.get('direction')} amount_px: {st.get('amount_px')}"
                    )
                if st.get("type") == "overlay_caption":
                    caps = st.get("captions") or []
                    for c in caps:
                        lines.append(f"    - caption: {c}")

        narration = item.get("narration_points") or []
        if narration:
            lines.append("- narration_points:")
            for n in narration:
                lines.append(f"  - {n}")
        editing = item.get("editing_notes") or []
        if editing:
            lines.append("- editing_notes:")
            for e in editing:
                lines.append(f"  - {e}")
        risks = item.get("risk_notes") or []
        if risks:
            lines.append("- risk_notes:")
            for r in risks:
                lines.append(f"  - {r}")
        lines.append("")
    lines.append("## 다음 단계")
    lines.append("- 실제 녹화 worker (예: Playwright) 는 별도 승인 + 키 등록 후 후속 단계에서 구현")
    lines.append("- 자막/내레이션/TTS/LTX 영상 생성/YouTube 업로드는 모두 별도 승인 단계")
    lines.append("")
    return "\n".join(lines)


def write_recording_queue_files(
    recording_queue: Sequence[Dict[str, Any]],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"web_recording_queue_{ts}"
    json_path = out_path / f"{base}.json"
    md_path = out_path / f"{base}.md"
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recording_count": len(recording_queue),
        "allowed_step_types": list(ALLOWED_STEP_TYPES),
        "forbidden_step_types": list(FORBIDDEN_STEP_TYPES),
        "queue": list(recording_queue),
        "notes": [
            "F-4S-7 웹 자동녹화 큐 PoC",
            "실제 브라우저 실행 / 녹화 / 업로드 / 댓글 / 가입 / 글쓰기 절대 금지",
            "click/fill/type/press 등 자동 입력 step 은 큐에 포함되지 않는다",
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_recording_queue_markdown(recording_queue), encoding="utf-8")
    return {"json": json_path, "md": md_path}
