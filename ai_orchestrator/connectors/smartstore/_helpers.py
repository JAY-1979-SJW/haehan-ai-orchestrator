"""공통 헬퍼 — 캐시 IO, 경로 상수."""
from __future__ import annotations

import json
import time as _time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_SS_DATA_DIR = ROOT / "data" / "smartstore"
_TMPL_DIR    = ROOT / "data" / "smartstore" / "desc_templates"

_FAILED_ERRORS = {"section_open_failed", "CDP_ERROR", "playwright_error"}


def ss_data_path(name: str) -> Path:
    _SS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SS_DATA_DIR / f"{name}.json"


def load_ss(name: str) -> dict:
    p = ss_data_path(name)
    if not p.exists():
        return {"ok": False, "error": "no_data",
                "hint": f"POST /smartstore/{name.replace('_', '-')}/collect 먼저 실행"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not data.get("ok") and data.get("error") in _FAILED_ERRORS:
            return {"ok": False, "error": "no_data",
                    "hint": f"이전 수집이 실패했습니다. collect 재실행 필요",
                    "last_error": data.get("error"),
                    "last_collected_at": data.get("collected_at")}
        return data
    except Exception as e:
        return {"ok": False, "error": str(e)}


def save_ss(name: str, data: dict) -> None:
    ss_data_path(name)  # mkdir 포함
    ss_data_path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tmpl_dir() -> Path:
    _TMPL_DIR.mkdir(parents=True, exist_ok=True)
    return _TMPL_DIR


def cdp_connect():
    """CDP 브라우저에 연결하고 첫 번째 page를 반환합니다."""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]
    return pw, browser, page


def now_iso() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def elapsed_ms(t0: float) -> int:
    return int((_time.monotonic() - t0) * 1000)
