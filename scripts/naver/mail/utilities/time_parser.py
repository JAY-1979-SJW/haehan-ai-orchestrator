"""네이버 메일 표시시간 → Asia/Seoul ISO datetime 정규화.

지원 입력 예:
  "오전 10:00", "오후 3:12", "어제", "오늘",
  "05.18", "2026.05.18", "05.18.", "2026.05.18 03:30",
  "5월 18일", "1분 전", "방금 전"

반환:
  ParsedTime(iso, warning)
  - iso: "YYYY-MM-DDTHH:MM:SS+09:00" 또는 ""
  - warning: 파싱 실패 사유 또는 가정한 부분 (e.g. '연도_가정=2026', '시간_없음_자정사용')

순수 함수 — datetime.now() 주입 가능해 테스트 결정적.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


@dataclass
class ParsedTime:
    iso: str
    warning: str = ""


_AM_PM_RE = re.compile(r"^(오전|오후)\s*(\d{1,2}):(\d{2})$")
_HM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DOT_FULL_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})\.?(?:\s+(\d{1,2}):(\d{2}))?$")
_DOT_SHORT_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.?$")
_KOR_MD_RE = re.compile(r"^(\d{1,2})월\s*(\d{1,2})일$")
_REL_MIN_RE = re.compile(r"^(\d{1,3})\s*분\s*전$")
_REL_HR_RE = re.compile(r"^(\d{1,2})\s*시간\s*전$")


def _kst_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_am_pm(s: str, today_0: datetime) -> ParsedTime | None:
    """오전/오후 시:분."""
    m = _AM_PM_RE.match(s)
    if m:
        ampm, hh, mm = m.group(1), int(m.group(2)), int(m.group(3))
        if ampm == "오후" and hh < 12:
            hh += 12
        if ampm == "오전" and hh == 12:
            hh = 0
        dt = today_0.replace(hour=hh, minute=mm)
        return ParsedTime(_iso(dt), "오늘_가정")
    return None


def _parse_hm(s: str, today_0: datetime) -> ParsedTime | None:
    """HH:MM."""
    m = _HM_RE.match(s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        dt = today_0.replace(hour=hh, minute=mm)
        return ParsedTime(_iso(dt), "오늘_가정")
    return None


def _parse_keyword(s: str, today_0: datetime, n: datetime) -> ParsedTime | None:
    """오늘/어제/방금 전."""
    if s in ("오늘",):
        return ParsedTime(_iso(today_0), "시간_없음_자정사용")
    if s in ("어제",):
        return ParsedTime(_iso(today_0 - timedelta(days=1)), "시간_없음_자정사용")
    if s in ("방금 전", "방금전"):
        return ParsedTime(_iso(n), "")
    return None


def _parse_relative(s: str, n: datetime) -> ParsedTime | None:
    """N분 전 / N시간 전."""
    m = _REL_MIN_RE.match(s)
    if m:
        dt = n - timedelta(minutes=int(m.group(1)))
        return ParsedTime(_iso(dt), "")
    m = _REL_HR_RE.match(s)
    if m:
        dt = n - timedelta(hours=int(m.group(1)))
        return ParsedTime(_iso(dt), "")
    return None


def _parse_dot_full(s: str) -> ParsedTime | None:
    """YYYY.MM.DD [ HH:MM ]."""
    m = _DOT_FULL_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) else 0
        mm = int(m.group(5)) if m.group(5) else 0
        try:
            dt = datetime(y, mo, d, hh, mm, tzinfo=KST)
            return ParsedTime(_iso(dt), "" if m.group(4) else "시간_없음_자정사용")
        except ValueError as exc:
            return ParsedTime("", f"date_invalid:{exc}")
    return None


def _parse_dot_short(s: str, n: datetime) -> ParsedTime | None:
    """MM.DD."""
    m = _DOT_SHORT_RE.match(s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            dt = datetime(n.year, mo, d, 0, 0, tzinfo=KST)
        except ValueError as exc:
            return ParsedTime("", f"date_invalid:{exc}")
        # 만약 미래로 잡히면 작년으로 보정
        if dt > n + timedelta(days=1):
            dt = dt.replace(year=n.year - 1)
            return ParsedTime(_iso(dt), f"연도_가정={dt.year}_미래보정")
        return ParsedTime(_iso(dt), f"연도_가정={dt.year}_시간_없음_자정사용")
    return None


def _parse_kor_md(s: str, n: datetime) -> ParsedTime | None:
    """M월 D일."""
    m = _KOR_MD_RE.match(s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            dt = datetime(n.year, mo, d, 0, 0, tzinfo=KST)
            if dt > n + timedelta(days=1):
                dt = dt.replace(year=n.year - 1)
                return ParsedTime(_iso(dt), f"연도_가정={dt.year}_미래보정")
            return ParsedTime(_iso(dt), f"연도_가정={dt.year}_시간_없음_자정사용")
        except ValueError as exc:
            return ParsedTime("", f"date_invalid:{exc}")
    return None


def parse_korean_time(display: str, *, now: datetime | None = None) -> ParsedTime:
    """한글/숫자 혼합 표시시간을 ISO 로 변환.

    실패해도 빈 iso + warning 반환 (호출자가 폐기하지 않도록).
    """
    if not display:
        return ParsedTime("", "empty_display")
    s = display.strip()
    n = _kst_now(now)
    today_0 = n.replace(hour=0, minute=0, second=0, microsecond=0)

    # 1) 오전/오후 시:분  → 오늘 날짜
    parsed = _parse_am_pm(s, today_0)
    if parsed is not None:
        return parsed

    # 2) HH:MM  → 오늘
    parsed = _parse_hm(s, today_0)
    if parsed is not None:
        return parsed

    # 3) "오늘" / "어제" / "방금 전"
    parsed = _parse_keyword(s, today_0, n)
    if parsed is not None:
        return parsed

    # 4) 상대 — N분 전 / N시간 전
    parsed = _parse_relative(s, n)
    if parsed is not None:
        return parsed

    # 5) YYYY.MM.DD [ HH:MM ]
    parsed = _parse_dot_full(s)
    if parsed is not None:
        return parsed

    # 6) MM.DD  → 같은 해(또는 미래라면 작년)
    parsed = _parse_dot_short(s, n)
    if parsed is not None:
        return parsed

    # 7) "M월 D일"
    parsed = _parse_kor_md(s, n)
    if parsed is not None:
        return parsed

    return ParsedTime("", f"unknown_format:{s[:30]}")
