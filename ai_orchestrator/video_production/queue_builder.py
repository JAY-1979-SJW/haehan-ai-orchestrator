"""LTX 영상 제작 큐 빌더 (F-4S-6).

설계 원칙:
- 입력: F-4S-5 content research JSON (ltx_video_briefs 키 포함) 또는 brief dict 리스트.
- 출력: LTX 영상 제작 지시서 큐 (JSON / Markdown). 실제 LTX 호출 없음.
- read-only / 분석 전용. 영상 생성, 업로드, 댓글, 가입, 글쓰기, OAuth 일체 금지.
- API key / client_secret 등 민감 문자열은 절대 큐/리포트에 포함하지 않는다.
- 법령/단가/안전 관련 표현은 risk_notes 에 "최종 검수 필요" 라벨을 추가한다.
- ltx_prompt 는 영상 제작 지시서 수준까지만 작성. 실제 API 호출 명령 미포함.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


VALID_DURATION_TYPES = ("short", "long")
VALID_TARGET_PLATFORMS = (
    "youtube_short",
    "youtube_long",
    "naver_blog",
    "cafe_post",
)

DEFAULT_MAX_ITEMS = 5
DEFAULT_DURATION_TYPE = "short"

# 법령/단가/안전 등 사실 검증이 반드시 필요한 표현
_REVIEW_REQUIRED_KEYWORDS: tuple = (
    "법", "법령", "법률", "기준", "규정", "조항", "시행령", "고시", "표준",
    "비용", "가격", "견적", "단가", "예산", "수수료", "원", "만원",
    "안전", "위험", "사고", "응급", "재해",
)

# 광고/비방/단정 금지 패턴 (간단 사전 체크)
_FORBIDDEN_TONE_PATTERNS = (
    "최고", "최저가", "100%", "보장", "무조건", "절대",
    "사기", "쓰레기", "최악", "비추",
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


def _coerce_target_platform(value: Any) -> str:
    text = _ensure_str(value).strip().lower()
    if text in VALID_TARGET_PLATFORMS:
        return text
    return "naver_blog"


def _infer_duration_type(target_platform: str, default_duration_type: str) -> str:
    if target_platform == "youtube_short":
        return "short"
    if target_platform == "youtube_long":
        return "long"
    return default_duration_type if default_duration_type in VALID_DURATION_TYPES else "short"


# ---------------------------------------------------------------------------
# Loading / extraction
# ---------------------------------------------------------------------------


def load_content_report(path: Path) -> Dict[str, Any]:
    """F-4S-5 콘텐츠 조사 리포트 JSON 을 로드한다."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("content report root must be an object")
    return data


def extract_ltx_briefs(report: Any) -> List[Dict[str, Any]]:
    """리포트(dict) 또는 brief 리스트에서 ltx_video_briefs 를 추출한다."""
    if isinstance(report, list):
        return [b for b in report if isinstance(b, dict)]
    if not isinstance(report, dict):
        return []
    briefs = report.get("ltx_video_briefs")
    if isinstance(briefs, list):
        return [b for b in briefs if isinstance(b, dict)]
    return []


# ---------------------------------------------------------------------------
# Brief normalization
# ---------------------------------------------------------------------------


