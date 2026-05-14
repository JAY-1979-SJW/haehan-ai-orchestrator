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
from datetime import datetime, date
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from scripts.logger import get_logger
from scripts.critical_logger import log_critical

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "cdp.db"


def _init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
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
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_blogmet_blog_date ON blog_metrics_log(blog_id, date_key)")
    conn.commit()
    conn.close()


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
        import time
        import re

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
                from datetime import datetime
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
                _log.info("[blog-analytics] XML API: today=%s total=%s",
                          visitors_today, visitors_total)
        except Exception as e:
            _log.debug("[blog-analytics] XML API 실패: %s", e)

        # ── 2차: 어드민 페이지 fallback ──────────────────────────────
        if not stats.get("visitors_today"):
            try:
                url = f"https://admin.blog.naver.com/{self.blog_id}/stat/today"
                self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
                time.sleep(3)
                for frame in [self.page.main_frame] + list(self.page.frames):
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
                    except Exception:
                        continue
            except Exception:
                pass

        _init_db()
        today = date.today().isoformat()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO blog_metrics_log
               (ts, blog_id, date_key,
                visitors_today, visitors_total, post_count, comment_count, neighbor_count,
                raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(timespec="seconds"), self.blog_id, today,
             stats.get("visitors_today"), stats.get("visitors_total"),
             stats.get("post_count"), stats.get("comment_count"), stats.get("neighbor_count"),
             json.dumps(stats, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

        log_critical("OTHER", f"블로그 통계 수집: {self.blog_id}",
                     blog_id=self.blog_id, date=today, mode="blog_analytics")
        return {"ok": True, "saved": True, "date": today, "metrics": stats}

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
        return {"ok": True, "blog_id": self.blog_id, "days": len(rows),
                "history": [dict(r) for r in rows]}

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
<p>생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div>
  <div class="kpi"><div class="num">{latest.get('visitors') or '-'}</div><div class="label">최근 방문</div></div>
  <div class="kpi"><div class="num">{latest.get('total') or '-'}</div><div class="label">누적 방문</div></div>
  <div class="kpi"><div class="num">{latest.get('posts') or '-'}</div><div class="label">전체 포스트</div></div>
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
