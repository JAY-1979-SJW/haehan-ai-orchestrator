"""EUM 단말기 일일 자동 점검 — 사람이 로그인/클릭 없이 매일 자동 실행.

흐름: 단말기설치현황 재조회(WEBMAN390M00) → 모니터링 분석(통신단절/장기설치/준공임박)
→ 이상 발견 시 요약을 별도 파일에 남김(알림 연동은 다음 단계).

전용 자동화 브라우저(기본 9223, 사용자 작업 브라우저 9222와 분리)를 사용한다.
로그인 세션이 없으면 조용히 건너뛰고 다음날 재시도(사람에게 재로그인 요청 안 함).

사용:
    python scripts/eum/daily_check.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env", encoding="utf-8")


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


AUTOMATION_CDP_PORT = int(os.environ.get("HAEHAN_AUTOMATION_CDP_PORT", "9223"))


def run_daily_check() -> dict[str, Any]:
    """단말기설치현황 재조회 + 모니터링 분석. 로그인 없으면 스킵."""
    import json as _json
    import time

    from playwright.sync_api import sync_playwright

    from scripts.archive.eum_legacy.eum_extract_all_devices import (
        click_page,
        extract_page_devices,
        get_page_count,
    )
    from scripts.eum.monitor import analyze

    today = datetime.now().strftime("%Y-%m-%d")
    result: dict[str, Any] = {"date": today, "ok": False, "skipped": False}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{AUTOMATION_CDP_PORT}")
            ctx = browser.contexts[0]
            pages = [pg for pg in ctx.pages if "eum.cw.or.kr" in pg.url]
            if not pages:
                # 로그인 세션 없음 — 조용히 스킵, 재로그인 요청하지 않음(다음날 자동 재시도)
                result["skipped"] = True
                result["reason"] = "no_eum_tab_or_login"
                return result
            page = pages[0]
            page.goto("https://eum.cw.or.kr/web/man/WEBMAN390M00", timeout=30000)
            page.wait_for_load_state("load", timeout=5000)
            # 표시 개수 60으로 설정 + 조회 버튼 클릭 (기본 상태로는 목록이 비어 있을 수 있음)
            page.evaluate(
                "() => { const sels = document.querySelectorAll('select');"
                " for (const sel of sels) { const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));"
                " if (opt60) { sel.value = opt60.value; sel.dispatchEvent(new Event('change', {bubbles:true})); return true; } }"
                " return false; }"
            )
            time.sleep(2.0)
            page.evaluate(
                "() => { const b = Array.from(document.querySelectorAll('button'))"
                ".find(e => e.textContent.trim() === '조회'); if (b) b.click(); }"
            )
            time.sleep(2.0)
            total_pages = get_page_count(page)
            all_devices: list[dict] = []
            for page_num in range(1, total_pages + 1):
                if page_num > 1:
                    click_page(page, page_num)
                    time.sleep(1.5)
                all_devices.extend(extract_page_devices(page))

            out_file = _eum_dir() / "eum_all_devices_complete.json"
            out_file.write_text(
                _json.dumps(
                    {"timestamp": datetime.now().isoformat(), "all_devices": all_devices}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
    except Exception as e:  # noqa: BLE001 - CDP 사용 불가 등으로 일일 점검 작업 실패 시 skipped=True, reason 기록 후 반환 - 실패를 성공으로 위장하지 않고 건너뜀으로 명시 처리
        result["skipped"] = True
        result["reason"] = f"cdp_unavailable: {type(e).__name__}"
        return result

    devices_file = _eum_dir() / "eum_all_devices_complete.json"
    if not devices_file.exists():
        result["skipped"] = True
        result["reason"] = "no_device_data_after_extract"
        return result

    data = json.loads(devices_file.read_text(encoding="utf-8"))
    devices = data.get("all_devices", [])
    analysis = analyze(devices)

    result.update(
        {
            "ok": True,
            "total_devices": len(devices),
            "disconnected_count": len(analysis.get("comm_disconnected", [])),
            "unused_count": len(analysis.get("long_installed", [])),
            "demolition_soon_count": len(analysis.get("demolition_soon", [])),
        }
    )

    out_dir = _eum_dir() / "daily_checks"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{today}.json").write_text(
        json.dumps({**result, "analysis": analysis}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    result = run_daily_check()
    if result.get("skipped"):
        print(f"[eum-daily-check] 스킵: {result.get('reason')}")
        return
    print(
        f"[eum-daily-check] {result['date']} 완료 — 전체 {result['total_devices']}대, "
        f"통신단절 {result['disconnected_count']}건, 장기설치 {result['unused_count']}건, "
        f"준공임박 {result['demolition_soon_count']}건"
    )


if __name__ == "__main__":
    main()
