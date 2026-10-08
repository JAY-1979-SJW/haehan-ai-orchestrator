"""수동 탐색 — 사용자가 이동한 현재 탭을 1회 분석/기록.

원칙:
  - 페이지 이동 안 함 (사용자가 직접)
  - 분석만: 타입 분류 + 폼 발견 + 봇 감지 + 미설계 페이지 자료화
  - 누적 저장: data/manual_visits/<host>/<page_slug>.json
  - 사이트맵 인덱스: data/manual_visits/<host>/_index.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from scripts.explorer.page_classifier import classify_page
from scripts.form.bot_radar import scan as bot_scan
from scripts.common.logger import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
VISITS_DIR = ROOT / "data" / "manual_visits"


def _safe_slug(url: str) -> str:
    p = urlparse(url)
    base = (p.path or "/").strip("/") or "root"
    if p.query:
        base += "_" + p.query
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", base)[:80]


def snapshot_current(page, *, save_html: bool = True, save_screenshot: bool = True) -> dict:
    """현재 page 1회 분석 + 저장."""
    try:
        url = page.url or ""
    except Exception:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
        url = ""
    if not url or url.startswith("chrome://"):
        return {"ok": False, "reason": f"invalid_url:{url}"}

    host = urlparse(url).hostname or "unknown"
    slug = _safe_slug(url)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    out_dir = VISITS_DIR / re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 분류 + 봇 스캔
    info = classify_page(page)
    try:
        br = bot_scan(page)
    except Exception:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
        br = {"level": "unknown"}

    # 스크린샷
    screenshot_path = None
    if save_screenshot:
        try:
            sp = out_dir / f"{slug}__{ts}.png"
            page.screenshot(path=str(sp), full_page=True)
            screenshot_path = sp.name
        except Exception as e:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
            log.debug("screenshot 실패: %s", e)

    # HTML
    html_path = None
    if save_html:
        try:
            html = page.content()
            hp = out_dir / f"{slug}__{ts}.html"
            hp.write_text(html, encoding="utf-8")
            html_path = hp.name
        except Exception:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
            pass

    # 페이지 메타
    record = {
        "url": url,
        "host": host,
        "title": (info["snapshot"].get("title") or "")[:200],
        "captured_at": datetime.now().isoformat(),
        "page_type": info["type"],
        "confidence": info["confidence"],
        "signals": info["signals"],
        "suggested_handlers": info["suggested_handlers"],
        "form_intent": info["discovery"].get("intent"),
        "form_fields_count": info["discovery"].get("fields_count"),
        "form_submit": info["discovery"].get("submit"),
        "bot_level": br.get("level"),
        "bot_vendors": br.get("vendors", []),
        "screenshot": screenshot_path,
        "html_file": html_path,
        "snapshot_brief": {
            "forms": info["snapshot"].get("forms"),
            "inputs_visible": info["snapshot"].get("inputs_visible"),
            "password_inputs": info["snapshot"].get("password_inputs"),
            "tables_count": len(info["snapshot"].get("tables", [])),
            "headings": info["snapshot"].get("headings", [])[:5],
            "pagination": len(info["snapshot"].get("pagination_signs", [])),
        },
    }

    # 페이지별 json 저장
    rec_path = out_dir / f"{slug}__{ts}.json"
    rec_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # 인덱스 누적
    idx_path = out_dir / "_index.json"
    idx = []
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
            idx = []
    idx.append({
        "captured_at": record["captured_at"],
        "url": url,
        "page_type": record["page_type"],
        "title": record["title"],
        "record": rec_path.name,
    })
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("[manual] snapshot %s [%s] → %s", url, record["page_type"], rec_path)
    return {"ok": True, "record": str(rec_path), "type": record["page_type"]}


def cli_snapshot() -> None:
    from scripts.browser.cdp.connection import get_page
    page = get_page()
    r = snapshot_current(page)
    if r["ok"]:
        print(f"✔ 스냅샷 저장: type={r['type']}")
        print(f"  {r['record']}")
    else:
        print(f"✘ {r.get('reason')}")


def cli_list(host: str = "") -> None:
    """저장된 페이지 인덱스 출력."""
    if host:
        dirs = [VISITS_DIR / re.sub(r"[^a-zA-Z0-9.-]", "_", host)]
    else:
        dirs = list(VISITS_DIR.iterdir()) if VISITS_DIR.exists() else []
    total = 0
    for d in dirs:
        if not d.is_dir():
            continue
        idx_path = d / "_index.json"
        if not idx_path.exists():
            continue
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 페이지 스냅샷(스크린샷/HTML/인덱스) 저장 도구 - 실패 시 조용히 스킵(pass/continue), 읽기전용 진단 도구
            continue
        print(f"\n[{d.name}] {len(idx)} 페이지")
        # 페이지 타입 통계
        types: dict = {}
        for r in idx:
            t = r.get("page_type", "?")
            types[t] = types.get(t, 0) + 1
        print(f"  타입 분포: {types}")
        # 최근 5개
        for r in idx[-5:]:
            print(f"  - [{r.get('page_type','?'):<14}] {r.get('title','')[:50]}  {r.get('url','')[:80]}")
        total += len(idx)
    if total == 0:
        print("저장된 수동 스냅샷 없음")
    else:
        print(f"\n총 {total} 페이지")


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.explorer.manual_snapshot <snap|list> [host]")
        return
    cmd = sys.argv[1]
    if cmd == "snap":
        cli_snapshot()
    elif cmd == "list":
        host = sys.argv[2] if len(sys.argv) > 2 else ""
        cli_list(host)
    else:
        print(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
