"""네이버 카페 게시글 분석기 — 3개월치 통계 및 보고서 생성.

브라우저 불필요. collector.py 수집 결과 JSON을 입력받아 분석.

사용:
    from scripts.naver.cafe.analyzer import analyze, load_latest

    data = load_latest()               # data/cafe/ 최신 raw 파일 자동 로드
    report = analyze(data)             # 분석 실행
    print(report["summary_text"])      # 텍스트 보고서 출력
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
_DATA_DIR = ROOT / "data" / "cafe"

# 분석에서 제외할 불용어 (제목 키워드 빈도에서)
_STOPWORDS = {
    "이", "가", "을", "를", "의", "에", "에서", "로", "으로", "과", "와", "도", "는", "은",
    "한", "하는", "하고", "있는", "있어", "있습니다", "합니다", "했습니다", "됩니다",
    "입니다", "되는", "것", "수", "더", "제", "그", "이번", "저", "좀", "어떻게",
    "어디", "왜", "뭐", "누가", "언제", "어떤", "같은", "관련", "질문", "문의",
    "부탁", "도움", "확인", "안녕하세요", "감사합니다", "감사", "안녕",
}


def load_latest(data_dir: str | None = None) -> list[dict]:
    """data/cafe/ 최신 raw_articles_*.json 자동 로드."""
    d = Path(data_dir) if data_dir else _DATA_DIR
    files = sorted(d.glob("raw_articles_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"수집 파일 없음: {d}")
    print(f"[analyzer] 파일 로드: {files[0].name}")
    return json.loads(files[0].read_text(encoding="utf-8"))


def _to_int(v: Any) -> int:
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except (ValueError, TypeError):
        return 0


def _week_label(d: date) -> str:
    """YYYY-WNN 형식 주차 레이블."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def analyze(articles: list[dict], top_n: int = 10) -> dict:
    """게시글 목록 분석 → 결과 dict 반환.

    결과 dict 구조:
        period          수집 기간 (start ~ end)
        total           총 게시글 수
        total_views     총 조회수
        total_likes     총 좋아요
        total_comments  총 댓글수
        by_board        게시판별 통계 {board: {count, views, likes, comments}}
        by_month        월별 {YYYY-MM: count}
        by_week         주별 {YYYY-WNN: count}
        by_weekday      요일별 {Mon: count, ...}
        top_views       조회수 상위 N
        top_likes       좋아요 상위 N
        top_comments    댓글 상위 N
        top_authors     작성자별 글 수 상위 N
        top_keywords    제목 키워드 빈도 상위 N
        top_tags        태그 빈도 상위 N
        summary_text    텍스트 보고서 (print용)
    """
    if not articles:
        return {"error": "데이터 없음"}

    dates = []
    for a in articles:
        try:
            d = date.fromisoformat(a["date"])
            dates.append(d)
        except (ValueError, KeyError, TypeError):
            dates.append(None)

    valid_dates = [d for d in dates if d]
    period_start = min(valid_dates).isoformat() if valid_dates else "unknown"
    period_end = max(valid_dates).isoformat() if valid_dates else "unknown"

    total = len(articles)
    total_views = sum(_to_int(a.get("view_count", 0)) for a in articles)
    total_likes = sum(_to_int(a.get("like_count", 0)) for a in articles)
    total_comments = sum(_to_int(a.get("comment_count", 0)) for a in articles)

    # ── 게시판별 ──────────────────────────────────────────────────────
    board_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "views": 0, "likes": 0, "comments": 0})
    for a in articles:
        b = a.get("board", "") or "미분류"
        board_stats[b]["count"] += 1
        board_stats[b]["views"] += _to_int(a.get("view_count", 0))
        board_stats[b]["likes"] += _to_int(a.get("like_count", 0))
        board_stats[b]["comments"] += _to_int(a.get("comment_count", 0))
    by_board = dict(sorted(board_stats.items(), key=lambda x: x[1]["count"], reverse=True))

    # ── 월별/주별/요일별 ─────────────────────────────────────────────
    month_counter: Counter = Counter()
    week_counter: Counter = Counter()
    weekday_counter: Counter = Counter()
    WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

    for d in dates:
        if d is None:
            continue
        month_counter[d.strftime("%Y-%m")] += 1
        week_counter[_week_label(d)] += 1
        weekday_counter[WEEKDAY_KR[d.weekday()]] += 1

    by_month = dict(sorted(month_counter.items()))
    by_week = dict(sorted(week_counter.items()))
    by_weekday = {k: weekday_counter[k] for k in WEEKDAY_KR}

    # ── TOP 게시글 ────────────────────────────────────────────────────
    def _top(key: str, n: int) -> list[dict]:
        return sorted(
            [{"title": a.get("title", "")[:40], "value": _to_int(a.get(key, 0)),
              "author": a.get("author", ""), "date": a.get("date", ""),
              "href": a.get("href", "")}
             for a in articles],
            key=lambda x: x["value"], reverse=True
        )[:n]

    top_views = _top("view_count", top_n)
    top_likes = _top("like_count", top_n)
    top_comments = _top("comment_count", top_n)

    # ── 작성자 활동 ───────────────────────────────────────────────────
    author_counter: Counter = Counter()
    author_views: Counter = Counter()
    for a in articles:
        author = a.get("author", "").strip() or "익명"
        author_counter[author] += 1
        author_views[author] += _to_int(a.get("view_count", 0))
    top_authors = [
        {"author": k, "count": v, "total_views": author_views[k]}
        for k, v in author_counter.most_common(top_n)
    ]

    # ── 제목 키워드 ───────────────────────────────────────────────────
    word_counter: Counter = Counter()
    for a in articles:
        title = a.get("title", "")
        # 한글 2글자 이상 단어만 추출
        words = re.findall(r"[가-힣]{2,}", title)
        for w in words:
            if w not in _STOPWORDS and len(w) >= 2:
                word_counter[w] += 1
    top_keywords = [{"word": k, "count": v} for k, v in word_counter.most_common(top_n * 2)]

    # ── 태그 ──────────────────────────────────────────────────────────
    tag_counter: Counter = Counter()
    for a in articles:
        for tag in a.get("tags", []):
            if tag:
                tag_counter[tag.strip()] += 1
    top_tags = [{"tag": k, "count": v} for k, v in tag_counter.most_common(top_n)]

    # ── 텍스트 보고서 ─────────────────────────────────────────────────
    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append("  네이버 카페 게시글 분석 보고서")
    lines.append(f"  수집 기간: {period_start} ~ {period_end}")
    lines.append(f"  분석 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(sep)

    lines.append("\n[1] 전체 요약")
    lines.append(f"  총 게시글 : {total:,}건")
    lines.append(f"  총 조회수 : {total_views:,}회")
    lines.append(f"  총 좋아요 : {total_likes:,}개")
    lines.append(f"  총 댓글   : {total_comments:,}개")
    if total > 0:
        lines.append(f"  평균 조회수 : {total_views / total:.1f}회/글")
        lines.append(f"  평균 댓글   : {total_comments / total:.1f}개/글")

    lines.append("\n[2] 게시판별 현황")
    for board, st in list(by_board.items())[:15]:
        lines.append(
            f"  {board or '미분류':<25}  {st['count']:>5}건  "
            f"조회 {st['views']:>6}  댓글 {st['comments']:>4}"
        )

    lines.append("\n[3] 월별 게시글 추이")
    for month, cnt in by_month.items():
        bar = "█" * min(cnt // 2, 40)
        lines.append(f"  {month}  {bar}  {cnt}건")

    lines.append("\n[4] 요일별 분포")
    for wd, cnt in by_weekday.items():
        bar = "█" * min(cnt // 3, 30)
        lines.append(f"  {wd}요일  {bar}  {cnt}건")

    lines.append(f"\n[5] 조회수 TOP {top_n}")
    for i, it in enumerate(top_views, 1):
        lines.append(f"  {i:>2}. [{it['value']:>5}회] {it['title']}  ({it['author']}, {it['date']})")

    lines.append(f"\n[6] 좋아요 TOP {top_n}")
    for i, it in enumerate(top_likes, 1):
        lines.append(f"  {i:>2}. [{it['value']:>4}개] {it['title']}  ({it['author']}, {it['date']})")

    lines.append(f"\n[7] 댓글 TOP {top_n}")
    for i, it in enumerate(top_comments, 1):
        lines.append(f"  {i:>2}. [{it['value']:>4}개] {it['title']}  ({it['author']}, {it['date']})")

    lines.append(f"\n[8] 활성 작성자 TOP {top_n}")
    for i, it in enumerate(top_authors, 1):
        lines.append(f"  {i:>2}. {it['author']:<20}  {it['count']:>3}건  총조회 {it['total_views']:>5}")

    lines.append(f"\n[9] 인기 키워드 (제목 기준 TOP {top_n * 2})")
    kw_line = "  " + "  |  ".join(f"{it['word']}({it['count']})" for it in top_keywords)
    lines.append(kw_line)

    if top_tags:
        lines.append(f"\n[10] 인기 태그 TOP {top_n}")
        tag_line = "  " + "  ".join(f"#{it['tag']}({it['count']})" for it in top_tags)
        lines.append(tag_line)

    lines.append(f"\n{sep}")
    summary_text = "\n".join(lines)

    return {
        "period": {"start": period_start, "end": period_end},
        "total": total,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "by_board": by_board,
        "by_month": by_month,
        "by_week": by_week,
        "by_weekday": by_weekday,
        "top_views": top_views,
        "top_likes": top_likes,
        "top_comments": top_comments,
        "top_authors": top_authors,
        "top_keywords": top_keywords,
        "top_tags": top_tags,
        "summary_text": summary_text,
    }


def save_report(report: dict, out_dir: str | None = None) -> dict[str, str]:
    """분석 결과를 JSON + TXT로 저장. 저장 경로 dict 반환."""
    d = Path(out_dir) if out_dir else _DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = d / f"analysis_report_{ts}.json"
    txt_path = d / f"analysis_report_{ts}.txt"

    # summary_text 제외한 JSON 저장
    report_json = {k: v for k, v in report.items() if k != "summary_text"}
    json_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(report.get("summary_text", ""), encoding="utf-8")

    print(f"[analyzer] 보고서 저장: {json_path.name}, {txt_path.name}")
    return {"json": str(json_path), "txt": str(txt_path)}
