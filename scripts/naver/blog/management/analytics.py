"""블로그 통계 자동 분석 — 방문/댓글/공감 시계열.

기능:
  - 일일 통계 자동 수집 (방문/댓글/공감)
  - DB 시계열 저장
  - 주간/월간 요약
  - 인기 글 TOP N
  - HTML 대시보드 생성
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import init_sqlite_schema

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[4]
DB_PATH = data_dir() / "cdp.db"


def _init_db():
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS blog_metrics_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            blog_id TEXT NOT NULL,
            date_key TEXT NOT NULL,
            visitors_today INTEGER,
            visitors_total INTEGER,
            post_count INTEGER,
            comment_count INTEGER,
            neighbor_count INTEGER,
            raw_json TEXT
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_blogmet_blog_date ON blog_metrics_log(blog_id, date_key)",
        ),
    )


class BlogAnalytics:
    """블로그 통계 자동 분석."""

    def __init__(self, page: Page, blog_id: str):
        self.page = page
        self.blog_id = blog_id

    def collect_daily(self) -> dict:
        """오늘 통계 수집 + DB 저장.

        1차: NVisitorgp4Ajax.naver XML API (가장 안정적)
        2차: 어드민 페이지 텍스트 정규식 (fallback)
        """
        import re
        import time

        stats = {}

        # ── 1차: XML API ─────────────────────────────────────────────
        try:
            xml_url = f"https://blog.naver.com/NVisitorgp4Ajax.naver?blogId={self.blog_id}"
            self.page.goto(xml_url, timeout=12000, wait_until="domcontentloaded")
            time.sleep(2)
            # XML 본문 그대로 가져오기
            xml_text = self.page.evaluate("() => document.body?.innerText || ''")
            if xml_text and "<" in xml_text:
                # <visitorcnt id="20260512" cnt="..." /> 형식
                visitors_today = None
                visitors_total = 0
                today_str = datetime.now().strftime("%Y%m%d")
                # 오늘 cnt
                m_today = re.search(rf'id="{today_str}"\s+cnt="(\d+)"', xml_text)
                if m_today:
                    visitors_today = int(m_today.group(1))
                # 전체 합계
                for m in re.finditer(r'cnt="(\d+)"', xml_text):
                    visitors_total += int(m.group(1))
                stats["visitors_today"] = visitors_today
                stats["visitors_total"] = visitors_total
                stats["_source"] = "xml_api"
                _log.info("[blog-analytics] XML API: today=%s total=%s", visitors_today, visitors_total)
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 통계 읽기전용 수집(XML API 1차 + 어드민 페이지 폴백) — 각 except는 다음 폴백 단계로 넘어가거나 부분 실패를 debug 로그로만 남기며, 로컬 앱 자체 지표 sqlite(cdp.db)에 INSERT만 하는 앱 전용 로그 DB로 운영 DB 삭제/스키마 변경과 무관.
            _log.debug("[blog-analytics] XML API 실패: %s", e)

        # ── 2차: 어드민 페이지 fallback ──────────────────────────────
        self._collect_admin_fallback(stats)

        _init_db()
        today = date.today().isoformat()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO blog_metrics_log
               (ts, blog_id, date_key,
                visitors_today, visitors_total, post_count, comment_count, neighbor_count,
                raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                self.blog_id,
                today,
                stats.get("visitors_today"),
                stats.get("visitors_total"),
                stats.get("post_count"),
                stats.get("comment_count"),
                stats.get("neighbor_count"),
                json.dumps(stats, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

        log_critical(
            "OTHER", f"블로그 통계 수집: {self.blog_id}", blog_id=self.blog_id, date=today, mode="blog_analytics"
        )
        return {"ok": True, "saved": True, "date": today, "metrics": stats}

    def _collect_admin_fallback(self, stats: dict) -> None:
        """2차: 어드민 페이지 fallback (stats 를 제자리 갱신)."""
        import time

        if not stats.get("visitors_today"):
            try:
                url = f"https://admin.blog.naver.com/{self.blog_id}/stat/today"
                self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(3)
                for frame in [self.page.main_frame, *self.page.frames]:
                    try:
                        snap = frame.evaluate("""
                        () => {
                            const txt = document.body?.innerText || '';
                            if (txt.length < 50) return null;
                            const get = (re) => {
                                const m = re.exec(txt);
                                return m ? parseInt(m[1].replace(/,/g, '')) : null;
                            };
                            return {
                                visitors_today: get(/오늘[^\\d]*([\\d,]+)/),
                                visitors_total: get(/전체[^\\d]*([\\d,]+)/),
                                post_count: get(/포스트[^\\d]*([\\d,]+)/),
                                comment_count: get(/댓글[^\\d]*([\\d,]+)/),
                                neighbor_count: get(/이웃[^\\d]*([\\d,]+)/),
                            };
                        }
                        """)
                        if snap and any(v is not None for v in snap.values()):
                            for k, v in snap.items():
                                if stats.get(k) is None and v is not None:
                                    stats[k] = v
                            break
                    except Exception:  # noqa: BLE001 - 네이버 블로그 통계 읽기전용 수집(XML API 1차 + 어드민 페이지 폴백) — 각 except는 다음 폴백 단계로 넘어가거나 부분 실패를 debug 로그로만 남기며, 로컬 앱 자체 지표 sqlite(cdp.db)에 INSERT만 하는 앱 전용 로그 DB로 운영 DB 삭제/스키마 변경과 무관.
                        continue
            except Exception:  # noqa: BLE001 - 네이버 블로그 통계 읽기전용 수집(XML API 1차 + 어드민 페이지 폴백) — 각 except는 다음 폴백 단계로 넘어가거나 부분 실패를 debug 로그로만 남기며, 로컬 앱 자체 지표 sqlite(cdp.db)에 INSERT만 하는 앱 전용 로그 DB로 운영 DB 삭제/스키마 변경과 무관.
                pass

    def daily_summary(self, days: int = 30) -> dict:
        """일자별 요약."""
        _init_db()
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT date_key, MAX(visitors_today) visitors,
                      MAX(visitors_total) total, MAX(post_count) posts
               FROM blog_metrics_log
               WHERE blog_id = ?
               GROUP BY date_key
               ORDER BY date_key DESC
               LIMIT ?""",
            (self.blog_id, days),
        ).fetchall()
        conn.close()
        return {"ok": True, "blog_id": self.blog_id, "days": len(rows), "history": [dict(r) for r in rows]}

    # ── 상세 분석: 유입경로 / 글별 조회수 순위 / 방문 추이 ──────────────────
    # admin.blog.naver.com/{blogId}/stat/* 는 공식 API가 없어 CDP로 직접 읽음
    # (2026-08-15 정책: [0] 벤더 API 섹션에 없는 도메인만 CDP 정당).
    # 실제 페이지는 iframe(blog.stat.naver.com)에 렌더링됨 — 메인 프레임이
    # 아니라 그 iframe의 inner_text를 읽어야 한다.

    def _read_stat_frame(self, path: str, ready_marker: str = "", timeout_ms: int = 15000) -> str:
        """통계 iframe(blog.stat.naver.com) 텍스트를 읽는다.

        iframe이 붙는 시점이 페이지마다 달라, 단순히 "비어있지 않음"만으로는
        아직 로딩 중인 스켈레톤 텍스트를 완성된 데이터로 오판할 수 있다
        (2026-08-17 실측: referer/rank_pv가 종종 빈 결과로 반환됨). 그 페이지
        고유의 완성 신호 문자열(ready_marker)이 나타날 때까지 폴링한다.
        """
        import time

        # 통계 어드민이 같은 origin 내 SPA 라우팅이라, 직전에 다른 stat/*
        # 페이지에 있다가 바로 goto()하면 내부 iframe이 갱신되지 않는 경우가
        # 있었다(2026-08-17 실측: rank_pv 다음 visit_pv 조회 시 프레임 자체가
        # 안 붙음). about:blank를 거쳐 완전히 새 네비게이션으로 만든다.
        self.page.goto("about:blank", timeout=timeout_ms)
        url = f"https://admin.blog.naver.com/{self.blog_id}/{path}"
        self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")

        deadline = time.time() + 12
        last_text = ""
        while time.time() < deadline:
            for frame in self.page.frames:
                if "stat.naver.com" in frame.url:
                    try:
                        text = frame.inner_text("body", timeout=5000)
                    except Exception:  # noqa: BLE001 - 네이버 블로그 통계 읽기전용 수집(XML API 1차 + 어드민 페이지 폴백) — 각 except는 다음 폴백 단계로 넘어가거나 부분 실패를 debug 로그로만 남기며, 로컬 앱 자체 지표 sqlite(cdp.db)에 INSERT만 하는 앱 전용 로그 DB로 운영 DB 삭제/스키마 변경과 무관.
                        continue
                    if text.strip():
                        last_text = text
                        if not ready_marker or ready_marker in text:
                            return text
            time.sleep(0.5)
        return last_text

    def collect_referer(self) -> dict:
        """유입경로 분석 (stat/referer) — 검색엔진/사이트별 유입 비율."""
        text = self._read_stat_frame("stat/referer", ready_marker="유입경로")
        if not text:
            return {"ok": False, "error": "no_data"}

        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        sources: list[dict] = []
        search_terms: list[dict] = []
        section = None
        for ln in lines:
            if ln == "상세 유입경로":
                section = "sources"
                continue
            if ln == "네이버 검색 상세 유입 경로":
                section = "terms"
                continue
            if ln in ("검색 유입", "사이트 유입", "유입경로", "문의"):
                section = None
                continue
            m = re.match(r"^(.+?)\t?\s*([\d.]+)%$", ln)
            if m and section == "sources":
                sources.append({"path": m.group(1).strip(), "pct": float(m.group(2))})
            elif m and section == "terms":
                search_terms.append({"term": m.group(1).strip(), "pct": float(m.group(2))})

        return {"ok": True, "sources": sources, "search_terms": search_terms}

    def collect_rank_pv(self, period: str = "week") -> dict:
        """글별 조회수 순위 (stat/rank_pv). period: day/week/month."""
        text = self._read_stat_frame("stat/rank_pv", ready_marker="조회수 순위 목록")
        if not text:
            return {"ok": False, "error": "no_data"}

        # 각 행은 "순위\t제목\t조회수\t타입\t작성일" 형태의 탭 구분 한 줄
        # (실측 2026-08-17: innerText가 테이블 셀을 개행이 아닌 탭으로 이어붙임)
        posts: list[dict] = []
        for ln in text.split("\n"):
            cells = ln.split("\t")
            if len(cells) < 4 or not re.match(r"^\d+$", cells[0].strip()):
                continue
            title = cells[1].strip()
            if not re.match(r"^\d+$", cells[2].strip()) or "존재하지 않는 게시물" in title:
                continue
            posts.append(
                {
                    "rank": int(cells[0].strip()),
                    "title": title,
                    "pv": int(cells[2].strip()),
                    "type": cells[3].strip(),
                    "date": cells[4].strip() if len(cells) > 4 else "",
                }
            )

        return {"ok": True, "period": period, "posts": posts}

    def collect_visit_trend(self, days: int = 14) -> dict:
        """일별 조회수 추이 (stat/visit_pv)."""
        text = self._read_stat_frame("stat/visit_pv", ready_marker="조회수 목록")
        if not text:
            return {"ok": False, "error": "no_data"}

        # "날짜\t전체\t피이웃\t서로이웃\t기타" 탭 구분 한 줄 (rank_pv와 동일 패턴)
        trend: list[dict] = []
        for ln in text.split("\n"):
            cells = ln.split("\t")
            if len(cells) < 5:
                continue
            m = re.match(r"^(\d{4}\.\d{2}\.\d{2}\.)", cells[0].strip())
            if not m or not all(re.match(r"^\d+$", c.strip()) for c in cells[1:5]):
                continue
            trend.append(
                {
                    "date": m.group(1),
                    "total": int(cells[1]),
                    "neighbor": int(cells[2]),
                    "mutual": int(cells[3]),
                    "other": int(cells[4]),
                }
            )
        return {"ok": True, "trend": trend[:days]}

    def collect_demo(self) -> dict:
        """성별·연령별 분포 (stat/demo)."""
        text = self._read_stat_frame("stat/demo", ready_marker="성별, 연령별 분포 목록")
        if not text:
            return {"ok": False, "error": "no_data"}
        return {"ok": True, "breakdown": self._parse_demo_rows(text)}

    def collect_device(self) -> dict:
        """기기별(모바일/PC) 분포 + 성별·연령별 분포 (stat/device)."""
        text = self._read_stat_frame("stat/device", ready_marker="사용자분포")
        if not text:
            return {"ok": False, "error": "no_data"}

        device: dict[str, float] = {}
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        try:
            idx = lines.index("전체")
            device = {"mobile": float(lines[idx + 1].rstrip("%")), "pc": float(lines[idx + 2].rstrip("%"))}
        except (ValueError, IndexError):
            pass

        return {"ok": True, "device": device, "breakdown": self._parse_demo_rows(text)}

    @staticmethod
    def _parse_demo_rows(text: str) -> list[dict]:
        """ "연령별\t성별\t조회수\t비율" 탭 구분 행 파싱 (demo/device 공용)."""
        rows: list[dict] = []
        for ln in text.split("\n"):
            cells = ln.split("\t")
            if len(cells) != 4:
                continue
            age, gender, count, pct = (c.strip() for c in cells)
            if gender not in ("남", "여") or not re.match(r"^\d+$", count):
                continue
            rows.append({"age": age, "gender": gender, "count": int(count), "pct": float(pct.rstrip("%"))})
        return rows

    def full_report(self) -> dict:
        """오늘 요약 + 유입경로 + 글별 순위 + 방문 추이 + 인구통계를 한 번에 수집."""
        today = self.collect_daily()
        referer = self.collect_referer()
        rank = self.collect_rank_pv()
        trend = self.collect_visit_trend()
        demo = self.collect_demo()
        device = self.collect_device()

        report = {
            "blog_id": self.blog_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "today": today.get("metrics", {}),
            "referer": referer,
            "rank_pv": rank,
            "visit_trend": trend,
            "demo": demo,
            "device": device,
        }

        out = data_dir() / "reports" / f"blog_analytics_{self.blog_id}_{date.today().isoformat()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["_file"] = str(out)

        log_critical("OTHER", f"블로그 상세 분석: {self.blog_id}", blog_id=self.blog_id, mode="blog_analytics_full")
        return report

    def generate_html(self, out_path: str = "data/blog_dashboard.html") -> dict:
        """HTML 대시보드 생성."""
        summary = self.daily_summary(days=30)
        history = summary["history"]
        if not history:
            return {"ok": False, "error": "no_data"}

        latest = history[0]
        html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<title>블로그 분석 - {self.blog_id}</title>
