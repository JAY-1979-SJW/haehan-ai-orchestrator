"""커뮤니티 자율 분석 스케줄러 — 등록된 사이트를 주기적으로 수집·분석·리포트 저장.

run_all_sites()  : 등록 사이트 전체를 수집→분석→리포트 저장 (수동/자동 공용)
list_reports()   : 저장된 리포트 목록(최근 우선)
get_state()      : last_run 등 상태
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_DIR = ROOT / "data" / "community"
_REPORTS_DIR = _DIR / "reports"
_STATE_FILE = _DIR / "scheduler_state.json"


def get_state() -> dict:
    if not _STATE_FILE.exists():
        return {"last_run": None, "last_reason": None, "last_count": 0}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_run": None}


def _save_state(state: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_all_sites(reason: str = "manual", max_posts: int = 40) -> dict[str, Any]:
    """등록된 모든 사이트를 수집→분석하고 리포트 파일로 저장."""
    from scripts.community.analyzer import analyze_posts
    from scripts.community.registry import list_sites
    from scripts.community.universal_extractor import extract_posts
    from scripts.web_connector import get_page

    sites = list_sites()
    site_reports = []
    for s in sites:
        url, name = s.get("url", ""), s.get("name", "")
        try:
            page = get_page()
            ex = extract_posts(page, url, max_posts=max_posts)
            if not ex.get("ok"):
                site_reports.append({"site": name, "url": url, "ok": False, "error": ex.get("error")})
                continue
            rep = analyze_posts(ex.get("posts", []), context=name)
            site_reports.append(
                {
                    "site": name,
                    "url": url,
                    "ok": bool(rep.get("ok")),
                    "analyzed_count": rep.get("analyzed_count", 0),
                    "summary": rep.get("summary", ""),
                    "trends": rep.get("trends", []),
                    "opportunities": rep.get("opportunities", []),
                    "topics": rep.get("topics", []),
                    "actions": rep.get("actions", []),
                    "error": rep.get("error"),
                }
            )
        except Exception as e:
            site_reports.append({"site": name, "url": url, "ok": False, "error": str(e)[:160]})

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "site_count": len(sites),
        "ok_count": sum(1 for r in site_reports if r.get("ok")),
        "reports": site_reports,
    }
    if sites:  # 사이트 없으면 빈 리포트 저장 안 함
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (_REPORTS_DIR / f"report_{ts}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _save_state(
        {
            "last_run": report["generated_at"],
            "last_reason": reason,
            "last_count": len(sites),
            "last_ok": report["ok_count"],
        }
    )
    return report


def list_reports(limit: int = 10) -> list[dict]:
    """저장된 리포트 목록(최근 우선) — 요약 메타만."""
    if not _REPORTS_DIR.exists():
        return []
    files = sorted(_REPORTS_DIR.glob("report_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append(
                {
                    "file": f.name,
                    "generated_at": d.get("generated_at"),
                    "reason": d.get("reason"),
                    "site_count": d.get("site_count"),
                    "ok_count": d.get("ok_count"),
                    "reports": d.get("reports", []),
                }
            )
        except Exception:
            continue
    return out


def seconds_since_last_run() -> float | None:
    st = get_state()
    lr = st.get("last_run")
    if not lr:
        return None
    try:
        last = datetime.fromisoformat(lr)
        return time.time() - last.timestamp()
    except Exception:
        return None
