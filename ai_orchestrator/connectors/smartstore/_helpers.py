"""공통 헬퍼 — 캐시 IO, 경로 상수."""

from __future__ import annotations

import json
import time as _time
from pathlib import Path

from ai_orchestrator.paths.runtime import data_dir

ROOT = Path(__file__).resolve().parents[3]


def _data_root() -> Path:
    """번들(exe) 환경과 개발 환경 모두에서 data/ 경로를 정확히 반환."""
    return data_dir()  # HAEHAN_DATA_DIR/HAEHAN_DATA_ROOT 해석은 paths.runtime 이 한다


_SS_DATA_DIR = _data_root() / "smartstore"
_TMPL_DIR = _data_root() / "smartstore" / "desc_templates"

_FAILED_ERRORS = {"section_open_failed", "CDP_ERROR", "playwright_error"}


def ss_data_path(name: str) -> Path:
    _SS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SS_DATA_DIR / f"{name}.json"


def load_ss(name: str) -> dict:
    p = ss_data_path(name)
    if not p.exists():
        return {"ok": False, "error": "no_data", "hint": f"POST /smartstore/{name.replace('_', '-')}/collect 먼저 실행"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not data.get("ok") and data.get("error") in _FAILED_ERRORS:
            return {
                "ok": False,
                "error": "no_data",
                "hint": "이전 수집이 실패했습니다. collect 재실행 필요",
                "last_error": data.get("error"),
                "last_collected_at": data.get("collected_at"),
            }
        return data
    except Exception as e:  # noqa: BLE001 - 스마트스토어 데이터 조회 실패를 {ok: False, error}로 반환 — 읽기 전용 캐시 조회
        return {"ok": False, "error": str(e)}


def save_ss(name: str, data: dict) -> None:
    ss_data_path(name)  # mkdir 포함
    ss_data_path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tmpl_dir() -> Path:
    _TMPL_DIR.mkdir(parents=True, exist_ok=True)
    return _TMPL_DIR


def run_with_cdp_page(fn):
    """공유 CDP 연결(scripts.browser.page.web_connector)의 기존 탭에서 fn(page)를 실행하고 결과를 반환.

    2026-09-30 이전엔 이 파일에 cdp_connect()가 있었는데, 호출마다 독자적으로
    sync_playwright().start()+connect_over_cdp()를 새로 맺는 패턴이라 이 저장소 CLAUDE.md
    '반복 실수' 항목(2026-09-29, #72~#76)이 이미 경고한 정확히 180000ms 고정 타임아웃
    위험을 그대로 갖고 있었다 — smartstore 라우터 9개 파일 21곳에서 이 패턴을 그대로
    복붙해 쓰고 있었고, 실제로 /orders/pending 등에서 15초 이상 응답 없음을 실측 확인해
    전부 이 함수로 교체(호출부가 하나도 안 남아 cdp_connect() 자체는 삭제).
    scripts/web_connector.py의 전용 브라우저 스레드(run_on_browser_thread)와 캐시된
    단일 연결(get_page)을 재사용해 매 호출마다 새 Playwright 드라이버를 띄우던 문제를 없앤다.
    """
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.browser.cdp.connection import get_page, run_on_browser_thread

    def _work():
        page = get_page()
        return fn(page)

    return run_on_browser_thread(_work)


def run_with_cdp_context(fn):
    """공유 CDP 연결(scripts.browser.page.web_connector)의 BrowserContext(여러 탭)로 fn(ctx)를 실행.

    run_with_cdp_page()와 같은 목적이지만, 팝업 관리처럼 ctx.pages 전체를 훑어 URL
    패턴으로 활성 탭을 골라야 하는 호출자(smartstore/popup.py)를 위한 컨텍스트 레벨 버전.
    """
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.browser.cdp.connection import get_context, run_on_browser_thread

    def _work():
        ctx = get_context()
        return fn(ctx)

    return run_on_browser_thread(_work)


def now_iso() -> str:
    import datetime

    return datetime.datetime.now().isoformat(timespec="seconds")


def elapsed_ms(t0: float) -> int:
    return int((_time.monotonic() - t0) * 1000)
