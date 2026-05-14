"""personal_explorer 결과 → 네이버 서비스 카탈로그 코드 자동 생성.

입력: data/sitemap/naver_personal_summary.json
출력: scripts/naver/services_catalog.py

생성되는 카탈로그:
  - SERVICES: {name: {url, category, desc, ...meta}}
  - get_service(name) -> dict
  - list_services(category=None) -> list
  - open_service(page, name) -> None      # 페이지 이동
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SUMMARY = ROOT / "data" / "sitemap" / "naver_personal_summary.json"
OUT = ROOT / "scripts" / "naver" / "services_catalog.py"


def main():
    if not SUMMARY.exists():
        print(f"✗ 탐색 결과 없음: {SUMMARY}")
        print(f"  먼저 실행: python scripts/naver/personal_explorer.py")
        sys.exit(1)

    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    services = data.get("services", [])

    lines = [
        '"""네이버 개인 서비스 카탈로그 (auto-generated).',
        f'',
        f'생성: {datetime.now().isoformat(timespec="seconds")}',
        f'원본: data/sitemap/naver_personal_summary.json',
        f'로그인 사용자: {data.get("logged_in_user", "")}',
        f'',
        f'사용:',
        f'  from scripts.naver.services_catalog import SERVICES, get_service, open_service',
        f'  open_service(page, "blog_admin")',
        f'  for s in list_services(category="콘텐츠"): ...',
        f'"""',
        'from __future__ import annotations',
        '',
        'from typing import Any',
        '',
        '',
        'SERVICES: dict[str, dict[str, Any]] = {',
    ]

    # 서비스별 dict 생성
    for s in services:
        name = s["name"]
        meta = s.get("meta") or {}
        entry = {
            "url": s.get("url", ""),
            "final_url": meta.get("url", s.get("url", "")),
            "category": s.get("category", ""),
            "desc": s.get("desc", ""),
            "ok": s.get("ok", False),
            "menu_count": s.get("menu_count", 0),
            "has_logout": bool(s.get("has_logout")),
            "access_denied": bool(s.get("access_denied")),
            "user_shown": s.get("user") or "",
            "menus": [{"text": m.get("text", ""), "href": m.get("href", "")}
                      for m in (meta.get("menus") or [])[:20]],
        }
        lines.append(f'    {name!r}: {{')
        for k, v in entry.items():
            if k == "menus":
                lines.append(f'        {k!r}: [')
                for m in v:
                    lines.append(f'            {{"text": {m["text"]!r}, "href": {m["href"]!r}}},')
                lines.append(f'        ],')
            else:
                lines.append(f'        {k!r}: {v!r},')
        lines.append('    },')
    lines.append('}')
    lines.append('')

    # 헬퍼 함수들
    lines.extend([
        '',
        'def get_service(name: str) -> dict | None:',
        '    """서비스 메타데이터 조회."""',
        '    return SERVICES.get(name)',
        '',
        '',
        'def list_services(category: str | None = None,',
        '                  only_accessible: bool = False) -> list[dict]:',
        '    """서비스 목록 조회.',
        '',
        '    Args:',
        '        category: 카테고리 필터 (포털/콘텐츠/커뮤니티/메일/일정/...)',
        '        only_accessible: True면 access_denied=False만 반환',
        '    """',
        '    items = []',
        '    for name, meta in SERVICES.items():',
        '        if category and meta.get("category") != category:',
        '            continue',
        '        if only_accessible and meta.get("access_denied"):',
        '            continue',
        '        items.append({"name": name, **meta})',
        '    return items',
        '',
        '',
        'def open_service(page, name: str, timeout_ms: int = 15000) -> bool:',
        '    """서비스 페이지로 이동."""',
        '    svc = SERVICES.get(name)',
        '    if not svc:',
        '        return False',
        '    try:',
        '        page.goto(svc["url"], timeout=timeout_ms, wait_until="domcontentloaded")',
        '        return True',
        '    except Exception:',
        '        return False',
        '',
        '',
        'def categories() -> list[str]:',
        '    """전체 카테고리 목록."""',
        '    return sorted({s["category"] for s in SERVICES.values()})',
        '',
        '',
        'CATEGORIES = sorted({s["category"] for s in SERVICES.values()})',
        f'TOTAL_SERVICES = {len(services)}',
        f'ACCESSIBLE_SERVICES = {sum(1 for s in services if s.get("ok") and not s.get("access_denied"))}',
        f'GENERATED_AT = {datetime.now().isoformat(timespec="seconds")!r}',
        '',
    ])

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ 카탈로그 생성: {OUT}")
    print(f"  서비스: {len(services)}개")
    print(f"  접근 가능: {sum(1 for s in services if s.get('ok') and not s.get('access_denied'))}개")


if __name__ == "__main__":
    main()
