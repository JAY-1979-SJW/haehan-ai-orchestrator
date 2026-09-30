"""블로그 자동 작성 규칙 모델 — 데이터·검증·승인 해시만 다룬다.

기준서: docs/specs/2026-09-30_blog_auto_writing_automation.md (v2, A단계)

순수 모듈이다: 파일·네트워크·브라우저·환경변수에 접근하지 않고 다른 업무 도메인도 import 하지 않는다
(블로그 분리 경계, docs/specs/naver_blog_content_standard.md §0). 저장·실행은 후속 단계(B/C)가 맡는다.

핵심 규칙
- 규칙은 사용자가 만든 것이고, `auto_publish` 는 **승인한 내용 그대로일 때만** 유효하다.
  승인 시점의 규칙 해시(`rule_hash`)가 현재 내용과 다르면 승인은 무효 → 초안까지만.
- 자동 발행이 허용된 계정은 `AUTO_PUBLISH_BLOG_IDS` 뿐이다(조명 계정 skyjwshin 은
  README 상 "발행 전 사람 검수 필요"라 초안까지만).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

MODES = ("draft_only", "auto_publish")
VISIBILITIES = ("public", "neighbors", "mutual", "private")
DEFAULT_BLOG_ID = "skyjwsin"
AUTO_PUBLISH_BLOG_IDS = frozenset({"skyjwsin"})

MAX_PER_DAY = 5
MAX_PER_WEEK = 21
MIN_GAP_SECONDS = 60
DEFAULT_GAP_SECONDS = 90
MAX_USER_TOPICS = 200
MAX_TIMES = 6
MAX_FORBIDDEN_WORDS = 100

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # 파일 이름으로 쓰이므로 경로 문자 금지
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    blog_id: str
    user_topics: tuple[dict[str, Any], ...]
    use_research: bool
    days: tuple[int, ...]  # 월=0 … 일=6 (datetime.weekday())
    times: tuple[str, ...]  # "HH:MM", 규칙 시간대의 현지 시각
    per_day: int
    per_week: int
    gap_seconds: int
    forbidden_words: tuple[str, ...]
    visibility: str
    mode: str
    approval: dict[str, str] | None = None
    paused: bool = False


# ── 검증 ─────────────────────────────────────────────────────────────────


def is_valid_rule_id(rule_id: Any) -> bool:
    """규칙 id 는 파일 이름으로 쓰인다 — 경로 문자가 들어간 값은 어디서든 거부한다."""
    return isinstance(rule_id, str) and bool(_ID_RE.match(rule_id))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str_list(value: Any, *, max_items: int, max_len: int) -> list[str] | None:
    if not isinstance(value, list) or len(value) > max_items:
        return None
    if not all(isinstance(v, str) and v.strip() and len(v) <= max_len for v in value):
        return None
    return [v.strip() for v in value]


def _check_topic(index: int, item: Any) -> tuple[dict[str, Any] | None, list[str]]:
    label = f"주제 {index + 1}번"
    if not isinstance(item, dict):
        return None, [f"{label}: 객체가 아님"]
    topic = item.get("topic")
    keywords = _str_list(item.get("keywords"), max_items=20, max_len=50)
    errors: list[str] = []
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 200:
        errors.append(f"{label}: topic 은 1~200자 문자열")
    if not keywords:
        errors.append(f"{label}: keywords 는 1개 이상(핵심 키워드가 첫 번째)")
    for key in ("angle", "source_description"):
        if item.get(key) is not None and not isinstance(item[key], str):
            errors.append(f"{label}: {key} 는 문자열")
    if errors:
        return None, errors
    clean = {"topic": topic.strip(), "keywords": keywords}
    for key in ("angle", "source_description"):
        if item.get(key):
            clean[key] = item[key]
    return clean, []


def _check_topics(data: dict[str, Any]) -> tuple[tuple[dict[str, Any], ...], bool, list[str]]:
    raw = data.get("user_topics", [])
    use_research = data.get("use_research", False)
    errors: list[str] = []
    if not isinstance(use_research, bool):
        errors.append("use_research 는 true/false")
        use_research = False
    if not isinstance(raw, list) or len(raw) > MAX_USER_TOPICS:
        return (), use_research, [*errors, f"user_topics 는 최대 {MAX_USER_TOPICS}개 목록"]
    topics: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        clean, errs = _check_topic(i, item)
        errors += errs
        if clean:
            topics.append(clean)
    if not errors and not topics and not use_research:
        errors.append("주제 출처가 없음: user_topics 또는 use_research 중 하나는 필요")
    return tuple(topics), use_research, errors


def _check_schedule(data: dict[str, Any]) -> tuple[tuple[int, ...], tuple[str, ...], list[str]]:
    days, times = data.get("days"), data.get("times")
    errors: list[str] = []
    if not (
        isinstance(days, list)
        and days
        and all(_is_int(d) and 0 <= d <= 6 for d in days)
        and len(set(days)) == len(days)
    ):
        errors.append("days 는 0(월)~6(일) 중복 없는 정수 목록(1개 이상)")
        days = []
    if not (
        isinstance(times, list)
        and 0 < len(times) <= MAX_TIMES
        and all(isinstance(t, str) and _TIME_RE.match(t) for t in times)
        and len(set(times)) == len(times)
    ):
        errors.append(f"times 는 'HH:MM' 형식 중복 없는 목록(1~{MAX_TIMES}개)")
        times = []
    return tuple(sorted(days)), tuple(sorted(times)), errors


def _check_limits(data: dict[str, Any]) -> tuple[int, int, int, list[str]]:
    per_day, per_week = data.get("per_day"), data.get("per_week")
    gap = data.get("gap_seconds", DEFAULT_GAP_SECONDS)
    errors: list[str] = []
    if not (_is_int(per_day) and 1 <= per_day <= MAX_PER_DAY):
        errors.append(f"per_day 는 1~{MAX_PER_DAY} 정수")
    if not (_is_int(per_week) and 1 <= per_week <= MAX_PER_WEEK):
        errors.append(f"per_week 는 1~{MAX_PER_WEEK} 정수")
    if not errors and per_week < per_day:
        errors.append("per_week 는 per_day 이상이어야 함")
    if not (_is_int(gap) and gap >= MIN_GAP_SECONDS):
        errors.append(f"gap_seconds 는 {MIN_GAP_SECONDS} 이상 정수(봇 감지 방지)")
    return per_day or 0, per_week or 0, gap if _is_int(gap) else 0, errors


def _check_approval(approval: Any) -> list[str]:
    if approval is None:
        return []
    ok = (
        isinstance(approval, dict)
        and isinstance(approval.get("approved_by"), str)
        and approval["approved_by"].strip()
        and isinstance(approval.get("approved_at"), str)
        and isinstance(approval.get("rule_hash"), str)
        and _HASH_RE.match(approval["rule_hash"])
    )
    return [] if ok else ["approval 은 approved_by·approved_at·rule_hash(64자 16진수)를 가진 객체 또는 null"]


def _check_identity(data: dict[str, Any], known_blog_ids: frozenset[str] | None) -> list[str]:
    errors: list[str] = []
    rule_id, name, blog_id = data.get("id"), data.get("name"), data.get("blog_id", DEFAULT_BLOG_ID)
    if not is_valid_rule_id(rule_id):
        errors.append("id 는 영문·숫자·_·- 1~64자(파일 이름으로 쓰임)")
    if not (isinstance(name, str) and name.strip() and len(name) <= 80):
        errors.append("name 은 1~80자 문자열")
    if not (isinstance(blog_id, str) and blog_id):
        errors.append("blog_id 는 문자열")
    elif known_blog_ids is not None and blog_id not in known_blog_ids:
        errors.append(f"등록되지 않은 blog_id: {blog_id}")
    return errors


def parse_rule(data: Any, *, known_blog_ids: frozenset[str] | None = None) -> tuple[Rule | None, list[str]]:
    """사전(JSON)을 규칙으로 바꾼다. 하나라도 어긋나면 (None, 오류 목록) — 보정·추측하지 않는다."""
    if not isinstance(data, dict):
        return None, ["규칙은 객체여야 함"]
    errors = _check_identity(data, known_blog_ids)
    topics, use_research, errs = _check_topics(data)
    errors += errs
    days, times, errs = _check_schedule(data)
    errors += errs
    per_day, per_week, gap, errs = _check_limits(data)
    errors += errs
    words = _str_list(data.get("forbidden_words", []), max_items=MAX_FORBIDDEN_WORDS, max_len=50)
    if words is None:
        errors.append(f"forbidden_words 는 문자열 목록(최대 {MAX_FORBIDDEN_WORDS}개)")
    if data.get("visibility", "public") not in VISIBILITIES:
        errors.append(f"visibility 는 {', '.join(VISIBILITIES)} 중 하나")
    if data.get("mode", "draft_only") not in MODES:
        errors.append(f"mode 는 {', '.join(MODES)} 중 하나")
    errors += _check_approval(data.get("approval"))
    if not isinstance(data.get("paused", False), bool):
        errors.append("paused 는 true/false")
    if errors:
        return None, errors
    return (
        Rule(
            id=data["id"],
            name=data["name"].strip(),
            blog_id=data.get("blog_id", DEFAULT_BLOG_ID),
            user_topics=topics,
            use_research=use_research,
            days=days,
            times=times,
            per_day=per_day,
            per_week=per_week,
            gap_seconds=gap,
            forbidden_words=tuple(words or ()),
            visibility=data.get("visibility", "public"),
            mode=data.get("mode", "draft_only"),
            approval=dict(data["approval"]) if data.get("approval") else None,
            paused=data.get("paused", False),
        ),
        [],
    )


def rule_to_dict(rule: Rule) -> dict[str, Any]:
    """저장용 사전. parse_rule(rule_to_dict(r)) 는 r 과 같은 규칙을 돌려준다."""
    return {
        "id": rule.id,
        "name": rule.name,
        "blog_id": rule.blog_id,
        "user_topics": [dict(t) for t in rule.user_topics],
        "use_research": rule.use_research,
        "days": list(rule.days),
        "times": list(rule.times),
        "per_day": rule.per_day,
        "per_week": rule.per_week,
        "gap_seconds": rule.gap_seconds,
        "forbidden_words": list(rule.forbidden_words),
        "visibility": rule.visibility,
        "mode": rule.mode,
        "approval": dict(rule.approval) if rule.approval else None,
        "paused": rule.paused,
    }


# ── 승인 ─────────────────────────────────────────────────────────────────

# 이 필드들이 바뀌면 사용자가 승인한 내용과 달라진 것이므로 승인이 무효가 된다.
# 이름(name)·일시정지(paused)·승인 기록 자체는 동작 범위를 바꾸지 않아 제외한다.
_HASHED_FIELDS = (
    "blog_id",
    "user_topics",
    "use_research",
    "days",
    "times",
    "per_day",
    "per_week",
    "gap_seconds",
    "forbidden_words",
    "visibility",
    "mode",
)


def rule_hash(rule: Rule) -> str:
    body = rule_to_dict(rule)
    canonical = json.dumps(
        {k: body[k] for k in _HASHED_FIELDS}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def approve(rule: Rule, approved_by: str, now: datetime) -> Rule:
    """지금 내용 그대로를 승인한 기록을 붙인 새 규칙. 승인자가 비어 있으면 거부."""
    if not approved_by or not approved_by.strip():
        raise ValueError("승인자(approved_by)가 필요함")
    approval = {
        "approved_by": approved_by.strip(),
        "approved_at": now.isoformat(timespec="seconds"),
        "rule_hash": rule_hash(rule),
    }
    return replace(rule, approval=approval)


def is_approval_valid(rule: Rule) -> bool:
    """승인 기록이 있고, 그 해시가 현재 규칙 내용과 같을 때만 True."""
    return bool(rule.approval) and rule.approval.get("rule_hash") == rule_hash(rule)


def effective_mode(rule: Rule, *, auto_publish_blog_ids: frozenset[str] = AUTO_PUBLISH_BLOG_IDS) -> str:
    """규칙이 원해도 승인이 무효이거나 자동 발행 불가 계정이면 draft_only."""
    if rule.mode == "auto_publish" and is_approval_valid(rule) and rule.blog_id in auto_publish_blog_ids:
        return "auto_publish"
    return "draft_only"


def approval_summary(rule: Rule) -> list[str]:
    """승인 화면에 보여 줄 "이 범위에서 자동 발행합니다" 요약 줄."""
    weekdays = "월화수목금토일"
    topic_source = []
    if rule.user_topics:
        topic_source.append(f"직접 입력한 주제 {len(rule.user_topics)}개")
    if rule.use_research:
        topic_source.append("리서치 결과 주제")
    return [
        f"계정: {rule.blog_id}",
        f"주제 출처: {' + '.join(topic_source)}",
        f"일정: 매주 {''.join(weekdays[d] for d in rule.days)} {', '.join(rule.times)}",
        f"한도: 하루 {rule.per_day}편 / 7일 {rule.per_week}편, 글 사이 {rule.gap_seconds}초 간격",
        f"공개 범위: {rule.visibility}",
        f"금칙어 {len(rule.forbidden_words)}개",
        "검사를 통과하지 못하거나 한도를 넘는 글은 발행하지 않고 초안으로 남깁니다",
    ]