<style>
body{{font-family:'Malgun Gothic';background:#f0f2f5;padding:24px}}
.kpi{{background:#fff;padding:20px;border-radius:8px;display:inline-block;margin:8px;min-width:150px;text-align:center}}
.num{{font-size:32px;font-weight:700;color:#1a3a5c}}
.label{{color:#888;font-size:12px}}
table{{background:#fff;width:100%;border-collapse:collapse;margin-top:24px;border-radius:8px;overflow:hidden}}
th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left}}
th{{background:#f4f7fb}}
</style></head><body>
<h1>📝 블로그 분석 — {self.blog_id}</h1>
<p>생성: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
<div>
  <div class="kpi"><div class="num">{latest.get("visitors") or "-"}</div><div class="label">최근 방문</div></div>
  <div class="kpi"><div class="num">{latest.get("total") or "-"}</div><div class="label">누적 방문</div></div>
  <div class="kpi"><div class="num">{latest.get("posts") or "-"}</div><div class="label">전체 포스트</div></div>
</div>
<h2>일자별 ({len(history)}일)</h2>
<table><thead><tr><th>날짜</th><th>방문</th><th>누적</th><th>포스트수</th></tr></thead><tbody>
"""
        for r in history:
            html += f"<tr><td>{r['date_key']}</td><td>{r.get('visitors') or '-'}</td><td>{r.get('total') or '-'}</td><td>{r.get('posts') or '-'}</td></tr>\n"
        html += "</tbody></table></body></html>"

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return {"ok": True, "file": str(out), "days": len(history)}
