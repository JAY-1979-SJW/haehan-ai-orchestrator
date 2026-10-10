"""CDP target 실시간 감시 — polling diff + 이벤트 합성 + target 선택.

기능:
  - CDP /json/list 의 page target 목록 diff (added/removed/url_changed/title_changed)
  - login_state_detector 로 각 target 의 로그인 상태 분류
  - target 선택 우선순위 함수 (작업 target / auth host / 새 popup / origin / 최신)
  - URL sanitize / email 마스킹은 detector 모듈 재사용

본 모듈은 pure 함수 위주이며, 실제 polling 루프는 desktop/local_server 에서 구동.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.agent_runtime.browser.login_state_detector import (
    GOOGLE_AUTH_HOSTS,
    LOGIN_REQUIRED,
    DetectionResult,
    classify,
    mask_email,
    sanitize_url,
)

# ── 이벤트 type 상수 ─────────────────────────────────────────────────

EVT_TARGET_CREATED = "target_created"
EVT_TARGET_CLOSED = "target_closed"
EVT_TARGET_URL_CHANGED = "target_url_changed"
EVT_TARGET_TITLE_CHANGED = "target_title_changed"
EVT_AUTH_POPUP_DETECTED = "auth_popup_detected"
EVT_LOGIN_STATE_CHANGED = "login_state_changed"


@dataclass
class TargetSnapshot:
    target_id: str
    url: str = ""
    title: str = ""
    seen_at: float = 0.0

    @property
    def sanitized_url(self) -> str:
        return sanitize_url(self.url)


@dataclass
class WatcherEvent:
    event_type: str
    target_id: str
    sanitized_url: str = ""
    title: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ── 입력 변환 ────────────────────────────────────────────────────────


def from_cdp_targets(rows: list[dict[str, Any]]) -> list[TargetSnapshot]:
    """CDP /json/list 응답을 TargetSnapshot 목록으로 변환."""
    now = time.time()
    out: list[TargetSnapshot] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if row.get("type") != "page":
            continue
        tid = str(row.get("id", "") or "")
        if not tid:
            continue
        out.append(
            TargetSnapshot(
                target_id=tid,
                url=str(row.get("url", "") or ""),
                title=str(row.get("title", "") or ""),
                seen_at=now,
            )
        )
    return out


# ── diff ─────────────────────────────────────────────────────────────


def compute_events(
    prev: list[TargetSnapshot],
    curr: list[TargetSnapshot],
) -> list[WatcherEvent]:
    """이전/현재 snapshot 비교 결과 이벤트 생성."""
    prev_map = {s.target_id: s for s in prev}
    curr_map = {s.target_id: s for s in curr}
    events: list[WatcherEvent] = []

    for tid, s in curr_map.items():
        if tid not in prev_map:
            host = _host_only(s.url)
            evt = WatcherEvent(
                event_type=EVT_TARGET_CREATED,
                target_id=tid,
                sanitized_url=s.sanitized_url,
                title=mask_email(s.title),
                extra={"host": host},
            )
            events.append(evt)
            if any(h in host for h in GOOGLE_AUTH_HOSTS) or "accounts." in host:
                events.append(
                    WatcherEvent(
                        event_type=EVT_AUTH_POPUP_DETECTED,
                        target_id=tid,
                        sanitized_url=s.sanitized_url,
                        title=mask_email(s.title),
                        extra={"host": host},
                    )
                )
            continue
        prev_s = prev_map[tid]
        if prev_s.url != s.url:
            events.append(
                WatcherEvent(
                    event_type=EVT_TARGET_URL_CHANGED,
                    target_id=tid,
                    sanitized_url=s.sanitized_url,
                    title=mask_email(s.title),
                    extra={
                        "prev_sanitized_url": sanitize_url(prev_s.url),
                    },
                )
            )
        if prev_s.title != s.title:
            events.append(
                WatcherEvent(
                    event_type=EVT_TARGET_TITLE_CHANGED,
                    target_id=tid,
                    sanitized_url=s.sanitized_url,
                    title=mask_email(s.title),
                )
            )

    for tid in prev_map:
        if tid not in curr_map:
            events.append(
                WatcherEvent(
                    event_type=EVT_TARGET_CLOSED,
                    target_id=tid,
                    sanitized_url=prev_map[tid].sanitized_url,
                    title=mask_email(prev_map[tid].title),
                )
            )
    return events


def _host_only(url: str) -> str:
    s = sanitize_url(url)
    if not s:
        return ""
    # scheme://host[:port]/path
    try:
        rest = s.split("://", 1)[1]
    except IndexError:
        return ""
    return rest.split("/", 1)[0]


# ── login state 합성 ────────────────────────────────────────────────


def detect_login_states(
    snapshots: list[TargetSnapshot],
    prev_states: dict[str, str] | None = None,
    body_sampler: Callable[[str], str] | None = None,
) -> dict[str, DetectionResult]:
    """각 target 의 로그인 상태를 일괄 분류.

    body_sampler 가 주어지면 target_id → 짧은 body text 를 조회한다.
    None 이면 빈 문자열로 처리(URL/title 만으로 분류).
    """
    out: dict[str, DetectionResult] = {}
    prev = prev_states or {}
    for s in snapshots:
        body = ""
        if body_sampler is not None:
            try:
                body = body_sampler(s.target_id) or ""
            except Exception:  # noqa: BLE001 - 로그인 상태 분류용 body_sampler 호출 실패 시 빈 문자열로 폴백 - classify()는 URL/title 만으로도 분류 가능한 보조 신호 수집 실패일 뿐, 로그인 세션 파기나 승인 판정과 무관한 읽기전용 샘플링
                body = ""
        out[s.target_id] = classify(
            s.url,
            title=s.title,
            body_sample=body,
            prev_state=prev.get(s.target_id, ""),
        )
    return out


def login_state_change_events(
    prev_states: dict[str, str],
    curr_states: dict[str, DetectionResult],
) -> list[WatcherEvent]:
    """상태 변화만 추출."""
    events: list[WatcherEvent] = []
    for tid, det in curr_states.items():
        prev = prev_states.get(tid, "")
        if det.state == prev:
            continue
        events.append(
            WatcherEvent(
                event_type=EVT_LOGIN_STATE_CHANGED,
                target_id=tid,
                sanitized_url=det.sanitized_url,
                title=det.title,
                extra={
                    "prev_state": prev,
                    "state": det.state,
                    "reason": det.reason,
                    "is_account_picker": det.is_account_picker,
                    "user_hint": det.detected_user_hint,
                },
            )
        )
    return events


# ── target 선택 (우선순위) ───────────────────────────────────────────


def choose_login_target(
    snapshots: list[TargetSnapshot],
    *,
    work_target_id: str = "",
    matching_origin: str = "",
    newest_first: bool = True,
) -> str:
    """로그인을 시작/수행할 target_id 선택.

    우선순위:
      1) work_target_id 가 살아있고 로그인 페이지면 그대로
      2) accounts.google.com 등 auth host target
      3) 새로 생성된 popup auth target (= auth host 와 동일하나 최신순)
      4) matching_origin 과 host 일치 target
      5) 최신 active target (있다면)
      6) "" (TARGET_NOT_FOUND)
    """
    if not snapshots:
        return ""

    snaps_by_id = {s.target_id: s for s in snapshots}
    by_recency = sorted(snapshots, key=lambda s: s.seen_at, reverse=newest_first)

    if work_target_id and work_target_id in snaps_by_id:
        s = snaps_by_id[work_target_id]
        det = classify(s.url, title=s.title)
        if det.state in (LOGIN_REQUIRED,) or det.is_auth_host:
            return work_target_id

    for s in by_recency:
        h = _host_only(s.url)
        if any(ah in h for ah in GOOGLE_AUTH_HOSTS) or "accounts." in h:
            return s.target_id

    if matching_origin:
        mo = matching_origin.lower()
        for s in by_recency:
            if mo in _host_only(s.url):
                return s.target_id

    return by_recency[0].target_id if by_recency else ""
