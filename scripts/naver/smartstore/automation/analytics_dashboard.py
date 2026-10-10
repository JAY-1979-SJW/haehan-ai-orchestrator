"""스마트스토어 분석 대시보드 자동 생성.

기능:
  - 매출/주문/방문/리뷰 자동 수집
  - 일/주/월 단위 집계
  - HTML 대시보드 자동 생성
  - DB 기반 시계열
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import Page

from ai_orchestrator.paths.runtime import data_dir
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.common.sqlite_helpers import init_sqlite_schema

_log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[3]
DB_PATH = data_dir() / "cdp.db"  # 예전 ROOT(parents[3])는 저장소 루트가 아니라 scripts/ 라 data/cdp.db 와 다른 DB 를 쓰던 버그


def _init_db():
    init_sqlite_schema(
        DB_PATH,
        (
            """
        CREATE TABLE IF NOT EXISTS smartstore_metrics_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            date_key TEXT NOT NULL,
            sales_today INTEGER,
            sales_week INTEGER,
            sales_month INTEGER,
            visitors_today INTEGER,
            orders_today INTEGER,
            raw_json TEXT
        )
    """,
            "CREATE INDEX IF NOT EXISTS idx_metrics_date ON smartstore_metrics_log(date_key)",
        ),
    )


class AnalyticsDashboard:
    """대시보드 자동 생성."""

    def __init__(self, page: Page):
        self.page = page

    def collect_today(self) -> dict:
        """오늘의 매출/방문/주문 자동 수집 + DB 저장."""
        from scripts.naver.smartstore import NaverSmartStore

        store = NaverSmartStore(self.page)
        stats = store.stats()
        if not stats.get("ok"):
            return stats

        _init_db()
        today = date.today().isoformat()
        now = datetime.now().isoformat(timespec="seconds")

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            """INSERT INTO smartstore_metrics_log
               (ts, date_key, sales_today, sales_week, sales_month,
                visitors_today, orders_today, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now,
                today,
                stats.get("sales_today"),
                stats.get("sales_week"),
                stats.get("sales_month"),
                stats.get("visitors_today"),
                stats.get("orders_today"),
                json.dumps(stats, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()
        log_critical("OTHER", "통계 수집", date=today, mode="analytics_collect")
        return {"ok": True, "saved": True, "date": today, "metrics": stats}

    def get_history(self, days: int = 30) -> list[dict]:
        """최근 N일 통계 DB 조회."""
        _init_db()
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM smartstore_metrics_log ORDER BY id DESC LIMIT ?", (days,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def generate_html(self, out_path: str = "data/smartstore_dashboard.html", days: int = 30) -> dict:
        """HTML 대시보드 자동 생성."""
        history = self.get_history(days=days)
        if not history:
            return {"ok": False, "error": "no_data"}

        # 최근 데이터
        latest = history[0]

        # 일자별 매출
        daily_sales = [(h["date_key"], h.get("sales_today") or 0) for h in reversed(history)]
        daily_visitors = [(h["date_key"], h.get("visitors_today") or 0) for h in reversed(history)]

        html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<title>스마트스토어 분석 대시보드</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; background: #f0f2f5; margin: 0; padding: 24px; }}
  h1 {{ color: #1a3a5c; }}
  .kpi-row {{ display: flex; gap: 16px; margin-bottom: 24px; }}
  .kpi {{ background: #fff; padding: 20px; border-radius: 8px; flex: 1; box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  .kpi .num {{ font-size: 32px; font-weight: 700; color: #1a3a5c; }}
  .kpi .label {{ color: #888; font-size: 12px; margin-top: 6px; }}
  table {{ width: 100%; background: #fff; border-collapse: collapse; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 10px; border-bottom: 1px solid #eee; text-align: left; }}
  th {{ background: #f4f7fb; }}
</style></head>
<body>
<h1>📊 스마트스토어 분석 대시보드</h1>
<p>생성: {datetime.now().strftime("%Y-%m-%d %H:%M")} | 최근 데이터: {latest.get("date_key", "")}</p>

<div class="kpi-row">
  <div class="kpi"><div class="num">{latest.get("sales_today") or "-"}</div><div class="label">오늘 매출 (원)</div></div>
  <div class="kpi"><div class="num">{latest.get("sales_week") or "-"}</div><div class="label">주간 매출</div></div>
  <div class="kpi"><div class="num">{latest.get("sales_month") or "-"}</div><div class="label">월간 매출</div></div>
  <div class="kpi"><div class="num">{latest.get("orders_today") or "-"}</div><div class="label">오늘 주문</div></div>
  <div class="kpi"><div class="num">{latest.get("visitors_today") or "-"}</div><div class="label">오늘 방문</div></div>
</div>

<h2>일자별 매출 ({days}일)</h2>
<table>
<thead><tr><th>날짜</th><th>매출</th><th>방문</th></tr></thead>
<tbody>
"""
        for d, s in daily_sales:
            v = next((vv for kk, vv in daily_visitors if kk == d), "-")
            html += f"<tr><td>{d}</td><td>{s:,}원</td><td>{v}</td></tr>\n"
        html += """</tbody></table>
</body></html>"""

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        log_critical("OTHER", f"대시보드 HTML 생성: {out.name}", days=days, file=str(out), mode="analytics_html")
        return {"ok": True, "file": str(out), "data_days": len(history)}