def normalize_video_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    """단일 brief 를 큐 빌더가 사용 가능한 표준 dict 로 정규화한다."""
    if not isinstance(brief, dict):
        return {
            "title": "",
            "hook": "",
            "scene_ideas": [],
            "subtitle_points": [],
            "source_basis": [],
            "target_platform": "naver_blog",
            "risk_notes": [],
            "score": 0.0,
        }
    title = _normalize_text(brief.get("title"), max_len=120)
    hook = _normalize_text(brief.get("hook"), max_len=160)
    scene_ideas_raw = brief.get("scene_ideas") or []
    scene_ideas = [_normalize_text(s, max_len=160) for s in scene_ideas_raw if _normalize_text(s)]
    subtitle_points_raw = brief.get("subtitle_points") or []
    subtitle_points = [
        _normalize_text(s, max_len=160) for s in subtitle_points_raw if _normalize_text(s)
    ]
    source_basis_raw = brief.get("source_basis") or []
    source_basis: List[Dict[str, str]] = []
    if isinstance(source_basis_raw, list):
        for src in source_basis_raw:
            if not isinstance(src, dict):
                continue
            source_basis.append(
                {
                    "platform": _ensure_str(src.get("platform")),
                    "source_type": _ensure_str(src.get("source_type")),
                    "url": _ensure_str(src.get("url")),
                    "title": _normalize_text(src.get("title"), max_len=120),
                }
            )
    target_platform = _coerce_target_platform(brief.get("target_platform"))
    risk_notes_raw = brief.get("risk_notes") or []
    risk_notes = [_normalize_text(r) for r in risk_notes_raw if _normalize_text(r)]
    try:
        score = float(brief.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    return {
        "title": title,
        "hook": hook,
        "scene_ideas": scene_ideas,
        "subtitle_points": subtitle_points,
        "source_basis": source_basis,
        "target_platform": target_platform,
        "risk_notes": risk_notes,
        "score": score,
    }


# ---------------------------------------------------------------------------
# Risk / review heuristics
# ---------------------------------------------------------------------------


def _augment_risk_notes(brief_norm: Dict[str, Any]) -> List[str]:
    """법령/단가/안전 / 광고 톤 / 출처 누락 케이스에 대해 risk_notes 보강."""
    notes: List[str] = list(brief_norm.get("risk_notes") or [])
    haystack_parts: List[str] = []
    haystack_parts.append(brief_norm.get("title") or "")
    haystack_parts.append(brief_norm.get("hook") or "")
    haystack_parts.extend(brief_norm.get("subtitle_points") or [])
    haystack_parts.extend(brief_norm.get("scene_ideas") or [])
    for src in brief_norm.get("source_basis") or []:
        haystack_parts.append(_ensure_str(src.get("title")))
    haystack = " ".join(haystack_parts).lower()

    matched_keywords: List[str] = []
    for kw in _REVIEW_REQUIRED_KEYWORDS:
        if kw and kw.lower() in haystack:
            matched_keywords.append(kw)
    if matched_keywords:
        unique_kws = sorted({k for k in matched_keywords})
        notes.append(
            "법령/단가/안전 표현 감지 — 최종 검수 필요 (matches: "
            + ", ".join(unique_kws[:5])
            + ")"
        )

    forbidden_hits: List[str] = []
    for kw in _FORBIDDEN_TONE_PATTERNS:
        if kw and kw.lower() in haystack:
            forbidden_hits.append(kw)
    if forbidden_hits:
        notes.append(
            "과장/비방 표현 후보 감지 — 표현 순화 필요 (matches: "
            + ", ".join(sorted({k for k in forbidden_hits})[:5])
            + ")"
        )

    if not (brief_norm.get("source_basis") or []):
        notes.append("출처 누락 — 인용 reference 확보 후 사용 권장")
    else:
        missing_url = [s for s in brief_norm["source_basis"] if not s.get("url")]
        if missing_url:
            notes.append("source_basis 일부 URL 누락 — 출처 확인 필요")

    notes.append("read-only 분석 결과 기반 — 실제 LTX 영상 생성/업로드 절대 자동 실행 금지")

    seen: List[str] = []
    for n in notes:
        if n and n not in seen:
            seen.append(n)
    return seen


def _needs_review(risk_notes: Sequence[str]) -> bool:
    text = " ".join(risk_notes or []).lower()
    triggers = ("최종 검수 필요", "표현 순화 필요", "출처 누락", "url 누락")
    if any(t in text for t in triggers):
        return True
    return True  # PoC 단계 — 항상 검수 필요로 처리


# ---------------------------------------------------------------------------
# Scene plan / LTX prompt
# ---------------------------------------------------------------------------


_SCENE_PURPOSES_SHORT = (
    ("문제 제기", "시청자가 30초 내 공감할 핵심 문제를 한 줄로 제시"),
    ("핵심 정보 전달", "근거 기반 핵심 메시지 1~2개 자막 강조"),
    ("CTA / 마무리", "강요 없는 안내 — 자료 다운로드 안내 또는 검수 권장 문구"),
)

_SCENE_PURPOSES_LONG = (
    ("오프닝 / 후크", "주제 한 줄 hook + 시청자 페르소나 명확화"),
    ("문제/배경 설명", "왜 지금 중요한지 배경/통계/사례 인용"),
    ("핵심 정보 1", "근거 기반 핵심 포인트 첫 번째 — 자막 키워드 노출"),
    ("핵심 정보 2", "보완 포인트 / 비교 / 체크리스트 형태로 시각화"),
    ("정리 / CTA", "요약 슬라이드 + 자료 다운로드 안내. 구독 유도 표현은 최소화"),
)


def _scene_purposes(duration_type: str) -> Sequence:
    if duration_type == "long":
        return _SCENE_PURPOSES_LONG
    return _SCENE_PURPOSES_SHORT


def _scene_caption(idx: int, brief: Dict[str, Any]) -> str:
    subtitles = brief.get("subtitle_points") or []
    if subtitles:
        return _normalize_text(subtitles[idx % len(subtitles)], max_len=80)
    title = brief.get("title") or "(no title)"
    return _normalize_text(title, max_len=60)


def _scene_visual_direction(idx: int, brief: Dict[str, Any]) -> str:
    scene_ideas = brief.get("scene_ideas") or []
    if scene_ideas:
        return _normalize_text(scene_ideas[idx % len(scene_ideas)], max_len=160)
    return "관련 b-roll 또는 도식 인서트. 실 인물 식별 가능 영상은 사용 금지."


def _scene_narration(idx: int, brief: Dict[str, Any], purpose_label: str) -> str:
    title = brief.get("title") or ""
    hook = brief.get("hook") or ""
    if idx == 0 and hook:
        return _normalize_text(hook, max_len=160)
    if title:
        return _normalize_text(f"[{purpose_label}] {title}", max_len=160)
    return _normalize_text(f"[{purpose_label}] 핵심 내용", max_len=160)


def build_scene_plan(brief: Dict[str, Any], duration_type: str) -> List[Dict[str, Any]]:
    purposes = _scene_purposes(duration_type)
    plan: List[Dict[str, Any]] = []
    for idx, (purpose_label, purpose_desc) in enumerate(purposes):
        plan.append(
            {
                "scene_no": idx + 1,
                "purpose": purpose_label,
                "visual_direction": _scene_visual_direction(idx, brief),
                "caption": _scene_caption(idx, brief),
                "narration": _scene_narration(idx, brief, purpose_desc),
            }
        )
    return plan


def build_ltx_prompt(queue_item: Dict[str, Any]) -> str:
    """LTX 제작 지시서 prompt. 실제 API 호출은 포함하지 않는다."""
    title = queue_item.get("title") or "(no title)"
    duration_type = queue_item.get("duration_type") or "short"
    target = queue_item.get("target_platform") or "naver_blog"
    hook = queue_item.get("hook") or ""
    subtitles = queue_item.get("subtitle_points") or []
    scene_plan = queue_item.get("scene_plan") or []
    source_basis = queue_item.get("source_basis") or []

    lines: List[str] = []
    lines.append("# LTX 영상 제작 지시서 (PoC — 실제 API 호출 금지)")
    lines.append(f"- 제목: {title}")
    lines.append(f"- 길이 타입: {duration_type}")
    lines.append(f"- 타깃 플랫폼: {target}")
    if hook:
        lines.append(f"- 오프닝 hook: {hook}")
    if subtitles:
        lines.append("- 핵심 자막 포인트:")
        for s in subtitles[:6]:
            lines.append(f"  - {s}")
    if scene_plan:
        lines.append("- 장면 구성:")
        for sc in scene_plan:
            lines.append(
                f"  - scene {sc.get('scene_no')} [{sc.get('purpose')}] "
                f"visual: {sc.get('visual_direction')} | caption: {sc.get('caption')}"
            )
    if source_basis:
        lines.append("- 출처:")
        for src in source_basis[:5]:
            lines.append(
                f"  - [{src.get('platform')}/{src.get('source_type')}] "
                f"{src.get('title') or '(no title)'} ({src.get('url') or '-'})"
            )
    lines.append("- 제약: 실제 LTX 호출/업로드/댓글/가입/글쓰기 모두 금지.")
    lines.append("- 제약: 법령/단가/안전 표현 포함 시 사람의 최종 검수 후에만 영상화.")
    lines.append("- 제약: 광고성/비방/단정 표현은 자막/내레이션에서 제외.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Queue building
# ---------------------------------------------------------------------------


def _format_queue_id(idx: int) -> str:
    return f"video_{idx:03d}"


def build_video_queue(
    briefs: Iterable[Any],
    *,
    default_duration_type: str = DEFAULT_DURATION_TYPE,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> List[Dict[str, Any]]:
    """brief 목록 → 영상 제작 큐 item 리스트."""
    if default_duration_type not in VALID_DURATION_TYPES:
        default_duration_type = DEFAULT_DURATION_TYPE
    if not briefs:
        return []
    queue: List[Dict[str, Any]] = []
    for raw in briefs:
        if max_items and len(queue) >= max_items:
            break
        norm = normalize_video_brief(raw if isinstance(raw, dict) else {})
        if not norm.get("title"):
            continue
        target = norm["target_platform"]
        duration_type = _infer_duration_type(target, default_duration_type)
        scene_plan = build_scene_plan(norm, duration_type)
        risk_notes = _augment_risk_notes(norm)
        queue_item: Dict[str, Any] = {
            "queue_id": _format_queue_id(len(queue) + 1),
            "status": "draft",
            "title": norm["title"],
            "hook": norm["hook"],
            "duration_type": duration_type,
            "target_platform": target,
            "scene_plan": scene_plan,
            "subtitle_points": list(norm["subtitle_points"]),
            "source_basis": [dict(s) for s in norm["source_basis"]],
            "ltx_prompt": "",
            "risk_notes": risk_notes,
            "review_required": _needs_review(risk_notes),
            "score": norm.get("score", 0.0),
        }
        queue_item["ltx_prompt"] = build_ltx_prompt(queue_item)
        queue.append(queue_item)
    return queue


# ---------------------------------------------------------------------------
# Markdown rendering / file output
# ---------------------------------------------------------------------------


def render_video_queue_markdown(queue: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("# LTX 영상 제작 큐 (PoC)")
    lines.append("")
    lines.append(f"- 총 큐 item: {len(queue)}")
    lines.append("- 실제 LTX API 호출 / 영상 생성 / 업로드는 별도 승인형 단계에서만 수행")
    lines.append("")
    if not queue:
        lines.append("## 큐 비어 있음")
        lines.append("- 입력 brief 가 없거나 제목 누락 항목만 존재합니다.")
        lines.append("")
        return "\n".join(lines)

    for item in queue:
        lines.append(f"## {item.get('queue_id')} — {item.get('title')}")
        lines.append(f"- status: {item.get('status')}")
        lines.append(f"- duration_type: {item.get('duration_type')}")
        lines.append(f"- target_platform: {item.get('target_platform')}")
        lines.append(f"- review_required: {item.get('review_required')}")
        if item.get("hook"):
            lines.append(f"- hook: {item.get('hook')}")
        subs = item.get("subtitle_points") or []
        if subs:
            lines.append("- subtitle_points:")
            for s in subs:
                lines.append(f"  - {s}")
        scene_plan = item.get("scene_plan") or []
        if scene_plan:
            lines.append("- scene_plan:")
            for sc in scene_plan:
                lines.append(
                    f"  - scene {sc.get('scene_no')} [{sc.get('purpose')}] "
                    f"caption='{sc.get('caption')}' visual='{sc.get('visual_direction')}'"
                )
        sources = item.get("source_basis") or []
        if sources:
            lines.append("- source_basis:")
            for src in sources:
                lines.append(
                    f"  - [{src.get('platform')}/{src.get('source_type')}] "
                    f"{src.get('title') or '(no title)'} ({src.get('url') or '-'})"
                )
        risks = item.get("risk_notes") or []
        if risks:
            lines.append("- risk_notes:")
            for r in risks:
                lines.append(f"  - {r}")
        prompt = item.get("ltx_prompt") or ""
        if prompt:
            lines.append("- ltx_prompt (preview):")
            for prompt_line in prompt.splitlines()[:6]:
                lines.append(f"  > {prompt_line}")
        lines.append("")
    lines.append("## 다음 단계")
    lines.append("- 검수 필요 항목은 사람이 검토 후 status='ready_for_render' 로 수동 변경")
    lines.append("- 실제 LTX 호출은 별도 승인 + 키 등록 후 후속 PoC 에서 진행")
    lines.append("")
    return "\n".join(lines)


def write_video_queue_files(
    queue: Sequence[Dict[str, Any]],
    out_dir: Path,
    *,
    timestamp: Optional[str] = None,
) -> Dict[str, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"video_queue_{ts}"
    json_path = out_path / f"{base}.json"
    md_path = out_path / f"{base}.md"
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "queue_count": len(queue),
        "queue": list(queue),
        "notes": [
            "F-4S-6 LTX 영상 제작 큐 PoC",
            "실제 LTX 호출/업로드/댓글/가입/글쓰기 절대 금지",
            "법령/단가/안전 표현은 review_required=True 로 표시",
        ],
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_video_queue_markdown(queue), encoding="utf-8")
    return {"json": json_path, "md": md_path}
