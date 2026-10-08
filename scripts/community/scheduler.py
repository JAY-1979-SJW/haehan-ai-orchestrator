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

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir

ROOT = Path(__file__).resolve().parents[2]
_DIR = data_dir() / "community"
_REPORTS_DIR = _DIR / "reports"
_STATE_FILE = _DIR / "scheduler_state.json"


def get_state() -> dict:
    if not _STATE_FILE.exists():
        return {"last_run": None, "last_reason": None, "last_count": 0}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 커뮤니티/gonobi 백그라운드 스케줄러 시작 및 상태파일 IO - 실패 시 로그만 남기고 기본값/스킵으로 계속
        return {"last_run": None}


def _save_state(state: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2))


def run_all_sites(reason: str = "manual", max_posts: int = 40) -> dict[str, Any]:
    """등록된 모든 사이트를 수집→분석하고 리포트 파일로 저장."""
    from scripts.community.analyzer import prepare_posts_for_review
    from scripts.community.registry import list_sites
    from scripts.community.universal_extractor import extract_posts
    from scripts.browser.cdp.connection import get_page

    sites = list_sites()
    site_reports = []
    # 브라우저(CDP)가 꺼져 있으면 사이트 수집 전에 먼저 기동한다(사이트별 9222 직접 연결도 이 뒤에 안전).
    cdp_error = ""
    if sites:
        try:
            get_page()
        except Exception as e:  # noqa: BLE001 - CDP 기동 실패는 사이트마다 반복하지 않고 한 번에 기록하고 수집을 건너뜀
            cdp_error = f"CDP 브라우저 기동 실패: {str(e)[:160]}"
    for s in sites:
        url, name = s.get("url", ""), s.get("name", "")
        if cdp_error:
            site_reports.append({"site": name, "url": url, "ok": False, "error": cdp_error})
            continue
        try:
            page = get_page()
            ex = extract_posts(page, url, max_posts=max_posts)
            if not ex.get("ok"):
                site_reports.append({"site": name, "url": url, "ok": False, "error": ex.get("error")})
                continue
            rep = prepare_posts_for_review(ex.get("posts", []), context=name)
            site_reports.append(
                {
                    "site": name,
                    "url": url,
                    "ok": bool(rep.get("ok")),
                    "post_count": rep.get("post_count", 0),
                    # AI 자동분석(trends/opportunities 등)은 더 이상 여기서 하지 않는다
                    # (2026-09-12, 유료 API 제거) — formatted_text를 Claude Code가
                    # 나중에 직접 읽고 분석한다.
                    "formatted_text": rep.get("formatted_text", ""),
                    "error": rep.get("error"),
                }
            )
        except Exception as e:  # noqa: BLE001 - 커뮤니티/gonobi 백그라운드 스케줄러 시작 및 상태파일 IO - 실패 시 로그만 남기고 기본값/스킵으로 계속
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

    # 알림 발송 (설정·활성화된 경우에만, best-effort)
    if sites:
        try:
            from scripts.community.notifier import notify_report

            notify_report(report)
        except Exception:  # noqa: BLE001 - 커뮤니티/gonobi 백그라운드 스케줄러 시작 및 상태파일 IO - 실패 시 로그만 남기고 기본값/스킵으로 계속
            pass

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
        except Exception:  # noqa: BLE001 - 커뮤니티/gonobi 백그라운드 스케줄러 시작 및 상태파일 IO - 실패 시 로그만 남기고 기본값/스킵으로 계속
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
    except Exception:  # noqa: BLE001 - 커뮤니티/gonobi 백그라운드 스케줄러 시작 및 상태파일 IO - 실패 시 로그만 남기고 기본값/스킵으로 계속
        return None
