"""navigator_session — CDP 세션 저장."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.browser.navigator.navigator_common import SESSION_BACKUP_DIR
from scripts.browser.cdp.connection import get_page


def save_session(label: str | None = None) -> Path:
    """현재 CDP 컨텍스트의 쿠키/localStorage를 storage_state.json으로 저장.

    label 미지정 시 타임스탬프 사용.
    저장 경로: data/browser_sessions/backups/{label}.json
    """
    SESSION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    name = label or datetime.now().strftime("session_%Y%m%d_%H%M%S")
    out_path = SESSION_BACKUP_DIR / f"{name}.json"

    print("=" * 60)
    print(f"세션 저장: {out_path}")
    print("=" * 60)

    page = get_page()
    page.context.storage_state(path=str(out_path))

    data = json.loads(out_path.read_text(encoding="utf-8"))
    cookies = data.get("cookies", [])
    origins = data.get("origins", [])
    domains = sorted({c.get("domain", "") for c in cookies})
    print(f"✓ 저장 완료 ({out_path.stat().st_size:,} bytes)")
    print(f"  쿠키: {len(cookies)}개 / 도메인: {len(domains)}")
    print(f"  localStorage origin: {len(origins)}개")
    print("=" * 60)
    return out_path
